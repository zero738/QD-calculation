from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from common import ROOT


PACKAGE = ROOT / "server_scnet_2024_1"
RESULT = PACKAGE / "results" / "static_audit.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def input_section(text: str, section: str) -> str:
    match = re.search(
        rf"(?ms)^\s*&{section}\b.*?^\s*&END\s+{section}\s*$",
        text,
    )
    return "\n".join(line.strip() for line in match.group(0).splitlines()) if match else ""


def value(text: str, keyword: str) -> str | None:
    match = re.search(rf"(?mi)^\s*{re.escape(keyword)}\s+(?:\[K\]\s+)?(\S+)", text)
    return match.group(1) if match else None


def main() -> int:
    config = json.loads((PACKAGE / "package_config.json").read_text(encoding="utf-8"))
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = {
        "README_SCNET_CN.md",
        "env_scnet.sh",
        "upload_manifest.txt",
        "collect_results.sh",
        "verify_server_outputs.py",
        "package_config.json",
        "scripts/00_check_environment.slurm",
        "scripts/01_cu2te_bulk_gamma.slurm",
        "scripts/02_cu2te_bulk_k222.slurm",
        "scripts/03_cu2te_bulk_k333.slurm",
        "scripts/04_cu2te_bulk_k444.slurm",
        "scripts/10_B0.slurm",
        "scripts/20_C50.slurm",
        "scripts/30_H1.slurm",
        "scripts/40_H2.slurm",
    }
    existing = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file()
    }
    add("required_package_files", required <= existing, "All required ASCII server package entry points must exist.")

    bad_paths = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if " " in path.relative_to(PACKAGE).as_posix()
        or any(ord(character) > 127 for character in path.relative_to(PACKAGE).as_posix())
    ]
    add("ascii_paths_without_spaces", not bad_paths, f"bad_paths={bad_paths}")

    task_ids = set(config["tasks"])
    add(
        "fixed_model_scope",
        task_ids
        == {
            "cu2te_bulk_gamma", "cu2te_bulk_k222", "cu2te_bulk_k333",
            "cu2te_bulk_k444", "B0", "C50", "H1", "H2",
        },
        f"task_ids={sorted(task_ids)}",
    )
    add(
        "no_forbidden_extension_models",
        not any(re.search(r"(?i)(^|/)(H3|H4|C25|C75|Au|NEGF|HSE06)(/|$)", item) for item in existing),
        "No H3/H4/C25/C75/Au/NEGF/HSE06 model path may exist.",
    )

    env = (PACKAGE / "env_scnet.sh").read_text(encoding="utf-8")
    required_env = (
        "module purge >/dev/null 2>&1 || true",
        "module load compiler/gnu/9.3.0",
        "module load compiler/intel/2021.3.0",
        "module load mpi/intelmpi/2021.3.0",
        "/public/software/apps/cp2k/2024.1/exe/local/cp2k.popt",
        "/public/software/apps/cp2k/2024.1/data",
    )
    add(
        "exact_scnet_environment",
        all(item in env for item in required_env) and "module load apps/cp2k" not in env,
        "Use the verified manual 2024.1 environment and never load the broken CP2K module.",
    )

    slurm_paths = sorted((PACKAGE / "scripts").glob("*.slurm"))
    slurm_texts = {path.name: path.read_text(encoding="utf-8") for path in slurm_paths}
    directives_ok = all(
        "#SBATCH --partition=kshctest02" in text
        and "#SBATCH --nodes=1" in text
        and re.search(r"(?m)^#SBATCH --ntasks=\d+$", text)
        and re.search(r"(?m)^#SBATCH --time=\d\d:\d\d:\d\d$", text)
        and re.search(r"(?m)^#SBATCH --job-name=\S+$", text)
        and re.search(r"(?m)^#SBATCH --output=\S+-%j\.out$", text)
        and re.search(r"(?m)^#SBATCH --error=\S+-%j\.err$", text)
        and "--exclusive" not in text
        for text in slurm_texts.values()
    )
    add("slurm_directives", directives_ok, "Every job is one-node kshctest02 with explicit resources and log files.")
    compute_scripts = {name: text for name, text in slurm_texts.items() if not name.startswith("00_")}
    add(
        "pure_mpi_srun",
        all('srun --mpi=pmix_v3 "$SCNET_CP2K_EXE"' in text for text in compute_scripts.values()),
        "Every compute job uses cp2k.popt through srun/pmix_v3.",
    )
    executable_text = "\n".join([env, (PACKAGE / "collect_results.sh").read_text(encoding="utf-8"), *slurm_texts.values()])
    add("no_automatic_submission", "sbatch" not in executable_text, "Executable scripts must never submit another job.")

    h2_script = slurm_texts["40_H2.slurm"]
    gate_index = h2_script.find("--gate-h2")
    srun_index = h2_script.find("srun --mpi=pmix_v3")
    add(
        "h2_strict_h1_gate_before_srun",
        gate_index >= 0 and srun_index > gate_index,
        "H2 must verify strict H1 success before any H2 srun command.",
    )

    budget = float(config["maximum_requested_cpu_hours"])
    add("cpu_hour_budget", budget <= 2000.0, f"maximum_requested_cpu_hours={budget}")
    add(
        "h2_resource_choice",
        config["resources"]["H2"] == {"ntasks": 24, "hours": 24.0},
        "H2 uses 24 MPI tasks for 24 h: 576 CPU h on one 32-core node.",
    )

    for task_id in ("B0", "C50", "H1", "H2"):
        generated = PACKAGE / "inputs" / task_id / "structure.extxyz"
        source = ROOT / "research_lite" / "inputs" / task_id / "structure.extxyz"
        add(
            f"{task_id}_structure_unchanged",
            generated.is_file()
            and generated.read_text(encoding="utf-8").splitlines()
            == source.read_text(encoding="utf-8").splitlines(),
            "Server structure text must equal the audited research_lite structure independent of platform line endings.",
        )
        input_text = (PACKAGE / "inputs" / task_id / "input.inp").read_text(encoding="utf-8")
        source_text = (ROOT / "research_lite" / "inputs" / task_id / "input_gamma.inp").read_text(encoding="utf-8")
        add(
            f"{task_id}_cell_and_coordinates_unchanged",
            input_section(input_text, "CELL") == input_section(source_text, "CELL")
            and input_section(input_text, "COORD") == input_section(source_text, "COORD"),
            "CELL and COORD blocks must be byte-equivalent after whitespace normalization.",
        )

    for task_id in ("B0", "C50"):
        text = (PACKAGE / "inputs" / task_id / "input.inp").read_text(encoding="utf-8")
        settings = {
            "eps_scf": value(text, "EPS_SCF"), "max_scf": value(text, "MAX_SCF"),
            "added_mos": value(text, "ADDED_MOS"), "alpha": value(text, "ALPHA"),
            "nbroyden": value(text, "NBROYDEN"), "temperature": value(text, "ELECTRONIC_TEMPERATURE"),
        }
        add(
            f"{task_id}_baseline_parameters",
            settings == {
                "eps_scf": "1e-06", "max_scf": "150", "added_mos": "40",
                "alpha": "0.15", "nbroyden": "8", "temperature": "500",
            },
            f"settings={settings}",
        )

    for task_id in ("H1", "H2"):
        text = (PACKAGE / "inputs" / task_id / "input.inp").read_text(encoding="utf-8")
        settings = {
            "eps_scf": value(text, "EPS_SCF"), "max_scf": value(text, "MAX_SCF"),
            "added_mos": value(text, "ADDED_MOS"), "alpha": value(text, "ALPHA"),
            "nbroyden": value(text, "NBROYDEN"), "temperature": value(text, "ELECTRONIC_TEMPERATURE"),
            "nlumo": value(text, "NLUMO"),
        }
        add(
            f"{task_id}_minimal_scf_fix",
            settings == {
                "eps_scf": "1e-06", "max_scf": "250", "added_mos": "100",
                "alpha": "0.08", "nbroyden": "12", "temperature": "500",
                "nlumo": "100",
            }
            and "ALGORITHM STANDARD" in text
            and "METHOD FERMI_DIRAC" in text,
            f"settings={settings}",
        )

    bulk_inputs = {
        "Gamma": PACKAGE / "inputs/cu2te_bulk/input_gamma.inp",
        "2 2 2": PACKAGE / "inputs/cu2te_bulk/input_k222.inp",
        "3 3 3": PACKAGE / "inputs/cu2te_bulk/input_k333.inp",
        "4 4 4": PACKAGE / "inputs/cu2te_bulk/input_k444.inp",
    }
    bulk_ok = True
    for mesh, path in bulk_inputs.items():
        text = path.read_text(encoding="utf-8")
        if mesh == "Gamma":
            bulk_ok &= "&KPOINTS" not in text.upper()
        else:
            bulk_ok &= f"SCHEME MONKHORST-PACK {mesh}" in text
        bulk_ok &= not any(token in text.upper() for token in ("&DOS", "&PDOS", "&LDOS", "V_HARTREE_CUBE", "E_DENSITY_CUBE"))
    add("bulk_energy_only_kpoint_ladder", bulk_ok, "Gamma/2x2x2/3x3x3/4x4x4 are energy-only inputs.")

    all_inputs = list((PACKAGE / "inputs").rglob("*.inp"))
    add(
        "fixed_geometry_only",
        all("RUN_TYPE ENERGY" in path.read_text(encoding="utf-8") and "GEO_OPT" not in path.read_text(encoding="utf-8").upper() for path in all_inputs),
        "No server input may request geometry optimization.",
    )

    status = list(csv_dicts(PACKAGE / "results/server_task_status.csv"))
    add(
        "server_results_truthfully_not_run",
        len(status) == 8
        and all(row["actually_run"] == "False" and row["status"] == "not_run" and row["total_energy_hartree"] == "" for row in status),
        "Initial server results must contain no invented energy or success state.",
    )
    metrics = list(csv_dicts(PACKAGE / "results/server_coverage_metrics.csv"))
    add(
        "server_metrics_blank_not_ready",
        len(metrics) == 3
        and all(row["status"] == "not_ready_for_paper" and row["value_ev"] == "" for row in metrics),
        "Formation-energy and curvature outputs remain blank before server runs.",
    )

    syntax_evidence = json.loads(
        (PACKAGE / "results/syntax_precheck_cp2k_2024_3.json").read_text(
            encoding="utf-8"
        )
    )
    syntax_hashes_valid = all(
        sha256(PACKAGE / item["input_file"]) == item["input_sha256"]
        for item in syntax_evidence.get("results", [])
    )
    add(
        "cp2k_2024_3_syntax_precheck_evidence",
        syntax_evidence.get("all_passed") is True
        and syntax_evidence.get("input_count") == 8
        and syntax_evidence.get("local_precheck_cp2k_version") == "CP2K version 2024.3"
        and syntax_evidence.get("target_server_cp2k_version") == "2024.1"
        and syntax_hashes_valid,
        "All 8 current inputs passed local CP2K 2024.3 --check; this is syntax-only evidence for a 2024.1 target.",
    )

    local_validation = json.loads(
        (PACKAGE / "results/local_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    add(
        "shell_syntax_and_unrun_scope_recorded",
        local_validation.get("server_cp2k_calculations_actually_run") is False
        and local_validation.get("shell_syntax", {}).get("exit_code") == 0
        and local_validation.get("shell_syntax", {}).get("checked_files") == 11,
        "Bash syntax passed for 11 shell/Slurm files while server execution remains explicitly false.",
    )

    old_h1 = json.loads((ROOT / "research_lite/runs/H1/output.parsed.json").read_text(encoding="utf-8"))
    add(
        "old_h1_failure_boundary",
        old_h1.get("scf_iterations_observed") == 72
        and old_h1.get("last_MO_smearing_warning_count") == 70
        and old_h1.get("last_MO_smearing_warning_persistent") is True
        and old_h1.get("energy_valid") is False,
        "Old H1 remains a timeout/non-convergence record, not a code-error or OOM claim.",
    )

    old_formation = list(csv_dicts(ROOT / "results/relative_coverage_formation_energy.csv"))
    add(
        "old_coverage_energy_not_paper_ready",
        bool(old_formation)
        and all(row.get("paper_eligibility_status") == "not_ready_for_paper" for row in old_formation),
        "Every old CP2K 2024.3 coverage-energy row must be explicitly excluded from paper conclusions.",
    )

    manifest = {}
    for line in (PACKAGE / "upload_manifest.txt").read_text(encoding="ascii").splitlines():
        digest, relative = line.split("  ", 1)
        manifest[relative] = digest
    manifest_ok = all((PACKAGE / relative).is_file() and sha256(PACKAGE / relative) == digest for relative, digest in manifest.items())
    add("upload_manifest_hashes", manifest_ok, f"manifest_entries={len(manifest)}")

    secret_re = re.compile(r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|-----BEGIN .*PRIVATE KEY-----", re.I)
    secret_hits = []
    for path in PACKAGE.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".cube", ".wfn"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if secret_re.search(text):
            secret_hits.append(path.relative_to(PACKAGE).as_posix())
    add("no_credentials_or_private_keys", not secret_hits, f"hits={secret_hits}")

    payload = {
        "check_count": len(checks),
        "passed_count": sum(item["passed"] for item in checks),
        "all_passed": all(item["passed"] for item in checks),
        "checks": checks,
        "scope": "static package audit only; no SCNet CP2K calculation was run",
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["all_passed"] else 1


def csv_dicts(path: Path):
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


if __name__ == "__main__":
    raise SystemExit(main())
