from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config
from run_smoke_tests import command_version


def main() -> int:
    config = load_config()
    image = config["cp2k"]["docker_image"]
    manifest = json.loads((ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8"))
    results = []
    for task in manifest:
        for input_kind, key in (("gamma", "gamma_input"), ("optional_k221", "optional_k221_input")):
            input_path = ROOT / task[key]
            command = [
                "docker", "run", "--rm", "-v", f"{input_path.parent.resolve()}:/work", "-w", "/work",
                image, "cp2k", "--check", "-i", input_path.name,
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
            combined = (completed.stdout + "\n" + completed.stderr).strip()
            results.append(
                {
                    "calculation_id": task["calculation_id"],
                    "input_kind": input_kind,
                    "input_file": task[key],
                    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                    "return_code": completed.returncode,
                    "check_passed": completed.returncode == 0 and "SUCCESS, the input could be parsed correctly." in combined,
                    "message": combined.splitlines()[-1] if combined else "no output",
                }
            )
    evidence = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "cp2k_version": command_version("docker", None, image),
        "docker_image": image,
        "check_command": "docker run --rm -v <input_dir>:/work -w /work cp2k/cp2k:2024.3 cp2k --check -i <input>",
        "all_passed": all(item["check_passed"] for item in results),
        "results": results,
        "warning": "CP2K --check verifies parsing only; it does not prove physical meaning or SCF convergence.",
    }
    destination = ROOT / "research_lite" / "cp2k_input_checks.json"
    destination.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sum(item['check_passed'] for item in results)}/{len(results)} inputs passed CP2K --check")
    return 0 if evidence["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
