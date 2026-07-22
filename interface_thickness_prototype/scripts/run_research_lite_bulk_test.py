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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _update_manifest() -> None:
    manifest_path = ROOT / "research_lite" / "manifest.json"
    tasks = json.loads(manifest_path.read_text(encoding="utf-8"))
    for task in tasks:
        if task["calculation_id"] == "cu2te_bulk":
            task["actually_run"] = True
            task["run_directory"] = "research_lite/runs/cu2te_bulk"
    manifest_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only the six-atom Cu2Te research_lite Gamma test")
    parser.add_argument("--threads", type=int)
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--allow-pull", action="store_true")
    parser.add_argument(
        "--archive-existing-as",
        help="Archive one existing audited attempt under runs/cu2te_bulk/history before rerunning",
    )
    args = parser.parse_args()

    config = load_config()
    cp_root = config["cp2k"]
    cp = cp_root["profiles"]["research_lite"]
    image = cp_root["docker_image"]
    threads = args.threads or cp_root["local_max_threads"]
    timeout_seconds = args.timeout_seconds or cp["bulk_test_timeout_seconds"]
    if not docker_available():
        raise SystemExit("Docker is not runnable; no research_lite calculation was attempted")
    ensure_image(image, args.allow_pull)

    source_dir = ROOT / "research_lite" / "inputs" / "cu2te_bulk"
    run_dir = ROOT / "research_lite" / "runs" / "cu2te_bulk"
    run_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = run_dir / "output.parsed.json"
    prior_metadata = run_dir / "run_metadata.json"
    if prior_metadata.is_file() and json.loads(prior_metadata.read_text(encoding="utf-8")).get("attempted"):
        archive_name = args.archive_existing_as
        if not archive_name:
            raise SystemExit("Refusing to overwrite the existing audited Cu2Te research_lite attempt")
        if Path(archive_name).name != archive_name:
            raise SystemExit("archive name must be one plain directory name")
        history_root = (run_dir / "history").resolve()
        archive_dir = (history_root / archive_name).resolve()
        if archive_dir.parent != history_root or archive_dir.exists():
            raise SystemExit("requested history archive is unsafe or already exists")
        archive_dir.mkdir(parents=True)
        for existing in list(run_dir.iterdir()):
            if existing.name == "history":
                continue
            shutil.move(str(existing), str(archive_dir / existing.name))

    input_snapshot = run_dir / "input.executed.inp"
    shutil.copy2(source_dir / "input_gamma.inp", input_snapshot)
    shutil.copy2(source_dir / "structure.cif", run_dir / "structure.cif")
    shutil.copy2(source_dir / "structure.xyz", run_dir / "structure.xyz")
    output_path = run_dir / "output.out"
    metadata_path = run_dir / "run_metadata.json"
    version = command_version("docker", None, image)
    manifest = json.loads((ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8"))
    task = next(item for item in manifest if item["calculation_id"] == "cu2te_bulk")
    container_name = f"cp2k-research-lite-{uuid.uuid4().hex[:8]}"
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
    started = _utc_now()
    metadata = {
        "calculation_id": "cu2te_bulk",
        "calculation_profile": "research_lite",
        "attempted": True,
        "started_at_utc": started,
        "finished_at_utc": None,
        "execution_command": f"docker run --rm -e OMP_NUM_THREADS={threads} -v <run_dir>:/work -w /work {image} cp2k -i input.executed.inp -o output.out",
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
        "kpoint_mesh": "implicit_gamma",
        "kpoint_convergence_checked": False,
        "kpoint_status_warning": "Gamma-only bulk reference; the 2x2x2 energy check has not been run",
        "dos_near_fermi_window_ev": cp["dos_near_fermi_window_ev"],
        "substrate_area_angstrom2": task["substrate_area_angstrom2"],
        "cu2te_formula_units": task["cu2te_formula_units"],
        "attempt_number": 2 if args.archive_existing_as else 1,
        "historical_attempt_archive": (
            f"history/{args.archive_existing_as}" if args.archive_existing_as else None
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    start_clock = time.perf_counter()
    process = subprocess.Popen(command, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return_code = process.returncode
        timed_out = False
        reason = "process_exit_0" if return_code == 0 else "nonzero_launcher_exit"
        stop_cause = "CP2K/Docker process exited normally" if return_code == 0 else "launcher returned a nonzero code; inspect stderr/output"
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "stop", "--time", "5", container_name], capture_output=True, text=True, timeout=20)
        stdout, stderr = process.communicate(timeout=20)
        return_code = process.returncode
        reason = "runner_timeout"
        stop_cause = f"runner enforced the configured {timeout_seconds}-second limit"
    wall_time = time.perf_counter() - start_clock
    (run_dir / "launcher_stdout.txt").write_text(stdout or "", encoding="utf-8")
    (run_dir / "launcher_stderr.txt").write_text(stderr or "", encoding="utf-8")
    metadata.update(
        {
            "finished_at_utc": _utc_now(),
            "timed_out": timed_out,
            "return_code": return_code,
            "termination_reason": reason,
            "confirmed_stop_cause": stop_cause,
            "wall_time_seconds": wall_time,
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    potential_cube = run_dir / "hartree_potential.cube"
    if potential_cube.is_file():
        write_planar_average(
            potential_cube, run_dir / "hartree_potential_planar_average.csv"
        )
    result = parse_research_run(run_dir)
    parsed_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _update_manifest()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["electronic_outputs_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
