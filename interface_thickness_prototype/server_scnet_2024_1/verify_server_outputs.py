#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "package_config.json"
HARTREE_TO_EV = 27.211386245988
TASK_ORDER = (
    "cu2te_bulk_gamma",
    "cu2te_bulk_k222",
    "cu2te_bulk_k333",
    "cu2te_bulk_k444",
    "B0",
    "C50",
    "H1",
    "H2",
)
ENERGY_RE = re.compile(
    r"ENERGY\|.*?energy\s*\[a\.u\.\]\s*:\s*([-+0-9.Ee]+)", re.I
)
SCF_CONVERGED_RE = re.compile(
    r"SCF\s+run\s+converged\s+in\s+(\d+)\s+steps", re.I
)
SCF_ITERATION_RE = re.compile(
    r"^\s*(\d+)\s+(?:NoMix|Broy\.)/Diag\.", re.I | re.M
)
VERSION_RE = re.compile(r"CP2K\|\s*version string:\s*(.+)", re.I)
PDOS_FERMI_RE = re.compile(
    r"(?:Fermi\s+energy:|E\(Fermi\)\s*=)\s*([-+0-9.Ee]+)", re.I
)
KIND_PDOS_RE = re.compile(r"-k(\d+)-\d+\.pdos$", re.I)
LDOS_RE = re.compile(r"-list(\d+)-\d+\.pdos$", re.I)


def read_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise SystemExit(f"missing package configuration: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_tsv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in raw:
            continue
        key, value = raw.split("\t", 1)
        values[key.strip()] = value.strip()
    return values


def as_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "", "pending") else None
    except ValueError:
        return None


def as_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "pending") else None
    except ValueError:
        return None


def numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    if not path.is_file():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "@")):
            continue
        try:
            rows.append([float(value) for value in line.split()])
        except ValueError:
            continue
    return rows


