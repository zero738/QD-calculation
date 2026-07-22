from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_cp2k_output import HARTREE_TO_EV, parse_output


PDOS_FERMI_RE = re.compile(
    r"(?:Fermi\s+energy:|E\(Fermi\)\s*=)\s*([-+0-9.Ee]+)", re.I
)
LDOS_FILE_RE = re.compile(r"(?:-list|-LDOS-)(\d+)(?:-\d+)?\.pdos$", re.I)
KIND_PDOS_FILE_RE = re.compile(r"(?:-k|-PDOS-)(\d+)(?:-\d+)?\.pdos$", re.I)


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


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _manifest_task(calculation_id: str | None) -> dict:
    if not calculation_id:
        return {}
    manifest_path = Path(__file__).resolve().parents[1] / "research_lite" / "manifest.json"
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, list):
        return {}
    return next(
        (task for task in manifest if task.get("calculation_id") == calculation_id),
        {},
    )


def _pdos_weight_near_fermi(rows: list[list[float]], fermi_hartree: float, window_ev: float) -> float:
    half_window_hartree = window_ev / (2.0 * HARTREE_TO_EV)
    return float(
        sum(
            sum(row[3:])
            for row in rows
            if len(row) >= 4 and abs(row[1] - fermi_hartree) <= half_window_hartree
        )
    )


