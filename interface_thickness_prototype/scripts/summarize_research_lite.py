from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import ROOT
from parse_cp2k_output import HARTREE_TO_EV


ALIASES = {"B0": "C0", "H1": "C100"}
COVERAGE = {"B0": 0.0, "C50": 50.0, "H1": 100.0, "H2": 100.0}
MODEL_META = {
    "B0": ROOT / "models" / "B0" / "model.json",
    "C50": ROOT / "coverage_models" / "C50" / "model.json",
    "H1": ROOT / "models" / "H1" / "model.json",
    "H2": ROOT / "models" / "H2" / "model.json",
}


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _parsed(task_id: str) -> dict:
    return _read_json(
        ROOT / "research_lite" / "runs" / task_id / "output.parsed.json"
    )


def _metadata(task_id: str) -> dict:
    return _read_json(
        ROOT / "research_lite" / "runs" / task_id / "run_metadata.json"
    )


def _blank(value):
    return "" if value is None else value


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_final_model_status() -> Path:
    fields = [
        "canonical_model_id",
        "aliases",
        "atom_count",
        "coverage_percent",
        "Cu2Te_repeat_count",
        "Cu2Te_thickness_angstrom",
        "actually_run",
        "return_code",
        "timed_out",
        "normal_program_end",
        "SCF_converged",
        "energy_valid",
        "electronic_outputs_complete",
        "SCF_steps",
        "SCF_iterations_observed",
        "last_SCF_iteration_index",
        "total_energy_hartree",
        "cp2k_warning_count",
        "unique_warning_messages",
        "warning_message_counts_json",
        "kpoint_mesh",
        "kpoint_status",
        "wall_time_seconds",
        "termination_reason",
        "confirmed_stop_cause",
        "warning_or_error",
        "prototype_only",
    ]
    rows = []
    bulk_k222_valid = bool(_parsed("cu2te_bulk_k222").get("energy_valid", False))
    for task_id in ("cu2te_bulk", "cu2te_bulk_k222", "B0", "C50", "H1", "H2"):
        parsed = _parsed(task_id)
        metadata = _metadata(task_id)
        if task_id.startswith("cu2te_bulk"):
            atom_count = 6
            coverage = repeat = thickness = None
            prototype_only = True
        else:
            model = _read_json(MODEL_META[task_id])
            atom_count = model.get("total_atoms")
            coverage = COVERAGE[task_id]
            repeat = model.get("cu2te_repeat_count")
            thickness = model.get("cu2te_z_span_angstrom")
            prototype_only = bool(model.get("prototype_only", True))
        kpoint_status = parsed.get("kpoint_status_warning", "")
        if task_id == "cu2te_bulk" and bulk_k222_valid:
            kpoint_status = (
                "Gamma-only bulk reference; a separate 2x2x2 minimum check "
                "completed and differs strongly, so neither mesh is a "
                "k-point-converged reference."
            )
        rows.append(
            {
                "canonical_model_id": task_id,
                "aliases": ALIASES.get(task_id, ""),
                "atom_count": atom_count,
                "coverage_percent": _blank(coverage),
                "Cu2Te_repeat_count": _blank(repeat),
                "Cu2Te_thickness_angstrom": _blank(thickness),
                "actually_run": bool(parsed.get("actually_run", False)),
                "return_code": _blank(metadata.get("return_code")),
                "timed_out": bool(metadata.get("timed_out", False)),
                "normal_program_end": bool(
                    parsed.get("normal_program_end", False)
                ),
                "SCF_converged": bool(parsed.get("scf_converged", False)),
                "energy_valid": bool(parsed.get("energy_valid", False)),
                "electronic_outputs_complete": bool(
                    parsed.get("electronic_outputs_complete", False)
                ),
                "SCF_steps": _blank(parsed.get("scf_steps")),
                "SCF_iterations_observed": _blank(
                    parsed.get("scf_iterations_observed")
                ),
                "last_SCF_iteration_index": _blank(
                    parsed.get("last_scf_iteration_index")
                ),
                "total_energy_hartree": _blank(parsed.get("total_energy_hartree")),
                "cp2k_warning_count": _blank(parsed.get("cp2k_warning_count")),
                "unique_warning_messages": " | ".join(
                    parsed.get("unique_warning_messages", [])
                ),
                "warning_message_counts_json": (
                    json.dumps(
                        parsed.get("warning_message_counts", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    if parsed.get("actually_run")
                    else ""
                ),
                "kpoint_mesh": parsed.get("kpoint_mesh", ""),
                "kpoint_status": kpoint_status,
                "wall_time_seconds": _blank(parsed.get("wall_time_seconds")),
                "termination_reason": metadata.get(
                    "termination_reason", parsed.get("termination_reason", "not_run")
                ),
                "confirmed_stop_cause": metadata.get("confirmed_stop_cause") or "",
                "warning_or_error": parsed.get("warning_or_error") or "",
                "prototype_only": prototype_only,
            }
        )
    destination = ROOT / "results" / "final_model_status.csv"
    _write_csv(destination, fields, rows)
    return destination


def write_coverage_model_summary() -> Path:
    fields = [
        "model_id",
        "canonical_calculation_id",
        "coverage_percent",
        "Cd_atoms",
        "Te_atoms",
        "Cu_atoms",
        "total_atoms",
        "Cu2Te_formula_units",
        "Cu2Te_repeat_count",
        "Cu2Te_atomic_plane_count",
        "Cu2Te_z_span_angstrom",
        "top_termination",
        "interface_contact_elements",
        "substrate_area_angstrom2",
        "prototype_only",
    ]
    rows = []
    sources = {
        "C0": ROOT / "coverage_models" / "C0" / "model.json",
        "C50": ROOT / "coverage_models" / "C50" / "model.json",
        "C100": ROOT / "coverage_models" / "C100" / "model.json",
    }
    canonical = {"C0": "B0", "C50": "C50", "C100": "H1"}
    for model_id, path in sources.items():
        meta = _read_json(path)
        counts = meta.get("counts", {})
        rows.append(
            {
                "model_id": model_id,
                "canonical_calculation_id": canonical[model_id],
                "coverage_percent": meta.get("coverage_percent"),
                "Cd_atoms": counts.get("Cd", 0),
                "Te_atoms": counts.get("Te", 0),
                "Cu_atoms": counts.get("Cu", 0),
                "total_atoms": meta.get("total_atoms"),
                "Cu2Te_formula_units": counts.get("Cu", 0) // 2,
                "Cu2Te_repeat_count": meta.get("cu2te_repeat_count"),
                "Cu2Te_atomic_plane_count": meta.get("cu2te_atomic_plane_count"),
                "Cu2Te_z_span_angstrom": meta.get("cu2te_z_span_angstrom"),
                "top_termination": meta.get("top_termination"),
                "interface_contact_elements": meta.get("interface_contact_elements"),
                "substrate_area_angstrom2": meta.get("lateral_area_angstrom2"),
                "prototype_only": meta.get("prototype_only", True),
            }
        )
    destination = ROOT / "results" / "coverage_model_summary.csv"
    _write_csv(destination, fields, rows)
    return destination


def write_kpoint_reference_check() -> Path:
    fields = [
        "reference_id",
        "formula_units_in_cell",
        "gamma_energy_hartree",
        "k222_energy_hartree",
        "delta_E_k222_minus_gamma_hartree_per_Cu2Te_formula_unit",
        "delta_E_k222_minus_gamma_ev_per_Cu2Te_formula_unit",
        "gamma_energy_valid",
        "k222_energy_valid",
        "status",
        "limitations",
    ]
    gamma = _parsed("cu2te_bulk")
    k222 = _parsed("cu2te_bulk_k222")
    formula_units = 2
    gamma_energy = (
        float(gamma["total_energy_hartree"]) if gamma.get("energy_valid") else None
    )
    k222_energy = (
        float(k222["total_energy_hartree"]) if k222.get("energy_valid") else None
    )
    delta_ha = delta_ev = None
    if gamma_energy is not None and k222_energy is not None:
        delta_ha = (k222_energy - gamma_energy) / formula_units
        delta_ev = delta_ha * HARTREE_TO_EV
    row = {
        "reference_id": "Cu2Te_bulk_same_6_atom_cell",
        "formula_units_in_cell": formula_units,
        "gamma_energy_hartree": _blank(gamma_energy),
        "k222_energy_hartree": _blank(k222_energy),
        "delta_E_k222_minus_gamma_hartree_per_Cu2Te_formula_unit": _blank(
            delta_ha
        ),
        "delta_E_k222_minus_gamma_ev_per_Cu2Te_formula_unit": _blank(delta_ev),
        "gamma_energy_valid": bool(gamma.get("energy_valid")),
        "k222_energy_valid": bool(k222.get("energy_valid")),
        "status": (
            "minimum_kpoint_difference_computed"
            if delta_ha is not None
            else "blank_missing_valid_gamma_or_k222_energy"
        ),
        "limitations": (
            "Single Gamma-to-2x2x2 comparison at fixed bulk geometry; it is not "
            "a k-point convergence study. A large difference warns that Gamma "
            "bulk and Gamma slab energies are not a converged common reference."
        ),
    }
    destination = ROOT / "results" / "kpoint_reference_check.csv"
    _write_csv(destination, fields, [row])
    return destination


def write_relative_coverage_formation_energy() -> tuple[Path, list[dict]]:
    fields = [
        "model_id",
        "canonical_calculation_id",
        "coverage_percent",
        "Cu2Te_formula_units_n",
        "substrate_area_angstrom2",
        "E_Ctheta_hartree_research_lite",
        "E_B0_hartree_research_lite",
        "E_bulk_Cu2Te_per_formula_unit_hartree_research_lite",
        "E_bulk_reference_kpoint_mesh",
        "slab_kpoint_mesh",
        "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2",
        "fixed_geometry_relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit",
        "energy_valid",
        "status",
        "limitations",
    ]
    bulk = _parsed("cu2te_bulk_k222")
    bulk_energy_per_fu = (
        float(bulk["total_energy_hartree"]) / 2.0
        if bulk.get("energy_valid")
        else None
    )
    b0 = _parsed("B0")
    b0_energy = (
        float(b0["total_energy_hartree"]) if b0.get("energy_valid") else None
    )
    rows = []
    for model_id, task_id in (("C0", "B0"), ("C50", "C50"), ("C100", "H1")):
        meta = _read_json(ROOT / "coverage_models" / model_id / "model.json")
        parsed = _parsed(task_id)
        energy = (
            float(parsed["total_energy_hartree"])
            if parsed.get("energy_valid")
            else None
        )
        formula_units = int(meta.get("counts", {}).get("Cu", 0) // 2)
        area = float(meta.get("lateral_area_angstrom2"))
        per_area = per_formula = None
        if (
            energy is not None
            and b0_energy is not None
            and bulk_energy_per_fu is not None
        ):
            numerator_ev = (
                energy - b0_energy - formula_units * bulk_energy_per_fu
            ) * HARTREE_TO_EV
            per_area = numerator_ev / area
            per_formula = (
                numerator_ev / formula_units if formula_units > 0 else None
            )
        rows.append(
            {
                "model_id": model_id,
                "canonical_calculation_id": task_id,
                "coverage_percent": meta.get("coverage_percent"),
                "Cu2Te_formula_units_n": formula_units,
                "substrate_area_angstrom2": area,
                "E_Ctheta_hartree_research_lite": _blank(energy),
                "E_B0_hartree_research_lite": _blank(b0_energy),
                "E_bulk_Cu2Te_per_formula_unit_hartree_research_lite": _blank(
                    bulk_energy_per_fu
                ),
                "E_bulk_reference_kpoint_mesh": bulk.get("kpoint_mesh", ""),
                "slab_kpoint_mesh": parsed.get("kpoint_mesh", ""),
                "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2": _blank(
                    per_area
                ),
                "fixed_geometry_relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit": _blank(
                    per_formula
                ),
                "energy_valid": bool(
                    parsed.get("energy_valid")
                    and b0.get("energy_valid")
                    and bulk.get("energy_valid")
                ),
                "status": (
                    "computed_from_real_converged_research_lite_energies"
                    if per_area is not None
                    else "blank_missing_one_or_more_valid_research_lite_energies"
                ),
                "limitations": (
                    "固定初始几何相对覆盖形成能，不是绝对表面能；界面未弛豫。"
                    "Cu2Te 参考仅做 2x2x2 最小检查，薄片仍为 Gamma；"
                    "极性 CdTe(111) 和原型晶相都未完成科研级收敛验证。"
                ),
            }
        )
    destination = ROOT / "results" / "relative_coverage_formation_energy.csv"
    _write_csv(destination, fields, rows)
    return destination, rows


def write_dft_proxy_summary() -> tuple[Path, list[dict]]:
    fields = [
        "model_id",
        "aliases",
        "coverage_percent",
        "Cu2Te_repeat_count",
        "energy_valid",
        "electronic_outputs_complete",
        "KS_orbital_count_near_EF_in_window",
        "KS_orbital_density_near_EF_per_ev_per_substrate_area",
        "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit",
        "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom",
        "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom",
        "cp2k_normalized_histogram_fraction_near_EF_per_ev",
        "vacuum_level_top_ev",
        "vacuum_level_bottom_ev",
        "top_surface_work_function_proxy_ev",
        "bottom_work_function_diagnostic_ev",
        "top_vacuum_plateau_status",
        "bottom_vacuum_plateau_status",
        "cp2k_warning_count",
        "last_MO_smearing_warning_count",
        "last_MO_smearing_warning_persistent",
        "warning_review_required",
        "fatal_warning_detected",
        "termination_reason",
        "limitations",
    ]
    rows = []
    for task_id in ("B0", "C50", "H1", "H2"):
        parsed = _parsed(task_id)
        metadata = _metadata(task_id)
        model = _read_json(MODEL_META[task_id])
        vacuum = parsed.get("vacuum_plateau_analysis", {})
        top = vacuum.get("top", {})
        bottom = vacuum.get("bottom", {})
        complete = bool(parsed.get("electronic_outputs_complete"))

        def value(key: str):
            return _blank(parsed.get(key) if complete else None)

        rows.append(
            {
                "model_id": task_id,
                "aliases": ALIASES.get(task_id, ""),
                "coverage_percent": COVERAGE[task_id],
                "Cu2Te_repeat_count": model.get("cu2te_repeat_count"),
                "energy_valid": bool(parsed.get("energy_valid")),
                "electronic_outputs_complete": complete,
                "KS_orbital_count_near_EF_in_window": value(
                    "KS_orbital_count_near_EF_in_window"
                ),
                "KS_orbital_density_near_EF_per_ev_per_substrate_area": value(
                    "KS_orbital_density_near_EF_per_ev_per_substrate_area"
                ),
                "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit": value(
                    "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit"
                ),
                "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom": value(
                    "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom"
                ),
                "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom": value(
                    "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom"
                ),
                "cp2k_normalized_histogram_fraction_near_EF_per_ev": value(
                    "cp2k_normalized_histogram_fraction_near_EF_per_ev"
                ),
                "vacuum_level_top_ev": value("vacuum_level_top_ev"),
                "vacuum_level_bottom_ev": value("vacuum_level_bottom_ev"),
                "top_surface_work_function_proxy_ev": value("work_function_top_ev"),
                "bottom_work_function_diagnostic_ev": value(
                    "work_function_bottom_ev"
                ),
                "top_vacuum_plateau_status": top.get(
                    "detection_status", "not_run"
                ),
                "bottom_vacuum_plateau_status": bottom.get(
                    "detection_status", "not_run"
                ),
                "cp2k_warning_count": _blank(parsed.get("cp2k_warning_count")),
                "last_MO_smearing_warning_count": _blank(
                    parsed.get("last_MO_smearing_warning_count")
                ),
                "last_MO_smearing_warning_persistent": bool(
                    parsed.get("last_MO_smearing_warning_persistent", False)
                ),
                "warning_review_required": bool(
                    parsed.get("warning_review_required", False)
                ),
                "fatal_warning_detected": bool(
                    parsed.get("fatal_warning_detected", False)
                ),
                "termination_reason": metadata.get("termination_reason", "not_run"),
                "limitations": (
                    "E-EF only for spectra; projected values are AO spectral-weight "
                    "proxies. Work-function values require a reliable continuous "
                    "vacuum plateau. No DFT contact resistance is calculated."
                ),
            }
        )
    destination = ROOT / "results" / "dft_proxy_summary.csv"
    _write_csv(destination, fields, rows)
    return destination, rows


def _float_or_none(value):
    if value in ("", None):
        return None
    return float(value)


def plot_coverage_formation_energy(rows: list[dict]) -> Path:
    destination = ROOT / "plots" / "coverage_formation_energy.png"
    destination.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    x = [float(row["coverage_percent"]) for row in rows]
    y = [
        _float_or_none(
            row[
                "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2"
            ]
        )
        for row in rows
    ]
    valid_x = [xx for xx, yy in zip(x, y) if yy is not None]
    valid_y = [yy for yy in y if yy is not None]
    if valid_x:
        ax.plot(valid_x, valid_y, "o-", color="#0F766E", lw=2)
    for xx, yy, row in zip(x, y, rows):
        if yy is None:
            ax.text(
                xx,
                0.05,
                f"{row['model_id']}\nno valid energy",
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="bottom",
                color="#9A3412",
                fontsize=9,
            )
    ax.axhline(0, color="#94A3B8", lw=0.8)
    ax.set_xticks([0, 50, 100])
    ax.set_xlabel("Cu₂Te coverage (%)")
    ax.set_ylabel("Fixed-geometry relative coverage formation energy (eV/Å²)")
    ax.set_title("Prototype fixed-geometry coverage-energy trend")
    ax.grid(axis="y", color="#E2E8F0", lw=0.8)
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)
    return destination


def plot_coverage_electronic_proxies(rows: list[dict]) -> Path:
    destination = ROOT / "plots" / "coverage_electronic_proxies.png"
    coverage_rows = [row for row in rows if row["model_id"] in {"B0", "C50", "H1"}]
    x = [float(row["coverage_percent"]) for row in coverage_rows]
    metrics = [
        (
            "KS_orbital_density_near_EF_per_ev_per_substrate_area",
            "KS orbital DOS near EF\n[orbitals/(eV·Å²)]",
        ),
        (
            "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit",
            "Cu₂Te projected weight near EF\n[weight/(eV·formula unit)]",
        ),
        (
            "CdTe_interface_projected_spectral_weight_near_EF_per_ev_per_atom",
            "CdTe interface projected weight\n[weight/(eV·interface atom)]",
        ),
        (
            "Cu2Te_interface_projected_spectral_weight_near_EF_per_ev_per_atom",
            "Cu₂Te interface projected weight\n[weight/(eV·interface atom)]",
        ),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0), sharex=True)
    for ax, (field, ylabel) in zip(axes.flat, metrics):
        values = [_float_or_none(row[field]) for row in coverage_rows]
        valid = [(xx, yy) for xx, yy in zip(x, values) if yy is not None]
        if valid:
            ax.plot(
                [item[0] for item in valid],
                [item[1] for item in valid],
                "o-",
                color="#2563EB",
                lw=1.8,
            )
        else:
            ax.text(
                0.5,
                0.5,
                "No complete electronic output",
                transform=ax.transAxes,
                ha="center",
                va="center",
                color="#9A3412",
            )
        for xx, value, row in zip(x, values, coverage_rows):
            if row["model_id"] == "H1" and value is None:
                ax.text(
                    xx,
                    0.04,
                    "H1\nno complete output",
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    color="#9A3412",
                    fontsize=8,
                )
        ax.set_ylabel(ylabel)
        ax.set_xticks([0, 50, 100])
        ax.grid(axis="y", color="#E2E8F0", lw=0.8)
    for ax in axes[-1, :]:
        ax.set_xlabel("Cu₂Te coverage (%)")
    fig.suptitle("Size-normalized research_lite electronic proxies (E−EF)")
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)
    return destination


