from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from common import ROOT

PACKAGE = ROOT / "server_scnet_2024_1"
RESULT = PACKAGE / "results/static_audit.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: str) -> str:
    return (PACKAGE / path).read_text(encoding="utf-8", errors="replace")


def rows(path: str) -> list[dict]:
    with (PACKAGE / path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    checks = []
    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = {
        "README_SCNET_CN.md", "env_scnet.sh", "submit_pipeline.sh", "monitor_pipeline.sh",
        "cancel_pipeline.sh", "check_server_inputs.py", "run_h1_controlled.py",
        "prepare_h2_input.py", "server_analysis.py", "verify_server_outputs.py",
        "package_results.py", "plot_results.py", "collect_results.sh",
        "scripts/00_check_environment.slurm", "scripts/30_H1.slurm", "scripts/40_H2.slurm",
        "scripts/90_finalize_after_H2.slurm", "scripts/91_finalize_if_H1_failed.slurm",
    }
    files = {path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*") if path.is_file()}
    add("required_package_files", required <= files, f"missing={sorted(required-files)}")
    bad_paths = [item for item in files if not item.isascii() or " " in item]
    add("ascii_paths_without_spaces", not bad_paths, f"bad_paths={bad_paths}")
    config = json.loads(read("package_config.json"))
    expected_tasks = {"cu2te_bulk_gamma", "cu2te_bulk_k222", "cu2te_bulk_k333", "cu2te_bulk_k444", "B0", "C50", "H1", "H2"}
    add("fixed_task_scope", set(config["tasks"]) == expected_tasks, str(sorted(config["tasks"])))
    add("no_forbidden_models", not any(re.search(r"(^|/)(H3|H4|C25|C75|Au|NEGF|HSE06)(/|$)", item, re.I) for item in files), "no extended model paths")

    env = read("env_scnet.sh")
    add("exact_cp2k_path", "/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt" in env, "target executable")
    add("no_broken_cp2k_module", "module load apps/cp2k" not in env, "manual modules only")
    add("pure_mpi_relative_runner", 'cd "$run_dir"' in env and '-i input.executed.inp -o output.out' in env and "srun --mpi=pmix_v3" in env, "cwd controls relative outputs")

    slurms = {path.name: path.read_text(encoding="utf-8") for path in (PACKAGE / "scripts").glob("*.slurm")}
    add("all_slurm_one_node", all("#SBATCH --nodes=1" in text for text in slurms.values()), str(len(slurms)))
    add("all_slurm_partition", all("#SBATCH --partition=kshctest02" in text for text in slurms.values()), "kshctest02")
    add("no_exclusive", all("--exclusive" not in text for text in slurms.values()), "none")
    add("slurm_no_recursive_sbatch", all("sbatch" not in text for text in slurms.values()), "sbatch only in login wrapper")
    submit = read("submit_pipeline.sh")
    add("submit_contains_controlled_sbatch", "sbatch --parsable" in submit, "one login-node submission wrapper")
    add("submit_refuses_old_evidence", "pipeline_jobs.json already exists" in submit and "runs/ contains evidence" in submit, "no overwrite")
    add("submit_partial_failure_cleanup_scoped", "submitted_ids" in submit and 'scancel "${submitted_ids[@]}"' in submit, "only current invocation")
    add("dependency_chain_afterok", submit.count("afterok:") >= 8, "environment through H2")
    add("H2_afterok_H1", 'afterok:$h1_id' in submit and "scripts/40_H2.slurm" in submit, "H2 dependency")
    add("two_finalize_paths", "afterany:$h2_id" in submit and "afterany:$h1_id" in submit, "success/failure collection")

    env_job = slurms["00_check_environment.slurm"]
    check_inputs = read("check_server_inputs.py")
    add("server_2024_1_check_invoked", "check_server_inputs.py" in env_job and "--cp2k" in env_job, "compute-node check")
    add("server_check_all_eight", 'for task_id, spec in config["tasks"].items()' in check_inputs and "all_inputs_passed" in check_inputs, "8 config tasks")
    add("server_check_failure_blocks", "afterok:$env_id" in submit, "nonzero environment job blocks chain")

    h1 = read("run_h1_controlled.py")
    add("H1_two_attempt_limit", all(token in h1 for token in ('"attempt_A"', '"attempt_B"')) and "attempt_C" not in h1, "at most A/B")
    add("H1_attempt_directories_separate", 'root / "attempt_A"' in h1 and '"attempt_B"' in h1, "independent cwd/evidence")
    add("H1_timeout_ladder", '"attempt_A", base_text, structure, args.cp2k, 7' in h1 and '"attempt_B", retry_text, structure, args.cp2k, 8' in h1, "7h+8h")
    add("H1_last_mo_retry", "persistent_last_mo_warning" in h1 and "attempt_B_more_unoccupied" in h1, "ADDED_MOS/NLUMO 160 policy")
    add("H1_residual_retry", "oscillating_scf_residual" in h1 and "attempt_B_gentler_mixing" in h1, "ALPHA 0.05 policy")
    add("H1_hard_failure_no_retry", "hard_configuration_failure" in h1 and "retry_started" in h1, "stop on hard error")
    add("H1_restart_provenance", "restart_source_manifest.json" in h1 and "old CP2K 2024.3" in h1 and "sha256" in h1, "verified WFN or ATOMIC fallback")
    add("H1_strict_success_files", "H1_SUCCESS.json" in h1 and "H1_SUCCESS.flag" in h1 and "H1_FAILURE.json" in h1, "exclusive evidence")

    prepare = read("prepare_h2_input.py")
    add("H2_dynamic_signature", "H1_SUCCESS.json" in prepare and "scf_signature" in prepare and "patch_keyword" in prepare, "inherits successful attempt")
    add("H2_absent_flag_blocked", "gate_h2" in prepare and "if not allowed" in prepare, "no success evidence => no H2")
    add("H2_geometry_invariants", "CdTe_interface_top_Te_count" in prepare and "Cu2Te_interface_bottom_Cu_count" in prepare and "== 13" in prepare and "== 32" in prepare, "interface checks")

    pipeline_state = read("pipeline_state.py")
    add("budget_recomputed_from_slurm", "parse_script" in pipeline_state and "maximum_requested_cpu_hours" in pipeline_state, "not hand-only")
    import sys
    sys.path.insert(0, str(PACKAGE))
    from pipeline_state import budget
    budget_record = budget()
    add("budget_below_1800", budget_record["valid"] and budget_record["maximum_requested_cpu_hours"] < 1800, str(budget_record["maximum_requested_cpu_hours"]))
    add("H1_resource_16x16", "#SBATCH --ntasks=16" in slurms["30_H1.slurm"] and "#SBATCH --time=16:00:00" in slurms["30_H1.slurm"], "256 CPU h")
    add("H2_resource_24x24", "#SBATCH --ntasks=24" in slurms["40_H2.slurm"] and "#SBATCH --time=24:00:00" in slurms["40_H2.slurm"], "576 CPU h")

    analysis = read("server_analysis.py")
    add("pdos_ldos_tolerance", "1.0e-6" in analysis and "MO identifiers differ" in analysis and "eigenvalues differ" in analysis, "strict consistency")
    add("dynamic_gaussian_integral", "10.0 * sigma" in analysis and "5.0e-4" in analysis and "KS orbitals/eV" in analysis, "dynamic domain")
    add("no_raw_total_dos_claim", "not raw total DOS" in analysis and "raw_total_DOS" not in analysis and "projected_spectral_weight" in analysis, "correct proxy names")
    add("B0_cu_projection_nullable", "if cu_curve is not None and formula_units else None" in analysis, "blank not zero")
    add("reference_not_hardcoded_indices", "common component/region/element/z clustered" in analysis and "hard-coded atom indices" in analysis, "metadata/z selection")
    add("reference_reliability_gates", "minimum_reference_grid_points" in analysis and "maximum_reference_std_ev" in analysis and "maximum_reference_slope_ev_per_angstrom" in analysis, "blank if unreliable")
    add("vacuum_reliability_gates", "vacuum_density_threshold_au" in analysis and "vacuum_minimum_width_angstrom" in analysis and "vacuum_maximum_std_ev" in analysis, "top/bottom independently gated")

    verifier = read("verify_server_outputs.py")
    add("bulk_444_gate", 'bulk[-1]["adjacent_delta_below_0p01_ev"] is True' in verifier, "formation gate")
    add("curvature_H1_gate", 'all(results[item]["strict_success"] for item in ("B0", "C50", "H1"))' in verifier, "curvature gate")
    status = rows("results/final_model_status.csv")
    add("initial_tasks_not_run", len(status) == 8 and all(row["status"] == "not_run" and row["total_energy_hartree"] == "" for row in status), "no fabricated values")
    formation = rows("results/relative_coverage_formation_energy.csv")
    add("initial_formation_blank", len(formation) == 2 and all(row["status"] == "not_ready_for_paper" and row["value_ev"] == "" for row in formation), "bulk/task gate")
    curvature = rows("results/coverage_curvature_proxy.csv")
    add("initial_curvature_blank", len(curvature) == 1 and curvature[0]["value_ev"] == "", "H1 unavailable")

    package_results = read("package_results.py")
    add("default_bundle_excludes_large", "LARGE_SUFFIXES" in package_results and "continue" in package_results and "scnet_results_bundle.tar.gz" in package_results, "no cube/WFN/restart")
    add("large_manifest_fields", all(token in package_results for token in ("absolute_path", "relative_path", "size_bytes", "sha256", "task_id", "attempt")), "optional file provenance")
    cancel = read("cancel_pipeline.sh")
    add("cancel_scoped_and_confirmed", "pipeline_jobs.json" in cancel and "CANCEL_CURRENT_PIPELINE" in cancel and 'scancel "${JOB_IDS[@]}"' in cancel, "no other jobs")
    finalizer = read("finalize_pipeline.py")
    add("atomic_finalize_lock", 'mkdir(parents=True, exist_ok=False)' in finalizer and ".finalize_lock" in finalizer, "no duplicate overwrite")

    for model in ("B0", "C50", "H1", "H2"):
        server = PACKAGE / f"inputs/{model}/structure.extxyz"
        source = ROOT / f"research_lite/inputs/{model}/structure.extxyz"
        add(f"{model}_structure_unchanged", server.read_text(encoding="utf-8").splitlines() == source.read_text(encoding="utf-8").splitlines(), "audited structure preserved")
    add("fixed_geometry_only", all("RUN_TYPE ENERGY" in path.read_text(encoding="utf-8") and "GEO_OPT" not in path.read_text(encoding="utf-8").upper() for path in (PACKAGE / "inputs").rglob("*.inp")), "no geometry optimization")

    manifest = {}
    for line in read("upload_manifest.txt").splitlines():
        expected, relative = line.split("  ", 1); manifest[relative] = expected
    add("upload_manifest_hashes", all((PACKAGE / path).is_file() and digest(PACKAGE / path) == value for path, value in manifest.items()), f"entries={len(manifest)}")
    secret = re.compile(r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|-----BEGIN .*PRIVATE KEY-----|AKIA[0-9A-Z]{16}", re.I)
    hits = [item for item in files if (PACKAGE / item).suffix.lower() not in {".png"} and secret.search((PACKAGE / item).read_text(encoding="utf-8", errors="replace"))]
    add("no_credentials", not hits, str(hits))
    old = rows("../results/relative_coverage_formation_energy.csv") if False else []
    old_path = ROOT / "results/relative_coverage_formation_energy.csv"
    with old_path.open("r", encoding="utf-8", newline="") as handle:
        old_rows = list(csv.DictReader(handle))
    add("old_coverage_not_paper_ready", bool(old_rows) and all(row.get("paper_eligibility_status") == "not_ready_for_paper" for row in old_rows), "2024.3 historical only")

    payload = {"check_count": len(checks), "passed_count": sum(item["passed"] for item in checks), "all_passed": all(item["passed"] for item in checks), "checks": checks, "scope": "static audit only; no SCNet calculation run"}
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
