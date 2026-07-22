from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_cp2k_output import HARTREE_TO_EV, parse_output


PDOS_FERMI_RE = re.compile(r"Fermi\s+energy:\s*([-+0-9.Ee]+)", re.I)


def _numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "@")):
            continue
        try:
            rows.append([float(value) for value in line.split()])
        except ValueError:
            continue
    return rows


def _relative(path: Path, run_dir: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.name


def parse_research_run(run_dir: Path) -> dict:
    output = run_dir / "output.out"
    input_path = run_dir / "input.executed.inp"
    metadata_path = run_dir / "run_metadata.json"
    result = parse_output(output, input_path, metadata_path)
    result["calculation_profile"] = "research_lite"
    result["fermi_reference_warning"] = "Raw CP2K internal potential reference; not a vacuum-aligned work function."
    output_text = output.read_text(encoding="utf-8", errors="replace") if output.is_file() else ""
    cp2k_warnings = []
    if "Projected density of states" in output_text and "not implemented for k points" in output_text:
        cp2k_warnings.append("CP2K 2024.3: projected DOS/LDOS is not implemented when KPOINTS is active")
    result["cp2k_warnings"] = cp2k_warnings

    pdos_files = sorted(run_dir.glob("*.pdos"))
    pdos_inventory = []
    for path in pdos_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rows = _numeric_rows(path)
        fermi_match = PDOS_FERMI_RE.search(text)
        pdos_inventory.append(
            {
                "file": _relative(path, run_dir),
                "numeric_rows": len(rows),
                "fermi_energy_hartree_in_header": float(fermi_match.group(1)) if fermi_match else None,
            }
        )

    dos_candidates = sorted(
        {
            *run_dir.glob("*.dos"),
            *run_dir.glob("*dos*.dat"),
        }
    )
    dos_inventory = []
    dos_near_fermi_bin_density = None
    normalized_dos_near_fermi = None
    for path in dos_candidates:
        rows = _numeric_rows(path)
        dos_inventory.append({"file": _relative(path, run_dir), "numeric_rows": len(rows)})
        # CP2K DOS energies and densities are printed in atomic units. Convert
        # the density to states/eV by dividing states/Ha by Ha/eV.
        if rows and result.get("fermi_energy_hartree") is not None and len(rows[0]) >= 2:
            window_ha = 0.10 / HARTREE_TO_EV
            near = [row[1] for row in rows if abs(row[0] - result["fermi_energy_hartree"]) <= window_ha]
            if near:
                dos_near_fermi_bin_density = float(sum(near) / len(near))
                if len(rows) > 1:
                    bin_width_ev = abs(rows[1][0] - rows[0][0]) * HARTREE_TO_EV
                    if bin_width_ev > 0:
                        # CP2K's DOS "Density" column sums to one over all
                        # histogram bins. Divide by bin width for normalized
                        # DOS per eV; do not label it as an absolute state count.
                        normalized_dos_near_fermi = dos_near_fermi_bin_density / bin_width_ev

    potential_cubes = sorted(run_dir.glob("*hartree*potential*.cube"))
    density_cubes = sorted(run_dir.glob("*density*.cube"))
    result.update(
        {
            "pdos_files": pdos_inventory,
            "dos_files": dos_inventory,
            "dos_near_fermi_mean_bin_density": dos_near_fermi_bin_density,
            "normalized_dos_near_fermi_per_ev": normalized_dos_near_fermi,
            "hartree_potential_cube_files": [_relative(path, run_dir) for path in potential_cubes],
            "electron_density_cube_files": [_relative(path, run_dir) for path in density_cubes],
            "pdos_output_present": bool(pdos_inventory and all(item["numeric_rows"] > 0 for item in pdos_inventory)),
            "dos_output_present": bool(dos_inventory and all(item["numeric_rows"] > 0 for item in dos_inventory)),
            "potential_output_present": bool(potential_cubes),
            "density_output_present": bool(density_cubes),
        }
    )
    result["research_output_complete"] = bool(
        result["program_completed"]
        and result["fermi_energy_hartree"] is not None
        and result["pdos_output_present"]
        and result["dos_output_present"]
        and result["potential_output_present"]
        and result["density_output_present"]
    )
    if result["program_completed"] and not result["research_output_complete"]:
        missing = [
            label
            for label, present in (
                ("Fermi energy", result["fermi_energy_hartree"] is not None),
                ("PDOS/LDOS", result["pdos_output_present"]),
                ("DOS", result["dos_output_present"]),
                ("Hartree potential cube", result["potential_output_present"]),
                ("electron-density cube", result["density_output_present"]),
            )
            if not present
        ]
        result["warning_or_error"] = "CP2K ended successfully, but research outputs are missing: " + ", ".join(missing)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse strict CP2K plus research_lite DOS/PDOS evidence")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = parse_research_run(args.run_dir)
    destination = args.json or args.run_dir / "output.parsed.json"
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["research_output_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
