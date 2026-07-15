from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_metadata
from parse_cp2k_output import parse_output

FIELDS = [
    "model_id", "Cd_atoms", "Te_atoms", "Cu_atoms", "total_atoms", "Cu_Te_layers",
    "initial_thickness_A", "initial_thickness_nm", "optimized_thickness_A",
    "minimum_distance_A", "lateral_area_A2", "lattice_mismatch_percent",
    "CP2K_completed", "SCF_converged", "geometry_optimization_converged",
    "total_energy_hartree", "total_energy_eV", "warnings",
]


def main() -> int:
    rows = []
    for model_id in ("T0", "T1", "T2"):
        meta = load_metadata(model_id)
        model_dir = ROOT / "models" / model_id
        parsed = parse_output(model_dir / "single_point.out", model_dir / "single_point.inp")
        warning = "" if parsed["program_completed"] else "CP2K not run or not proven converged"
        rows.append({
            "model_id": model_id,
            "Cd_atoms": meta["counts"].get("Cd", 0), "Te_atoms": meta["counts"].get("Te", 0), "Cu_atoms": meta["counts"].get("Cu", 0),
            "total_atoms": meta["total_atoms"], "Cu_Te_layers": meta["cu_te_layers"],
            "initial_thickness_A": f"{meta['initial_cute_thickness_angstrom']:.6f}", "initial_thickness_nm": f"{meta['initial_cute_thickness_nm']:.6f}",
            "optimized_thickness_A": "", "minimum_distance_A": f"{meta['minimum_distance_angstrom']:.6f}",
            "lateral_area_A2": f"{meta['lateral_area_angstrom2']:.6f}", "lattice_mismatch_percent": f"{meta['lattice_mismatch_percent_unstrained']:.6f}",
            "CP2K_completed": parsed["program_completed"], "SCF_converged": parsed["scf_converged"],
            "geometry_optimization_converged": parsed["geometry_optimization_converged"],
            "total_energy_hartree": parsed["total_energy_hartree"], "total_energy_eV": parsed["total_energy_ev"], "warnings": warning,
        })
    (ROOT / "results").mkdir(exist_ok=True)
    output = ROOT / "results" / "model_summary.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
