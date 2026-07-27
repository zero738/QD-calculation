from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "server_scnet_2024_1"
sys.path.insert(0, str(PACKAGE))

from pipeline_state import budget
from server_analysis import (
    build_retry_input, classify_attempt_failure, common_cdte_reference,
    pdos_consistency, build_spectral_proxies, analyze_potential,
)
from verify_server_outputs import coverage_and_curvature, read_config, verify_task


@pytest.mark.parametrize("name", ["submit_pipeline.sh", "monitor_pipeline.sh", "cancel_pipeline.sh"])
def test_pipeline_entrypoints_exist(name):
    assert (PACKAGE / name).is_file()


@pytest.mark.parametrize("path", sorted((PACKAGE / "scripts").glob("*.slurm")))
def test_no_slurm_recursively_calls_sbatch(path):
    assert "sbatch" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", sorted((PACKAGE / "scripts").glob("*.slurm")))
def test_slurm_resolves_package_from_submit_directory(path):
    text = path.read_text(encoding="utf-8")
    assert 'PACKAGE_ROOT="${SLURM_SUBMIT_DIR:-' in text


def test_server_environment_loads_supported_python():
    text = (PACKAGE / "env_scnet.sh").read_text(encoding="utf-8")
    assert "module load python/3.8.10" in text


def test_submit_pipeline_is_only_controlled_sbatch_owner():
    text = (PACKAGE / "submit_pipeline.sh").read_text(encoding="utf-8")
    assert "sbatch --parsable" in text
    assert "pipeline_jobs.json already exists" in text
    assert "runs/ contains evidence" in text
    assert "submitted_ids" in text


def test_relative_cp2k_outputs_use_task_cwd():
    text = (PACKAGE / "env_scnet.sh").read_text(encoding="utf-8")
    assert 'cd "$run_dir"' in text
    assert "-i input.executed.inp -o output.out" in text
    assert '$RUN_DIR/output.out' not in text


@pytest.mark.parametrize("name", [
    "01_cu2te_bulk_gamma.slurm", "02_cu2te_bulk_k222.slurm",
    "03_cu2te_bulk_k333.slurm", "04_cu2te_bulk_k444.slurm",
    "10_B0.slurm", "20_C50.slurm", "40_H2.slurm",
])
def test_normal_compute_scripts_use_shared_cwd_runner(name):
    assert 'scnet_run_cp2k "$RUN_DIR"' in (PACKAGE / "scripts" / name).read_text(encoding="utf-8")


def test_h1_attempts_run_with_attempt_directory_as_cwd():
    text = (PACKAGE / "run_h1_controlled.py").read_text(encoding="utf-8")
    assert "cwd=directory" in text
    assert '"-i", "input.executed.inp", "-o", "output.out"' in text


def test_server_2024_1_check_is_environment_gate():
    env_job = (PACKAGE / "scripts/00_check_environment.slurm").read_text(encoding="utf-8")
    checker = (PACKAGE / "check_server_inputs.py").read_text(encoding="utf-8")
    assert "check_server_inputs.py" in env_job
    assert 'config["tasks"].items()' in checker
    assert "server_cp2k_2024_1_input_checks.json" in checker
    assert "CP2K version 2024.1" in checker


def test_server_check_failure_blocks_main_chain():
    submit = (PACKAGE / "submit_pipeline.sh").read_text(encoding="utf-8")
    assert 'afterok:$env_id' in submit
    assert submit.index("00_check_environment.slurm") < submit.index("01_cu2te_bulk_gamma.slurm")


def test_dependency_order_and_h2_afterok_h1():
    text = (PACKAGE / "submit_pipeline.sh").read_text(encoding="utf-8")
    ordered = ["00_check_environment", "01_cu2te_bulk_gamma", "02_cu2te_bulk_k222", "03_cu2te_bulk_k333", "04_cu2te_bulk_k444", "10_B0", "20_C50", "30_H1", "40_H2"]
    positions = [text.rindex(f"scripts/{item}.slurm") for item in ordered]
    assert positions == sorted(positions)
    assert 'afterok:$h1_id' in text


def _scf_output(warnings: bool = False, oscillating: bool = False) -> str:
    lines = []
    for index in range(1, 11):
        residual = [2e-4, 8e-5, 1.5e-4, 7e-5, 1.4e-4, 6e-5, 1.3e-4, 5e-5, 1.2e-4, 5e-5][index - 1] if oscillating else 1e-3 / index
        lines.append(f" {index:3d} Broy./Diag. 0.08E+00  1.0 {residual:.8E} -100.0 0.0")
        if warnings:
            lines.append("WARNING: Fermi-Dirac smearing includes the last MO")
    return "\n".join(lines)


def test_persistent_last_mo_warning_triggers_unoccupied_retry():
    assert classify_attempt_failure(_scf_output(warnings=True))["classification"] == "persistent_last_mo_warning"


