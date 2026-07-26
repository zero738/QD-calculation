from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT
from parse_research_lite_output import parse_research_run


TASKS = ("cu2te_bulk", "cu2te_bulk_k222", "B0", "C50", "H1", "H2")


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path, key: str) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _same_number(left: object, right: object, tolerance: float = 1.0e-10) -> bool:
    if _is_blank(left) and _is_blank(right):
        return True
    if _is_blank(left) or _is_blank(right):
        return False
    return math.isclose(
        float(left), float(right), rel_tol=0.0, abs_tol=float(tolerance)
    )


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def audit_code_and_gates() -> list[dict]:
    gates = _read_json(ROOT / "results" / "pre_run_gates.json")
    gate_by_name = {
        item.get("gate"): item
        for item in gates.get("checks", [])
        if isinstance(item, dict)
    }
    return [
        _check(
            "pre_run_hard_gates",
            bool(gates.get("all_gates_passed")),
            "The recorded pre-run gate file must report every hard gate passed.",
        ),
        _check(
            "cp2k_check_all_inputs",
            bool(
                gate_by_name.get("all_inputs_pass_cp2k_2024_3_check", {})
                .get("passed")
            ),
            "All generated research_lite inputs must pass CP2K 2024.3 --check.",
        ),
        _check(
            "existing_bulk_warning_gate",
            bool(
                gate_by_name.get("existing_bulk_warning_count_is_19", {})
                .get("passed")
            ),
            "The existing implicit-Gamma Cu2Te bulk output must reparse to 19 warnings.",
        ),
    ]


def audit_raw_outputs_against_csv() -> list[dict]:
    final_rows = _read_csv(
        ROOT / "results" / "final_model_status.csv", "canonical_model_id"
    )
    checks: list[dict] = []
    for task_id in TASKS:
        run_dir = ROOT / "research_lite" / "runs" / task_id
        metadata = _read_json(run_dir / "run_metadata.json")
        stored = _read_json(run_dir / "output.parsed.json")
        row = final_rows[task_id]
        if metadata.get("attempted"):
            fresh = parse_research_run(run_dir)
            matches = (
                fresh.get("energy_valid") == stored.get("energy_valid")
                and fresh.get("electronic_outputs_complete")
                == stored.get("electronic_outputs_complete")
                and fresh.get("scf_steps") == stored.get("scf_steps")
                and fresh.get("scf_iterations_observed")
                == stored.get("scf_iterations_observed")
                and fresh.get("cp2k_warning_count")
                == stored.get("cp2k_warning_count")
                and _same_number(
                    fresh.get("total_energy_hartree"),
                    stored.get("total_energy_hartree"),
                )
            )
            checks.append(
                _check(
                    f"{task_id}_fresh_parse_matches_stored",
                    matches,
                    "Fresh strict parsing of the raw CP2K evidence must match output.parsed.json.",
                )
            )
            csv_matches = (
                str(fresh.get("energy_valid")).lower()
                == row["energy_valid"].lower()
                and str(fresh.get("electronic_outputs_complete")).lower()
                == row["electronic_outputs_complete"].lower()
                and _same_number(fresh.get("scf_steps"), row["SCF_steps"])
                and _same_number(
                    fresh.get("scf_iterations_observed"),
                    row["SCF_iterations_observed"],
                )
                and _same_number(
                    fresh.get("total_energy_hartree"),
                    row["total_energy_hartree"],
                )
                and _same_number(
                    fresh.get("cp2k_warning_count"),
                    row["cp2k_warning_count"],
                )
            )
            checks.append(
                _check(
                    f"{task_id}_raw_parse_matches_final_csv",
                    csv_matches,
                    "Raw-output strict status, SCF count, energy and warning count must match final_model_status.csv.",
                )
            )
        else:
            no_invented_result = (
                row["actually_run"].lower() == "false"
                and row["energy_valid"].lower() == "false"
                and _is_blank(row["SCF_steps"])
                and _is_blank(row["total_energy_hartree"])
            )
            checks.append(
                _check(
                    f"{task_id}_unrun_has_no_invented_result",
                    no_invented_result,
                    "An unattempted task must have no SCF count or energy in the final CSV.",
                )
            )
    return checks


