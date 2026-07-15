from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HARTREE_TO_EV = 27.211386245988
ENERGY_RE = re.compile(r"ENERGY\|.*?energy\s*\[a\.u\.\]\s*:\s*([-+0-9.Ee]+)", re.I)


def parse_output(path: Path, input_path: Path | None = None) -> dict:
    result = {
        "output_file": str(path), "exists": path.is_file(), "program_completed": False,
        "scf_converged": False, "geometry_optimization_converged": None,
        "total_energy_hartree": None, "total_energy_ev": None, "error": None,
    }
    if not path.is_file():
        result["error"] = "output file does not exist; no calculation result is available"
        return result
    text = path.read_text(encoding="utf-8", errors="replace")
    upper = text.upper()
    aborted = any(token in upper for token in ("ABORT", "PROGRAM STOPPED", "SCF RUN NOT CONVERGED"))
    ended = "PROGRAM ENDED AT" in upper
    result["scf_converged"] = "SCF RUN CONVERGED" in upper and "SCF RUN NOT CONVERGED" not in upper
    energies = ENERGY_RE.findall(text)
    if energies:
        energy = float(energies[-1])
        result["total_energy_hartree"] = energy
        result["total_energy_ev"] = energy * HARTREE_TO_EV
    is_geo = False
    if input_path and input_path.is_file():
        is_geo = "RUN_TYPE GEO_OPT" in input_path.read_text(encoding="utf-8", errors="replace").upper()
    if is_geo or "GEOMETRY OPTIMIZATION" in upper:
        result["geometry_optimization_converged"] = "GEOMETRY OPTIMIZATION COMPLETED" in upper and not aborted
    geo_ok = (not is_geo) or bool(result["geometry_optimization_converged"])
    result["program_completed"] = bool(ended and result["scf_converged"] and not aborted and energies and geo_ok)
    if aborted:
        result["error"] = "CP2K reported an abort, stop, or unconverged SCF"
    elif not ended:
        result["error"] = "normal CP2K end marker is missing"
    elif not result["scf_converged"]:
        result["error"] = "explicit SCF convergence marker is missing"
    elif not energies:
        result["error"] = "no total FORCE_EVAL energy was found"
    elif is_geo and not result["geometry_optimization_converged"]:
        result["error"] = "geometry optimization did not reach its convergence criteria"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict CP2K output parser")
    parser.add_argument("output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = parse_output(args.output, args.input)
    destination = args.json or args.output.with_suffix(".parsed.json")
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["program_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
