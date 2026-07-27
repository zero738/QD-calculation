#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from server_analysis import write_json
from verify_server_outputs import read_config, verify_task

ROOT = Path(__file__).resolve().parent


def run_checked(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("after-h2", "h1-failure"), required=True)
    args = parser.parse_args()
    config = read_config()
    h1 = verify_task("H1", config)
    if args.mode == "h1-failure" and h1["strict_success"]:
        print("H1 strict success: failure finalizer exits without creating a report or lock.")
        return 0
    lock = ROOT / "results/.finalize_lock"
    try:
        lock.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print("Final results are already being generated or were generated; no overwrite.")
        return 0
    state = {
        "mode": args.mode, "started_at": dt.datetime.now().astimezone().isoformat(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", "unknown"),
        "h1_strict_success": h1["strict_success"], "status": "running",
    }
    write_json(lock / "state.json", state)
    try:
        if args.mode == "h1-failure":
            jobs_path = ROOT / "pipeline_jobs.json"
            if jobs_path.is_file():
                jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
                h2_job = str(jobs["H2_job_id"])
                subprocess.run(["scancel", h2_job], check=False)
                write_json(ROOT / "results/H2_blocked_by_H1.json", {
                    "status": "blocked_by_H1", "H2_job_id": h2_job,
                    "reason": "H1 failed strict verification after at most one controlled retry",
                })
        run_checked(["python3", "verify_server_outputs.py", "--all", "--write-results"])
        run_checked(["python3", "generate_reports.py"])
        # Missing matplotlib is an allowed plot state and plot_results.py exits 0.
        run_checked(["python3", "plot_results.py"])
        run_checked(["python3", "package_results.py"])
        state.update({"status": "complete", "finished_at": dt.datetime.now().astimezone().isoformat()})
        write_json(lock / "state.json", state)
        return 0
    except Exception as exc:
        state.update({"status": "failed", "error": str(exc), "finished_at": dt.datetime.now().astimezone().isoformat()})
        write_json(lock / "state.json", state)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
