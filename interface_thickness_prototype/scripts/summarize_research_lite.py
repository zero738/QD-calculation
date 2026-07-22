from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT
from parse_cp2k_output import HARTREE_TO_EV


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _blank(value):
    return "" if value is None else value


def write_research_summary() -> Path:
    manifest = _read_json(ROOT / "research_lite" / "manifest.json") or []
    fields = [
        "calculation_id",
        "calculation_profile",
        "actually_run",
        "normal_program_end",
        "SCF_converged",
        "SCF_steps",
        "total_energy_hartree",
        "fermi_energy_hartree",
        "fermi_energy_ev_raw_cp2k_reference",
        "DOS_output_present",
        "PDOS_LDOS_output_present",
        "potential_output_present",
        "normalized_DOS_near_EF_per_ev",
        "wall_time_seconds",
        "research_output_complete",
        "warning_or_error",
    ]
    rows = []
    for task in manifest:
        parsed = _read_json(ROOT / "research_lite" / "runs" / task["calculation_id"] / "output.parsed.json") or {}
        rows.append(
            {
                "calculation_id": task["calculation_id"],
                "calculation_profile": "research_lite",
                "actually_run": bool(parsed.get("actually_run", False)),
                "normal_program_end": bool(parsed.get("normal_program_end", False)),
                "SCF_converged": bool(parsed.get("scf_converged", False)),
                "SCF_steps": _blank(parsed.get("scf_steps")),
                "total_energy_hartree": _blank(parsed.get("total_energy_hartree")),
                "fermi_energy_hartree": _blank(parsed.get("fermi_energy_hartree")),
                "fermi_energy_ev_raw_cp2k_reference": _blank(parsed.get("fermi_energy_ev")),
                "DOS_output_present": bool(parsed.get("dos_output_present", False)),
                "PDOS_LDOS_output_present": bool(parsed.get("pdos_output_present", False)),
                "potential_output_present": bool(parsed.get("potential_output_present", False)),
                "normalized_DOS_near_EF_per_ev": _blank(parsed.get("normalized_dos_near_fermi_per_ev")),
                "wall_time_seconds": _blank(parsed.get("wall_time_seconds")),
                "research_output_complete": bool(parsed.get("research_output_complete", False)),
                "warning_or_error": parsed.get("warning_or_error") or "not run",
            }
        )
    destination = ROOT / "results" / "research_lite_summary.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def write_coverage_model_summary() -> Path:
    fields = [
        "model_id",
        "coverage_percent",
        "Cd_atoms",
        "Te_atoms",
        "Cu_atoms",
        "total_atoms",
        "Cu2Te_repeat_count",
        "Cu2Te_atomic_plane_count",
        "Cu2Te_z_span_angstrom",
        "top_termination",
        "interface_contact_elements",
        "interface_minimum_distance_angstrom",
        "minimum_distance_angstrom",
        "substrate_area_angstrom2",
        "lateral_units_present",
        "lateral_units_total",
        "film_morphology",
        "stripe_edge_direction",
        "stripe_periodicity",
        "prototype_only",
    ]
    rows = []
    for model_id in ("C0", "C50", "C100"):
        meta = _read_json(ROOT / "coverage_models" / model_id / "model.json") or {}
        counts = meta.get("counts", {})
        rows.append(
            {
                "model_id": model_id,
                "coverage_percent": meta.get("coverage_percent"),
                "Cd_atoms": counts.get("Cd", 0),
                "Te_atoms": counts.get("Te", 0),
                "Cu_atoms": counts.get("Cu", 0),
                "total_atoms": meta.get("total_atoms"),
                "Cu2Te_repeat_count": meta.get("cu2te_repeat_count"),
                "Cu2Te_atomic_plane_count": meta.get("cu2te_atomic_plane_count"),
                "Cu2Te_z_span_angstrom": meta.get("cu2te_z_span_angstrom"),
                "top_termination": meta.get("top_termination"),
                "interface_contact_elements": meta.get("interface_contact_elements"),
                "interface_minimum_distance_angstrom": _blank(meta.get("interface_minimum_distance_angstrom")),
                "minimum_distance_angstrom": meta.get("minimum_distance_angstrom"),
                "substrate_area_angstrom2": meta.get("lateral_area_angstrom2"),
                "lateral_units_present": meta.get("lateral_cu2te_units_present"),
                "lateral_units_total": meta.get("lateral_cu2te_units_total_at_full_coverage"),
                "film_morphology": meta.get("film_morphology"),
                "stripe_edge_direction": meta.get("stripe_edge_direction"),
                "stripe_periodicity": meta.get("stripe_periodicity"),
                "prototype_only": meta.get("prototype_only"),
            }
        )
    destination = ROOT / "results" / "coverage_model_summary.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def write_relative_coverage_formation_energy() -> Path:
    fields = [
        "model_id",
        "coverage_percent",
        "Cu2Te_formula_units_n",
        "substrate_area_angstrom2",
        "E_Ctheta_hartree_research_lite",
        "E_C0_hartree_research_lite",
        "E_bulk_Cu2Te_per_formula_unit_hartree_research_lite",
        "relative_coverage_formation_energy_ev_per_angstrom2",
        "relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit",
        "status",
        "warning",
    ]
    bulk = _read_json(ROOT / "research_lite" / "runs" / "cu2te_bulk" / "output.parsed.json") or {}
    # The source bulk cell has two Cu2Te formula units. Its energy may be real,
    # but coverage energies remain blank until C0/C50/C100 research_lite runs exist.
    bulk_per_fu = bulk.get("total_energy_hartree") / 2.0 if bulk.get("program_completed") else None
    rows = []
    # C0 is structurally identical to B0, so the B0 research_lite task is the
    # single canonical zero-coverage calculation.
    c0 = _read_json(ROOT / "research_lite" / "runs" / "B0" / "output.parsed.json")
    c0_energy = c0.get("total_energy_hartree") if c0 and c0.get("research_output_complete") else None
    for model_id in ("C0", "C50", "C100"):
        meta = _read_json(ROOT / "coverage_models" / model_id / "model.json") or {}
        counts = meta.get("counts", {})
        n_formula = int(counts.get("Cu", 0) / 2)
        run_id = "B0" if model_id == "C0" else model_id
        parsed = _read_json(ROOT / "research_lite" / "runs" / run_id / "output.parsed.json")
        energy = parsed.get("total_energy_hartree") if parsed and parsed.get("research_output_complete") else None
        per_area = per_formula = None
        if energy is not None and c0_energy is not None and bulk_per_fu is not None:
            numerator_ev = (energy - c0_energy - n_formula * bulk_per_fu) * HARTREE_TO_EV
            per_area = numerator_ev / float(meta["lateral_area_angstrom2"])
            per_formula = 0.0 if n_formula == 0 else numerator_ev / n_formula
        rows.append(
            {
                "model_id": model_id,
                "coverage_percent": meta.get("coverage_percent"),
                "Cu2Te_formula_units_n": n_formula,
                "substrate_area_angstrom2": meta.get("lateral_area_angstrom2"),
                "E_Ctheta_hartree_research_lite": _blank(energy),
                "E_C0_hartree_research_lite": _blank(c0_energy),
                "E_bulk_Cu2Te_per_formula_unit_hartree_research_lite": _blank(bulk_per_fu),
                "relative_coverage_formation_energy_ev_per_angstrom2": _blank(per_area),
                "relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit": _blank(per_formula),
                "status": "ready_to_compute" if per_area is not None else "not_calculated_missing_research_lite_coverage_energies",
                "warning": "相对覆盖形成能；不得用 smoke 能量填充，也不是绝对表面能。",
            }
        )
    destination = ROOT / "results" / "relative_coverage_formation_energy.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def write_dft_proxy_summary() -> Path:
    fields = [
        "model_id",
        "coverage_percent",
        "research_lite_actually_run",
        "work_function_ev",
        "normalized_DOS_near_EF_per_ev",
        "interface_charge_transfer_e",
        "potential_barrier_proxy_ev",
        "status",
        "warning",
    ]
    rows = []
    for model_id, meta_path in (
        ("B0", ROOT / "models" / "B0" / "model.json"),
        ("C50", ROOT / "coverage_models" / "C50" / "model.json"),
        ("C100", ROOT / "coverage_models" / "C100" / "model.json"),
        ("H1", ROOT / "models" / "H1" / "model.json"),
        ("H2", ROOT / "models" / "H2" / "model.json"),
    ):
        meta = _read_json(meta_path) or {}
        parsed = _read_json(ROOT / "research_lite" / "runs" / model_id / "output.parsed.json")
        rows.append(
            {
                "model_id": model_id,
                "coverage_percent": meta.get("coverage_percent", 0 if model_id == "B0" else 100),
                "research_lite_actually_run": bool(parsed and parsed.get("actually_run")),
                "work_function_ev": "",
                "normalized_DOS_near_EF_per_ev": _blank(parsed.get("normalized_dos_near_fermi_per_ev") if parsed and parsed.get("research_output_complete") else None),
                "interface_charge_transfer_e": "",
                "potential_barrier_proxy_ev": "",
                "status": "not_calculated",
                "warning": "极性 CdTe(111) 薄片仅可用于收敛后相对趋势；当前不得解释为接触电阻或器件效率。",
            }
        )
    destination = ROOT / "results" / "dft_proxy_summary.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def main() -> int:
    (ROOT / "results").mkdir(exist_ok=True)
    for output in (write_coverage_model_summary(), write_research_summary(), write_relative_coverage_formation_energy(), write_dft_proxy_summary()):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
