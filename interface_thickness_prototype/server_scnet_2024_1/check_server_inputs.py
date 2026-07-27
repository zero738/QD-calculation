#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from server_analysis import sha256, write_json

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Check all SCNet inputs with the target CP2K")
    parser.add_argument("--cp2k", default="/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt")
    args = parser.parse_args()
    config = json.loads((ROOT / "package_config.json").read_text(encoding="utf-8"))
    version_run = subprocess.run([args.cp2k, "--version"], capture_output=True, text=True)
    version_text = (version_run.stdout + "\n" + version_run.stderr).strip()
    version_ok = version_run.returncode == 0 and "CP2K version 2024.1" in version_text
    results = []
    for task_id, spec in config["tasks"].items():
        input_path = ROOT / "inputs" / spec["input_dir"] / spec["input_name"]
        command = [args.cp2k, "--check", "-i", input_path.name]
        checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            completed = subprocess.run(
                command, cwd=input_path.parent, capture_output=True, text=True,
                env={**os.environ, "CP2K_DATA_DIR": config["cp2k_data_dir"]}, timeout=180,
            )
            stdout, stderr, return_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return_code = 124
        combined = (stdout + "\n" + stderr).strip()
        passed = bool(
            version_ok and return_code == 0
            and "SUCCESS, the input could be parsed correctly." in combined
        )
        results.append({
            "task_id": task_id,
            "input_path": input_path.relative_to(ROOT).as_posix(),
            "input_sha256": sha256(input_path),
            "cp2k_version": version_text.splitlines()[0] if version_text else "",
            "command": " ".join(command),
            "return_code": return_code,
            "check_passed": passed,
            "stdout_summary": "\n".join(stdout.splitlines()[-20:]),
            "stderr_summary": "\n".join(stderr.splitlines()[-20:]),
            "checked_at_utc": checked_at,
        })
    payload = {
        "target_cp2k_version": "2024.1", "version_check_passed": version_ok,
        "all_inputs_passed": version_ok and all(item["check_passed"] for item in results),
        "input_count": len(results), "results": results,
        "scope": "real CP2K 2024.1 --check on an SCNet compute node; syntax only, not SCF execution",
    }
    write_json(ROOT / "results/server_cp2k_2024_1_input_checks.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_inputs_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
