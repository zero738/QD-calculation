#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from server_analysis import HARTREE_TO_EV, scf_signature, sha256, verify_run_directory, write_json

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "package_config.json"
TASK_ORDER = (
    "cu2te_bulk_gamma", "cu2te_bulk_k222", "cu2te_bulk_k333", "cu2te_bulk_k444",
    "B0", "C50", "H1", "H2",
)


def read_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["package_root"] = str(ROOT)
    return config


def empty_result(task_id: str, spec: dict) -> dict:
    return {
        "task_id": task_id, "actually_run": False, "status": "not_run",
        "strict_success": False, "return_code": None, "normal_program_end": False,
        "scf_converged": False, "scf_steps": None, "scf_iterations_observed": 0,
        "total_energy_hartree": None, "energy_valid": False,
        "electronic_outputs_complete": False, "cp2k_version": None,
        "input_hash_valid": False, "wall_time_seconds": None,
        "kpoint_mesh": spec["kpoint_mesh"], "successful_attempt": None,
        "warning_or_error": "no server run evidence",
    }


def _h1_success_record() -> dict | None:
    path = ROOT / "runs" / "H1" / "H1_SUCCESS.json"
    flag = ROOT / "runs" / "H1" / "H1_SUCCESS.flag"
    if not path.is_file() or not flag.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify_task(task_id: str, config: dict | None = None) -> dict:
    config = config or read_config()
    spec = config["tasks"][task_id]
    if task_id == "H1":
        success = _h1_success_record()
        if success:
            attempt = success.get("successful_attempt")
            run_dir = ROOT / "runs" / "H1" / str(attempt)
            result = verify_run_directory(
                "H1", run_dir, spec, config, success.get("successful_input_sha256")
            )
            result["successful_attempt"] = attempt
            success_matches = bool(
                result["strict_success"]
                and sha256(run_dir / "structure.extxyz") == success.get("structure_sha256")
                and scf_signature(run_dir / "input.executed.inp") == success.get("scf_signature")
            )
            result["strict_success"] = success_matches
            result["status"] = "strict_success" if success_matches else "stale_or_invalid_H1_SUCCESS"
            if not success_matches:
                result["energy_valid"] = False
                result["total_energy_hartree"] = None
            return result
        attempts = []
        for name in ("attempt_A", "attempt_B"):
            directory = ROOT / "runs" / "H1" / name
            if directory.is_dir():
                attempts.append(verify_run_directory("H1", directory, spec, config))
        if not attempts:
            return empty_result(task_id, spec)
        latest = attempts[-1]
        latest.update({
            "task_id": "H1", "status": "failed_after_controlled_retry" if len(attempts) == 2 else "attempt_A_failed",
            "strict_success": False, "energy_valid": False, "total_energy_hartree": None,
            "successful_attempt": None,
            "attempts": [{"run_dir": item["run_dir"], "strict_success": item["strict_success"]} for item in attempts],
        })
        return latest
    run_dir = ROOT / "runs" / task_id
    if not run_dir.is_dir() or not any(run_dir.iterdir()):
        return empty_result(task_id, spec)
    result = verify_run_directory(task_id, run_dir, spec, config, spec["input_sha256"] if task_id != "H2" else None)
    if task_id == "H2":
        success = _h1_success_record()
        preparation = run_dir / "H2_PREPARATION.json"
        dynamic_signature_valid = bool(
            success and preparation.is_file()
            and json.loads(preparation.read_text(encoding="utf-8")).get("status") == "ready"
            and scf_signature(run_dir / "input.executed.inp") == success.get("scf_signature")
        )
        result["H1_dynamic_signature_valid"] = dynamic_signature_valid
        if not dynamic_signature_valid:
            result["strict_success"] = False
            result["energy_valid"] = False
            result["total_energy_hartree"] = None
    result["status"] = "strict_success" if result["strict_success"] else "strict_validation_failed"
    result["successful_attempt"] = None
    result["kpoint_mesh"] = spec["kpoint_mesh"]
    result["warning_or_error"] = "" if result["strict_success"] else "strict evidence incomplete or inconsistent"
    return result


def gate_h2(config: dict | None = None) -> tuple[bool, dict]:
    config = config or read_config()
    success = _h1_success_record()
    h1 = verify_task("H1", config)
    allowed = bool(success and h1["strict_success"])
    detail = {
        "h2_submission_allowed": allowed,
        "h1_strict_success": h1["strict_success"],
        "h1_electronic_outputs_complete": h1.get("electronic_outputs_complete", False),
        "successful_attempt": success.get("successful_attempt") if success else None,
        "h1_success_flag_present": (ROOT / "runs/H1/H1_SUCCESS.flag").is_file(),
        "h1_success_json_present": (ROOT / "runs/H1/H1_SUCCESS.json").is_file(),
        "warning": "H2 dynamic input preparation is allowed." if allowed else "H2 is blocked by H1.",
    }
    return allowed, detail


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field) for field in fields} for row in rows])


