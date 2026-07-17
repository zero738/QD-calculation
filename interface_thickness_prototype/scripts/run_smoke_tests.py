from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config
from parse_cp2k_output import parse_output


def command_version(mode: str, cp2k_command: str | None, image: str) -> str:
    if mode == "docker":
        command = ["docker", "run", "--rm", image, "cp2k", "--version"]
    else:
        command = [str(cp2k_command), "--version"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    combined = completed.stdout + "\n" + completed.stderr
    for line in combined.splitlines():
        if "CP2K version" in line:
            return line.strip()
    return combined.strip().splitlines()[0] if combined.strip() else "unknown"


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    completed = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed.returncode == 0


def choose_mode(requested: str, cp2k_command: str | None) -> tuple[str, str | None]:
    if cp2k_command:
        resolved = shutil.which(cp2k_command) or cp2k_command
        return "native", resolved
    for candidate in ("cp2k.psmp", "cp2k.popt", "cp2k"):
        if shutil.which(candidate):
            return "native", shutil.which(candidate)
    if requested in ("auto", "docker") and docker_available():
        return "docker", None
    if requested == "native":
        raise RuntimeError("native CP2K executable was not found")
    raise RuntimeError("neither native CP2K nor a running Docker engine is available")


def ensure_image(image: str, allow_pull: bool) -> None:
    inspected = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if inspected.returncode == 0:
        return
    if not allow_pull:
        raise RuntimeError(f"Docker image {image} is absent and --no-pull was requested")
    pulled = subprocess.run(["docker", "pull", image], check=False)
    if pulled.returncode != 0:
        raise RuntimeError(f"failed to pull trusted CP2K image {image}")


def sanitized_command(mode: str, cp2k_command: str | None, image: str) -> str:
    if mode == "docker":
        return (
            f"docker run --rm --name <container> --cpus <threads> --shm-size 1g "
            f"-e OMP_NUM_THREADS=<threads> "
            f"-v <task_dir>:/work -w /work {image} cp2k -i input.inp -o output.out"
        )
    return f"{cp2k_command} -i input.inp -o output.out"


def _archive_previous_attempt(task_dir: Path) -> None:
    metadata_path = task_dir / "run_metadata.json"
    if not metadata_path.is_file():
        return
    parsed_path = task_dir / "output.parsed.json"
    if parsed_path.is_file():
        try:
            previous_parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous_parsed = {}
        # The current successful artifacts are sufficient; history is retained
        # only for failed, timed-out, or externally interrupted attempts.
        if previous_parsed.get("program_completed") is True:
            return
    try:
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        previous = {}
    archive_id = str(previous.get("started_at_utc") or "unknown-time")
    for token in ("-", ":", "+", "."):
        archive_id = archive_id.replace(token, "")
    archive_dir = task_dir / "attempt_history" / archive_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "input.executed.inp",
        "output.out",
        "output.parsed.json",
        "run_metadata.json",
    ):
        source = task_dir / filename
        if source.is_file():
            shutil.copy2(source, archive_dir / filename)


def _classify_confirmed_termination(
    output: Path,
    timed_out: bool,
    timeout_seconds: int,
    mode: str,
    return_code: int | None,
) -> tuple[str, str]:
    if timed_out:
        return (
            "runner_timeout",
            f"the runner enforced its {timeout_seconds}-second task timeout and requested "
            f"{'Docker container stop' if mode == 'docker' else 'process termination'}",
        )
    text = output.read_text(encoding="utf-8", errors="replace").upper() if output.is_file() else ""
    if "SCF RUN NOT CONVERGED" in text or "SCF_NOT_CONVERGED" in text:
        return "cp2k_scf_not_converged", "CP2K output explicitly reports an unconverged SCF"
    if "[ABORT]" in text or "ABORT|" in text:
        return "cp2k_abort", "CP2K output contains an explicit abort marker"
    if return_code == 0:
        return "process_exit_0", "launcher process exited with return code 0"
    return (
        "nonzero_exit_unclassified",
        f"launcher process exited with return code {return_code}; the originating cause "
        "was not determined by the runner",
    )


