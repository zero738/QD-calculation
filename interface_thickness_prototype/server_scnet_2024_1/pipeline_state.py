#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPUTE_SCRIPTS = [
    "00_check_environment.slurm", "01_cu2te_bulk_gamma.slurm",
    "02_cu2te_bulk_k222.slurm", "03_cu2te_bulk_k333.slurm",
    "04_cu2te_bulk_k444.slurm", "10_B0.slurm", "20_C50.slurm",
    "30_H1.slurm", "40_H2.slurm", "90_finalize_after_H2.slurm",
    "91_finalize_if_H1_failed.slurm",
]


def parse_time(value: str) -> float:
    fields = [int(item) for item in value.split(":")]
    if len(fields) == 3:
        hours, minutes, seconds = fields
        return hours + minutes / 60 + seconds / 3600
    if len(fields) == 2:
        minutes, seconds = fields
        return minutes / 60 + seconds / 3600
    raise ValueError(value)


def parse_script(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    def directive(name: str) -> str:
        match = re.search(rf"(?m)^#SBATCH\s+--{re.escape(name)}=(\S+)\s*$", text)
        if not match:
            raise ValueError(f"{path.name}: missing --{name}")
        return match.group(1)
    ntasks = int(directive("ntasks")); hours = parse_time(directive("time"))
    return {
        "script": f"scripts/{path.name}", "partition": directive("partition"),
        "nodes": int(directive("nodes")), "ntasks": ntasks,
        "time_limit": directive("time"), "requested_hours": hours,
        "maximum_cpu_hours": ntasks * hours, "has_exclusive": "--exclusive" in text,
    }


def budget() -> dict:
    records = [parse_script(ROOT / "scripts" / name) for name in COMPUTE_SCRIPTS]
    total = sum(item["maximum_cpu_hours"] for item in records)
    valid = bool(
        total < 1800 and all(item["nodes"] == 1 for item in records)
        and all(item["partition"] == "kshctest02" for item in records)
        and not any(item["has_exclusive"] for item in records)
    )
    return {"valid": valid, "maximum_requested_cpu_hours": total, "limit_cpu_hours": 1800, "jobs": records}


def record_pipeline(args: argparse.Namespace) -> int:
    entries = {}
    for raw in args.entry:
        task, job_id, dependency, script = raw.split("|", 3)
        entries[task] = {"job_id": job_id, "dependency": dependency, "script": script}
    resources = {Path(item["script"]).name: item for item in budget()["jobs"]}
    for entry in entries.values():
        entry.update(resources[Path(entry["script"]).name])
    payload = {
        "pipeline_id": args.pipeline_id,
        "submitted_at": dt.datetime.now().astimezone().isoformat(),
        "git_commit": args.git_commit,
        "partition": "kshctest02",
        "maximum_requested_cpu_hours": budget()["maximum_requested_cpu_hours"],
        "jobs": entries,
        "H2_job_id": entries["H2"]["job_id"],
        "finalize_job_ids": [entries["finalize_after_H2"]["job_id"], entries["finalize_if_H1_failed"]["job_id"]],
    }
    path = ROOT / "pipeline_jobs.json"
    if path.exists():
        raise SystemExit("refusing to overwrite pipeline_jobs.json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def monitor() -> int:
    path = ROOT / "pipeline_jobs.json"
    if not path.is_file():
        print("pipeline_jobs.json not found")
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["job_id"] for item in payload["jobs"].values()]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n=== squeue ===")
    subprocess.run(["squeue", "-j", ",".join(ids), "-o", "%.18i %.24j %.10T %.10M %.10l %.20R"], check=False)
    print("\n=== sacct ===")
    subprocess.run(["sacct", "-j", ",".join(ids), "--format=JobID,JobName,State,Elapsed,Timelimit,ExitCode"], check=False)
    h1 = ROOT / "runs/H1"
    print("\n=== H1 attempts/gate ===")
    for name in ("attempt_A", "attempt_B", "H1_SUCCESS.json", "H1_FAILURE.json"):
        print(f"{name}: {'present' if (h1 / name).exists() else 'absent'}")
    print(f"H2 blocked: {not (h1 / 'H1_SUCCESS.flag').is_file()}")
    print(f"results: {ROOT / 'results'}")
    print(f"bundle: {ROOT / 'scnet_results_bundle.tar.gz'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("budget")
    record = sub.add_parser("record")
    record.add_argument("--pipeline-id", required=True); record.add_argument("--git-commit", required=True)
    record.add_argument("--entry", action="append", required=True)
    sub.add_parser("monitor")
    args = parser.parse_args()
    if args.command == "budget":
        payload = budget(); print(json.dumps(payload, indent=2)); return 0 if payload["valid"] else 2
    if args.command == "record":
        return record_pipeline(args)
    return monitor()


if __name__ == "__main__":
    raise SystemExit(main())
