from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import load_metadata, load_model, minimum_distance, total_vacuum
from parse_cp2k_output import parse_output
from validate_models import validate


def test_models_read_and_validate():
    assert validate()["ok"]
    assert all(len(load_model(mid)) > 0 for mid in ("T0", "T1", "T2"))


def test_counts_thickness_and_substrate_invariance():
    meta = {mid: load_metadata(mid) for mid in ("T0", "T1", "T2")}
    assert meta["T2"]["counts"]["Cu"] > meta["T1"]["counts"]["Cu"] > meta["T0"]["counts"].get("Cu", 0)
    assert meta["T2"]["initial_cute_thickness_angstrom"] > meta["T1"]["initial_cute_thickness_angstrom"] > 0
    n = meta["T0"]["substrate_atom_count"]
    reference = load_model("T0")[:n]
    for mid in ("T1", "T2"):
        trial = load_model(mid)[:n]
        assert trial.get_chemical_symbols() == reference.get_chemical_symbols()
        assert np.allclose(trial.positions, reference.positions)


def test_vacuum_distance_elements_and_pbc():
    for mid in ("T0", "T1", "T2"):
        atoms = load_model(mid)
        assert set(atoms.get_chemical_symbols()) <= {"Cd", "Te", "Cu"}
        assert tuple(atoms.pbc) == (True, True, False)
        assert total_vacuum(atoms) >= 18.0 - 1e-8
        assert minimum_distance(atoms) >= 1.80
        assert "region" in atoms.arrays and "fixed" in atoms.arrays
        assert all(str(region) for region in atoms.arrays["region"])


def test_cp2k_periodicity_and_valence_settings():
    for mid in ("T0", "T1", "T2"):
        for name in ("single_point.inp", "test_geo_opt.inp"):
            text = (ROOT / "models" / mid / name).read_text(encoding="utf-8")
            assert text.upper().count("PERIODIC XY") >= 2
            assert "PSOLVER ANALYTIC" in text
            assert "PERIODIC XYZ" not in text.upper()
            assert "GTH-PBE-q12" in text and "GTH-PBE-q6" in text
        if mid != "T0":
            assert "GTH-PBE-q11" in (ROOT / "models" / mid / "single_point.inp").read_text(encoding="utf-8")


def test_missing_output_is_not_success(tmp_path):
    result = parse_output(tmp_path / "missing.out")
    assert not result["program_completed"] and not result["scf_converged"]
    assert result["error"]


def test_unconverged_output_is_not_success(tmp_path):
    output = tmp_path / "bad.out"
    output.write_text("SCF run NOT converged\nENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -1.0\nPROGRAM ENDED AT\n", encoding="utf-8")
    result = parse_output(output)
    assert not result["program_completed"] and not result["scf_converged"]


def test_converged_output_is_recognized(tmp_path):
    output = tmp_path / "good.out"
    output.write_text("SCF run converged in 8 steps\nENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -12.5\nPROGRAM ENDED AT\n", encoding="utf-8")
    result = parse_output(output)
    assert result["program_completed"] and result["scf_converged"]
    assert result["total_energy_hartree"] == -12.5


def test_incomplete_geometry_optimization_is_not_success(tmp_path):
    input_file = tmp_path / "geo.inp"
    input_file.write_text("&GLOBAL\n RUN_TYPE GEO_OPT\n&END GLOBAL\n", encoding="utf-8")
    output = tmp_path / "geo.out"
    output.write_text("SCF run converged in 8 steps\nENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]: -12.5\nPROGRAM ENDED AT\n", encoding="utf-8")
    result = parse_output(output, input_file)
    assert not result["program_completed"]
    assert result["geometry_optimization_converged"] is False
    assert "geometry optimization" in result["error"]
