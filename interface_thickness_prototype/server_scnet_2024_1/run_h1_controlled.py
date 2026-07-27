#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from server_analysis import (
    build_retry_input, classify_attempt_failure, scf_signature, sha256,
    verify_run_directory, write_json,
)

ROOT = Path(__file__).resolve().parent


def write_metadata(path: Path, values: dict) -> None:
    path.write_text("".join(f"{key}\t{value}\n" for key, value in values.items()), encoding="utf-8")


def environment_record(directory: Path, cp2k: str, input_path: Path) -> None:
    version = subprocess.run([cp2k, "--version"], capture_output=True, text=True)
    git_commit = subprocess.run(
        ["git", "-C", str(ROOT.parent.parent), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    limits = subprocess.run(["bash", "-lc", "ulimit -a"], capture_output=True, text=True)
    memory_text = ""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        memory_text = "\n".join(
            line for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith(("MemTotal", "MemAvailable"))
        )
    lines = [
        f"recorded_at={dt.datetime.now().astimezone().isoformat()}",
        f"hostname={socket.gethostname()}", f"job_id={os.environ.get('SLURM_JOB_ID', 'unknown')}",
        f"partition={os.environ.get('SLURM_JOB_PARTITION', 'unknown')}",
        f"ntasks={os.environ.get('SLURM_NTASKS', 'unknown')}", f"cp2k_executable={cp2k}",
        f"cp2k_data_dir={os.environ.get('CP2K_DATA_DIR', 'unknown')}",
        f"input_sha256={sha256(input_path)}", "cp2k_version_begin",
        (version.stdout + version.stderr).strip(), "cp2k_version_end",
        f"git_commit={(git_commit.stdout.strip() or 'unavailable')}",
        f"loaded_modules={os.environ.get('LOADEDMODULES', 'unavailable')}",
        "ulimit_begin", limits.stdout.strip(), "ulimit_end",
        "memory_begin", memory_text or "unavailable", "memory_end",
    ]
    (directory / "environment.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_attempt(name: str, input_text: str, structure_source: Path, cp2k: str, timeout_hours: int, spec: dict, config: dict, restart_source: Path | None = None, restart_manifest_payload: dict | None = None) -> dict:
    root = ROOT / "runs/H1"
    directory = root / name
    if directory.exists():
        raise RuntimeError(f"refusing to overwrite existing H1 evidence: {directory}")
    directory.mkdir(parents=True)
    input_path = directory / "input.executed.inp"
    input_path.write_text(input_text, encoding="utf-8", newline="\n")
    shutil.copy2(structure_source, directory / "structure.extxyz")
    if restart_source is not None:
        shutil.copy2(restart_source, directory / "restart_from_attempt_A.wfn")
    if restart_manifest_payload is not None:
        write_json(directory / "restart_source_manifest.json", restart_manifest_payload)
    environment_record(directory, cp2k, input_path)
    started = dt.datetime.now().astimezone().isoformat()
    start = time.monotonic()
    metadata = {
        "task_id": "H1", "attempt": name, "started_at": started, "finished_at": "",
        "wall_time_seconds": "", "return_code": "pending",
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "unknown"),
        "partition": os.environ.get("SLURM_JOB_PARTITION", "unknown"),
        "ntasks": os.environ.get("SLURM_NTASKS", "unknown"),
        "input_sha256": sha256(input_path), "structure_sha256": sha256(directory / "structure.extxyz"),
        "timeout_hours": timeout_hours,
    }
    write_metadata(directory / "run_metadata.tsv", metadata)
    command = [
        "timeout", "--signal=TERM", "--kill-after=60s", f"{timeout_hours}h",
        "srun", "--mpi=pmix_v3", cp2k, "-i", "input.executed.inp", "-o", "output.out",
    ]
    try:
        completed = subprocess.run(
            command, cwd=directory, capture_output=True, text=True,
            timeout=timeout_hours * 3600 + 120,
        )
        return_code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    (directory / "launcher_stdout.txt").write_text(stdout, encoding="utf-8")
    (directory / "launcher_stderr.txt").write_text(stderr, encoding="utf-8")
    metadata.update({
        "finished_at": dt.datetime.now().astimezone().isoformat(),
        "wall_time_seconds": round(time.monotonic() - start, 3), "return_code": return_code,
        "termination_reason": "timeout" if return_code in {124, 137} else ("process_exit_0" if return_code == 0 else "nonzero_exit"),
    })
    write_metadata(directory / "run_metadata.tsv", metadata)
    result = verify_run_directory("H1", directory, spec, config, sha256(input_path))
    result["attempt"] = name
    return result


def restart_manifest(attempt_a: Path, base_input_hash: str, structure_hash: str) -> tuple[Path | None, dict]:
    candidates = sorted(
        {path for pattern in ("*.wfn", "*WFN*", "*.restart") for path in attempt_a.glob(pattern) if path.is_file()}
    )
    records = [{
        "source": str(path.resolve()), "relative_source": path.relative_to(ROOT).as_posix(),
        "type": "WFN" if "wfn" in path.name.lower() else "restart",
        "size_bytes": path.stat().st_size, "sha256": sha256(path),
    } for path in candidates]
    version_ok = "CP2K version 2024.1" in (attempt_a / "output.out").read_text(
        encoding="utf-8", errors="replace"
    ) if (attempt_a / "output.out").is_file() else False
    hashes_ok = (
        sha256(attempt_a / "input.executed.inp") == base_input_hash
        and sha256(attempt_a / "structure.extxyz") == structure_hash
    )
    chosen = next((path for path in candidates if "wfn" in path.name.lower()), None) if version_ok and hashes_ok else None
    fallback = "no verified WFN; SCF_GUESS ATOMIC"
    if chosen and base_input_hash and structure_hash:
        fallback = "verified same-run CP2K 2024.1 attempt_A WFN copied; SCF_GUESS RESTART"
    manifest = {
        "attempt_A_base_input_sha256": base_input_hash,
        "attempt_A_structure_sha256": structure_hash,
        "attempt_A_cp2k_2024_1_confirmed": version_ok,
        "attempt_A_input_and_structure_hashes_confirmed": hashes_ok,
        "candidates": records, "chosen_wfn": chosen.name if chosen else None, "decision": fallback,
        "forbidden_source": "old CP2K 2024.3 WFN/restart files are never searched or used",
    }
    return chosen, manifest


def success_record(attempt: str, result: dict) -> dict:
    run_dir = ROOT / "runs/H1" / attempt
    signature = scf_signature(run_dir / "input.executed.inp")
    return {
        "status": "strict_success", "successful_attempt": attempt,
        "EPS_SCF": signature["EPS_SCF"], "MAX_SCF": signature["MAX_SCF"],
        "ADDED_MOS": signature["ADDED_MOS"], "NLUMO": signature["NLUMO"],
        "ALPHA": signature["ALPHA"], "NBROYDEN": signature["NBROYDEN"],
        "electronic_temperature_K": signature["ELECTRONIC_TEMPERATURE"],
        "diagonalization_method": signature["DIAGONALIZATION"],
        "successful_input_sha256": sha256(run_dir / "input.executed.inp"),
        "structure_sha256": sha256(run_dir / "structure.extxyz"),
        "scf_signature": signature, "verification": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run H1 with at most one controlled retry")
    parser.add_argument("--cp2k", required=True)
    args = parser.parse_args()
    config = json.loads((ROOT / "package_config.json").read_text(encoding="utf-8"))
    config["package_root"] = str(ROOT)
    spec = config["tasks"]["H1"]
    root = ROOT / "runs/H1"
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"refusing to overwrite H1 evidence: {root}")
    root.mkdir(parents=True, exist_ok=True)
    base_input = ROOT / "inputs/H1/input.inp"
    structure = ROOT / "inputs/H1/structure.extxyz"
    base_text = base_input.read_text(encoding="utf-8")
    result_a = run_attempt("attempt_A", base_text, structure, args.cp2k, 7, spec, config)
    write_json(root / "attempt_A/attempt_result.json", result_a)
    if result_a["strict_success"]:
        record = success_record("attempt_A", result_a)
        write_json(root / "H1_SUCCESS.json", record)
        (root / "H1_SUCCESS.flag").write_text("strict_success attempt_A\n", encoding="ascii")
        return 0
    output_text = (root / "attempt_A/output.out").read_text(encoding="utf-8", errors="replace") if (root / "attempt_A/output.out").is_file() else ""
    classification = classify_attempt_failure(output_text, result_a.get("input_hash_valid", False))
    write_json(root / "attempt_A/failure_classification.json", classification)
    if classification["classification"] == "hard_configuration_failure" or classification["classification"] == "unclassified_failure_no_retry":
        write_json(root / "H1_FAILURE.json", {"status": classification["classification"], "attempt_A": result_a, "retry_started": False})
        return 2
    retry_policy = config["h1_controlled_retry"]
    if classification["classification"] == "persistent_last_mo_warning":
        variant_key = "attempt_B_more_unoccupied"
    elif classification["classification"] == "oscillating_scf_residual":
        variant_key = "attempt_B_gentler_mixing"
    else:
        write_json(root / "H1_FAILURE.json", {"status": "unclassified_failure_no_retry", "attempt_A": result_a, "retry_started": False})
        return 2
    variant = retry_policy[variant_key]
    chosen_wfn, manifest = restart_manifest(root / "attempt_A", sha256(base_input), sha256(structure))
    retry_text = build_retry_input(base_text, variant, "restart_from_attempt_A.wfn" if chosen_wfn else None)
    result_b = run_attempt(
        "attempt_B", retry_text, structure, args.cp2k, 8, spec, config,
        restart_source=chosen_wfn, restart_manifest_payload=manifest,
    )
    write_json(root / "attempt_B/attempt_result.json", result_b)
    if result_b["strict_success"]:
        record = success_record("attempt_B", result_b)
        record["retry_trigger"] = classification
        write_json(root / "H1_SUCCESS.json", record)
        (root / "H1_SUCCESS.flag").write_text("strict_success attempt_B\n", encoding="ascii")
        return 0
    write_json(root / "H1_FAILURE.json", {
        "status": "failed_after_controlled_retry", "retry_trigger": classification,
        "attempt_A": result_a, "attempt_B": result_b,
    })
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