def bulk_rows(results: dict[str, dict], config: dict) -> list[dict]:
    rows = []
    previous = None
    for task_id in TASK_ORDER[:4]:
        result = results[task_id]
        total = result["total_energy_hartree"] if result["energy_valid"] else None
        per_fu = total / 2.0 if total is not None else None
        delta = (per_fu - previous) * HARTREE_TO_EV if per_fu is not None and previous is not None else None
        passed = abs(delta) < 0.01 if delta is not None else None
        rows.append({
            "task_id": task_id, "kpoint_mesh": config["tasks"][task_id]["kpoint_mesh"],
            "total_energy_hartree": total,
            "energy_hartree_per_formula_unit": per_fu,
            "adjacent_delta_ev_per_formula_unit": delta,
            "adjacent_delta_below_0p01_ev": passed,
            "status": "minimum_reference_converged" if task_id.endswith("k444") and passed else "not_run_or_not_converged",
            "energy_semantics": "fixed geometry, unified 500 K electronic smearing energy proxy",
        })
        previous = per_fu if per_fu is not None else None
    return rows


def coverage_and_curvature(results: dict[str, dict], bulk: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    area = 236.37089524795562
    bulk_ready = bool(bulk[-1]["adjacent_delta_below_0p01_ev"] is True and bulk[-1]["energy_hartree_per_formula_unit"] is not None)
    mu = bulk[-1]["energy_hartree_per_formula_unit"] if bulk_ready else None
    b0 = results["B0"]
    rows = []
    for model, n_fu in (("C50", 16), ("H1", 32)):
        item = results[model]
        ready = bool(bulk_ready and b0["strict_success"] and item["strict_success"])
        value = item["total_energy_hartree"] - b0["total_energy_hartree"] - n_fu * mu if ready else None
        rows.append({
            "model_id": model, "metric_name": "fixed_initial_geometry_relative_coverage_formation_energy",
            "value_hartree": value, "value_ev": value * HARTREE_TO_EV if value is not None else None,
            "value_ev_per_angstrom2": value * HARTREE_TO_EV / area if value is not None else None,
            "value_ev_per_Cu2Te_formula_unit": value * HARTREE_TO_EV / n_fu if value is not None else None,
            "status": "prototype_proxy_available" if ready else "not_ready_for_paper",
            "limitations": "not absolute surface energy; fixed geometry; polar slab; C50 is a periodic stripe",
        })
    curvature_ready = all(results[item]["strict_success"] for item in ("B0", "C50", "H1"))
    value = results["H1"]["total_energy_hartree"] + results["B0"]["total_energy_hartree"] - 2 * results["C50"]["total_energy_hartree"] if curvature_ready else None
    curvature = [{
        "metric_name": "coverage_curvature_E_H1_plus_E_B0_minus_2E_C50",
        "value_hartree": value, "value_ev": value * HARTREE_TO_EV if value is not None else None,
        "value_ev_per_angstrom2": value * HARTREE_TO_EV / area if value is not None else None,
        "status": "prototype_proxy_available" if curvature_ready else "not_ready_for_paper",
        "interpretation": "Cu2Te chemical potential cancels; deviation of current periodic C50 stripe from endpoint linear interpolation; not an absolute surface energy or all 50% morphologies",
    }]
    return rows, curvature


def proxy_rows(results: dict[str, dict]) -> tuple[list[dict], list[dict], list[dict]]:
    proxies, alignment, work = [], [], []
    for task_id in ("B0", "C50", "H1", "H2"):
        item = results[task_id]
        proxies.append({
            "model_id": task_id, "status": "available" if item.get("electronic_outputs_complete") else item["status"],
            "KS_orbital_count_near_EF_in_window": item.get("KS_orbital_count_near_EF_in_window"),
            "KS_orbital_density_near_EF_per_ev": item.get("KS_orbital_density_near_EF_per_ev"),
            "KS_orbital_density_near_EF_per_ev_per_substrate_area": item.get("KS_orbital_density_near_EF_per_ev_per_substrate_area"),
            "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit": item.get("Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit"),
            "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom": item.get("CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom"),
            "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom": item.get("Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom"),
            "spectral_integral_valid": item.get("spectral_integral_valid"),
            "contact_scope": "DFT proxy only; no theoretical contact resistance in ohm*cm2",
        })
        align = item.get("relative_fermi_alignment", {})
        alignment.append({
            "model_id": task_id,
            "status": align.get("status", "not_run" if not item["actually_run"] else "unreliable_or_not_found"),
            "EF_minus_CdTe_reference_potential_ev": align.get("EF_minus_CdTe_reference_potential_ev"),
            "reference_z_start": align.get("reference_z_start"),
            "reference_z_end": align.get("reference_z_end"),
            "selected_layers": json.dumps(align.get("selected_layers"), ensure_ascii=False) if align.get("selected_layers") is not None else None,
            "atom_count": align.get("atom_count"),
            "grid_point_count": align.get("grid_point_count"),
            "potential_mean_ev": align.get("potential_mean_ev"),
            "potential_std_ev": align.get("potential_std_ev"),
            "slope_ev_per_angstrom": align.get("slope_ev_per_angstrom"),
        })
        wf = item.get("work_function", {})
        work.append({
            "model_id": task_id,
            "top_status": wf.get("top_status", "not_run" if not item["actually_run"] else "unreliable_or_not_found"),
            "bottom_status": wf.get("bottom_status", "not_run" if not item["actually_run"] else "unreliable_or_not_found"),
            "vacuum_level_top_ev": wf.get("vacuum_level_top_ev"),
            "vacuum_level_bottom_ev": wf.get("vacuum_level_bottom_ev"),
            "work_function_top_ev": wf.get("work_function_top_ev"),
            "work_function_bottom_ev": wf.get("work_function_bottom_ev"),
            "top_std_ev": wf.get("top_std_ev"), "bottom_std_ev": wf.get("bottom_std_ev"),
            "top_slope_ev_per_angstrom": wf.get("top_slope_ev_per_angstrom"),
            "bottom_slope_ev_per_angstrom": wf.get("bottom_slope_ev_per_angstrom"),
            "scope_warning": wf.get("scope_warning"),
        })
    return proxies, alignment, work


def write_results(results: dict[str, dict], config: dict) -> dict:
    directory = ROOT / "results"
    status_fields = [
        "task_id", "actually_run", "status", "strict_success", "return_code",
        "normal_program_end", "scf_converged", "scf_steps", "scf_iterations_observed",
        "total_energy_hartree", "energy_valid", "electronic_outputs_complete",
        "cp2k_version", "input_hash_valid", "wall_time_seconds", "kpoint_mesh",
        "successful_attempt", "warning_or_error",
    ]
    write_csv(directory / "final_model_status.csv", list(results.values()), status_fields)
    write_csv(directory / "server_task_status.csv", list(results.values()), status_fields)
    bulk = bulk_rows(results, config)
    write_csv(directory / "bulk_kpoint_convergence.csv", bulk)
    formation, curvature = coverage_and_curvature(results, bulk, config)
    write_csv(directory / "relative_coverage_formation_energy.csv", formation)
    write_csv(directory / "coverage_curvature_proxy.csv", curvature)
    proxies, alignment, work = proxy_rows(results)
    write_csv(directory / "dft_proxy_summary.csv", proxies)
    write_csv(directory / "relative_fermi_alignment.csv", alignment)
    write_csv(directory / "work_function_status.csv", work)
    resource_rows = []
    for task_id, item in config["resources"].items():
        resource_rows.append({"task_id": task_id, "ntasks": item["ntasks"], "requested_hours": item["hours"], "maximum_cpu_hours": item["ntasks"] * item["hours"], "recorded_wall_time_seconds": results.get(task_id, {}).get("wall_time_seconds")})
    write_csv(directory / "scnet_resource_usage.csv", resource_rows)
    gate = {
        "server_tasks_actually_run": any(item["actually_run"] for item in results.values()),
        "all_required_tasks_strict_success": all(item["strict_success"] for item in results.values()),
        "paper_ready": False,
        "paper_ready_reason": "prototype structures and convergence gates; server tasks are initially not run",
        "bulk_reference_converged": bulk[-1]["adjacent_delta_below_0p01_ev"] is True,
        "H2_blocked_by_H1": not results["H1"]["strict_success"],
        "forbidden_claims": ["absolute surface energy", "true contact resistance", "optimal thickness", "optimal concentration", "unique experimental Cu2-xTe phase"],
    }
    write_json(directory / "final_scientific_gate.json", gate)
    payload = {"all_tasks": results, "bulk": bulk, "formation": formation, "curvature": curvature, "scientific_gate": gate}
    write_json(directory / "server_verification.json", payload)
    write_json(directory / "pipeline_audit.json", {"status": "not_run" if not gate["server_tasks_actually_run"] else "collected", "checks": gate})
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
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
    results = {task: verify_task(task, config) for task in TASK_ORDER}
    payload = write_results(results, config) if args.write_results else {"all_tasks": results}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
