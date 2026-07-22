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
from parse_research_lite_output import parse_research_run


def _meta(kind: str, model_id: str) -> dict:
    return json.loads((ROOT / kind / model_id / "model.json").read_text(encoding="utf-8"))


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
    assert np.array_equal(c0.pbc, b0.pbc) and np.array_equal(c100.pbc, h1.pbc)
    for array_name in ("component", "region", "fixed"):
        assert np.array_equal(c0.arrays[array_name], b0.arrays[array_name])
        assert np.array_equal(c100.arrays[array_name], h1.arrays[array_name])
    assert Counter(c50.get_chemical_symbols()) == Counter({"Cd": 39, "Te": 55, "Cu": 32})
    film = c50[78:]
    assert Counter(film.get_chemical_symbols()) == Counter({"Cu": 32, "Te": 16})
    assert Counter(film.get_chemical_symbols())["Cu"] == 2 * Counter(film.get_chemical_symbols())["Te"]


def test_c50_retains_only_complete_contiguous_lateral_units():
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
            assert Counter(np.asarray(film.get_chemical_symbols())[mask]) == Counter({"Cu": 4, "Te": 2})
    assert occupied == [(ii, jj) for ii in (1, 2) for jj in range(4)]


def test_coverage_interface_geometry_and_termination_are_invariant():
    metas = {model_id: _meta("coverage_models", model_id) for model_id in ("C0", "C50", "C100")}
    assert [metas[key]["coverage_percent"] for key in ("C0", "C50", "C100")] == [0.0, 50.0, 100.0]
    assert metas["C50"]["lateral_cu2te_units_present"] == 8
    assert metas["C100"]["lateral_cu2te_units_present"] == 16
    assert metas["C50"]["cu2te_repeat_count"] == metas["C100"]["cu2te_repeat_count"] == 1
    assert metas["C50"]["cu2te_atomic_plane_count"] == metas["C100"]["cu2te_atomic_plane_count"] == 4
    assert metas["C50"]["top_termination"] == metas["C100"]["top_termination"] == "Cu"
    assert metas["C50"]["interface_first_contact_element"] == metas["C100"]["interface_first_contact_element"] == "Cu"
    assert np.isclose(metas["C50"]["cu2te_z_span_angstrom"], metas["C100"]["cu2te_z_span_angstrom"])
    assert np.isclose(metas["C50"]["interface_minimum_distance_angstrom"], metas["C100"]["interface_minimum_distance_angstrom"])
    assert minimum_distance(read(ROOT / "coverage_models" / "C50" / "structure.extxyz")) >= 1.8


