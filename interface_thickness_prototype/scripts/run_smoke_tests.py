from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
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
            f"docker run --rm --cpus <threads> --shm-size 1g -e OMP_NUM_THREADS=<threads> "
            f"-v <task_dir>:/work -w /work {image} cp2k -i input.inp -o output.out"
        )
    return f"{cp2k_command} -i input.inp -o output.out"


def execute_task(
    task: dict,
    mode: str,
    cp2k_command: str | None,
    image: str,
    threads: int,
    version: str,
) -> dict:
    task_dir = ROOT / "smoke_tests" / task["id"]
    output = task_dir / "output.out"
    parsed_path = task_dir / "output.parsed.json"
    metadata_path = task_dir / "run_metadata.json"
    input_path = task_dir / "input.inp"
    executed_input = task_dir / "input.executed.inp"
    for stale in (output, parsed_path, metadata_path):
        if stale.is_file():
            stale.unlink()
    shutil.copy2(input_path, executed_input)
    input_sha256 = hashlib.sha256(executed_input.read_bytes()).hexdigest()
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(threads)
    if mode == "docker":
        command = [
            "docker",
            "run",
            "--rm",
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
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - begin
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
        "wall_time_seconds": round(elapsed, 6),
        "return_code": completed.returncode,
        "launcher_stdout": completed.stdout[-4000:],
        "launcher_stderr": completed.stderr[-4000:],
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    parsed = parse_output(output, executed_input, metadata_path)
    parsed_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"{task['id']}: return={completed.returncode}, normal_end={parsed['normal_program_end']}, "
        f"SCF={parsed['scf_converged']}, strict_success={parsed['program_completed']}"
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
    if [task["id"] for task in tasks] != expected:
        raise SystemExit("smoke-test manifest order disagrees with config.yaml")
    if args.through:
        if args.through not in expected:
            raise SystemExit(f"unknown --through calculation id: {args.through}")
        tasks = tasks[: expected.index(args.through) + 1]
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
        parsed = execute_task(task, mode, cp2k_command, image, threads, version)
        all_success = bool(parsed["program_completed"])
    refresh_summary()
    return 0 if all_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
