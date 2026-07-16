from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config


def short_command(command: list[str], timeout: int = 20) -> dict:
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "return_code": None, "output": str(error)}
    raw = completed.stdout + b"\n" + completed.stderr
    if b"\x00" in raw:
        text = raw.decode("utf-16le", errors="replace")
    else:
        text = raw.decode(errors="replace")
    return {
        "ok": completed.returncode == 0,
        "return_code": completed.returncode,
        "output": text.strip()[:2000],
    }


def main() -> int:
    config = load_config()
    command_names = (
        "cp2k",
        "cp2k.psmp",
        "cp2k.popt",
        "docker",
        "wsl",
        "mpiexec",
        "mpirun",
        "srun",
        "sbatch",
    )
    commands = {name: shutil.which(name) for name in command_names}
    packages = {}
    for name in ("ase", "numpy", "PyYAML", "matplotlib", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    docker_status = short_command(["docker", "info", "--format", "{{.ServerVersion}}"])
    if not commands["docker"]:
        docker_status = {"ok": False, "return_code": None, "output": "docker command not found"}
    image = config["cp2k"]["docker_image"]
    docker_image = (
        short_command(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        if docker_status["ok"]
        else {"ok": False, "return_code": None, "output": "Docker engine unavailable"}
    )
    wsl_status = (
        short_command(["wsl", "--list", "--quiet"])
        if commands["wsl"]
        else {"ok": False, "return_code": None, "output": "wsl command not found"}
    )
    wsl_text = wsl_status["output"].replace("\ufffd", "").strip() if wsl_status["ok"] else ""
    # On Windows without a distribution, `wsl --list --quiet` may return an
    # installation-help paragraph with exit code zero.  It is not a distro name.
    if "https://aka.ms/" in wsl_text or "Windows Subsystem" in wsl_text or "适用于 Linux" in wsl_text:
        wsl_text = ""
    result = {
        "python": sys.version,
        "platform": platform.platform(),
        "commands": commands,
        "packages": packages,
        "native_cp2k_available": any(commands[name] for name in ("cp2k", "cp2k.psmp", "cp2k.popt")),
        "docker_engine_available": docker_status["ok"],
        "docker_server_version": docker_status["output"] if docker_status["ok"] else None,
        "configured_cp2k_image": image,
        "configured_cp2k_image_present": docker_image["ok"],
        "configured_cp2k_image_id": docker_image["output"] if docker_image["ok"] else None,
        "wsl_command_available": bool(commands["wsl"]),
        "wsl_distributions": [line.strip() for line in wsl_text.splitlines() if line.strip()],
        "runnable_cp2k_path_available": bool(
            any(commands[name] for name in ("cp2k", "cp2k.psmp", "cp2k.popt"))
            or (docker_status["ok"] and docker_image["ok"])
        ),
        "note": "Environment discovery only; actual execution is recorded per smoke-test task.",
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "environment.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
