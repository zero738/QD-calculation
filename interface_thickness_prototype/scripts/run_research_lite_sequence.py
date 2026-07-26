from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config
from parse_research_lite_output import parse_research_run
from planar_average_cube import write_planar_average
from run_smoke_tests import command_version, docker_available, ensure_image


ORDER = ("cu2te_bulk_k222", "B0", "C50", "H1", "H2")
DEPENDENCY = {
    "cu2te_bulk_k222": "cu2te_bulk",
    "B0": "cu2te_bulk_k222",
    "C50": "B0",
    "H1": "C50",
    "H2": "H1",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> list[dict]:
    return json.loads(
        (ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8")
    )


def _canonical_task(task_id: str) -> dict:
    canonical_id = "cu2te_bulk" if task_id == "cu2te_bulk_k222" else task_id
    return next(
        task for task in _manifest() if task["calculation_id"] == canonical_id
    )


def _success(task_id: str, parsed: dict) -> bool:
    if task_id == "cu2te_bulk_k222":
        return bool(parsed.get("energy_valid"))
    return bool(parsed.get("energy_valid") and parsed.get("electronic_outputs_complete"))


def _dependency_is_satisfied(task_id: str) -> tuple[bool, str]:
    dependency = DEPENDENCY[task_id]
    parsed = _read_json(
        ROOT / "research_lite" / "runs" / dependency / "output.parsed.json"
    )
    if dependency == "cu2te_bulk":
        okay = bool(parsed.get("energy_valid") and parsed.get("electronic_outputs_complete"))
    else:
        okay = _success(dependency, parsed)
    return okay, dependency


def _update_manifest(task_id: str) -> None:
    if task_id == "cu2te_bulk_k222":
        return
    manifest_path = ROOT / "research_lite" / "manifest.json"
    tasks = _manifest()
    for task in tasks:
        if task["calculation_id"] == task_id:
            task["actually_run"] = True
            task["run_directory"] = f"research_lite/runs/{task_id}"
    manifest_path.write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_task(
    task_id: str,
    threads: int,
    allow_pull: bool,
    archive_existing_as: str | None = None,
) -> int:
    okay, dependency = _dependency_is_satisfied(task_id)
    if not okay:
        raise SystemExit(
            f"dependency gate failed: {task_id} requires successful {dependency}"
        )
    config = load_config()
    cp_root = config["cp2k"]
    profile = cp_root["profiles"]["research_lite"]
    image = cp_root["docker_image"]
    timeout_seconds = int(profile["task_timeout_seconds"][task_id])
    if not docker_available():
        raise SystemExit("Docker is not runnable; no calculation was attempted")
    ensure_image(image, allow_pull)

    task = _canonical_task(task_id)
    source_dir = ROOT / Path(task["gamma_input"]).parent
    if task_id == "cu2te_bulk_k222":
        source_input = ROOT / task["optional_kpoint_check_input"]
        kpoint_mesh = "2x2x2"
        kpoint_checked = True
        expected_electronic_outputs = False
        status_warning = (
            "Minimum 2x2x2 bulk k-point energy check only; this single comparison "
            "does not establish k-point convergence."
        )
    else:
        source_input = ROOT / task["gamma_input"]
        kpoint_mesh = "implicit_gamma"
        kpoint_checked = False
        expected_electronic_outputs = True
        status_warning = task["gamma_reference_scope"]

    run_dir = ROOT / "research_lite" / "runs" / task_id
    run_dir.mkdir(parents=True, exist_ok=True)
    prior_metadata = _read_json(run_dir / "run_metadata.json")
    prior_parsed = _read_json(run_dir / "output.parsed.json")
    if prior_metadata.get("attempted"):
        if _success(task_id, prior_parsed):
            print(f"{task_id}: already successful; refusing to repeat it")
            return 0
        if not archive_existing_as:
            raise SystemExit(
                f"refusing to overwrite the existing audited {task_id} attempt"
            )
        if Path(archive_existing_as).name != archive_existing_as:
            raise SystemExit("archive name must be one plain directory name")
        history_root = (run_dir / "history").resolve()
        archive_dir = (history_root / archive_existing_as).resolve()
        if archive_dir.parent != history_root or archive_dir.exists():
            raise SystemExit("requested history archive is unsafe or already exists")
        archive_dir.mkdir(parents=True)
        for existing in list(run_dir.iterdir()):
            if existing.name == "history":
                continue
            shutil.move(str(existing), str(archive_dir / existing.name))
    if any(run_dir.iterdir()):
        if set(path.name for path in run_dir.iterdir()) != {"history"}:
            raise SystemExit(
                f"refusing to use non-empty unaudited run directory: {run_dir}"
            )

    input_snapshot = run_dir / "input.executed.inp"
    shutil.copy2(source_input, input_snapshot)
    for structure_name in ("structure.cif", "structure.xyz", "structure.extxyz"):
        source_structure = source_dir / structure_name
        if source_structure.is_file():
            shutil.copy2(source_structure, run_dir / structure_name)

    output_path = run_dir / "output.out"
    metadata_path = run_dir / "run_metadata.json"
    parsed_path = run_dir / "output.parsed.json"
    version = command_version("docker", None, image)
    container_name = f"cp2k-research-{task_id.lower()}-{uuid.uuid4().hex[:8]}"
    command = [
        "docker",
        "run",
        "--name",
        container_name,
        "--rm",
        "-e",
        f"OMP_NUM_THREADS={threads}",
        "-v",
        f"{run_dir.resolve()}:/work",
        "-w",
        "/work",
        image,
        "cp2k",
        "-i",
        "input.executed.inp",
        "-o",
        "output.out",
    ]
    metadata = {
        "calculation_id": task_id,
        "canonical_structure_id": task["calculation_id"],
        "calculation_profile": "research_lite",
        "attempted": True,
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "execution_command": (
            f"docker run --rm -e OMP_NUM_THREADS={threads} "
            f"-v <run_dir>:/work -w /work {image} "
            "cp2k -i input.executed.inp -o output.out"
        ),
        "cp2k_version": version,
        "docker_image": image,
        "cpu_threads": threads,
        "timeout_seconds": timeout_seconds,
        "timed_out": False,
        "return_code": None,
        "termination_reason": "running",
        "confirmed_stop_cause": None,
        "wall_time_seconds": None,
        "input_sha256": _sha256(input_snapshot),
        "kpoint_mesh": kpoint_mesh,
        "kpoint_convergence_checked": kpoint_checked,
        "kpoint_status_warning": status_warning,
        "dos_near_fermi_window_ev": profile["dos_near_fermi_window_ev"],
        "substrate_area_angstrom2": task["substrate_area_angstrom2"],
        "cu2te_formula_units": task["cu2te_formula_units"],
        "expected_electronic_outputs": expected_electronic_outputs,
        "dependency_gate": dependency,
        "historical_attempt_archive": (
            f"history/{archive_existing_as}" if archive_existing_as else None
        ),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    started_clock = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=run_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return_code = process.returncode
        timed_out = False
        termination_reason = (
            "launcher_exit_0_pending_output_validation"
            if return_code == 0
            else "nonzero_launcher_exit"
        )
        stop_cause = (
            "Docker/CP2K process returned zero; strict output validation is pending"
            if return_code == 0
            else "launcher returned a nonzero code; inspect stderr and CP2K output"
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(
            ["docker", "stop", "--time", "5", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stdout, stderr = process.communicate(timeout=30)
        return_code = process.returncode
        termination_reason = "runner_timeout"
        stop_cause = (
            f"runner enforced the configured {timeout_seconds}-second hard limit"
        )
    wall_time = time.perf_counter() - started_clock
    (run_dir / "launcher_stdout.txt").write_text(stdout or "", encoding="utf-8")
    (run_dir / "launcher_stderr.txt").write_text(stderr or "", encoding="utf-8")
    metadata.update(
        {
            "finished_at_utc": _utc_now(),
            "timed_out": timed_out,
            "return_code": return_code,
            "termination_reason": termination_reason,
            "confirmed_stop_cause": stop_cause,
            "wall_time_seconds": wall_time,
        }
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    potential_cube = run_dir / "hartree_potential.cube"
    if potential_cube.is_file():
        write_planar_average(
            potential_cube,
            run_dir / "hartree_potential_planar_average.csv",
        )
    result = parse_research_run(run_dir)
    if timed_out:
        metadata["termination_reason"] = "runner_timeout"
    elif return_code != 0:
        metadata["termination_reason"] = "nonzero_launcher_exit"
    elif _success(task_id, result):
        metadata["termination_reason"] = "strict_success"
        metadata["confirmed_stop_cause"] = (
            "normal CP2K end marker, explicit SCF convergence, valid energy"
            + (
                ", and complete requested electronic outputs"
                if expected_electronic_outputs
                else ""
            )
        )
    else:
        metadata["termination_reason"] = "strict_validation_failed"
        metadata["confirmed_stop_cause"] = (
            "process returned zero but one or more strict CP2K success/output "
            "criteria were not met"
        )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = parse_research_run(run_dir)
    parsed_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _update_manifest(task_id)
    print(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "calculation_id",
                    "energy_valid",
                    "electronic_outputs_complete",
                    "scf_steps",
                    "total_energy_hartree",
                    "wall_time_seconds",
                    "cp2k_warning_count",
                    "termination_reason",
                    "warning_or_error",
                )
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if _success(task_id, result) else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one gated research_lite task without overwriting evidence"
    )
    parser.add_argument("task_id", choices=ORDER)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--allow-pull", action="store_true")
    parser.add_argument("--archive-existing-as")
    args = parser.parse_args()
    config = load_config()
    threads = args.threads or int(config["cp2k"]["local_max_threads"])
    if not 1 <= threads <= 8:
        raise SystemExit("local research_lite runner is limited to 1-8 CPU threads")
    return run_task(
        args.task_id,
        threads,
        args.allow_pull,
        args.archive_existing_as,
    )


if __name__ == "__main__":
    raise SystemExit(main())