def pdos_record(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = numeric_rows(path)
    fermi = PDOS_FERMI_RE.search(text)
    return {
        "file": path.name,
        "mo_ids": [int(round(row[0])) for row in rows if len(row) >= 2],
        "eigenvalues_hartree": [row[1] for row in rows if len(row) >= 2],
        "fermi_energy_hartree": float(fermi.group(1)) if fermi else None,
        "numeric_rows": len(rows),
    }


def same_float_lists(first: list[float], second: list[float], tolerance: float) -> bool:
    return len(first) == len(second) and all(
        abs(a - b) <= tolerance for a, b in zip(first, second)
    )


def gaussian_domain_integral(
    energies_ev: list[float], fwhm_ev: float = 0.10
) -> tuple[float, bool]:
    lower, upper = -20.0, 45.0
    sigma = fwhm_ev / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    scale = sigma * math.sqrt(2.0)
    captured = sum(
        0.5
        * (
            math.erf((upper - energy) / scale)
            - math.erf((lower - energy) / scale)
        )
        for energy in energies_ev
    )
    expected = float(len(energies_ev))
    valid = expected > 0 and math.isclose(
        captured, expected, rel_tol=5.0e-4, abs_tol=1.0e-6
    )
    return captured, valid


def input_value(text: str, keyword: str) -> str | None:
    match = re.search(rf"(?mi)^\s*{re.escape(keyword)}\s+([^#\s]+)", text)
    return match.group(1) if match else None


def scf_signature(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return {
        "eps_scf": input_value(text, "EPS_SCF"),
        "max_scf": input_value(text, "MAX_SCF"),
        "added_mos": input_value(text, "ADDED_MOS"),
        "temperature": input_value(text, "ELECTRONIC_TEMPERATURE"),
        "mixing_alpha": input_value(text, "ALPHA"),
        "nbroyden": input_value(text, "NBROYDEN"),
        "standard_diagonalization": bool(
            re.search(r"(?mi)^\s*ALGORITHM\s+STANDARD\s*$", text)
        ),
        "fermi_dirac": "METHOD FERMI_DIRAC" in text.upper(),
    }


def physics_signature(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    basis_sets = sorted(set(re.findall(r"(?mi)^\s*BASIS_SET\s+(\S+)", text)))
    potentials = sorted(set(re.findall(r"(?mi)^\s*POTENTIAL\s+(\S+)", text)))
    return {
        "run_type": input_value(text, "RUN_TYPE"),
        "charge": input_value(text, "CHARGE"),
        "multiplicity": input_value(text, "MULTIPLICITY"),
        "cutoff": input_value(text, "CUTOFF"),
        "rel_cutoff": input_value(text, "REL_CUTOFF"),
        "eps_scf": input_value(text, "EPS_SCF"),
        "temperature": input_value(text, "ELECTRONIC_TEMPERATURE"),
        "basis_sets": basis_sets,
        "potentials": potentials,
        "pbe": "&XC_FUNCTIONAL PBE" in text.upper(),
        "implicit_gamma": "&KPOINTS" not in text.upper(),
        "periodic_xy": text.upper().count("PERIODIC XY") >= 2,
    }


def analyze_electronic_outputs(run_dir: Path, input_path: Path, scf_steps: int | None) -> dict:
    input_text = input_path.read_text(encoding="utf-8", errors="replace")
    expected_kind_count = len(
        re.findall(r"(?mi)^\s*&KIND\s+\S+\s*$", input_text)
    )
    expected_ldos_count = len(re.findall(r"(?mi)^\s*&LDOS\s*$", input_text))
    kind_records: dict[int, dict] = {}
    ldos_records: dict[int, dict] = {}
    for path in sorted(run_dir.glob("*.pdos")):
        kind_match = KIND_PDOS_RE.search(path.name)
        ldos_match = LDOS_RE.search(path.name)
        if kind_match:
            kind_records[int(kind_match.group(1))] = pdos_record(path)
        elif ldos_match:
            ldos_records[int(ldos_match.group(1))] = pdos_record(path)

    expected_ldos_indices = set(range(1, expected_ldos_count + 1))
    consistency_errors: list[str] = []
    if len(kind_records) != expected_kind_count:
        consistency_errors.append(
            f"expected {expected_kind_count} kind-PDOS files, found {len(kind_records)}"
        )
    if set(ldos_records) != expected_ldos_indices:
        consistency_errors.append(
            f"expected LDOS indices {sorted(expected_ldos_indices)}, found {sorted(ldos_records)}"
        )
    records = [kind_records[index] for index in sorted(kind_records)] + [
        ldos_records[index] for index in sorted(ldos_records)
    ]
    reference = records[0] if records else None
    if reference is None or reference["numeric_rows"] == 0:
        consistency_errors.append("no non-empty PDOS/LDOS reference list")
    else:
        for record in records[1:]:
            if record["mo_ids"] != reference["mo_ids"]:
                consistency_errors.append(f"MO index mismatch: {record['file']}")
            if not same_float_lists(
                record["eigenvalues_hartree"],
                reference["eigenvalues_hartree"],
                1.0e-6,
            ):
                consistency_errors.append(f"eigenvalue mismatch: {record['file']}")
            fermi_a = reference["fermi_energy_hartree"]
            fermi_b = record["fermi_energy_hartree"]
            if fermi_a is None or fermi_b is None or abs(fermi_a - fermi_b) > 1.0e-6:
                consistency_errors.append(f"Fermi-energy mismatch: {record['file']}")

    spectrum_integral = None
    spectrum_expected = None
    spectrum_valid = False
    if reference and not consistency_errors and reference["fermi_energy_hartree"] is not None:
        fermi = reference["fermi_energy_hartree"]
        energies_ev = [
            (energy - fermi) * HARTREE_TO_EV
            for energy in reference["eigenvalues_hartree"]
        ]
        spectrum_integral, spectrum_valid = gaussian_domain_integral(energies_ev)
        spectrum_expected = len(energies_ev)

    dos_files = [
        path
        for path in run_dir.iterdir()
        if path.is_file() and (path.suffix.lower() == ".dos" or "dos" in path.name.lower())
        and path.suffix.lower() != ".pdos"
    ] if run_dir.is_dir() else []
    dos_complete = bool(dos_files) and all(numeric_rows(path) for path in dos_files)
    hartree_complete = any(run_dir.glob("*hartree*potential*.cube"))
    density_complete = any(run_dir.glob("*density*.cube"))

    output_text = (run_dir / "output.out").read_text(
        encoding="utf-8", errors="replace"
    ) if (run_dir / "output.out").is_file() else ""
    last_mo_warning_count = output_text.count(
        "Fermi-Dirac smearing includes the last MO"
    )
    persistent = bool(
        scf_steps
        and last_mo_warning_count >= 3
        and last_mo_warning_count >= math.ceil(0.8 * scf_steps)
    )
    return {
        "kind_pdos_count": len(kind_records),
        "expected_kind_pdos_count": expected_kind_count,
        "ldos_count": len(ldos_records),
        "expected_ldos_count": expected_ldos_count,
        "pdos_ldos_consistent": not consistency_errors,
        "pdos_ldos_consistency_errors": consistency_errors,
        "dos_complete": dos_complete,
        "hartree_cube_complete": hartree_complete,
        "electron_density_cube_complete": density_complete,
        "spectrum_integral": spectrum_integral,
        "spectrum_expected_mo_count": spectrum_expected,
        "spectrum_integral_valid": spectrum_valid,
        "last_mo_smearing_warning_count": last_mo_warning_count,
        "last_mo_smearing_warning_persistent": persistent,
        "electronic_outputs_complete": bool(
            not consistency_errors
            and dos_complete
            and hartree_complete
            and density_complete
            and spectrum_valid
            and not persistent
        ),
    }


def verify_task(task_id: str, config: dict) -> dict:
    spec = config["tasks"][task_id]
    run_dir = ROOT / "runs" / task_id
    output_path = run_dir / "output.out"
    input_path = run_dir / "input.executed.inp"
    metadata_path = run_dir / "run_metadata.tsv"
    environment_path = run_dir / "environment.txt"
    metadata = read_tsv(metadata_path)
    text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""
    return_code = as_int(metadata.get("return_code"))
    step_counts = [int(value) for value in SCF_CONVERGED_RE.findall(text)]
    iteration_indices = [int(value) for value in SCF_ITERATION_RE.findall(text)]
    energies = [float(value) for value in ENERGY_RE.findall(text)]
    versions = VERSION_RE.findall(text)
    cp2k_version = versions[-1].strip() if versions else None
    normal_end = "PROGRAM ENDED AT" in text.upper()
    aborted = any(
        token in text.upper()
        for token in ("ABORT|", "[ABORT]", "*** ERROR", "SCF RUN NOT CONVERGED")
    )
    scf_converged = bool(step_counts) and not aborted
    total_energy = energies[-1] if energies else None
    warning_count = len(re.findall(r"(?mi)^\s*\*{3}\s*WARNING\s+in\s+", text))
    metadata_hash = metadata.get("input_sha256")
    actual_hash = sha256(input_path)
    package_input = ROOT / "inputs" / spec["input_dir"] / spec["input_name"]
    package_hash = spec.get("input_sha256") or sha256(package_input)
    input_hash_valid = bool(
        actual_hash and metadata_hash == actual_hash and package_hash == actual_hash
    )
    version_valid = bool(cp2k_version and "CP2K version 2024.1" in cp2k_version)
    evidence_complete = metadata_path.is_file() and environment_path.is_file() and input_path.is_file()
    energy_valid = bool(
        output_path.is_file()
        and return_code == 0
        and normal_end
        and scf_converged
        and total_energy is not None
        and not aborted
        and version_valid
        and input_hash_valid
        and evidence_complete
    )
    electronic = {
        "kind_pdos_count": None,
        "expected_kind_pdos_count": None,
        "ldos_count": None,
        "expected_ldos_count": None,
        "pdos_ldos_consistent": None,
        "pdos_ldos_consistency_errors": [],
        "dos_complete": None,
        "hartree_cube_complete": None,
        "electron_density_cube_complete": None,
        "spectrum_integral": None,
        "spectrum_expected_mo_count": None,
        "spectrum_integral_valid": None,
        "last_mo_smearing_warning_count": text.count(
            "Fermi-Dirac smearing includes the last MO"
        ),
        "last_mo_smearing_warning_persistent": None,
        "electronic_outputs_complete": False,
    }
    if spec["expected_electronic_outputs"] and input_path.is_file():
        electronic = analyze_electronic_outputs(
            run_dir, input_path, sum(step_counts) if step_counts else None
        )
    electronic_complete = bool(
        energy_valid
        and spec["expected_electronic_outputs"]
        and electronic["electronic_outputs_complete"]
    )
    strict_success = bool(
        energy_valid
        and (
            electronic_complete
            if spec["expected_electronic_outputs"]
            else True
        )
    )
    if strict_success:
        status = "strict_success"
        error = ""
    elif not output_path.is_file() and not metadata_path.is_file():
        status = "not_run"
        error = "no server run evidence"
    elif return_code is None:
        status = "incomplete_or_scheduler_terminated"
        error = "return code was not recorded; do not infer OOM or timeout without scheduler evidence"
    else:
        status = "strict_validation_failed"
        failures = []
        for label, okay in (
            ("return_code_0", return_code == 0),
            ("normal_program_end", normal_end),
            ("scf_converged", scf_converged),
            ("total_energy", total_energy is not None),
            ("cp2k_2024_1", version_valid),
            ("input_hash", input_hash_valid),
            ("run_evidence", evidence_complete),
            (
                "electronic_outputs",
                electronic_complete if spec["expected_electronic_outputs"] else True,
            ),
        ):
            if not okay:
                failures.append(label)
        error = "failed: " + ", ".join(failures)
    result = {
        "task_id": task_id,
        "actually_run": output_path.is_file() or metadata_path.is_file(),
        "status": status,
        "strict_success": strict_success,
        "return_code": return_code,
        "normal_program_end": normal_end,
        "scf_converged": scf_converged,
        "scf_steps": sum(step_counts) if step_counts else None,
        "scf_iterations_observed": len(iteration_indices),
        "total_energy_hartree": total_energy if energy_valid else None,
        "energy_valid": energy_valid,
        "electronic_outputs_complete": electronic_complete,
        "cp2k_version": cp2k_version,
        "cp2k_version_valid": version_valid,
        "input_sha256": actual_hash,
        "input_hash_valid": input_hash_valid,
        "environment_record_present": environment_path.is_file(),
        "wall_time_seconds": as_float(metadata.get("wall_time_seconds")),
        "ntasks": as_int(metadata.get("ntasks")),
        "kpoint_mesh": spec["kpoint_mesh"],
        "cp2k_warning_count": warning_count,
        "warning_or_error": error,
        **electronic,
    }
    if run_dir.is_dir() and (
        output_path.is_file() or metadata_path.is_file() or input_path.is_file()
    ):
        (run_dir / "verification.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return result


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def bulk_kpoint_rows(results: dict[str, dict], config: dict) -> list[dict]:
    threshold = float(config["kpoint_convergence_threshold_ev_per_formula_unit"])
    ids = (
        "cu2te_bulk_gamma",
        "cu2te_bulk_k222",
        "cu2te_bulk_k333",
        "cu2te_bulk_k444",
    )
    rows = []
    previous = None
    for task_id in ids:
        result = results[task_id]
        total = result["total_energy_hartree"] if result["energy_valid"] else None
        per_fu = total / 2.0 if total is not None else None
        delta_ev = (
            (per_fu - previous) * HARTREE_TO_EV
            if per_fu is not None and previous is not None
            else None
        )
        adjacent_pass = abs(delta_ev) < threshold if delta_ev is not None else None
        rows.append(
            {
                "task_id": task_id,
                "kpoint_mesh": config["tasks"][task_id]["kpoint_mesh"],
                "energy_valid": result["energy_valid"],
                "total_energy_hartree": total,
                "energy_hartree_per_Cu2Te_formula_unit": per_fu,
                "delta_from_previous_ev_per_Cu2Te_formula_unit": delta_ev,
                "adjacent_difference_below_0p01_ev": adjacent_pass,
                "status": (
                    "minimum_adjacent_check_passed"
                    if adjacent_pass is True
                    else "not_converged_or_not_available"
                ),
                "next_step": (
                    "manual_5x5x5_check_needed"
                    if task_id == "cu2te_bulk_k444" and adjacent_pass is False
                    else ""
                ),
            }
        )
        previous = per_fu if per_fu is not None else None
    return rows


def coverage_rows(results: dict[str, dict], config: dict, bulk_rows: list[dict]) -> list[dict]:
    b0, c50, h1 = (results[key] for key in ("B0", "C50", "H1"))
    input_paths = {
        key: ROOT / "runs" / key / "input.executed.inp"
        for key in ("B0", "C50", "H1")
    }
    signatures = {
        key: physics_signature(path) for key, path in input_paths.items()
    }
    same_physics = all(signatures[key] == signatures["B0"] for key in ("C50", "H1"))
    all_three = b0["strict_success"] and c50["strict_success"] and h1["strict_success"]
    curvature_ready = bool(all_three and same_physics)
    curvature_ha = (
        h1["total_energy_hartree"]
        + b0["total_energy_hartree"]
        - 2.0 * c50["total_energy_hartree"]
        if curvature_ready
        else None
    )
    bulk_ready = bool(
        bulk_rows[-1]["energy_valid"]
        and bulk_rows[-1]["adjacent_difference_below_0p01_ev"] is True
    )
    bulk_per_fu = bulk_rows[-1]["energy_hartree_per_Cu2Te_formula_unit"] if bulk_ready else None
    area = float(config["tasks"]["B0"]["substrate_area_angstrom2"])
    rows = []
    for model_id, n_fu in (("C50", 16), ("H1", 32)):
        model = results[model_id]
        ready = bool(
            model["strict_success"]
            and b0["strict_success"]
            and same_physics
            and bulk_ready
        )
        formation_ha = (
            model["total_energy_hartree"]
            - b0["total_energy_hartree"]
            - n_fu * bulk_per_fu
            if ready
            else None
        )
        rows.append(
            {
                "metric_id": f"{model_id}_fixed_geometry_relative_coverage_formation_energy",
                "value_hartree": formation_ha,
                "value_ev": formation_ha * HARTREE_TO_EV if formation_ha is not None else None,
                "value_ev_per_angstrom2": (
                    formation_ha * HARTREE_TO_EV / area if formation_ha is not None else None
                ),
                "value_ev_per_Cu2Te_formula_unit": (
                    formation_ha * HARTREE_TO_EV / n_fu if formation_ha is not None else None
                ),
                "status": (
                    "computed_fixed_geometry_prototype_not_absolute_surface_energy"
                    if ready
                    else "not_ready_for_paper"
                ),
                "requirements": "CP2K 2024.1 strict B0/model success plus converged bulk adjacent k-point check",
                "limitations": "fixed initial geometry; polar slab; Gamma slab; prototype Cu2Te phase",
            }
        )
    rows.append(
        {
            "metric_id": "coverage_curvature_E_H1_plus_E_B0_minus_2E_C50",
            "value_hartree": curvature_ha,
            "value_ev": curvature_ha * HARTREE_TO_EV if curvature_ha is not None else None,
            "value_ev_per_angstrom2": (
                curvature_ha * HARTREE_TO_EV / area if curvature_ha is not None else None
            ),
            "value_ev_per_Cu2Te_formula_unit": None,
            "status": "computed_prototype_proxy" if curvature_ready else "not_ready_for_paper",
            "requirements": "strict same-version/same-major-physics B0, C50 and H1 results",
            "limitations": "bulk chemical potential cancels; periodic C50 stripe is not every 50% island morphology",
        }
    )
    return rows


def write_results(results: dict[str, dict], config: dict) -> dict:
    results_dir = ROOT / "results"
    task_fields = [
        "task_id", "actually_run", "status", "strict_success", "return_code",
        "normal_program_end", "scf_converged", "scf_steps",
        "scf_iterations_observed", "total_energy_hartree", "energy_valid",
        "electronic_outputs_complete", "cp2k_version", "cp2k_version_valid",
        "input_hash_valid", "environment_record_present", "wall_time_seconds",
        "ntasks", "kpoint_mesh", "cp2k_warning_count",
        "last_mo_smearing_warning_count", "last_mo_smearing_warning_persistent",
        "pdos_ldos_consistent", "spectrum_integral_valid", "warning_or_error",
    ]
    write_csv(
        results_dir / "server_task_status.csv",
        [{field: result.get(field) for field in task_fields} for result in results.values()],
        task_fields,
    )
    bulk_rows = bulk_kpoint_rows(results, config)
    write_csv(
        results_dir / "bulk_kpoint_convergence.csv",
        bulk_rows,
        list(bulk_rows[0]),
    )
    metrics = coverage_rows(results, config, bulk_rows)
    write_csv(
        results_dir / "server_coverage_metrics.csv",
        metrics,
        list(metrics[0]),
    )
    payload = {
        "target_cp2k_version": config["target_cp2k_version"],
        "server_calculations_actually_run": any(
            result["actually_run"] for result in results.values()
        ),
        "all_tasks": results,
        "bulk_kpoint_rows": bulk_rows,
        "coverage_metrics": metrics,
        "scientific_boundary": config["scientific_boundary"],
    }
    (results_dir / "server_verification.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def gate_h2(config: dict) -> tuple[bool, dict]:
    h1 = verify_task("H1", config)
    h1_input = ROOT / "runs" / "H1" / "input.executed.inp"
    h2_input = ROOT / "inputs" / "H2" / "input.inp"
    signatures_match = h1_input.is_file() and scf_signature(h1_input) == scf_signature(h2_input)
    allowed = bool(h1["strict_success"] and signatures_match)
    detail = {
        "h2_submission_allowed": allowed,
        "h1_strict_success": h1["strict_success"],
        "h1_electronic_outputs_complete": h1["electronic_outputs_complete"],
        "h1_last_mo_warning_persistent": h1["last_mo_smearing_warning_persistent"],
        "h1_h2_scf_signatures_match": signatures_match,
        "warning": (
            "H2 may be submitted manually."
            if allowed
            else "H2 is blocked; do not submit it."
        ),
    }
    return allowed, detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly verify future SCNet CP2K 2024.1 outputs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", choices=TASK_ORDER)
    group.add_argument("--all", action="store_true")
    group.add_argument("--gate-h2", action="store_true")
    parser.add_argument("--write-results", action="store_true")
    args = parser.parse_args()
    config = read_config()
    if args.gate_h2:
        allowed, detail = gate_h2(config)
        print(json.dumps(detail, indent=2, ensure_ascii=False))
        return 0 if allowed else 3
    if args.task:
        result = verify_task(args.task, config)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["strict_success"] else 2
    results = {task_id: verify_task(task_id, config) for task_id in TASK_ORDER}
    payload = write_results(results, config) if args.write_results else {"all_tasks": results}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