def _read_spectrum(task_id: str) -> dict[str, np.ndarray] | None:
    path = ROOT / "research_lite" / "runs" / task_id / "spectral_proxies.csv"
    if not path.is_file():
        return None
    data = np.genfromtxt(path, delimiter=",", names=True)
    return {name: np.asarray(data[name], dtype=float) for name in data.dtype.names}


def plot_thickness_h1_h2() -> Path:
    destination = ROOT / "plots" / "thickness_H1_H2_DOS.png"
    spectra = {"H1": _read_spectrum("H1"), "H2": _read_spectrum("H2")}
    both_available = all(spectrum is not None for spectrum in spectra.values())
    columns = [
        (
            "KS_orbital_DOS_per_ev_per_substrate_angstrom2",
            "KS orbital DOS / area\n[orbitals/(eV·Å²)]",
        ),
        (
            "Cu2Te_projected_spectral_weight_per_ev_per_formula_unit",
            "Cu₂Te projected weight / FU\n[weight/(eV·FU)]",
        ),
        (
            "Cu2Te_interface_projected_spectral_weight_per_ev_per_atom",
            "Cu₂Te interface weight / atom\n[weight/(eV·atom)]",
        ),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(8.2, 9.2), sharex=True)
    colors = {"H1": "#2563EB", "H2": "#DC2626"}
    any_curve = False
    for ax, (column, ylabel) in zip(axes, columns):
        if both_available:
            for task_id, spectrum in spectra.items():
                if column not in spectrum:
                    continue
                y = spectrum[column]
                mask = np.isfinite(y)
                if np.any(mask):
                    any_curve = True
                    ax.plot(
                        spectrum["energy_minus_fermi_ev"][mask],
                        y[mask],
                        label=task_id,
                        color=colors[task_id],
                        lw=1.3,
                    )
        ax.axvline(0, color="#111827", ls="--", lw=0.8)
        ax.set_xlim(-2.0, 2.0)
        ax.set_ylabel(ylabel)
        ax.grid(color="#E2E8F0", lw=0.7)
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend()
    if not both_available or not any_curve:
        axes[1].text(
            0.5,
            0.5,
            "H1 and H2 complete spectra are not both available;\n"
            "no thickness curve is asserted",
            transform=axes[1].transAxes,
            ha="center",
            va="center",
            color="#9A3412",
        )
    axes[-1].set_xlabel("Energy relative to Fermi level, E−EF (eV)")
    fig.suptitle("H1/H2 size-normalized thickness proxies")
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)
    return destination


