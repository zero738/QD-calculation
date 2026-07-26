from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from ase.io import read

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import load_config, minimum_distance
from parse_cp2k_output import parse_output
from parse_research_lite_output import (
    _last_mo_smearing_persistent,
    gaussian_spectrum,
    parse_research_run,
)


def _meta(kind: str, model_id: str) -> dict:
    return json.loads(
        (ROOT / kind / model_id / "model.json").read_text(encoding="utf-8")
    )


def _manifest() -> list[dict]:
    return json.loads(
        (ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8")
    )


def test_coverage_counts_stoichiometry_and_exact_endpoints():
    b0 = read(ROOT / "models" / "B0" / "structure.extxyz")
    h1 = read(ROOT / "models" / "H1" / "structure.extxyz")
    c0 = read(ROOT / "coverage_models" / "C0" / "structure.extxyz")
    c50 = read(ROOT / "coverage_models" / "C50" / "structure.extxyz")
    c100 = read(ROOT / "coverage_models" / "C100" / "structure.extxyz")
    assert [len(c0), len(c50), len(c100)] == [78, 126, 174]
    assert c0.get_chemical_symbols() == b0.get_chemical_symbols()
    assert c100.get_chemical_symbols() == h1.get_chemical_symbols()
    assert np.allclose(c0.positions, b0.positions) and np.allclose(c0.cell, b0.cell)
    assert np.allclose(c100.positions, h1.positions) and np.allclose(c100.cell, h1.cell)
    for array_name in ("component", "region", "fixed"):
        assert np.array_equal(c0.arrays[array_name], b0.arrays[array_name])
        assert np.array_equal(c100.arrays[array_name], h1.arrays[array_name])
    assert Counter(c50.get_chemical_symbols()) == Counter(
        {"Cd": 39, "Te": 55, "Cu": 32}
    )
    film = c50[78:]
    assert Counter(film.get_chemical_symbols()) == Counter({"Cu": 32, "Te": 16})


def test_c50_retains_complete_contiguous_lateral_units_and_safe_distances():
    c50 = read(ROOT / "coverage_models" / "C50" / "structure.extxyz")
    film = c50[78:]
    fractional = np.mod(film.get_scaled_positions(wrap=False), 1.0)
    i = np.floor((fractional[:, 0] + 1.0e-8) * 4).astype(int) % 4
    j = np.floor((fractional[:, 1] + 1.0e-8) * 4).astype(int) % 4
    occupied = []
    for ii in range(4):
        for jj in range(4):
            mask = (i == ii) & (j == jj)
            if not np.any(mask):
                continue
            occupied.append((ii, jj))
            assert Counter(np.asarray(film.get_chemical_symbols())[mask]) == Counter(
                {"Cu": 4, "Te": 2}
            )
    assert occupied == [(ii, jj) for ii in (1, 2) for jj in range(4)]
    assert minimum_distance(c50) >= 1.8


def test_region_derived_interface_groups_are_nonempty_and_thickness_consistent():
    tasks = {task["calculation_id"]: task for task in _manifest()}
    assert [tasks[key]["atom_count"] for key in ("B0", "C50", "H1", "H2")] == [
        78,
        126,
        174,
        270,
    ]
    groups = {
        key: {
            group["label"]: group["indices_1based"]
            for group in tasks[key]["ldos_groups"]
        }
        for key in ("B0", "C50", "H1", "H2")
    }
    assert len(groups["B0"]["CdTe_interface_top_Te"]) == 13
    assert len(groups["C50"]["CdTe_interface_top_Te"]) == 13
    assert len(groups["C50"]["Cu2Te_interface_bottom_Cu"]) == 16
    assert len(groups["H1"]["CdTe_interface_top_Te"]) == len(
        groups["H2"]["CdTe_interface_top_Te"]
    ) == 13
    assert len(groups["H1"]["Cu2Te_interface_bottom_Cu"]) == len(
        groups["H2"]["Cu2Te_interface_bottom_Cu"]
    ) == 32
    for model_id in ("B0", "C50", "H1", "H2"):
        atoms = read(ROOT / tasks[model_id]["source_structure"])
        regions = np.asarray(atoms.arrays["region"], dtype=str)
        symbols = np.asarray(atoms.get_chemical_symbols(), dtype=str)
        expected_cdte = set(
            np.flatnonzero(
                (regions == "interface_cdte_surface") & (symbols == "Te")
            )
            + 1
        )
        assert set(groups[model_id]["CdTe_interface_top_Te"]) == expected_cdte
        if model_id != "B0":
            expected_cu = set(
                np.flatnonzero(
                    (regions == "interface_cu2te_contact") & (symbols == "Cu")
                )
                + 1
            )
            assert set(groups[model_id]["Cu2Te_interface_bottom_Cu"]) == expected_cu


def test_coverage_interface_geometry_and_termination_are_invariant():
    metas = {
        model_id: _meta("coverage_models", model_id)
        for model_id in ("C0", "C50", "C100")
    }
    assert [metas[key]["coverage_percent"] for key in ("C0", "C50", "C100")] == [
        0.0,
        50.0,
        100.0,
    ]
    assert metas["C50"]["cu2te_repeat_count"] == metas["C100"][
        "cu2te_repeat_count"
    ] == 1
    assert metas["C50"]["top_termination"] == metas["C100"][
        "top_termination"
    ] == "Cu"
    assert metas["C50"]["interface_first_contact_element"] == metas["C100"][
        "interface_first_contact_element"
    ] == "Cu"
    assert np.isclose(
        metas["C50"]["cu2te_z_span_angstrom"],
        metas["C100"]["cu2te_z_span_angstrom"],
    )
    assert np.isclose(
        metas["C50"]["interface_minimum_distance_angstrom"],
        metas["C100"]["interface_minimum_distance_angstrom"],
    )


def test_research_lite_profile_and_energy_only_kpoint_checks_are_fully_written():
    config = load_config()
    research = config["cp2k"]["profiles"]["research_lite"]
    manifest = _manifest()
    assert [task["calculation_id"] for task in manifest] == [
        "cu2te_bulk",
        "B0",
        "C50",
        "H1",
        "H2",
    ]
    assert not list((ROOT / "research_lite" / "inputs" / "C100").glob("input*.inp"))
    assert next(task for task in manifest if task["calculation_id"] == "B0")[
        "result_aliases"
    ] == ["C0"]
    assert next(task for task in manifest if task["calculation_id"] == "H1")[
        "result_aliases"
    ] == ["C100"]
    for task in manifest:
        gamma = (ROOT / task["gamma_input"]).read_text(encoding="utf-8")
        kpoint_check = (ROOT / task["optional_kpoint_check_input"]).read_text(
            encoding="utf-8"
        )
        assert "&DIAGONALIZATION" in gamma and "&SMEAR ON" in gamma
        assert f"EPS_SCF {research['eps_scf']}" in gamma
        assert f"ADDED_MOS {research['added_mos']}" in gamma
        assert "&DOS ON" in gamma and "&PDOS ON" in gamma and "&LDOS" in gamma
        assert "&V_HARTREE_CUBE ON" in gamma and "&E_DENSITY_CUBE ON" in gamma
        assert "&KPOINTS" not in gamma
        expected_mesh = (
            [2, 2, 2] if task["calculation_id"] == "cu2te_bulk" else [2, 2, 1]
        )
        assert task["optional_kpoint_mesh"] == expected_mesh
        assert (
            f"SCHEME MONKHORST-PACK {' '.join(map(str, expected_mesh))}"
            in kpoint_check
        )
        for forbidden in (
            "&PDOS ON",
            "&DOS ON",
            "&V_HARTREE_CUBE ON",
            "&E_DENSITY_CUBE ON",
        ):
            assert forbidden not in kpoint_check
        assert "Energy-only k-point check" in kpoint_check


def test_cp2k_2024_3_check_evidence_matches_current_inputs():
    evidence = json.loads(
        (ROOT / "research_lite" / "cp2k_input_checks.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["cp2k_version"] == "CP2K version 2024.3"
    assert evidence["all_passed"] and len(evidence["results"]) == 10
    for result in evidence["results"]:
        path = ROOT / result["input_file"]
        assert result["check_passed"] and result["return_code"] == 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == result["input_sha256"]


def test_existing_bulk_output_reparse_counts_all_nonfatal_elpa_warnings():
    run_dir = ROOT / "research_lite" / "runs" / "cu2te_bulk"
    parsed = parse_research_run(run_dir)
    assert parsed["energy_valid"] and parsed["electronic_outputs_complete"]
    assert parsed["cp2k_warning_count"] == 19
    assert parsed["warning_message_counts"] == {
        "WARNING in fm/cp_fm_elpa.F:522 :: Setting real_kernel for ELPA failed": 19
    }
    assert parsed["warning_review_required"] and not parsed["fatal_warning_detected"]
    assert parsed["pdos_consistency_valid"] and parsed["unique_MO_count"] == 70
    assert parsed["spectral_integral_valid"]
    assert np.isclose(parsed["spectral_integral_KS_orbitals"], 70.0)
    assert "raw_total_dos_near_fermi_per_ev" not in parsed
    assert (
        parsed["cp2k_normalized_histogram_fraction_near_EF_per_ev"] is not None
    )


def test_base_parser_never_hides_cp2k_warnings():
    run_dir = ROOT / "research_lite" / "runs" / "cu2te_bulk"
    parsed = parse_output(
        run_dir / "output.out",
        run_dir / "input.executed.inp",
        run_dir / "run_metadata.json",
    )
    assert parsed["cp2k_warning_count"] == 19
    assert parsed["energy_valid"]


def test_completed_slab_warning_counts_include_multiline_messages():
    expected = {
        "B0": {
            "WARNING in fm/cp_fm_elpa.F:522 :: Setting real_kernel for ELPA failed": 39
        },
        "C50": {
            "WARNING in fm/cp_fm_elpa.F:522 :: Setting real_kernel for ELPA failed": 241,
            (
                "WARNING in qs_mo_occupation.F:592 :: Fermi-Dirac smearing "
                "includes the last MO => Add more MOs for proper smearing."
            ): 2,
        },
    }
    for task_id, counts in expected.items():
        run_dir = ROOT / "research_lite" / "runs" / task_id
        parsed = parse_output(
            run_dir / "output.out",
            run_dir / "input.executed.inp",
            run_dir / "run_metadata.json",
        )
        assert parsed["warning_message_counts"] == counts
        assert parsed["cp2k_warning_count"] == sum(counts.values())
        assert parsed["warning_review_required"]
        assert not parsed["fatal_warning_detected"]


def test_last_mo_smearing_warning_only_invalidates_persistent_occupation_truncation():
    assert not _last_mo_smearing_persistent(2, 84)
    assert _last_mo_smearing_persistent(80, 84)
    assert not _last_mo_smearing_persistent(2, 2)
    assert not _last_mo_smearing_persistent(0, None)


def _write_synthetic_projected_file(
    path: Path,
    eigenvalues: list[float],
    weights: list[float],
    fermi: float = 0.1,
) -> None:
    lines = [f"# E(Fermi) = {fermi:.6f} a.u."]
    for index, (eigenvalue, weight) in enumerate(
        zip(eigenvalues, weights), start=1
    ):
        lines.append(f"{index} {eigenvalue:.8f} 1.0 {weight:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_research_parser_accepts_consistent_synthetic_pdos_and_ldos(tmp_path):
    (tmp_path / "input.executed.inp").write_text(
        "&GLOBAL\n RUN_TYPE ENERGY\n&END GLOBAL\n", encoding="utf-8"
    )
    (tmp_path / "run_metadata.json").write_text(
        json.dumps(
            {
                "calculation_id": "cu2te_bulk",
                "attempted": True,
                "return_code": 0,
                "timed_out": False,
                "cu2te_formula_units": 2,
                "expected_electronic_outputs": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "output.out").write_text(
        "CP2K| version string: CP2K version 2024.3\n"
        "SCF run converged in 7 steps\n"
        "Fermi energy: 0.100000\n"
        "ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -10.0\n"
        "PROGRAM ENDED AT\n",
        encoding="utf-8",
    )
    eigenvalues = [0.09, 0.10, 0.11]
    for name, weights in (
        ("synthetic-k1-1.pdos", [0.4, 0.4, 0.4]),
        ("synthetic-k2-1.pdos", [0.6, 0.6, 0.6]),
        ("synthetic-list1-1.pdos", [0.4, 0.4, 0.4]),
        ("synthetic-list2-1.pdos", [0.6, 0.6, 0.6]),
    ):
        _write_synthetic_projected_file(
            tmp_path / name, eigenvalues, weights
        )
    (tmp_path / "total_dos.dat").write_text(
        "0.090 0.3333 1.0\n0.100 0.3333 1.0\n0.110 0.3334 1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "hartree_potential.cube").write_text("present", encoding="utf-8")
    (tmp_path / "electron_density.cube").write_text("present", encoding="utf-8")
    result = parse_research_run(tmp_path)
    assert result["energy_valid"] and result["electronic_outputs_complete"]
    assert result["pdos_consistency_valid"] and result["unique_MO_count"] == 3
    assert result["spectral_integral_valid"]
    assert (
        result[
            "Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit"
        ]
        is not None
    )


def test_pdos_consistency_mismatch_is_a_hard_parse_failure(tmp_path):
    (tmp_path / "input.executed.inp").write_text(
        "&GLOBAL\n RUN_TYPE ENERGY\n&END GLOBAL\n", encoding="utf-8"
    )
    (tmp_path / "run_metadata.json").write_text(
        json.dumps(
            {
                "calculation_id": "cu2te_bulk",
                "attempted": True,
                "return_code": 0,
                "timed_out": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "output.out").write_text(
        "SCF run converged in 2 steps\n"
        "Fermi energy: 0.100000\n"
        "ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -1.0\n"
        "PROGRAM ENDED AT\n",
        encoding="utf-8",
    )
    _write_synthetic_projected_file(
        tmp_path / "bad-k1-1.pdos", [0.09, 0.10], [0.5, 0.5]
    )
    _write_synthetic_projected_file(
        tmp_path / "bad-k2-1.pdos", [0.09, 0.12], [0.5, 0.5]
    )
    _write_synthetic_projected_file(
        tmp_path / "bad-list1-1.pdos", [0.09, 0.10], [0.5, 0.5]
    )
    _write_synthetic_projected_file(
        tmp_path / "bad-list2-1.pdos", [0.09, 0.10], [0.5, 0.5]
    )
    (tmp_path / "total_dos.dat").write_text(
        "0.09 0.5 1\n0.10 0.5 1\n", encoding="utf-8"
    )
    (tmp_path / "hartree_potential.cube").write_text("present", encoding="utf-8")
    (tmp_path / "electron_density.cube").write_text("present", encoding="utf-8")
    result = parse_research_run(tmp_path)
    assert result["energy_valid"]
    assert not result["pdos_consistency_valid"]
    assert not result["electronic_outputs_complete"]
    assert any("eigenvalues differ" in error for error in result["pdos_consistency_errors"])


def test_size_doubling_spectral_normalization_and_cp2k_histogram_semantics():
    grid = np.arange(-5.0, 5.0001, 0.01)
    energies_a = np.asarray([-1.0, 0.0, 1.0])
    energies_b = np.tile(energies_a, 2)
    curve_a = gaussian_spectrum(energies_a, grid, 0.10)
    curve_b = gaussian_spectrum(energies_b, grid, 0.10)
    integral_a = np.trapezoid(curve_a, grid)
    integral_b = np.trapezoid(curve_b, grid)
    assert np.isclose(integral_b, 2.0 * integral_a, rtol=1.0e-6)
    assert np.allclose(curve_b / 20.0, curve_a / 10.0, rtol=1.0e-12)
    cp2k_normalized_histogram_a = np.asarray([0.5, 0.5])
    cp2k_normalized_histogram_b = np.asarray([0.5, 0.5])
    assert np.isclose(cp2k_normalized_histogram_a.sum(), 1.0)
    assert np.isclose(cp2k_normalized_histogram_b.sum(), 1.0)
    assert not np.isclose(cp2k_normalized_histogram_b.sum(), integral_b)


def test_experiment_template_has_required_unit_bearing_headers():
    expected = [
        "sample_id",
        "solution_concentration_umol_ml",
        "measured_thickness_nm",
        "coverage_percent",
        "PCE_percent",
        "Voc_V",
        "Jsc_mA_cm2",
        "FF_percent",
        "series_resistance_ohm_cm2",
        "contact_resistance_ohm_cm2",
        "contact_resistance_method",
        "replicate_id",
    ]
    with (ROOT / "results" / "experiment_data_template.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.reader(handle))
    assert rows == [expected]