def test_residual_oscillation_triggers_gentler_mixing_retry():
    assert classify_attempt_failure(_scf_output(oscillating=True))["classification"] == "oscillating_scf_residual"


@pytest.mark.parametrize("message", ["CP2K ABORT in input", "basis set not found", "MPI_ABORT", "permission denied"])
def test_hard_configuration_errors_do_not_retry(message):
    assert classify_attempt_failure(message)["classification"] == "hard_configuration_failure"


def test_attempt_b_unoccupied_variant_keeps_eps_and_standard_method():
    base = (PACKAGE / "inputs/H1/input.inp").read_text(encoding="utf-8")
    text = build_retry_input(base, {"added_mos": 160, "pdos_nlumo": 160, "mixing_alpha": 0.08, "nbroyden": 12}, None)
    assert "ADDED_MOS 160" in text and "NLUMO 160" in text
    assert "EPS_SCF 1e-06" in text and "ALGORITHM STANDARD" in text and "&OT" not in text.upper()


def test_attempt_b_mixing_variant_is_exactly_controlled():
    base = (PACKAGE / "inputs/H1/input.inp").read_text(encoding="utf-8")
    text = build_retry_input(base, {"added_mos": 100, "pdos_nlumo": 100, "mixing_alpha": 0.05, "nbroyden": 16}, None)
    assert "ALPHA 0.05" in text and "NBROYDEN 16" in text and "EPS_SCF 1e-06" in text


def test_h1_has_no_third_attempt():
    text = (PACKAGE / "run_h1_controlled.py").read_text(encoding="utf-8")
    assert "attempt_C" not in text
    assert json.loads((PACKAGE / "package_config.json").read_text(encoding="utf-8"))["h1_controlled_retry"]["maximum_attempts"] == 2


def test_h2_dynamically_inherits_success_signature_and_checks_geometry():
    text = (PACKAGE / "prepare_h2_input.py").read_text(encoding="utf-8")
    for token in ("H1_SUCCESS.json", "patch_keyword", "scf_signature", "== 13", "== 32"):
        assert token in text


def test_absent_h1_success_blocks_h2():
    result = verify_task("H1", read_config())
    assert result["strict_success"] is False
    assert not (PACKAGE / "runs/H1/H1_SUCCESS.flag").exists()


def _write_pdos(path: Path, eigenvalues=( -0.1, 0.1), fermi=0.0, projection=(0.5, 0.5)):
    path.write_text(
        f"# Fermi energy: {fermi}\n" + "\n".join(
            f"{index} {energy} 1.0 {weight}" for index, (energy, weight) in enumerate(zip(eigenvalues, projection), 1)
        ) + "\n", encoding="utf-8"
    )


def test_synthetic_pdos_ldos_consistency_and_ks_integral(tmp_path):
    _write_pdos(tmp_path / "x-k1-1.pdos")
    _write_pdos(tmp_path / "x-list1-1.pdos")
    record = pdos_consistency(tmp_path, ["CdTe_interface_top_Te"])
    assert record["valid"] is True
    spectrum = build_spectral_proxies(tmp_path, record, ["CdTe_interface_top_Te"], 10.0, 0, {"CdTe_interface_top_Te": 1})
    assert spectrum["spectral_integral_valid"] is True
    assert spectrum["spectral_integral_expected_KS_orbitals"] == 2
    assert spectrum["Cu2Te_projected_spectral_weight_near_EF_per_ev_per_formula_unit"] is None


def test_synthetic_pdos_ldos_mismatch_is_failure(tmp_path):
    _write_pdos(tmp_path / "x-k1-1.pdos")
    _write_pdos(tmp_path / "x-list1-1.pdos", eigenvalues=(-0.2, 0.1))
    assert pdos_consistency(tmp_path, ["CdTe_interface_top_Te"])["valid"] is False


def test_cp2k_normalized_histogram_is_not_called_raw_total_dos():
    combined = (PACKAGE / "server_analysis.py").read_text(encoding="utf-8") + (PACKAGE / "README_SCNET_CN.md").read_text(encoding="utf-8")
    assert "CP2K `total_dos.dat` 只称归一化直方图谱形" in combined
    assert "not raw total DOS" in combined
    assert "raw_total_DOS" not in combined


def test_common_cdte_reference_uses_metadata_and_z_not_atom_ids():
    reference = common_cdte_reference(PACKAGE)
    assert reference["status"] == "candidate"
    assert reference["atom_count"] > 0
    assert "no hard-coded atom indices" in reference["selection_method"]


