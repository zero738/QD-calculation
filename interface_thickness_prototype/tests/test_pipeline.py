from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from ase.io import read

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import load_config, load_metadata, load_model, minimum_distance, total_vacuum, z_layers
from generate_cp2k_inputs import SMOKE_BASIS
from parse_cp2k_output import parse_output
from validate_models import validate


def test_models_read_and_validate():
    assert validate()["ok"]
    assert all(len(load_model(model_id)) > 0 for model_id in ("B0", "H1", "H2"))


def test_complete_repeat_counts_planes_and_thickness():
    metadata = {model_id: load_metadata(model_id) for model_id in ("B0", "H1", "H2")}
    assert [metadata[model_id]["cu2te_repeat_count"] for model_id in ("B0", "H1", "H2")] == [0, 1, 2]
    assert [metadata[model_id]["cu2te_atomic_plane_count"] for model_id in ("B0", "H1", "H2")] == [0, 4, 8]
    assert metadata["H2"]["total_atoms"] > metadata["H1"]["total_atoms"] > metadata["B0"]["total_atoms"]
    assert metadata["H2"]["cu2te_z_span_angstrom"] > metadata["H1"]["cu2te_z_span_angstrom"] > 0


def test_substrate_interface_and_top_termination_are_invariant():
    metadata = {model_id: load_metadata(model_id) for model_id in ("B0", "H1", "H2")}
    assert metadata["H1"]["top_termination"] == metadata["H2"]["top_termination"] == "Cu"
    assert metadata["H1"]["interface_first_contact_element"] == metadata["H2"]["interface_first_contact_element"] == "Cu"
    assert metadata["H1"]["interface_contact_elements"] == metadata["H2"]["interface_contact_elements"]
    assert np.isclose(
        metadata["H1"]["interface_minimum_distance_angstrom"],
        metadata["H2"]["interface_minimum_distance_angstrom"],
    )
    substrate_count = metadata["B0"]["substrate_atom_count"]
    reference = load_model("B0")[:substrate_count]
    for model_id in ("H1", "H2"):
        trial = load_model(model_id)[:substrate_count]
        assert trial.get_chemical_symbols() == reference.get_chemical_symbols()
        assert np.allclose(trial.positions, reference.positions)
        film = load_model(model_id)[substrate_count:]
        assert len(z_layers(film, 0.20)) == metadata[model_id]["cu2te_atomic_plane_count"]


def test_all_structure_formats_read_back():
    for model_id in ("B0", "H1", "H2"):
        expected = load_metadata(model_id)["total_atoms"]
        for filename in ("structure.cif", "structure.xyz", "structure.extxyz"):
            assert len(read(ROOT / "models" / model_id / filename)) == expected


def test_vacuum_distance_elements_pbc_and_classification():
    for model_id in ("B0", "H1", "H2"):
        atoms = load_model(model_id)
        assert set(atoms.get_chemical_symbols()) <= {"Cd", "Te", "Cu"}
        assert tuple(atoms.pbc) == (True, True, False)
        assert total_vacuum(atoms) >= 18.0 - 1e-8
        assert minimum_distance(atoms) >= 1.80
        assert {"component", "region", "fixed"}.issubset(atoms.arrays)


def test_cp2k_smoke_basis_potentials_and_periodicity():
    for path in sorted((ROOT / "smoke_tests").glob("*/input.inp")):
        text = path.read_text(encoding="utf-8")
        assert "BASIS_SET_FILE_NAME BASIS_MOLOPT" in text
        assert "POTENTIAL_FILE_NAME GTH_POTENTIALS" in text
        assert "&RESTART OFF" in text
        for element in ("Cd", "Te", "Cu"):
            if f"&KIND {element}" in text:
                basis, potential, _ = SMOKE_BASIS[element]
                assert basis in text and potential in text
        if "_bulk_" in path.parent.name:
            assert text.upper().count("PERIODIC XYZ") >= 2
        else:
            assert text.upper().count("PERIODIC XY") >= 2
            assert "PSOLVER ANALYTIC" in text


def test_smoke_ladder_order_and_geo_limit():
    config = load_config()
    manifest = json.loads((ROOT / "smoke_tests" / "manifest.json").read_text(encoding="utf-8"))
    assert [task["id"] for task in manifest] == config["smoke_tests"]["ordered_calculation_ids"]
    assert [task["atom_count"] for task in manifest[:2]] == [8, 6]
    geo_text = (ROOT / "smoke_tests" / "05_h1_short_geo_opt" / "input.inp").read_text(encoding="utf-8")
    assert "RUN_TYPE GEO_OPT" in geo_text
    assert "MAX_ITER 5" in geo_text


