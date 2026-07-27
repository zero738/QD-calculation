from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config
from run_smoke_tests import command_version


def main() -> int:
    package = ROOT / "server_scnet_2024_1"
    config = json.loads((package / "package_config.json").read_text(encoding="utf-8"))
    image = load_config()["cp2k"]["docker_image"]
    unique_inputs = []
    seen = set()
    for task_id, task in config["tasks"].items():
        relative = Path("inputs") / task["input_dir"] / task["input_name"]
        if relative.as_posix() not in seen:
            unique_inputs.append((task_id, relative))
            seen.add(relative.as_posix())
    results = []
    for task_id, relative in unique_inputs:
        input_path = package / relative
        command = [
            "docker", "run", "--rm",
            "-v", f"{input_path.parent.resolve()}:/work",
            "-w", "/work",
            image, "cp2k", "--check", "-i", input_path.name,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=90
        )
        combined = (completed.stdout + "\n" + completed.stderr).strip()
        results.append(
            {
                "task_id": task_id,
                "input_file": relative.as_posix(),
                "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "return_code": completed.returncode,
                "check_passed": completed.returncode == 0
                and "SUCCESS, the input could be parsed correctly." in combined,
                "last_message": combined.splitlines()[-1] if combined else "no output",
            }
        )
    evidence = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_precheck_cp2k_version": command_version("docker", None, image),
        "target_server_cp2k_version": "2024.1",
        "docker_image": image,
        "all_passed": all(item["check_passed"] for item in results),
        "input_count": len(results),
        "results": results,
        "scope": (
            "Syntax-only precheck with local CP2K 2024.3. This is not a CP2K "
            "2024.1 server run and proves neither SCF convergence nor scientific validity."
        ),
    }
    destination = package / "results" / "syntax_precheck_cp2k_2024_3.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{sum(item['check_passed'] for item in results)}/{len(results)} inputs passed CP2K 2024.3 --check")
    return 0 if evidence["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