def test_research_lite_profile_is_distinct_and_fully_written_to_inputs():
    config = load_config()
    profiles = config["cp2k"]["profiles"]
    assert set(profiles) == {"smoke_ot", "research_lite"}
    research = profiles["research_lite"]
    manifest = json.loads((ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8"))
    assert [task["calculation_id"] for task in manifest] == ["cu2te_bulk", "B0", "C50", "H1", "H2"]
    assert not list((ROOT / "research_lite" / "inputs" / "C100").glob("input*.inp"))
    assert next(task for task in manifest if task["calculation_id"] == "B0")["result_aliases"] == ["C0"]
    assert next(task for task in manifest if task["calculation_id"] == "H1")["result_aliases"] == ["C100"]
    for task in manifest:
        gamma = (ROOT / task["gamma_input"]).read_text(encoding="utf-8")
        kpoint_check = (ROOT / task["optional_kpoint_check_input"]).read_text(encoding="utf-8")
        assert "PROFILE research_lite" in gamma
        assert "&DIAGONALIZATION" in gamma and "&SMEAR ON" in gamma
        assert f"EPS_SCF {research['eps_scf']}" in gamma
        assert f"MAX_SCF {research['max_scf']}" in gamma
        assert f"ADDED_MOS {research['added_mos']}" in gamma
        assert f"ELECTRONIC_TEMPERATURE [K] {research['electronic_temperature_k']}" in gamma
        assert f"CUTOFF {research['cutoff_ry']}" in gamma
        assert f"REL_CUTOFF {research['rel_cutoff_ry']}" in gamma
        assert "&DOS ON" in gamma and "&PDOS ON" in gamma and "&LDOS" in gamma
        assert "&V_HARTREE_CUBE ON" in gamma and "&E_DENSITY_CUBE ON" in gamma
        assert "&KPOINTS" not in gamma
        expected_mesh = [2, 2, 2] if task["calculation_id"] == "cu2te_bulk" else [2, 2, 1]
        assert task["optional_kpoint_mesh"] == expected_mesh
        assert f"SCHEME MONKHORST-PACK {' '.join(map(str, expected_mesh))}" in kpoint_check
        assert "&PDOS ON" not in kpoint_check and "not implemented for KPOINTS" in kpoint_check
        if task["periodic"] == "XY":
            assert gamma.upper().count("PERIODIC XY") >= 2 and "PSOLVER ANALYTIC" in gamma
        else:
            assert gamma.upper().count("PERIODIC XYZ") >= 2


def test_cp2k_2024_3_check_evidence_matches_current_inputs():
    evidence = json.loads((ROOT / "research_lite" / "cp2k_input_checks.json").read_text(encoding="utf-8"))
    assert evidence["cp2k_version"] == "CP2K version 2024.3"
    assert evidence["all_passed"] and len(evidence["results"]) == 10
    for result in evidence["results"]:
        path = ROOT / result["input_file"]
        assert result["check_passed"] and result["return_code"] == 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == result["input_sha256"]


def test_unrun_models_have_no_fabricated_research_values():
    with (ROOT / "results" / "research_lite_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["calculation_id"]: row for row in csv.DictReader(handle)}
    for model_id in ("B0", "C50", "H1", "H2"):
        assert rows[model_id]["actually_run"] == "False"
        assert rows[model_id]["total_energy_hartree"] == ""
        assert rows[model_id]["fermi_energy_hartree"] == ""
    with (ROOT / "results" / "relative_coverage_formation_energy.csv").open(encoding="utf-8", newline="") as handle:
        formation = list(csv.DictReader(handle))
    for row in formation:
        assert row["relative_coverage_formation_energy_ev_per_angstrom2"] == ""
        assert row["relative_coverage_formation_energy_ev_per_Cu2Te_formula_unit"] == ""
        assert "smoke" in row["warning"]


def test_coverage_summaries_use_only_canonical_calculation_ids():
    with (ROOT / "results" / "relative_coverage_formation_energy.csv").open(encoding="utf-8", newline="") as handle:
        formation = {row["model_id"]: row for row in csv.DictReader(handle)}
    assert formation["C0"]["canonical_calculation_id"] == "B0"
    assert formation["C50"]["canonical_calculation_id"] == "C50"
    assert formation["C100"]["canonical_calculation_id"] == "H1"
    assert formation["C0"]["E_bulk_kpoint_mesh"] == "implicit_gamma"
    assert formation["C0"]["E_bulk_kpoint_convergence_checked"] == "False"

    with (ROOT / "results" / "dft_proxy_summary.csv").open(encoding="utf-8", newline="") as handle:
        proxies = {row["model_id"]: row for row in csv.DictReader(handle)}
    assert list(proxies) == ["C0", "C50", "C100", "H2"]
    assert proxies["C0"]["canonical_calculation_id"] == "B0"
    assert proxies["C100"]["canonical_calculation_id"] == "H1"
    for row in proxies.values():
        assert "raw total DOS is not size-normalized" in row["warning"]


def test_actual_bulk_rerun_has_separate_energy_and_electronic_states():
    run_dir = ROOT / "research_lite" / "runs" / "cu2te_bulk"
    parsed = parse_research_run(run_dir)
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["calculation_profile"] == "research_lite"
    assert metadata["timeout_seconds"] == 300 and metadata["timed_out"] is False
    assert metadata["return_code"] == 0 and metadata["termination_reason"] == "process_exit_0"
    assert parsed["program_completed"] and parsed["scf_converged"] and parsed["scf_steps"]
    assert parsed["energy_valid"]
    assert parsed["total_energy_hartree"] is not None and parsed["fermi_energy_hartree"] is not None
    assert parsed["dos_output_present"] and parsed["potential_output_present"]
    assert parsed["pdos_output_present"] and parsed["ldos_output_present"]
    assert parsed["electronic_outputs_complete"] and parsed["research_output_complete"]
    assert not parsed["cp2k_warnings"]
    assert parsed["raw_total_dos_near_fermi_per_ev"] is not None
    assert parsed["total_dos_near_fermi_per_ev_per_substrate_angstrom2"] is None
    assert parsed["cu2te_projected_dos_near_fermi_per_ev_per_formula_unit"] is not None
    assert parsed["kpoint_mesh"] == "implicit_gamma"
    assert parsed["kpoint_convergence_checked"] is False
    assert (run_dir / "input.executed.inp").is_file() and (run_dir / "output.out").is_file()
    assert (run_dir / "total_dos.dat").is_file()
    assert (run_dir / "hartree_potential_planar_average.csv").is_file()
    history = run_dir / "history" / "attempt_01_explicit_gamma_kpoints"
    historical = parse_research_run(history)
    assert historical["energy_valid"] and not historical["electronic_outputs_complete"]


def test_research_parser_accepts_complete_synthetic_artifact_set(tmp_path):
    (tmp_path / "input.executed.inp").write_text("&GLOBAL\n RUN_TYPE ENERGY\n&END GLOBAL\n", encoding="utf-8")
    (tmp_path / "run_metadata.json").write_text(
        json.dumps({"calculation_id": "cu2te_bulk", "attempted": True, "return_code": 0, "timed_out": False, "calculation_profile": "research_lite", "cu2te_formula_units": 2}),
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
    (tmp_path / "region-LDOS-1.pdos").write_text("# Fermi energy: 0.1 a.u.\n1 0.10 1.0 0.5\n", encoding="utf-8")
    (tmp_path / "region-LDOS-2.pdos").write_text("# Fermi energy: 0.1 a.u.\n1 0.10 1.0 0.5\n", encoding="utf-8")
    (tmp_path / "total_dos.dat").write_text("0.100 2.0 1.0\n0.102 1.0 0.5\n", encoding="utf-8")
    (tmp_path / "hartree_potential.cube").write_text("present", encoding="utf-8")
    (tmp_path / "electron_density.cube").write_text("present", encoding="utf-8")
    result = parse_research_run(tmp_path)
    assert result["research_output_complete"]
    assert result["energy_valid"] and result["electronic_outputs_complete"]
    assert result["pdos_output_present"] and result["dos_output_present"]
    assert result["raw_total_dos_near_fermi_per_ev"] is not None
    assert result["cu2te_projected_dos_near_fermi_per_ev_per_formula_unit"] is not None


def test_experiment_template_has_only_required_header_fields():
    expected = [
        "sample_id", "solution_concentration_umol_ml", "measured_thickness_nm", "coverage_percent",
        "PCE_percent", "Voc_V", "Jsc_mA_cm2", "FF_percent", "series_resistance_ohm_cm2",
        "contact_resistance_ohm_cm2", "contact_resistance_method", "replicate_id",
    ]
    with (ROOT / "results" / "experiment_data_template.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows == [expected]