def plot_work_function(rows: list[dict]) -> Path:
    destination = ROOT / "plots" / "work_function_trend.png"
    labels = [row["model_id"] for row in rows]
    values = [_float_or_none(row["top_surface_work_function_proxy_ev"]) for row in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    valid_indices = [index for index, value in enumerate(values) if value is not None]
    if valid_indices:
        ax.plot(
            valid_indices,
            [values[index] for index in valid_indices],
            "o-",
            color="#7C3AED",
            lw=2,
        )
    for index, value, row in zip(range(len(rows)), values, rows):
        if value is None:
            ax.scatter(index, 0, marker="x", color="#9A3412", s=60)
            ax.text(
                index,
                0,
                row["top_vacuum_plateau_status"],
                rotation=45,
                ha="left",
                va="bottom",
                fontsize=8,
                color="#9A3412",
            )
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel("Top-surface work-function proxy (eV)")
    ax.set_title("Vacuum-aligned top-surface proxy; unreliable plateaus omitted")
    ax.grid(axis="y", color="#E2E8F0", lw=0.8)
    fig.tight_layout()
    fig.savefig(destination, dpi=180)
    plt.close(fig)
    return destination


def write_paper_results_summary(
    formation_rows: list[dict],
    proxy_rows: list[dict],
) -> Path:
    task_lines = []
    for task_id in ("cu2te_bulk", "cu2te_bulk_k222", "B0", "C50", "H1", "H2"):
        parsed = _parsed(task_id)
        metadata = _metadata(task_id)
        if parsed.get("energy_valid"):
            task_lines.append(
                f"- {task_id}: 真实运行并通过能量门禁；SCF {parsed.get('scf_steps')} 步，"
                f"E = {parsed.get('total_energy_hartree'):.12f} Ha，"
                f"{parsed.get('wall_time_seconds'):.2f} s，"
                f"CP2K 警告 {parsed.get('cp2k_warning_count')} 条。"
            )
        elif parsed.get("actually_run"):
            task_lines.append(
                f"- {task_id}: 已真实尝试但未通过能量门禁；"
                f"停止原因 `{metadata.get('termination_reason')}`，"
                f"观察到 {parsed.get('scf_iterations_observed')} 次 SCF 迭代，"
                f"{metadata.get('wall_time_seconds'):.2f} s，"
                f"CP2K 警告 {parsed.get('cp2k_warning_count')} 条；"
                f"{parsed.get('warning_or_error') or '严格输出条件未满足'}。"
            )
        else:
            task_lines.append(f"- {task_id}: 未运行。")
    available_formation = [
        row
        for row in formation_rows
        if row[
            "fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2"
        ]
        != ""
    ]
    trend_text = (
        "、".join(
            f"{row['model_id']}={float(row['fixed_geometry_relative_coverage_formation_energy_ev_per_angstrom2']):.6f} eV/Å²"
            for row in available_formation
        )
        if available_formation
        else "覆盖能趋势尚无足够的有效 research_lite 能量，数值保持空白"
    )
    reliable_work = [
        row for row in proxy_rows if row["top_surface_work_function_proxy_ev"] != ""
    ]
    work_text = (
        "、".join(
            f"{row['model_id']}={float(row['top_surface_work_function_proxy_ev']):.4f} eV"
            for row in reliable_work
        )
        if reliable_work
        else "没有模型获得可靠的顶部真空平台，功函数代理保持空白"
    )
    gamma = _parsed("cu2te_bulk")
    k222 = _parsed("cu2te_bulk_k222")
    kpoint_delta_ev = None
    if gamma.get("energy_valid") and k222.get("energy_valid"):
        kpoint_delta_ev = (
            (
                float(k222["total_energy_hartree"])
                - float(gamma["total_energy_hartree"])
            )
            / 2.0
            * HARTREE_TO_EV
        )
    kpoint_text = (
        f"{kpoint_delta_ev:.6f} eV/Cu₂Te formula unit "
        "(E₂×₂×₂−EΓ；量级很大，不能称为已收敛)"
        if kpoint_delta_ev is not None
        else "缺少有效的 Gamma 或 2×2×2 体相能量"
    )
    content = f"""# 最小论文功能框架：真实结果与边界

## 1. 本轮真实计算证据

{chr(10).join(task_lines)}

所有 smoke 总能量仍只作为管线证据，不参与本页覆盖能或电子结构比较。

## 2. 可以陈述的原型趋势

- 固定初始几何相对覆盖形成能：{trend_text}。
- Cu₂Te 最低 k 点差值：{kpoint_text}。
- C50 的负覆盖形成能量级受未弛豫几何、Gamma 薄片与 2×2×2 bulk 混合参考、极性薄片和未完成收敛测试共同影响，只能视为原型筛查数值，不能据此排序实验稳定性。
- 顶部功函数代理：{work_text}。
- 可比较的电子结构量只包括：由唯一 KS 轨道列表按统一 0.10 eV FWHM 高斯展宽得到的每面积谱、每 Cu₂Te 化学式单位投影谱权重，以及每个界面原子的投影谱权重。
- 所有谱以 E−EF 对齐，只比较形状和规范化代理；这不是跨模型的真空能级对齐。

## 3. 合理但仍需实验或更严谨计算验证的解释

- 若覆盖率或厚度改变了界面附近的投影谱权重，可作为界面电子态变化的 DFT 代理指标。
- 若未来获得可靠连续真空平台，顶部功函数代理可与实验接触电阻、串联电阻、Voc 和膜厚做相关性比较。
- 固定几何能量可以筛查原型趋势，但结构弛豫、取向、晶相、k 点和横向超胞收敛都可能改变排序。

## 4. 当前不能声称

- 不能声称 DFT 直接计算了真实接触电阻或器件效率。
- 不能声称已经预测最佳实验膜厚。
- 不能声称当前 Cu₂Te 结构就是实验 Cu₂₋ₓTe 的唯一真实晶相。
- 不能直接比较不同模型的原始 CP2K Fermi 能量。
- 不能把未弛豫的固定初始几何相对覆盖形成能称为绝对表面能。
- 不能把 Gamma 薄片结果称为完成 k 点收敛；Cu₂Te 2×2×2 也只是一次最低检查。
"""
    destination = ROOT / "PAPER_RESULTS_SUMMARY.md"
    destination.write_text(content, encoding="utf-8", newline="\n")
    return destination


def main() -> int:
    outputs = [
        write_final_model_status(),
        write_coverage_model_summary(),
        write_kpoint_reference_check(),
    ]
    formation_path, formation_rows = write_relative_coverage_formation_energy()
    proxy_path, proxy_rows = write_dft_proxy_summary()
    outputs.extend([formation_path, proxy_path])
    outputs.extend(
        [
            plot_coverage_formation_energy(formation_rows),
            plot_coverage_electronic_proxies(proxy_rows),
            plot_thickness_h1_h2(),
            plot_work_function(proxy_rows),
            write_paper_results_summary(formation_rows, proxy_rows),
        ]
    )
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