def _stop_timed_out_process(
    process: subprocess.Popen,
    mode: str,
    container_name: str | None,
) -> tuple[str, str, dict]:
    cleanup: dict = {}
    if mode == "docker" and container_name:
        stopped = subprocess.run(
            ["docker", "stop", "--timeout", "5", container_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        cleanup["docker_stop_return_code"] = stopped.returncode
        cleanup["docker_stop_stdout"] = stopped.stdout[-1000:]
        cleanup["docker_stop_stderr"] = stopped.stderr[-1000:]
    else:
        process.terminate()
        cleanup["native_terminate_requested"] = True

    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        if mode == "docker" and container_name:
            removed = subprocess.run(
                ["docker", "rm", "--force", container_name],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            cleanup["docker_force_remove_return_code"] = removed.returncode
            cleanup["docker_force_remove_stderr"] = removed.stderr[-1000:]
        else:
            process.kill()
            cleanup["native_kill_requested"] = True
        stdout, stderr = process.communicate(timeout=30)
    return stdout or "", stderr or "", cleanup


def execute_task(
    task: dict,
    mode: str,
    cp2k_command: str | None,
    image: str,
    threads: int,
    version: str,
    timeout_seconds: int,
) -> dict:
    task_dir = ROOT / "smoke_tests" / task["id"]
    output = task_dir / "output.out"
    parsed_path = task_dir / "output.parsed.json"
    metadata_path = task_dir / "run_metadata.json"
    input_path = task_dir / "input.inp"
    executed_input = task_dir / "input.executed.inp"
    _archive_previous_attempt(task_dir)
    for stale in (output, parsed_path, metadata_path):
        if stale.is_file():
            stale.unlink()
    shutil.copy2(input_path, executed_input)
    input_sha256 = hashlib.sha256(executed_input.read_bytes()).hexdigest()
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(threads)
    container_name = None
    if mode == "docker":
        safe_id = task["id"].replace("_", "-")
        container_name = f"cp2k-smoke-{safe_id}-{uuid.uuid4().hex[:8]}"
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--cpus",
            str(threads),
            "--shm-size",
            "1g",
            "-e",
            f"OMP_NUM_THREADS={threads}",
            "-v",
            f"{task_dir.resolve()}:/work",
            "-w",
            "/work",
            image,
            "cp2k",
            "-i",
            "input.inp",
            "-o",
            "output.out",
        ]
        cwd = ROOT
    else:
        command = [str(cp2k_command), "-i", "input.inp", "-o", "output.out"]
        cwd = task_dir
    started = datetime.now(timezone.utc).isoformat()
    begin = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Write a durable start record before waiting. If the runner itself is
    # externally killed, the partial output remains explicitly unclassified
    # instead of looking like an unexplained or fabricated final result.
    running_metadata = {
        "calculation_id": task["id"],
        "attempted": True,
        "started_at_utc": started,
        "execution_mode": mode,
        "execution_command": sanitized_command(mode, cp2k_command, image),
        "executed_input_file": "input.executed.inp",
        "executed_input_sha256": input_sha256,
        "cp2k_version": version,
        "docker_image": image if mode == "docker" else None,
        "cpu_threads": threads,
        "timeout_seconds": timeout_seconds,
        "wall_time_seconds": None,
        "timed_out": False,
        "termination_reason": "running_or_external_interruption_unclassified",
        "confirmed_stop_cause": "task started; no termination has been observed yet",
        "return_code": None,
        "timeout_cleanup": None,
        "launcher_stdout": "",
        "launcher_stderr": "",
    }
    metadata_path.write_text(
        json.dumps(running_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    timed_out = False
    timeout_cleanup: dict = {}
    try:
        launcher_stdout, launcher_stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        launcher_stdout, launcher_stderr, timeout_cleanup = _stop_timed_out_process(
            process, mode, container_name
        )
    elapsed = time.perf_counter() - begin
    return_code = process.returncode
    termination_reason, confirmed_stop_cause = _classify_confirmed_termination(
        output, timed_out, timeout_seconds, mode, return_code
    )
    metadata = {
        "calculation_id": task["id"],
        "attempted": True,
        "started_at_utc": started,
        "execution_mode": mode,
        "execution_command": sanitized_command(mode, cp2k_command, image),
        "executed_input_file": "input.executed.inp",
        "executed_input_sha256": input_sha256,
        "cp2k_version": version,
        "docker_image": image if mode == "docker" else None,
        "cpu_threads": threads,
        "timeout_seconds": timeout_seconds,
        "wall_time_seconds": round(elapsed, 6),
        "timed_out": timed_out,
        "termination_reason": termination_reason,
        "confirmed_stop_cause": confirmed_stop_cause,
        "return_code": return_code,
        "timeout_cleanup": timeout_cleanup or None,
        "launcher_stdout": launcher_stdout[-4000:],
        "launcher_stderr": launcher_stderr[-4000:],
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    parsed = parse_output(output, executed_input, metadata_path)
    parsed_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"{task['id']}: return={return_code}, reason={termination_reason}, "
        f"normal_end={parsed['normal_program_end']}, SCF={parsed['scf_converged']}, "
        f"strict_success={parsed['program_completed']}"
    )
    return parsed


def refresh_summary() -> None:
    from summarize_results import main as summarize_main

    summarize_main()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ordered CP2K smoke-test ladder")
    parser.add_argument("--mode", choices=("auto", "native", "docker"), default="auto")
    parser.add_argument("--cp2k-command")
    parser.add_argument("--docker-image")
    parser.add_argument("--threads", type=int)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        help="override every selected task timeout (otherwise config.yaml is used per task)",
    )
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument(
        "--through",
        help="stop after this calculation id while preserving the configured prerequisite order",
    )
    args = parser.parse_args()

    config = load_config()
    image = args.docker_image or config["cp2k"]["docker_image"]
    threads = args.threads or config["cp2k"]["local_max_threads"]
    if threads < 1 or threads > 8:
        raise SystemExit("--threads must be between 1 and 8 for this prototype")
    manifest_path = ROOT / "smoke_tests" / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("smoke-test inputs are missing; run generate_cp2k_inputs.py first")
    tasks = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = config["smoke_tests"]["ordered_calculation_ids"]
    configured_timeouts = config["smoke_tests"].get("timeout_seconds", {})
    if [task["id"] for task in tasks] != expected:
        raise SystemExit("smoke-test manifest order disagrees with config.yaml")
    if args.through:
        if args.through not in expected:
            raise SystemExit(f"unknown --through calculation id: {args.through}")
        tasks = tasks[: expected.index(args.through) + 1]
    missing_timeouts = [task["id"] for task in tasks if task["id"] not in configured_timeouts]
    if missing_timeouts and args.timeout_seconds is None:
        raise SystemExit(f"missing per-task timeout(s) in config.yaml: {missing_timeouts}")
    if args.timeout_seconds is not None and args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be positive")
    try:
        mode, cp2k_command = choose_mode(args.mode, args.cp2k_command)
        if mode == "docker":
            ensure_image(image, not args.no_pull)
        version = command_version(mode, cp2k_command, image)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        refresh_summary()
        return 3

    print(f"execution mode: {mode}; CP2K: {version}; threads: {threads}")
    all_success = True
    for task in tasks:
        if not all_success:
            print(f"SKIP {task['id']}: previous ladder level did not pass strict checks")
            continue
        timeout_seconds = args.timeout_seconds or int(configured_timeouts[task["id"]])
        if timeout_seconds < 1:
            raise SystemExit(f"timeout for {task['id']} must be positive")
        parsed = execute_task(
            task, mode, cp2k_command, image, threads, version, timeout_seconds
        )
        all_success = bool(parsed["program_completed"])
    refresh_summary()
    return 0 if all_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
