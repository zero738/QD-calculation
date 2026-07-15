from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT


def main() -> int:
    commands = {name: shutil.which(name) for name in ("cp2k", "cp2k.psmp", "cp2k.popt", "mpiexec", "srun", "sbatch")}
    packages = {}
    for name in ("ase", "numpy", "PyYAML", "matplotlib", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    result = {
        "python": sys.version, "platform": platform.platform(), "commands": commands, "packages": packages,
        "cp2k_available": any(commands[name] for name in ("cp2k", "cp2k.psmp", "cp2k.popt")),
        "note": "Command discovery only; CP2K was not executed by this inspection.",
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "environment.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