def parse_research_run(run_dir: Path) -> dict:
    output = run_dir / "output.out"
    input_path = run_dir / "input.executed.inp"
    metadata_path = run_dir / "run_metadata.json"
    metadata = _read_json(metadata_path)
    result = parse_output(output, input_path, metadata_path)
    result["calculation_profile"] = "research_lite"
    task = _manifest_task(metadata.get("calculation_id"))
    executed_input = (
        input_path.read_text(encoding="utf-8", errors="replace")
        if input_path.is_file()
        else ""
    )
    inferred_kpoint_mesh = "implicit_gamma"
    if "&KPOINTS" in executed_input.upper():
        mesh_match = re.search(
            r"SCHEME\s+MONKHORST-PACK\s+(\d+)\s+(\d+)\s+(\d+)",
            executed_input,
            re.I,
        )
        inferred_kpoint_mesh = (
            "x".join(mesh_match.groups()) if mesh_match else "explicit_gamma"
        )
    window_ev = float(
        metadata.get(
            "dos_near_fermi_window_ev",
            task.get("dos_near_fermi_window_ev", 0.20),
        )
    )
    substrate_area = metadata.get(
        "substrate_area_angstrom2", task.get("substrate_area_angstrom2")
    )
    formula_units = metadata.get(
        "cu2te_formula_units", task.get("cu2te_formula_units")
    )
    expected_ldos_groups = task.get("ldos_groups", [])
    result.update(
        {
            "dos_near_fermi_window_ev": window_ev,
            "substrate_area_angstrom2": substrate_area,
            "cu2te_formula_units": formula_units,
            "kpoint_mesh": metadata.get("kpoint_mesh", inferred_kpoint_mesh),
            "kpoint_convergence_checked": bool(
                metadata.get("kpoint_convergence_checked", False)
            ),
            "kpoint_status_warning": metadata.get(
                "kpoint_status_warning",
                (
                    "Historical explicit-Gamma reference; k-point convergence has not been checked"
                    if inferred_kpoint_mesh == "explicit_gamma"
                    else task.get(
                        "gamma_reference_scope",
                        "Gamma-only reference; k-point convergence has not been checked",
                    )
                ),
            ),
        }
    )
    result["fermi_reference_warning"] = "Raw CP2K internal potential reference; not a vacuum-aligned work function."
    output_text = output.read_text(encoding="utf-8", errors="replace") if output.is_file() else ""
    cp2k_warnings = []
    if "Projected density of states" in output_text and "not implemented for k points" in output_text:
        cp2k_warnings.append("CP2K 2024.3: projected DOS/LDOS is not implemented when KPOINTS is active")
    result["cp2k_warnings"] = cp2k_warnings

    pdos_files = sorted(run_dir.glob("*.pdos"))
    pdos_inventory = []
    ldos_by_index: dict[int, list[list[float]]] = {}
    for path in pdos_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        rows = _numeric_rows(path)
        fermi_match = PDOS_FERMI_RE.search(text)
        ldos_match = LDOS_FILE_RE.search(path.name)
        kind_match = KIND_PDOS_FILE_RE.search(path.name)
        output_kind = "LDOS" if ldos_match else ("PDOS" if kind_match else "UNKNOWN")
        output_index = int((ldos_match or kind_match).group(1)) if (ldos_match or kind_match) else None
        group_label = None
        if output_kind == "LDOS" and output_index is not None:
            ldos_by_index[output_index] = rows
            if 1 <= output_index <= len(expected_ldos_groups):
                group_label = expected_ldos_groups[output_index - 1].get("label")
        pdos_inventory.append(
            {
                "file": _relative(path, run_dir),
                "output_kind": output_kind,
                "output_index": output_index,
                "group_label": group_label,
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
    raw_total_dos_near_fermi_per_ev = None
    for path in dos_candidates:
        rows = _numeric_rows(path)
        dos_inventory.append({"file": _relative(path, run_dir), "numeric_rows": len(rows)})
        # CP2K DOS energies and densities are printed in atomic units. Convert
        # the density to states/eV by dividing states/Ha by Ha/eV.
        if rows and result.get("fermi_energy_hartree") is not None and len(rows[0]) >= 2:
            window_ha = window_ev / (2.0 * HARTREE_TO_EV)
            near = [row[1] for row in rows if abs(row[0] - result["fermi_energy_hartree"]) <= window_ha]
            if near:
                dos_near_fermi_bin_density = float(sum(near) / len(near))
                if len(rows) > 1:
                    bin_width_ev = abs(rows[1][0] - rows[0][0]) * HARTREE_TO_EV
                    if bin_width_ev > 0:
                        # CP2K's DOS "Density" column sums to one over all
                        # histogram bins. Divide by bin width for normalized
                        # DOS per eV; do not label it as an absolute state count.
                        raw_total_dos_near_fermi_per_ev = dos_near_fermi_bin_density / bin_width_ev

    total_dos_per_area = None
    if raw_total_dos_near_fermi_per_ev is not None and substrate_area:
        total_dos_per_area = raw_total_dos_near_fermi_per_ev / float(substrate_area)

    selected_ldos_indices = [
        index
        for index, group in enumerate(expected_ldos_groups, start=1)
        if group.get("label") == "Cu2Te_film"
        or str(group.get("label", "")).endswith("_bulk")
    ]
    projected_weight = None
    projected_per_formula = None
    if (
        result.get("fermi_energy_hartree") is not None
        and selected_ldos_indices
        and all(index in ldos_by_index for index in selected_ldos_indices)
    ):
        projected_weight = sum(
            _pdos_weight_near_fermi(
                ldos_by_index[index], result["fermi_energy_hartree"], window_ev
            )
            for index in selected_ldos_indices
        )
        if formula_units:
            projected_per_formula = (
                projected_weight / window_ev / float(formula_units)
            )

    expected_ldos_present = (
        all(
            index in ldos_by_index and len(ldos_by_index[index]) > 0
            for index in range(1, len(expected_ldos_groups) + 1)
        )
        if expected_ldos_groups
        else bool(ldos_by_index and all(ldos_by_index.values()))
    )

    potential_cubes = sorted(run_dir.glob("*hartree*potential*.cube"))
    density_cubes = sorted(run_dir.glob("*density*.cube"))
    result.update(
        {
            "pdos_files": pdos_inventory,
            "dos_files": dos_inventory,
            "raw_total_dos_near_fermi_mean_bin_density": dos_near_fermi_bin_density,
            "raw_total_dos_near_fermi_per_ev": raw_total_dos_near_fermi_per_ev,
            "total_dos_near_fermi_per_ev_per_substrate_angstrom2": total_dos_per_area,
            "cu2te_projected_weight_near_fermi_raw": projected_weight,
            "cu2te_projected_dos_near_fermi_per_ev_per_formula_unit": projected_per_formula,
            "cu2te_projected_dos_method": "sum of Cu2Te LDOS projection weights in a rectangular EF window, divided by window width and Cu2Te formula units",
            # Compatibility aliases retained for older result readers.
            "dos_near_fermi_mean_bin_density": dos_near_fermi_bin_density,
            "normalized_dos_near_fermi_per_ev": raw_total_dos_near_fermi_per_ev,
            "hartree_potential_cube_files": [_relative(path, run_dir) for path in potential_cubes],
            "electron_density_cube_files": [_relative(path, run_dir) for path in density_cubes],
            "ldos_output_present": expected_ldos_present,
            "pdos_output_present": bool(
                pdos_inventory
                and all(item["numeric_rows"] > 0 for item in pdos_inventory)
                and expected_ldos_present
            ),
            "dos_output_present": bool(dos_inventory and all(item["numeric_rows"] > 0 for item in dos_inventory)),
            "potential_output_present": bool(potential_cubes),
            "density_output_present": bool(density_cubes),
        }
    )
    result["electronic_outputs_complete"] = bool(
        result["energy_valid"]
        and result["fermi_energy_hartree"] is not None
        and result["pdos_output_present"]
        and result["dos_output_present"]
        and result["potential_output_present"]
        and result["density_output_present"]
    )
    result["research_output_complete"] = result["electronic_outputs_complete"]
    if result["energy_valid"] and not result["electronic_outputs_complete"]:
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
        result["warning_or_error"] = "Energy is valid, but electronic outputs are missing: " + ", ".join(missing)
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
    return 0 if result["electronic_outputs_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
