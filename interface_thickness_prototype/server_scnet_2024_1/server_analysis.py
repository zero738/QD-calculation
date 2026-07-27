#!/usr/bin/env python3
"""Standard-library analysis shared by SCNet runners and result collection.

The module intentionally has no NumPy, ASE, or matplotlib dependency.  It is
strict about missing evidence: an absent or inconsistent value remains None.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

HARTREE_TO_EV = 27.211386245988
ENERGY_RE = re.compile(r"ENERGY\|.*?Total FORCE_EVAL.*?energy.*?:\s*([-+0-9.Ee]+)", re.I)
SCF_CONVERGED_RE = re.compile(r"SCF\s+run\s+converged\s+in\s+(\d+)\s+steps", re.I)
VERSION_RE = re.compile(r"CP2K\|\s*version string:\s*(.+)", re.I)
FERMI_RE = re.compile(r"(?:Fermi\s+energy:|E\(Fermi\)\s*=)\s*([-+0-9.Ee]+)", re.I)
SCF_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(?:NoMix|Broy\.)/Diag\.\s+\S+\s+\S+\s+([-+0-9.Ee]+)",
    re.I | re.M,
)
LAST_MO_TEXT = "Fermi-Dirac smearing includes the last MO"
HARD_FAILURE_PATTERNS = {
    "missing_basis_or_potential": re.compile(
        r"(basis set|potential).*(not found|missing|unknown)|cannot find.*(basis|potential)", re.I
    ),
    "input_or_cp2k_abort": re.compile(r"CP2K\s+ABORT|ABORT\s+in|input.*error|unknown keyword", re.I),
    "mpi_or_dynamic_library": re.compile(
        r"error while loading shared libraries|symbol lookup error|MPI_ABORT|PMIX ERROR", re.I
    ),
    "filesystem": re.compile(r"permission denied|no space left|cannot create|read-only file system", re.I),
}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def input_value(text: str, keyword: str) -> str | None:
    match = re.search(
        rf"(?mi)^\s*{re.escape(keyword)}\s+(?:\[K\]\s+)?([^#\s]+)", text
    )
    return match.group(1) if match else None


def scf_signature(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return {
        "EPS_SCF": input_value(text, "EPS_SCF"),
        "MAX_SCF": input_value(text, "MAX_SCF"),
        "ADDED_MOS": input_value(text, "ADDED_MOS"),
        "NLUMO": input_value(text, "NLUMO"),
        "ALPHA": input_value(text, "ALPHA"),
        "NBROYDEN": input_value(text, "NBROYDEN"),
        "ELECTRONIC_TEMPERATURE": input_value(text, "ELECTRONIC_TEMPERATURE"),
        "DIAGONALIZATION": "STANDARD" if re.search(
            r"(?mi)^\s*ALGORITHM\s+STANDARD\s*$", text
        ) else None,
        "SMEARING": "FERMI_DIRAC" if "METHOD FERMI_DIRAC" in text.upper() else None,
    }


def patch_keyword(text: str, keyword: str, value: str) -> str:
    pattern = re.compile(rf"(?mi)^(\s*{re.escape(keyword)}\s+)(?:\[K\]\s+)?([^#\s]+)")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one {keyword}; found {len(matches)}")
    return pattern.sub(lambda match: match.group(1) + value, text, count=1)


def build_retry_input(base_text: str, variant: dict, restart_wfn_name: str | None) -> str:
    text = base_text
    for keyword, value in (
        ("ADDED_MOS", variant["added_mos"]),
        ("NLUMO", variant["pdos_nlumo"]),
        ("ALPHA", variant["mixing_alpha"]),
        ("NBROYDEN", variant["nbroyden"]),
    ):
        text = patch_keyword(text, keyword, str(value))
    if input_value(text, "EPS_SCF") not in {"1e-06", "1.0e-6", "1E-06"}:
        raise ValueError("controlled retry must retain EPS_SCF=1e-6")
    guess = "RESTART" if restart_wfn_name else "ATOMIC"
    text = re.sub(r"(?mi)^\s*SCF_GUESS\s+\S+\s*$", "      SCF_GUESS " + guess, text)
    if not re.search(r"(?mi)^\s*SCF_GUESS\s+", text):
        marker = re.search(r"(?mi)^\s*&SCF\s*$", text)
        if not marker:
            raise ValueError("missing SCF section")
        text = text[: marker.end()] + "\n      SCF_GUESS " + guess + text[marker.end() :]
    text = re.sub(r"(?mi)^\s*WFN_RESTART_FILE_NAME\s+\S+\s*\n?", "", text)
    if restart_wfn_name:
        dft = re.search(r"(?mi)^\s*&DFT\s*$", text)
        if not dft:
            raise ValueError("missing DFT section")
        text = text[: dft.end()] + f"\n    WFN_RESTART_FILE_NAME {restart_wfn_name}" + text[dft.end() :]
    return text.rstrip() + "\n"


def parse_extxyz(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        raise ValueError(f"invalid extxyz: {path}")
    count = int(lines[0].strip())
    properties_match = re.search(r'Properties="?([^"\s]+)', lines[1])
    if not properties_match:
        raise ValueError(f"extxyz Properties declaration is missing: {path}")
    tokens = properties_match.group(1).split(":")
    properties = []
    for index in range(0, len(tokens), 3):
        properties.append((tokens[index], int(tokens[index + 2])))
    atoms = []
    for index, line in enumerate(lines[2 : 2 + count], start=1):
        fields = line.split()
        values = {}
        cursor = 0
        for name, width in properties:
            value = fields[cursor : cursor + width]
            values[name] = value[0] if width == 1 else value
            cursor += width
        if not all(name in values for name in ("species", "pos", "component", "region", "fixed")):
            raise ValueError(f"missing component/region/fixed properties at atom {index}")
        position = values["pos"]
        atoms.append(
            {
                "index": index,
                "element": values["species"],
                "x": float(position[0]),
                "y": float(position[1]),
                "z": float(position[2]),
                "component": values["component"],
                "region": values["region"],
                "fixed": str(values["fixed"]).lower() in {"t", "true", "1"},
            }
        )
    if len(atoms) != count:
        raise ValueError(f"extxyz atom count mismatch: expected {count}, read {len(atoms)}")
    return atoms


def cluster_layers(atoms: list[dict], tolerance: float = 0.20) -> list[dict]:
    ordered = sorted(atoms, key=lambda atom: atom["z"])
    groups: list[list[dict]] = []
    for atom in ordered:
        if not groups or abs(atom["z"] - statistics.mean(a["z"] for a in groups[-1])) > tolerance:
            groups.append([atom])
        else:
            groups[-1].append(atom)
    return [
        {
            "z": statistics.mean(atom["z"] for atom in group),
            "count": len(group),
            "elements": dict(sorted((element, sum(a["element"] == element for a in group)) for element in {a["element"] for a in group})),
            "regions": sorted({atom["region"] for atom in group}),
        }
        for group in groups
    ]


def common_cdte_reference(package_root: Path, tolerance: float = 0.20) -> dict:
    model_layers = {}
    for model in ("B0", "C50", "H1", "H2"):
        atoms = [
            atom for atom in parse_extxyz(package_root / "inputs" / model / "structure.extxyz")
            if atom["component"] == "cdte_substrate" and "interface" not in atom["region"]
        ]
        layers = cluster_layers(atoms, tolerance)
        if len(layers) < 4:
            return {"status": "unreliable_or_not_found", "reason": f"{model} has fewer than four internal CdTe layers"}
        # The lowest remaining layer is the bottom slab surface; the top
        # interface layer was already excluded by its region label.
        model_layers[model] = layers[1:]
    signatures = []
    for layer in model_layers["B0"]:
        signature = (round(layer["z"], 5), tuple(layer["elements"].items()), layer["count"])
        if all(
            any(
                abs(other["z"] - layer["z"]) <= tolerance
                and other["elements"] == layer["elements"]
                and other["count"] == layer["count"]
                for other in model_layers[model]
            )
            for model in ("C50", "H1", "H2")
        ):
            signatures.append(layer)
    if len(signatures) < 3:
        return {"status": "unreliable_or_not_found", "reason": "fewer than three common internal CdTe layers"}
    selected = signatures
    spacings = [selected[i + 1]["z"] - selected[i]["z"] for i in range(len(selected) - 1)]
    return {
        "status": "candidate",
        "reference_z_start": selected[0]["z"],
        "reference_z_end": selected[-1]["z"],
        "selected_layers": selected,
        "atom_count": sum(layer["count"] for layer in selected),
        "macroscopic_window_angstrom": 2.0 * statistics.median(spacings) if spacings else None,
        "selection_method": "common component/region/element/z clustered CdTe internal layers; no hard-coded atom indices",
    }


def parse_scf_residuals(text: str) -> list[tuple[int, float]]:
    return [(int(match.group(1)), float(match.group(2))) for match in SCF_LINE_RE.finditer(text)]


def last_mo_warning_state(text: str) -> dict:
    iterations = list(SCF_LINE_RE.finditer(text))
    warning_positions = [match.start() for match in re.finditer(re.escape(LAST_MO_TEXT), text, re.I)]
    count = len(warning_positions)
    n_iter = len(iterations)
    fraction = count / n_iter if n_iter else 0.0
    late_boundary = iterations[max(0, math.ceil(0.8 * n_iter) - 1)].start() if iterations else len(text)
    late = any(position >= late_boundary for position in warning_positions)
    return {
        "count": count,
        "scf_iterations": n_iter,
        "fraction": fraction,
        "present_in_last_20_percent": late,
        "persistent": bool(n_iter and (fraction >= 0.8 or late)),
    }


def residuals_oscillate(residuals: list[tuple[int, float]], eps_scf: float = 1.0e-6) -> bool:
    values = [value for _, value in residuals[-12:]]
    if len(values) < 8 or values[-1] <= eps_scf:
        return False
    increases = sum(current > previous * 1.05 for previous, current in zip(values, values[1:]))
    sign_changes = 0
    deltas = [current - previous for previous, current in zip(values, values[1:])]
    for first, second in zip(deltas, deltas[1:]):
        if first * second < 0:
            sign_changes += 1
    return min(values) > eps_scf * 5 and increases >= 3 and sign_changes >= 3


def classify_attempt_failure(output_text: str, input_hash_valid: bool = True) -> dict:
    if not input_hash_valid:
        return {"classification": "hard_configuration_failure", "reason": "input hash mismatch"}
    for name, pattern in HARD_FAILURE_PATTERNS.items():
        if pattern.search(output_text):
            return {"classification": "hard_configuration_failure", "reason": name}
    warning = last_mo_warning_state(output_text)
    if warning["persistent"]:
        return {"classification": "persistent_last_mo_warning", "reason": warning}
    residuals = parse_scf_residuals(output_text)
    if residuals_oscillate(residuals):
        return {
            "classification": "oscillating_scf_residual",
            "reason": {"last_residuals": residuals[-12:]},
        }
    return {"classification": "unclassified_failure_no_retry", "reason": "no permitted retry trigger"}


def numeric_pdos_rows(path: Path) -> tuple[list[list[float]], float | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    fermi_match = FERMI_RE.search(text)
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "@")):
            continue
        try:
            values = [float(value) for value in line.split()]
        except ValueError:
            continue
        if len(values) >= 3:
            rows.append(values)
    return rows, float(fermi_match.group(1)) if fermi_match else None


def normalized_cp2k_histogram(run_dir: Path, fermi_ha: float | None, half_window_ev: float = 0.10) -> dict:
    files = sorted({*run_dir.glob("*.dos"), *run_dir.glob("*dos*.dat")})
    value = None
    inventory = []
    for path in files:
        numeric = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip() or raw.lstrip().startswith(("#", "@")):
                continue
            try:
                row = [float(item) for item in raw.split()]
            except ValueError:
                continue
            if len(row) >= 2:
                numeric.append(row)
        inventory.append({"file": path.name, "numeric_rows": len(numeric)})
        if fermi_ha is not None and len(numeric) > 1:
            near = [row[1] for row in numeric if abs((row[0] - fermi_ha) * HARTREE_TO_EV) <= half_window_ev]
            bin_width_ev = abs(numeric[1][0] - numeric[0][0]) * HARTREE_TO_EV
            if near and bin_width_ev > 0:
                value = sum(near) / len(near) / bin_width_ev
    return {
        "dos_files": inventory, "dos_present": bool(inventory and all(item["numeric_rows"] for item in inventory)),
        "cp2k_normalized_histogram_fraction_near_EF_per_ev": value,
        "cp2k_normalized_histogram_definition": "normalized histogram spectral-shape fraction per eV; not raw total DOS, not KS states/eV, and never area-normalized as states/eV/angstrom2",
    }


def pdos_consistency(run_dir: Path, expected_ldos_groups: list[str], tolerance: float = 1.0e-6, expected_kind_count: int | None = None) -> dict:
    kind_files = sorted(path for path in run_dir.glob("*.pdos") if re.search(r"-k\d+-\d+\.pdos$", path.name, re.I))
    ldos_files = sorted(path for path in run_dir.glob("*.pdos") if re.search(r"-list\d+-\d+\.pdos$", path.name, re.I))
    errors = []
    if not kind_files:
        errors.append("missing kind-PDOS")
    if expected_kind_count is not None and len(kind_files) != expected_kind_count:
        errors.append(f"expected {expected_kind_count} kind-PDOS files, found {len(kind_files)}")
    if len(ldos_files) != len(expected_ldos_groups):
        errors.append(f"expected {len(expected_ldos_groups)} LDOS files, found {len(ldos_files)}")
    records = []
    for path in kind_files + ldos_files:
        rows, fermi = numeric_pdos_rows(path)
        records.append({"path": path, "rows": rows, "fermi": fermi})
    reference = records[0] if records else None
    if reference:
        ref_ids = [int(round(row[0])) for row in reference["rows"]]
        ref_eigen = [row[1] for row in reference["rows"]]
        ref_fermi = reference["fermi"]
        for record in records[1:]:
            ids = [int(round(row[0])) for row in record["rows"]]
            eigen = [row[1] for row in record["rows"]]
            if ids != ref_ids:
                errors.append(f"{record['path'].name}: MO identifiers differ")
            if len(eigen) != len(ref_eigen) or any(abs(a - b) > tolerance for a, b in zip(eigen, ref_eigen)):
                errors.append(f"{record['path'].name}: eigenvalues differ")
            if ref_fermi is None or record["fermi"] is None or abs(record["fermi"] - ref_fermi) > tolerance:
                errors.append(f"{record['path'].name}: Fermi energy differs or is missing")
    return {
        "valid": bool(reference and not errors),
        "errors": errors,
        "kind_files": [path.name for path in kind_files],
        "ldos_files": [path.name for path in ldos_files],
        "records": records,
        "reference_rows": reference["rows"] if reference else [],
        "fermi_energy_hartree": reference["fermi"] if reference else None,
    }


def gaussian_value(x: float, center: float, sigma: float) -> float:
    return math.exp(-0.5 * ((x - center) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def trapezoid(values: list[float], step: float) -> float:
    return step * (sum(values) - 0.5 * values[0] - 0.5 * values[-1]) if len(values) > 1 else 0.0


def build_spectral_proxies(
    run_dir: Path,
    consistency: dict,
    ldos_groups: list[str],
    substrate_area: float | None,
    formula_units: int,
    group_atom_counts: dict[str, int],
    fwhm_ev: float = 0.10,
) -> dict:
    if not consistency["valid"]:
        return {"spectral_integral_valid": False, "error": "; ".join(consistency["errors"])}
    rows = consistency["reference_rows"]
    fermi = float(consistency["fermi_energy_hartree"])
    energies = [(row[1] - fermi) * HARTREE_TO_EV for row in rows]
    sigma = fwhm_ev / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    step = min(0.005, sigma / 8.0)
    lower = min(energies) - 10.0 * sigma
    upper = max(energies) + 10.0 * sigma
    point_count = int(math.ceil((upper - lower) / step)) + 1
    dynamic_grid = [lower + index * step for index in range(point_count)]
    total_dynamic = [sum(gaussian_value(x, energy, sigma) for energy in energies) for x in dynamic_grid]
    integral = trapezoid(total_dynamic, step)
    expected = float(len(energies))
    integral_valid = expected > 0 and abs(integral - expected) / expected <= 5.0e-4
    compare_step = 0.01
    compare_grid = [-5.0 + index * compare_step for index in range(1001)]
    total_curve = [sum(gaussian_value(x, energy, sigma) for energy in energies) for x in compare_grid]
    projections: dict[str, list[float] | None] = {label: None for label in ldos_groups}
    ldos_records = [record for record in consistency["records"] if re.search(r"-list\d+-\d+\.pdos$", record["path"].name, re.I)]
    for label, record in zip(ldos_groups, ldos_records):
        weights = [sum(row[3:]) for row in record["rows"]]
        projections[label] = [
            sum(weight * gaussian_value(x, energy, sigma) for weight, energy in zip(weights, energies))
            for x in compare_grid
        ]
    spectral_path = run_dir / "spectral_proxies.csv"
    with spectral_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["E_minus_EF_ev", "KS_orbitals_per_ev"] + [f"{label}_projected_spectral_weight_per_ev" for label in ldos_groups]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, energy in enumerate(compare_grid):
            record = {"E_minus_EF_ev": energy, "KS_orbitals_per_ev": total_curve[index]}
            for label in ldos_groups:
                curve = projections[label]
                record[f"{label}_projected_spectral_weight_per_ev"] = curve[index] if curve is not None else ""
            writer.writerow(record)
    near = [index for index, energy in enumerate(compare_grid) if abs(energy) <= 0.1000001]
    def window_average(curve: list[float] | None) -> float | None:
        return statistics.mean(curve[index] for index in near) if curve is not None and near else None
    cu_curve = projections.get("Cu2Te_film")
    cdte_curve = projections.get("CdTe_interface_top_Te")
    cu_interface_curve = projections.get("Cu2Te_interface_bottom_Cu")
    count_near = sum(abs(energy) <= 0.1 for energy in energies)
    density_near = window_average(total_curve)
    return {
        "KS_orbital_count_near_EF_in_window": count_near,
        "KS_orbital_density_near_EF_per_ev": density_near,
        "KS_orbital_density_near_EF_per_ev_per_substrate_area": density_near / substrate_area if density_near is not None and substrate_area else None,
        "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit": window_average(cu_curve) / formula_units if cu_curve is not None and formula_units else None,
        "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom": window_average(cdte_curve) / group_atom_counts.get("CdTe_interface_top_Te", 0) if cdte_curve is not None and group_atom_counts.get("CdTe_interface_top_Te") else None,
        "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom": window_average(cu_interface_curve) / group_atom_counts.get("Cu2Te_interface_bottom_Cu", 0) if cu_interface_curve is not None and group_atom_counts.get("Cu2Te_interface_bottom_Cu") else None,
        "spectral_integral_KS_orbitals": integral,
        "spectral_integral_expected_KS_orbitals": int(expected),
        "spectral_integral_valid": integral_valid,
        "spectral_dynamic_min_ev": lower,
        "spectral_dynamic_max_ev": upper,
        "gaussian_broadening_fwhm_ev": fwhm_ev,
        "total_spectrum_unit": "KS orbitals/eV; no spin-degeneracy multiplier",
        "projected_spectrum_unit": "projected_spectral_weight/eV; not exact total state count",
        "spectral_proxy_file": spectral_path.name,
    }


def read_cube_planar(path: Path) -> tuple[list[float], list[float]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        raise ValueError("cube file is too short")
    atom_line = lines[2].split()
    atom_count = abs(int(atom_line[0]))
    origin_z = float(atom_line[3])
    axes = [lines[index].split() for index in (3, 4, 5)]
    nx, ny, nz = (abs(int(axis[0])) for axis in axes)
    dz_bohr = float(axes[2][3])
    data_start = 6 + atom_count
    values = [float(token) for line in lines[data_start:] for token in line.split()]
    expected = nx * ny * nz
    if len(values) < expected:
        raise ValueError(f"cube contains {len(values)} values; expected {expected}")
    sums = [0.0] * nz
    for index, value in enumerate(values[:expected]):
        sums[index % nz] += value
    planar = [value / (nx * ny) for value in sums]
    bohr_to_angstrom = 0.529177210903
    z = [(origin_z + index * dz_bohr) * bohr_to_angstrom for index in range(nz)]
    return z, planar


def moving_average(z: list[float], values: list[float], width: float) -> list[float]:
    result = []
    half = width / 2.0
    left = 0
    right = 0
    running = 0.0
    for center in z:
        while right < len(z) and z[right] <= center + half:
            running += values[right]
            right += 1
        while left < len(z) and z[left] < center - half:
            running -= values[left]
            left += 1
        result.append(running / max(1, right - left))
    return result


def linear_slope(z: list[float], values: list[float]) -> float | None:
    if len(z) < 2:
        return None
    mean_z = statistics.mean(z)
    mean_v = statistics.mean(values)
    denominator = sum((item - mean_z) ** 2 for item in z)
    return sum((item - mean_z) * (value - mean_v) for item, value in zip(z, values)) / denominator if denominator else 0.0


def continuous_segments(indices: list[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for index in indices:
        if not groups or index != groups[-1][-1] + 1:
            groups.append([index])
        else:
            groups[-1].append(index)
    return groups


def analyze_potential(run_dir: Path, structure_path: Path, fermi_ha: float | None, common_reference: dict, settings: dict) -> dict:
    result = {
        "relative_fermi_alignment": {"status": "unreliable_or_not_found", "EF_minus_CdTe_reference_potential_ev": None},
        "work_function": {
            "top_status": "unreliable_or_not_found", "bottom_status": "unreliable_or_not_found",
            "vacuum_level_top_ev": None, "vacuum_level_bottom_ev": None,
            "work_function_top_ev": None, "work_function_bottom_ev": None,
        },
    }
    potential_files = sorted(run_dir.glob("*hartree*potential*.cube"))
    density_files = sorted(run_dir.glob("*density*.cube"))
    if not potential_files or not density_files or not structure_path.is_file() or fermi_ha is None:
        result["reason"] = "missing Hartree cube, density cube, structure, or Fermi energy"
        return result
    z, raw_hartree = read_cube_planar(potential_files[-1])
    zd, density = read_cube_planar(density_files[-1])
    if len(z) != len(zd) or any(abs(a - b) > 1.0e-6 for a, b in zip(z, zd)):
        result["reason"] = "potential/density cube grids differ"
        return result
    potential_ev = [-value * HARTREE_TO_EV for value in raw_hartree]
    macro_width = common_reference.get("macroscopic_window_angstrom") or 1.0
    macro = moving_average(z, potential_ev, macro_width)
    rows_path = run_dir / "planar_average_potential_density.csv"
    with rows_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["z_angstrom", "cp2k_v_hartree_raw_hartree", "electrostatic_potential_ev", "macroscopic_potential_ev", "electron_density_au"])
        writer.writerows(zip(z, raw_hartree, potential_ev, macro, density))
    if common_reference.get("status") == "candidate":
        start, end = common_reference["reference_z_start"], common_reference["reference_z_end"]
        selected = [i for i, value in enumerate(z) if start <= value <= end]
        values = [macro[i] for i in selected]
        zs = [z[i] for i in selected]
        std = statistics.pstdev(values) if len(values) > 1 else None
        slope = linear_slope(zs, values)
        width = end - start
        reliable = bool(
            width >= settings["minimum_reference_width_angstrom"]
            and len(selected) >= settings["minimum_reference_grid_points"]
            and std is not None and std <= settings["maximum_reference_std_ev"]
            and slope is not None and abs(slope) <= settings["maximum_reference_slope_ev_per_angstrom"]
        )
        mean = statistics.mean(values) if values else None
        result["relative_fermi_alignment"] = {
            "status": "reliable_prototype_proxy" if reliable else "unreliable_or_not_found",
            "EF_minus_CdTe_reference_potential_ev": fermi_ha * HARTREE_TO_EV - mean if reliable and mean is not None else None,
            "reference_z_start": start, "reference_z_end": end,
            "selected_layers": common_reference.get("selected_layers"),
            "atom_count": common_reference.get("atom_count"),
            "grid_point_count": len(selected), "potential_mean_ev": mean,
            "potential_std_ev": std, "slope_ev_per_angstrom": slope,
            "macroscopic_window_angstrom": macro_width,
            "method": common_reference.get("selection_method"),
        }
    atoms = parse_extxyz(structure_path)
    min_z, max_z = min(atom["z"] for atom in atoms), max(atom["z"] for atom in atoms)
    exclusion = settings["vacuum_atom_exclusion_angstrom"]
    max_slope = settings["vacuum_maximum_slope_ev_per_angstrom"]
    local_slopes = [0.0] + [abs((potential_ev[i] - potential_ev[i - 1]) / (z[i] - z[i - 1])) if z[i] != z[i - 1] else math.inf for i in range(1, len(z))]
    for side, candidate in (
        ("bottom", [i for i, value in enumerate(z) if value <= min_z - exclusion]),
        ("top", [i for i, value in enumerate(z) if value >= max_z + exclusion]),
    ):
        allowed = [i for i in candidate if abs(density[i]) <= settings["vacuum_density_threshold_au"] and local_slopes[i] <= max_slope]
        valid = []
        for segment in continuous_segments(allowed):
            width = z[segment[-1]] - z[segment[0]] if len(segment) > 1 else 0.0
            values = [potential_ev[i] for i in segment]
            std = statistics.pstdev(values) if len(values) > 1 else math.inf
            slope = linear_slope([z[i] for i in segment], values)
            if width >= settings["vacuum_minimum_width_angstrom"] and std <= settings["vacuum_maximum_std_ev"] and slope is not None and abs(slope) <= max_slope:
                valid.append((width, segment, std, slope))
        if valid:
            _, segment, std, slope = max(valid, key=lambda item: item[0])
            mean = statistics.mean(potential_ev[i] for i in segment)
            result["work_function"].update({
                f"{side}_status": "reliable_prototype_proxy",
                f"vacuum_level_{side}_ev": mean,
                f"work_function_{side}_ev": mean - fermi_ha * HARTREE_TO_EV,
                f"{side}_z_start": z[segment[0]], f"{side}_z_end": z[segment[-1]],
                f"{side}_grid_point_count": len(segment), f"{side}_std_ev": std,
                f"{side}_slope_ev_per_angstrom": slope,
            })
    result["work_function"]["scope_warning"] = "polar CdTe(111), fixed initial geometry; prototype work-function proxy, not publication-grade absolute work function"
    return result


def group_atom_counts(structure_path: Path) -> dict[str, int]:
    atoms = parse_extxyz(structure_path)
    return {
        "CdTe_substrate": sum(atom["component"] == "cdte_substrate" for atom in atoms),
        "Cu2Te_film": sum(atom["component"] == "cu2te_film" for atom in atoms),
        "CdTe_interface_top_Te": sum(atom["region"] == "interface_cdte_surface" and atom["element"] == "Te" for atom in atoms),
        "Cu2Te_interface_bottom_Cu": sum(atom["region"] == "interface_cu2te_bottom" and atom["element"] == "Cu" for atom in atoms),
    }


def verify_run_directory(task_id: str, run_dir: Path, spec: dict, config: dict, expected_input_hash: str | None = None) -> dict:
    input_path = run_dir / "input.executed.inp"
    output_path = run_dir / "output.out"
    metadata_path = run_dir / "run_metadata.tsv"
    text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""
    metadata = {}
    if metadata_path.is_file():
        for line in metadata_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\t" in line:
                key, value = line.split("\t", 1)
                metadata[key] = value
    version_match = VERSION_RE.search(text)
    cp2k_version = version_match.group(1).strip() if version_match else None
    energy_matches = ENERGY_RE.findall(text)
    total_energy = float(energy_matches[-1]) if energy_matches else None
    converged = bool(SCF_CONVERGED_RE.search(text))
    normal_end = "PROGRAM ENDED AT" in text
    return_code = None
    try:
        return_code = int(metadata.get("return_code", ""))
    except ValueError:
        pass
    actual_hash = sha256(input_path)
    hash_valid = bool(actual_hash and expected_input_hash and actual_hash == expected_input_hash) if expected_input_hash else bool(actual_hash)
    warning = last_mo_warning_state(text)
    structure_path = run_dir / "structure.extxyz"
    electronic = {"valid": not spec.get("expected_electronic_outputs", False)}
    spectral = {}
    potential = {}
    if spec.get("expected_electronic_outputs", False):
        consistency = pdos_consistency(
            run_dir, spec.get("ldos_groups", []),
            float(config["spectral_analysis"]["pdos_ldos_tolerance_hartree"]),
            spec.get("expected_kind_pdos_count"),
        )
        counts = group_atom_counts(structure_path) if structure_path.is_file() else {}
        spectral = build_spectral_proxies(
            run_dir, consistency, spec.get("ldos_groups", []),
            spec.get("substrate_area_angstrom2"), int(spec.get("formula_units", 0)), counts,
            float(config["spectral_analysis"]["fwhm_ev"]),
        ) if consistency["valid"] else {"spectral_integral_valid": False}
        common = common_cdte_reference(Path(config.get("package_root", run_dir.parents[1])))
        potential = analyze_potential(
            run_dir, structure_path, consistency.get("fermi_energy_hartree"), common,
            config["potential_analysis"],
        )
        cubes_ok = bool(list(run_dir.glob("*hartree*potential*.cube")) and list(run_dir.glob("*density*.cube")))
        histogram = normalized_cp2k_histogram(run_dir, consistency.get("fermi_energy_hartree"))
        dos_ok = histogram["dos_present"]
        electronic = {
            "valid": bool(consistency["valid"] and spectral.get("spectral_integral_valid") and cubes_ok and dos_ok and not warning["persistent"]),
            "pdos_ldos_consistent": consistency["valid"],
            "pdos_ldos_errors": consistency["errors"],
            "dos_present": dos_ok, "cubes_present": cubes_ok,
            **histogram, **spectral, **potential,
        }
    energy_valid = bool(return_code == 0 and normal_end and converged and total_energy is not None and cp2k_version and "2024.1" in cp2k_version and hash_valid)
    strict = bool(energy_valid and electronic["valid"])
    result = {
        "task_id": task_id, "run_dir": str(run_dir), "actually_run": output_path.is_file() or metadata_path.is_file(),
        "return_code": return_code, "normal_program_end": normal_end, "scf_converged": converged,
        "scf_steps": sum(int(value) for value in SCF_CONVERGED_RE.findall(text)) if converged else None,
        "scf_iterations_observed": len(parse_scf_residuals(text)),
        "scf_residuals_last_12": parse_scf_residuals(text)[-12:],
        "total_energy_hartree": total_energy if energy_valid else None,
        "energy_valid": energy_valid, "electronic_outputs_complete": electronic["valid"],
        "strict_success": strict, "cp2k_version": cp2k_version,
        "input_sha256": actual_hash, "input_hash_valid": hash_valid,
        "last_mo_smearing_warning": warning,
        "wall_time_seconds": metadata.get("wall_time_seconds"),
        "energy_semantics": "Total FORCE_EVAL (QS) energy under fixed geometry and unified 500 K electronic smearing; not asserted to be strict 0 K energy",
        "electronic_thermodynamic_lines": [
            line.strip() for line in text.splitlines()
            if re.search(r"electronic.*entropy|free\s+energy|entropy.*energy", line, re.I)
        ],
        **electronic,
    }
    if run_dir.is_dir() and result["actually_run"]:
        write_json(run_dir / "verification.json", result)
    return result