def test_missing_output_is_not_success(tmp_path):
    result = parse_output(tmp_path / "missing.out")
    assert not result["program_completed"]
    assert not result["actually_run"]
    assert not result["scf_converged"]
    assert result["warning_or_error"]


def test_unconverged_output_is_not_success(tmp_path):
    output = tmp_path / "bad.out"
    output.write_text(
        "SCF run NOT converged\nENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -1.0\nPROGRAM ENDED AT\n",
        encoding="utf-8",
    )
    result = parse_output(output)
    assert result["normal_program_end"]
    assert not result["program_completed"]
    assert not result["scf_converged"]


def test_normal_end_without_explicit_scf_convergence_is_not_success(tmp_path):
    output = tmp_path / "ambiguous.out"
    output.write_text(
        "ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -1.0\nPROGRAM ENDED AT\n",
        encoding="utf-8",
    )
    result = parse_output(output)
    assert result["normal_program_end"]
    assert not result["program_completed"]
    assert not result["scf_converged"]


def test_converged_output_extracts_version_steps_and_energy(tmp_path):
    output = tmp_path / "good.out"
    output.write_text(
        "CP2K| version string: CP2K version 2024.3\n"
        "SCF run converged in 8 steps\n"
        "ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -12.5\n"
        "PROGRAM ENDED AT\n"
        "PROGRAM STOPPED IN /work\n",
        encoding="utf-8",
    )
    result = parse_output(output)
    assert result["program_completed"]
    assert result["scf_converged"]
    assert result["scf_steps"] == 8
    assert result["total_energy_hartree"] == -12.5
    assert result["cp2k_version"] == "CP2K version 2024.3"


def test_incomplete_geometry_optimization_is_not_success(tmp_path):
    input_file = tmp_path / "geo.inp"
    input_file.write_text("&GLOBAL\n RUN_TYPE GEO_OPT\n&END GLOBAL\n", encoding="utf-8")
    output = tmp_path / "geo.out"
    output.write_text(
        "SCF run converged in 8 steps\n"
        "ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -12.5\n"
        "PROGRAM ENDED AT\n",
        encoding="utf-8",
    )
    result = parse_output(output, input_file)
    assert result["normal_program_end"]
    assert result["scf_converged"]
    assert not result["program_completed"]
    assert result["geometry_optimization_converged"] is False
    assert "geometry optimization" in result["warning_or_error"]


def test_generated_summaries_match_metadata_and_manifest():
    with (ROOT / "results" / "model_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        model_rows = list(csv.DictReader(handle))
    assert [row["model_id"] for row in model_rows] == ["B0", "H1", "H2"]
    assert int(model_rows[1]["Cu2Te_atomic_plane_count"]) == 4
    assert int(model_rows[2]["Cu2Te_atomic_plane_count"]) == 8
    with (ROOT / "results" / "smoke_test_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        smoke_rows = list(csv.DictReader(handle))
    assert [row["calculation_id"] for row in smoke_rows] == load_config()["smoke_tests"]["ordered_calculation_ids"]


def test_recorded_real_runs_have_matching_input_snapshots_and_strict_status():
    for calculation_id in ("01_cdte_bulk_sp", "02_cu2te_bulk_sp", "03_b0_slab_sp"):
        task_dir = ROOT / "smoke_tests" / calculation_id
        metadata = json.loads((task_dir / "run_metadata.json").read_text(encoding="utf-8"))
        executed = task_dir / metadata["executed_input_file"]
        assert executed.is_file() and (task_dir / "output.out").is_file()
        assert hashlib.sha256(executed.read_bytes()).hexdigest() == metadata["executed_input_sha256"]
        parsed = parse_output(task_dir / "output.out", executed, task_dir / "run_metadata.json")
        if calculation_id in ("01_cdte_bulk_sp", "02_cu2te_bulk_sp"):
            assert parsed["normal_program_end"] and parsed["scf_converged"] and parsed["program_completed"]
            assert parsed["total_energy_hartree"] is not None
        else:
            assert parsed["actually_run"]
            assert not parsed["normal_program_end"]
            assert not parsed["scf_converged"]
            assert not parsed["program_completed"]