def test_missing_cubes_leave_alignment_and_work_function_blank(tmp_path):
    structure = PACKAGE / "inputs/B0/structure.extxyz"
    result = analyze_potential(tmp_path, structure, -0.2, common_cdte_reference(PACKAGE), read_config()["potential_analysis"])
    assert result["relative_fermi_alignment"]["EF_minus_CdTe_reference_potential_ev"] is None
    assert result["work_function"]["work_function_top_ev"] is None
    assert result["work_function"]["work_function_bottom_ev"] is None


def _write_1d_cube(path: Path, values):
    lines = ["synthetic", "synthetic", "1 0.0 0.0 0.0", "1 1.0 0.0 0.0", "1 0.0 1.0 0.0", f"{len(values)} 0.0 0.0 1.0", "1 1.0 0.0 0.0 0.0"]
    lines.extend(" ".join(f"{value:.8e}" for value in values[index:index + 6]) for index in range(0, len(values), 6))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def test_synthetic_flat_internal_and_vacuum_potential_passes_strict_gates(tmp_path):
    count = 60
    potential = [-0.1] * count
    density = []
    for index in range(count):
        z_angstrom = index * 0.529177210903
        density.append(1.0e-4 if 8.0 <= z_angstrom <= 21.0 else 0.0)
    _write_1d_cube(tmp_path / "hartree_potential.cube", potential)
    _write_1d_cube(tmp_path / "electron_density.cube", density)
    result = analyze_potential(tmp_path, PACKAGE / "inputs/B0/structure.extxyz", -0.2, common_cdte_reference(PACKAGE), read_config()["potential_analysis"])
    assert result["relative_fermi_alignment"]["status"] == "reliable_prototype_proxy"
    assert result["relative_fermi_alignment"]["EF_minus_CdTe_reference_potential_ev"] is not None
    assert result["work_function"]["top_status"] == "reliable_prototype_proxy"
    assert result["work_function"]["bottom_status"] == "reliable_prototype_proxy"


def test_bulk_not_converged_keeps_formation_blank():
    results = {name: {"strict_success": False, "total_energy_hartree": None} for name in ("B0", "C50", "H1")}
    bulk = [{"adjacent_delta_below_0p01_ev": None, "energy_hartree_per_formula_unit": None}]
    formation, curvature = coverage_and_curvature(results, bulk, read_config())
    assert all(row["value_ev"] is None for row in formation)
    assert curvature[0]["value_ev"] is None


def test_initial_outputs_use_blank_missing_values_not_zero():
    with (PACKAGE / "results/final_model_status.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert all(row["status"] == "not_run" and row["total_energy_hartree"] == "" for row in rows)


def test_resource_budget_is_parsed_from_slurm_and_below_limit():
    record = budget()
    assert record["valid"] is True
    assert record["maximum_requested_cpu_hours"] < 1800
    assert all(item["nodes"] == 1 and item["partition"] == "kshctest02" for item in record["jobs"])


def test_cancel_only_uses_recorded_pipeline_ids_and_confirmation():
    text = (PACKAGE / "cancel_pipeline.sh").read_text(encoding="utf-8")
    assert "pipeline_jobs.json" in text and "CANCEL_CURRENT_PIPELINE" in text
    assert 'scancel "${JOB_IDS[@]}"' in text


def test_finalize_paths_use_atomic_lock():
    text = (PACKAGE / "finalize_pipeline.py").read_text(encoding="utf-8")
    assert ".finalize_lock" in text and "exist_ok=False" in text
    assert "H2_blocked_by_H1.json" in text


def test_default_result_bundle_excludes_large_optional_files():
    text = (PACKAGE / "package_results.py").read_text(encoding="utf-8")
    assert 'LARGE_SUFFIXES = (".wfn", ".restart", ".cube")' in text
    for field in ("absolute_path", "relative_path", "size_bytes", "sha256", "task_id", "attempt"):
        assert field in text


def test_plot_missing_state_is_labeled_not_zeroed():
    text = (PACKAGE / "plot_results.py").read_text(encoding="utf-8")
    assert "missing / failed / blocked" in text
    assert "no zero substitution" in text


def test_windows_bundle_excludes_sensitive_and_large_artifacts():
    text = (ROOT / "make_scnet_bundle.ps1").read_text(encoding="utf-8")
    for token in (".git", ".venv", "__pycache__", ".wfn", ".restart", ".cube", "scnet_upload_bundle.zip"):
        assert token in text


def test_no_extended_models_or_methods_in_task_paths():
    paths = [path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*")]
    assert not any(re.search(r"(^|/)(H3|H4|C25|C75|Au|NEGF|HSE06)(/|$)", item, re.I) for item in paths)


def test_no_secret_patterns_in_text_package():
    pattern = re.compile(r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|-----BEGIN .*PRIVATE KEY-----|AKIA[0-9A-Z]{16}")
    hits = []
    for path in PACKAGE.rglob("*"):
        if path.is_file() and path.suffix.lower() not in {".png"}:
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                hits.append(path)
    assert not hits
