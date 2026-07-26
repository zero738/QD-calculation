from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config
from parse_cp2k_output import HARTREE_TO_EV, parse_output
from planar_average_cube import analyze_vacuum_plateaus


PDOS_FERMI_RE = re.compile(
    r"(?:Fermi\s+energy:|E\(Fermi\)\s*=)\s*([-+0-9.Ee]+)", re.I
)
LDOS_FILE_RE = re.compile(r"(?:-list|-LDOS-)(\d+)(?:-\d+)?\.pdos$", re.I)
KIND_PDOS_FILE_RE = re.compile(r"(?:-k|-PDOS-)(\d+)(?:-\d+)?\.pdos$", re.I)


def _last_mo_smearing_persistent(warning_count: int, scf_steps: int | None) -> bool:
    """Flag occupation truncation only when it persists through most SCF steps."""
    if not scf_steps or warning_count < 3:
        return False
    return int(warning_count) >= math.ceil(0.8 * int(scf_steps))


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
    manifest_path = ROOT / "research_lite" / "manifest.json"
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, list):
        return {}
    canonical = "cu2te_bulk" if calculation_id == "cu2te_bulk_k222" else calculation_id
    return next(
        (task for task in manifest if task.get("calculation_id") == canonical),
        {},
    )


def gaussian_spectrum(
    energies_ev: np.ndarray,
    grid_ev: np.ndarray,
    fwhm_ev: float,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Return a Gaussian-broadened spectrum whose integral is sum(weights)."""
    energies = np.asarray(energies_ev, dtype=float)
    grid = np.asarray(grid_ev, dtype=float)
    if weights is None:
        weights_array = np.ones(energies.size, dtype=float)
    else:
        weights_array = np.asarray(weights, dtype=float)
    if energies.ndim != 1 or weights_array.shape != energies.shape:
        raise ValueError("energies and weights must be one-dimensional and aligned")
    sigma = float(fwhm_ev) / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    if sigma <= 0:
        raise ValueError("Gaussian FWHM must be positive")
    normalization = 1.0 / (sigma * math.sqrt(2.0 * math.pi))
    spectrum = np.zeros(grid.shape, dtype=float)
    for start in range(0, energies.size, 256):
        stop = min(start + 256, energies.size)
        delta = grid[:, None] - energies[None, start:stop]
        kernels = normalization * np.exp(-0.5 * (delta / sigma) ** 2)
        spectrum += kernels @ weights_array[start:stop]
    return spectrum


def _integral(y: np.ndarray, x: np.ndarray) -> float:
    return float(np.trapezoid(y, x))


def _window_average(
    spectrum: np.ndarray,
    grid_ev: np.ndarray,
    window_ev: float,
) -> float:
    half = float(window_ev) / 2.0
    mask = (grid_ev >= -half) & (grid_ev <= half)
    if np.count_nonzero(mask) < 2:
        raise ValueError("spectral grid has too few points in the EF window")
    return _integral(spectrum[mask], grid_ev[mask]) / float(window_ev)


def _pdos_records(
    run_dir: Path,
    expected_groups: list[dict],
) -> tuple[list[dict], dict[int, dict], list[dict]]:
    inventory: list[dict] = []
    ldos_by_index: dict[int, dict] = {}
    kind_records: list[dict] = []
    for path in sorted(run_dir.glob("*.pdos")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rows = _numeric_rows(path)
        fermi_match = PDOS_FERMI_RE.search(text)
        ldos_match = LDOS_FILE_RE.search(path.name)
        kind_match = KIND_PDOS_FILE_RE.search(path.name)
        output_kind = "LDOS" if ldos_match else ("PDOS" if kind_match else "UNKNOWN")
        match = ldos_match or kind_match
        output_index = int(match.group(1)) if match else None
        group_label = None
        if output_kind == "LDOS" and output_index is not None:
            if 1 <= output_index <= len(expected_groups):
                group_label = expected_groups[output_index - 1].get("label")
        record = {
            "path": path,
            "file": _relative(path, run_dir),
            "output_kind": output_kind,
            "output_index": output_index,
            "group_label": group_label,
            "rows": rows,
            "numeric_rows": len(rows),
            "fermi_energy_hartree_in_header": (
                float(fermi_match.group(1)) if fermi_match else None
            ),
        }
        inventory.append(record)
        if output_kind == "LDOS" and output_index is not None:
            ldos_by_index[output_index] = record
        elif output_kind == "PDOS":
            kind_records.append(record)
    return inventory, ldos_by_index, kind_records


def _validate_pdos_consistency(
    inventory: list[dict],
    kind_records: list[dict],
    expected_groups: list[dict],
    ldos_by_index: dict[int, dict],
    eigen_tolerance: float,
    fermi_tolerance: float,
) -> tuple[bool, list[str], dict | None]:
    errors: list[str] = []
    if not kind_records:
        errors.append("no kind-PDOS file is present; a unique MO list cannot be built")
        return False, errors, None
    reference = kind_records[0]
    reference_rows = reference["rows"]
    if not reference_rows or any(len(row) < 4 for row in reference_rows):
        errors.append(f"{reference['file']} has no complete MO rows")
        return False, errors, None
    reference_ids = np.asarray([int(round(row[0])) for row in reference_rows], dtype=int)
    reference_eigenvalues = np.asarray([row[1] for row in reference_rows], dtype=float)
    reference_fermi = reference["fermi_energy_hartree_in_header"]
    if reference_fermi is None:
        errors.append(f"{reference['file']} has no Fermi energy in its header")
    for index in range(1, len(expected_groups) + 1):
        if index not in ldos_by_index:
            errors.append(
                f"missing LDOS file for generated group {index} "
                f"({expected_groups[index - 1].get('label')})"
            )
    for record in inventory:
        if record["output_kind"] not in {"PDOS", "LDOS"}:
            errors.append(f"unclassified projected-output file: {record['file']}")
            continue
        rows = record["rows"]
        if len(rows) != len(reference_rows):
            errors.append(
                f"{record['file']} has {len(rows)} MO rows; expected {len(reference_rows)}"
            )
            continue
        if any(len(row) < 4 for row in rows):
            errors.append(f"{record['file']} contains an incomplete projected MO row")
            continue
        ids = np.asarray([int(round(row[0])) for row in rows], dtype=int)
        eigenvalues = np.asarray([row[1] for row in rows], dtype=float)
        if not np.array_equal(ids, reference_ids):
            errors.append(f"{record['file']} MO identifiers differ from kind-PDOS reference")
        if not np.allclose(
            eigenvalues,
            reference_eigenvalues,
            rtol=0.0,
            atol=float(eigen_tolerance),
        ):
            errors.append(f"{record['file']} eigenvalues differ from kind-PDOS reference")
        fermi = record["fermi_energy_hartree_in_header"]
        if fermi is None:
            errors.append(f"{record['file']} has no Fermi energy in its header")
        elif reference_fermi is not None and not math.isclose(
            float(fermi),
            float(reference_fermi),
            rel_tol=0.0,
            abs_tol=float(fermi_tolerance),
        ):
            errors.append(f"{record['file']} Fermi energy differs from kind-PDOS reference")
    reference_data = {
        "mo_ids": reference_ids,
        "eigenvalues_hartree": reference_eigenvalues,
        "fermi_energy_hartree": reference_fermi,
    }
    return not errors, errors, reference_data


def _projection_weights(record: dict) -> np.ndarray:
    return np.asarray([sum(row[3:]) for row in record["rows"]], dtype=float)


def _write_spectrum_csv(
    path: Path,
    grid: np.ndarray,
    total: np.ndarray,
    area: float | None,
    projection_curves: dict[str, np.ndarray | None],
    formula_units: int | None,
    group_counts: dict[str, int],
) -> None:
    columns = [
        "energy_minus_fermi_ev",
        "KS_orbital_DOS_per_ev",
        "KS_orbital_DOS_per_ev_per_substrate_angstrom2",
        "Cu2Te_projected_spectral_weight_per_ev",
        "Cu2Te_projected_spectral_weight_per_ev_per_formula_unit",
        "CdTe_interface_projected_spectral_weight_per_ev_per_atom",
        "Cu2Te_interface_projected_spectral_weight_per_ev_per_atom",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for index, energy in enumerate(grid):
            film_value = (
                projection_curves["Cu2Te_film"][index]
                if projection_curves.get("Cu2Te_film") is not None
                else None
            )
            cdte_interface = (
                projection_curves["CdTe_interface_top_Te"][index]
                if projection_curves.get("CdTe_interface_top_Te") is not None
                else None
            )
            cu_interface = (
                projection_curves["Cu2Te_interface_bottom_Cu"][index]
                if projection_curves.get("Cu2Te_interface_bottom_Cu") is not None
                else None
            )
            writer.writerow(
                [
                    f"{energy:.8f}",
                    f"{total[index]:.12e}",
                    "" if not area else f"{total[index] / area:.12e}",
                    "" if film_value is None else f"{film_value:.12e}",
                    (
                        ""
                        if film_value is None or not formula_units
                        else f"{film_value / formula_units:.12e}"
                    ),
                    (
                        ""
                        if cdte_interface is None
                        else f"{cdte_interface / group_counts['CdTe_interface_top_Te']:.12e}"
                    ),
                    (
                        ""
                        if cu_interface is None
                        else f"{cu_interface / group_counts['Cu2Te_interface_bottom_Cu']:.12e}"
                    ),
                ]
            )


def parse_research_run(run_dir: Path) -> dict:
    output = run_dir / "output.out"
    input_path = run_dir / "input.executed.inp"
    metadata_path = run_dir / "run_metadata.json"
    metadata = _read_json(metadata_path)
    result = parse_output(output, input_path, metadata_path)
    last_mo_warning_count = sum(
        count
        for message, count in result.get("warning_message_counts", {}).items()
        if "Fermi-Dirac smearing includes the last MO" in message
    )
    last_mo_warning_persistent = _last_mo_smearing_persistent(
        last_mo_warning_count,
        result.get("scf_steps")
        or result.get("last_scf_iteration_index")
        or result.get("scf_iterations_observed"),
    )
    result.update(
        {
            "last_MO_smearing_warning_count": last_mo_warning_count,
            "last_MO_smearing_warning_persistent": last_mo_warning_persistent,
            "last_MO_smearing_warning_interpretation": (
                "Persistent occupation of the highest available MO makes the "
                "requested electronic spectrum incomplete; a transient early-SCF "
                "warning remains reviewable but does not invalidate a later clean "
                "converged spectrum."
            ),
        }
    )
    result["calculation_id"] = metadata.get("calculation_id")
    result["calculation_profile"] = "research_lite"
    task = _manifest_task(metadata.get("calculation_id"))
    config = load_config()["cp2k"]["profiles"]["research_lite"]
    expected_electronic_outputs = bool(
        metadata.get("expected_electronic_outputs", True)
    )
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
            task.get("dos_near_fermi_window_ev", config["dos_near_fermi_window_ev"]),
        )
    )
    substrate_area = metadata.get(
        "substrate_area_angstrom2", task.get("substrate_area_angstrom2")
    )
    formula_units = metadata.get(
        "cu2te_formula_units", task.get("cu2te_formula_units")
    )
    expected_groups = task.get("ldos_groups", [])
    group_counts = {
        group["label"]: len(group.get("indices_1based", []))
        for group in expected_groups
    }
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
                task.get(
                    "gamma_reference_scope",
                    "Gamma-only reference; k-point convergence has not been checked",
                ),
            ),
            "fermi_reference_warning": (
                "Raw CP2K Fermi energy uses the calculation's internal reference. "
                "Only E-EF spectral shapes or vacuum-aligned slab proxies are compared."
            ),
            "expected_electronic_outputs": expected_electronic_outputs,
            "ldos_group_atom_counts": group_counts,
        }
    )

    inventory, ldos_by_index, kind_records = _pdos_records(run_dir, expected_groups)
    consistency_valid, consistency_errors, reference = _validate_pdos_consistency(
        inventory,
        kind_records,
        expected_groups,
        ldos_by_index,
        float(config["pdos_eigenvalue_tolerance_hartree"]),
        float(config["pdos_fermi_tolerance_hartree"]),
    )
    inventory_public = [
        {key: value for key, value in record.items() if key not in {"path", "rows"}}
        for record in inventory
    ]
    expected_ldos_present = bool(expected_groups) and all(
        index in ldos_by_index and ldos_by_index[index]["numeric_rows"] > 0
        for index in range(1, len(expected_groups) + 1)
    )
    result.update(
        {
            "pdos_files": inventory_public,
            "pdos_consistency_valid": consistency_valid,
            "pdos_consistency_errors": consistency_errors,
            "ldos_output_present": expected_ldos_present,
            "pdos_output_present": bool(
                inventory
                and kind_records
                and expected_ldos_present
                and consistency_valid
            ),
            "unique_MO_count": (
                int(len(reference["mo_ids"])) if reference is not None else None
            ),
        }
    )

    dos_inventory: list[dict] = []
    normalized_histogram_near_ef = None
    for path in sorted({*run_dir.glob("*.dos"), *run_dir.glob("*dos*.dat")}):
        rows = _numeric_rows(path)
        dos_inventory.append(
            {"file": _relative(path, run_dir), "numeric_rows": len(rows)}
        )
        if (
            rows
            and result.get("fermi_energy_hartree") is not None
            and len(rows[0]) >= 2
            and len(rows) > 1
        ):
            half_window_ha = window_ev / (2.0 * HARTREE_TO_EV)
            near = [
                row[1]
                for row in rows
                if abs(row[0] - result["fermi_energy_hartree"]) <= half_window_ha
            ]
            bin_width_ev = abs(rows[1][0] - rows[0][0]) * HARTREE_TO_EV
            if near and bin_width_ev > 0:
                normalized_histogram_near_ef = float(
                    sum(near) / len(near) / bin_width_ev
                )
    result.update(
        {
            "dos_files": dos_inventory,
            "dos_output_present": bool(
                dos_inventory and all(item["numeric_rows"] > 0 for item in dos_inventory)
            ),
            "cp2k_normalized_histogram_fraction_near_EF_per_ev": (
                normalized_histogram_near_ef
            ),
            "cp2k_normalized_histogram_definition": (
                "CP2K 2024.3 DOS Density is normalized over all histogram bins; "
                "this field is a spectral-shape fraction per eV, not total KS-orbital DOS."
            ),
        }
    )

    result.update(
        {
            "KS_orbital_count_near_EF_in_window": None,
            "KS_orbital_density_near_EF_per_ev": None,
            "KS_orbital_density_near_EF_per_ev_per_substrate_area": None,
            "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit": None,
            "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom": None,
            "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom": None,
            "spectral_integral_KS_orbitals": None,
            "spectral_integral_expected_KS_orbitals": None,
            "spectral_integral_valid": False,
            "gaussian_broadening_fwhm_ev": float(
                config["gaussian_broadening_fwhm_ev"]
            ),
            "spectral_energy_reference": "E_minus_EF",
            "spectral_proxy_file": None,
        }
    )
    if consistency_valid and reference is not None:
        fermi_ha = float(reference["fermi_energy_hartree"])
        energies_ev = (
            np.asarray(reference["eigenvalues_hartree"], dtype=float) - fermi_ha
        ) * HARTREE_TO_EV
        grid = np.arange(
            float(config["spectral_grid_min_ev"]),
            float(config["spectral_grid_max_ev"])
            + 0.5 * float(config["spectral_grid_step_ev"]),
            float(config["spectral_grid_step_ev"]),
        )
        total_curve = gaussian_spectrum(
            energies_ev,
            grid,
            float(config["gaussian_broadening_fwhm_ev"]),
        )
        total_integral = _integral(total_curve, grid)
        expected_integral = float(energies_ev.size)
        integral_valid = math.isclose(
            total_integral,
            expected_integral,
            rel_tol=float(config["spectral_integral_relative_tolerance"]),
            abs_tol=1.0e-6,
        )
        half_window = window_ev / 2.0
        direct_count = int(np.count_nonzero(np.abs(energies_ev) <= half_window))
        ks_density = _window_average(total_curve, grid, window_ev)
        label_to_record = {
            expected_groups[index - 1]["label"]: record
            for index, record in ldos_by_index.items()
            if 1 <= index <= len(expected_groups)
        }
        curves: dict[str, np.ndarray | None] = {
            "Cu2Te_film": None,
            "CdTe_interface_top_Te": None,
            "Cu2Te_interface_bottom_Cu": None,
        }
        if task.get("source_kind") == "bulk":
            bulk_records = [
                label_to_record[label]
                for label in ("Cu_bulk", "Te_bulk")
                if label in label_to_record
            ]
            if len(bulk_records) == 2:
                weights = sum(
                    (_projection_weights(record) for record in bulk_records),
                    start=np.zeros(energies_ev.size, dtype=float),
                )
                curves["Cu2Te_film"] = gaussian_spectrum(
                    energies_ev,
                    grid,
                    float(config["gaussian_broadening_fwhm_ev"]),
                    weights,
                )
        elif "Cu2Te_film" in label_to_record:
            curves["Cu2Te_film"] = gaussian_spectrum(
                energies_ev,
                grid,
                float(config["gaussian_broadening_fwhm_ev"]),
                _projection_weights(label_to_record["Cu2Te_film"]),
            )
        for label in (
            "CdTe_interface_top_Te",
            "Cu2Te_interface_bottom_Cu",
        ):
            if label in label_to_record:
                curves[label] = gaussian_spectrum(
                    energies_ev,
                    grid,
                    float(config["gaussian_broadening_fwhm_ev"]),
                    _projection_weights(label_to_record[label]),
                )
        spectrum_path = run_dir / "spectral_proxies.csv"
        _write_spectrum_csv(
            spectrum_path,
            grid,
            total_curve,
            float(substrate_area) if substrate_area else None,
            curves,
            int(formula_units) if formula_units else None,
            group_counts,
        )
        result.update(
            {
                "KS_orbital_count_near_EF_in_window": direct_count,
                "KS_orbital_density_near_EF_per_ev": ks_density,
                "KS_orbital_density_near_EF_per_ev_per_substrate_area": (
                    ks_density / float(substrate_area) if substrate_area else None
                ),
                "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit": (
                    _window_average(curves["Cu2Te_film"], grid, window_ev)
                    / float(formula_units)
                    if curves["Cu2Te_film"] is not None and formula_units
                    else None
                ),
                "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom": (
                    _window_average(
                        curves["CdTe_interface_top_Te"], grid, window_ev
                    )
                    / group_counts["CdTe_interface_top_Te"]
                    if curves["CdTe_interface_top_Te"] is not None
                    else None
                ),
                "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom": (
                    _window_average(
                        curves["Cu2Te_interface_bottom_Cu"], grid, window_ev
                    )
                    / group_counts["Cu2Te_interface_bottom_Cu"]
                    if curves["Cu2Te_interface_bottom_Cu"] is not None
                    else None
                ),
                "spectral_integral_KS_orbitals": total_integral,
                "spectral_integral_expected_KS_orbitals": int(expected_integral),
                "spectral_integral_valid": integral_valid,
                "spectral_proxy_file": spectrum_path.name,
                "KS_orbital_density_method": (
                    "externally Gaussian-broadened unique kind-PDOS MO list; "
                    "window-average over E-EF and no assumed spin degeneracy"
                ),
                "projected_spectral_weight_method": (
                    "atomic-orbital projected spectral-weight proxy using the same "
                    "0.10 eV FWHM Gaussian and E-EF grid; not an exact total state count"
                ),
            }
        )

    potential_cubes = sorted(run_dir.glob("*hartree*potential*.cube"))
    density_cubes = sorted(run_dir.glob("*density*.cube"))
    result.update(
        {
            "hartree_potential_cube_files": [
                _relative(path, run_dir) for path in potential_cubes
            ],
            "electron_density_cube_files": [
                _relative(path, run_dir) for path in density_cubes
            ],
            "potential_output_present": bool(potential_cubes),
            "density_output_present": bool(density_cubes),
        }
    )
    vacuum = analyze_vacuum_plateaus(run_dir, result.get("fermi_energy_ev"))
    result.update(
        {
            "vacuum_plateau_analysis": vacuum,
            "vacuum_level_top_ev": vacuum.get("vacuum_level_top_ev"),
            "vacuum_level_bottom_ev": vacuum.get("vacuum_level_bottom_ev"),
            "work_function_top_ev": vacuum.get("work_function_top_ev"),
            "work_function_bottom_ev": vacuum.get("work_function_bottom_ev"),
        }
    )
    result["electronic_outputs_complete"] = bool(
        expected_electronic_outputs
        and result["energy_valid"]
        and result["fermi_energy_hartree"] is not None
        and result["pdos_output_present"]
        and result["dos_output_present"]
        and result["potential_output_present"]
        and result["density_output_present"]
        and result["pdos_consistency_valid"]
        and result["spectral_integral_valid"]
        and not result["last_MO_smearing_warning_persistent"]
    )
    result["research_output_complete"] = result["electronic_outputs_complete"]
    if result["energy_valid"] and expected_electronic_outputs and not result["electronic_outputs_complete"]:
        missing = [
            label
            for label, present in (
                ("Fermi energy", result["fermi_energy_hartree"] is not None),
                ("consistent PDOS/LDOS", result["pdos_output_present"]),
                ("CP2K normalized DOS histogram", result["dos_output_present"]),
                ("Hartree potential cube", result["potential_output_present"]),
                ("electron-density cube", result["density_output_present"]),
                ("Gaussian spectral integral check", result["spectral_integral_valid"]),
                (
                    "untruncated final Fermi-Dirac occupation",
                    not result["last_MO_smearing_warning_persistent"],
                ),
            )
            if not present
        ]
        result["warning_or_error"] = (
            "Energy is valid, but electronic outputs are incomplete: "
            + ", ".join(missing)
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse strict CP2K and research_lite spectral evidence"
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = parse_research_run(args.run_dir)
    destination = args.json or args.run_dir / "output.parsed.json"
    destination.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (
        result["energy_valid"]
        and (
            result["electronic_outputs_complete"]
            or not result["expected_electronic_outputs"]
        )
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