def audit_scientific_dimensions_and_claims() -> list[dict]:
    proxy_rows = _read_csv(ROOT / "results" / "dft_proxy_summary.csv", "model_id")
    formation_rows = _read_csv(
        ROOT / "results" / "relative_coverage_formation_energy.csv", "model_id"
    )
    kpoint_row = next(
        iter(
            _read_csv(
                ROOT / "results" / "kpoint_reference_check.csv", "reference_id"
            ).values()
        )
    )
    status_rows = _read_csv(
        ROOT / "results" / "final_model_status.csv", "canonical_model_id"
    )
    checks: list[dict] = []

    proxy_header = next(iter(proxy_rows.values())).keys()
    checks.append(
        _check(
            "no_raw_total_dos_comparison_field",
            not any("raw_total" in field.lower() for field in proxy_header),
            "The cross-model proxy table must not expose a raw total-DOS comparison field.",
        )
    )
    b0 = proxy_rows["B0"]
    checks.append(
        _check(
            "B0_cu2te_projections_are_blank",
            _is_blank(
                b0[
                    "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit"
                ]
            )
            and _is_blank(
                b0[
                    "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom"
                ]
            ),
            "The bare CdTe model has no Cu2Te formula units or Cu interface atoms, so both fields must be blank.",
        )
    )
    checks.append(
        _check(
            "aliases_are_unique",
            status_rows["B0"]["aliases"] == "C0"
            and status_rows["H1"]["aliases"] == "C100"
            and all(
                status_rows[key]["aliases"] == ""
                for key in ("C50", "H2", "cu2te_bulk", "cu2te_bulk_k222")
            ),
            "C0 must reference only B0 and C100 must reference only H1.",
        )
    )

    for model_id, task_id in (("C0", "B0"), ("C50", "C50"), ("C100", "H1")):
        row = formation_rows[model_id]
        references_valid = (
            status_rows[task_id]["energy_valid"].lower() == "true"
            and status_rows["B0"]["energy_valid"].lower() == "true"
            and status_rows["cu2te_bulk_k222"]["energy_valid"].lower() == "true"
        )
        numeric_present = not _is_blank(
            row[
                "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2"
            ]
        )
        checks.append(
            _check(
                f"{model_id}_formation_energy_validity_gate",
                numeric_present == references_valid,
                "A formation-energy value is allowed only when the slab, B0 and 2x2x2 bulk reference energies are valid.",
            )
        )
    checks.append(
        _check(
            "formation_reference_and_dimensions_are_explicit",
            all(
                row["E_bulk_reference_kpoint_mesh"] == "2x2x2"
                and row["slab_kpoint_mesh"] in {"", "implicit_gamma"}
                and "ev_per_angstrom2"
                in "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2"
                for row in formation_rows.values()
            ),
            "The minimum bulk reference mesh and per-area dimensions must be explicit.",
        )
    )
    gamma_energy = float(status_rows["cu2te_bulk"]["total_energy_hartree"])
    k222_energy = float(status_rows["cu2te_bulk_k222"]["total_energy_hartree"])
    expected_delta_ev = (k222_energy - gamma_energy) / 2.0 * 27.211386245988
    checks.append(
        _check(
            "bulk_kpoint_difference_is_per_formula_unit_and_reproducible",
            int(kpoint_row["formula_units_in_cell"]) == 2
            and math.isclose(
                float(
                    kpoint_row[
                        "delta_E_k222_minus_gamma_ev_per_Cu2Te_formula_unit"
                    ]
                ),
                expected_delta_ev,
                rel_tol=0.0,
                abs_tol=1.0e-10,
            )
            and "not a k-point convergence study" in kpoint_row["limitations"],
            "The Gamma-to-2x2x2 bulk difference must use two Cu2Te formula units and remain labelled as a minimum check.",
        )
    )
    checks.append(
        _check(
            "C0_per_formula_unit_value_is_undefined_not_zero",
            _is_blank(
                formation_rows["C0"][
                    "fixed_geometry_relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit"
                ]
            ),
            "C0 has zero Cu2Te formula units, so a per-formula-unit quotient is undefined and must remain blank.",
        )
    )

    for task_id, row in proxy_rows.items():
        top_reliable = row["top_vacuum_plateau_status"] == "reliable"
        work_present = not _is_blank(row["top_surface_work_function_proxy_ev"])
        checks.append(
            _check(
                f"{task_id}_work_function_reliability_gate",
                top_reliable == work_present,
                "A top work-function proxy is allowed only when the continuous vacuum plateau is reliable.",
            )
        )
        complete = row["electronic_outputs_complete"].lower() == "true"
        normalized_present = not _is_blank(
            row["KS_orbital_density_near_EF_per_ev_per_substrate_area"]
        )
        checks.append(
            _check(
                f"{task_id}_normalized_spectrum_completeness_gate",
                complete == normalized_present,
                "The size-normalized KS spectral metric must be present exactly for complete electronic outputs.",
            )
        )

    paper = (ROOT / "PAPER_RESULTS_SUMMARY.md").read_text(encoding="utf-8")
    checks.append(
        _check(
            "paper_summary_keeps_claim_boundary",
            "当前不能声称" in paper
            and "真实接触电阻" in paper
            and "最佳实验膜厚" in paper
            and "唯一真实晶相" in paper,
            "The paper-facing summary must explicitly prohibit unsupported resistance, optimum-thickness and phase claims.",
        )
    )
    return checks


def main() -> int:
    rounds = {
        "round_1_code_tests_and_pre_run_gates": audit_code_and_gates(),
        "round_2_raw_outputs_vs_csv": audit_raw_outputs_against_csv(),
        "round_3_scientific_dimensions_normalization_references_and_claims": (
            audit_scientific_dimensions_and_claims()
        ),
    }
    all_checks = [check for checks in rounds.values() for check in checks]
    report = {
        "audit_rounds": rounds,
        "check_count": len(all_checks),
        "passed_count": sum(check["passed"] for check in all_checks),
        "all_passed": all(check["passed"] for check in all_checks),
    }
    destination = ROOT / "results" / "final_audit.json"
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
