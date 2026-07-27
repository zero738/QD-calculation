from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "server_scnet_2024_1"
sys.path.insert(0, str(PACKAGE))
from verify_server_outputs import gate_h2, read_config, verify_task


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_value(text: str, keyword: str) -> str | None:
    match = re.search(
        rf"(?mi)^\s*{re.escape(keyword)}\s+(?:\[K\]\s+)?(\S+)", text
    )
    return match.group(1) if match else None


def test_scnet_package_has_ascii_server_paths_and_required_files():
    required = {
        "README_SCNET_CN.md",
        "env_scnet.sh",
        "upload_manifest.txt",
        "collect_results.sh",
        "verify_server_outputs.py",
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
    present = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file()
    }
    assert required <= present
    assert all(
        " " not in relative and relative.isascii()
        for relative in (
            path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*")
        )
    )


def test_scnet_task_scope_and_budget_are_fixed():
    config = read_config()
    assert set(config["tasks"]) == {
        "cu2te_bulk_gamma",
        "cu2te_bulk_k222",
        "cu2te_bulk_k333",
        "cu2te_bulk_k444",
        "B0",
        "C50",
        "H1",
        "H2",
    }
    assert config["maximum_requested_cpu_hours"] <= 2000
    assert config["resources"]["H2"] == {"ntasks": 24, "hours": 24.0}
    assert config["server_calculations_actually_run"] is False


def test_scnet_structures_are_text_identical_to_research_lite():
    for task_id in ("B0", "C50", "H1", "H2", "cu2te_bulk"):
        server = PACKAGE / "inputs" / task_id / "structure.extxyz"
        source = ROOT / "research_lite" / "inputs" / task_id / "structure.extxyz"
        assert server.read_text(encoding="utf-8").splitlines() == source.read_text(
            encoding="utf-8"
        ).splitlines()


def test_b0_c50_keep_existing_physical_and_scf_baseline():
    for task_id in ("B0", "C50"):
        text = (PACKAGE / "inputs" / task_id / "input.inp").read_text(
            encoding="utf-8"
        )
        assert "RUN_TYPE ENERGY" in text
        assert "&XC_FUNCTIONAL PBE" in text
        assert input_value(text, "CUTOFF") == "400"
        assert input_value(text, "REL_CUTOFF") == "60"
        assert input_value(text, "EPS_SCF") == "1e-06"
        assert input_value(text, "MAX_SCF") == "150"
        assert input_value(text, "ADDED_MOS") == "40"
        assert input_value(text, "ALPHA") == "0.15"
        assert input_value(text, "NBROYDEN") == "8"
        assert input_value(text, "ELECTRONIC_TEMPERATURE") == "500"
        assert "ALGORITHM STANDARD" in text
        assert "METHOD FERMI_DIRAC" in text
        assert "&KPOINTS" not in text.upper()


def test_h1_minimal_fix_and_h2_match_without_eps_relaxation():
    signatures = []
    for task_id in ("H1", "H2"):
        text = (PACKAGE / "inputs" / task_id / "input.inp").read_text(
            encoding="utf-8"
        )
        signature = {
            "eps_scf": input_value(text, "EPS_SCF"),
            "max_scf": input_value(text, "MAX_SCF"),
            "added_mos": input_value(text, "ADDED_MOS"),
            "alpha": input_value(text, "ALPHA"),
            "nbroyden": input_value(text, "NBROYDEN"),
            "temperature": input_value(text, "ELECTRONIC_TEMPERATURE"),
            "nlumo": input_value(text, "NLUMO"),
        }
        assert signature == {
            "eps_scf": "1e-06",
            "max_scf": "250",
            "added_mos": "100",
            "alpha": "0.08",
            "nbroyden": "12",
            "temperature": "500",
            "nlumo": "100",
        }
        assert "ALGORITHM STANDARD" in text
        assert "&OT" not in text.upper()
        signatures.append(signature)
    assert signatures[0] == signatures[1]


def test_bulk_kpoint_ladder_is_energy_only_and_finite():
    expected = {
        "input_gamma.inp": None,
        "input_k222.inp": "2 2 2",
        "input_k333.inp": "3 3 3",
        "input_k444.inp": "4 4 4",
    }
    for filename, mesh in expected.items():
        text = (PACKAGE / "inputs/cu2te_bulk" / filename).read_text(
            encoding="utf-8"
        )
        if mesh is None:
            assert "&KPOINTS" not in text.upper()
        else:
            assert f"SCHEME MONKHORST-PACK {mesh}" in text
        assert not any(
            token in text.upper()
            for token in (
                "&DOS", "&PDOS", "&LDOS", "V_HARTREE_CUBE", "E_DENSITY_CUBE"
            )
        )
    assert not (PACKAGE / "inputs/cu2te_bulk/input_k555.inp").exists()


def test_slurm_jobs_are_one_node_manual_pure_mpi_jobs():
    for path in (PACKAGE / "scripts").glob("*.slurm"):
        text = path.read_text(encoding="utf-8")
        assert "#SBATCH --partition=kshctest02" in text
        assert "#SBATCH --nodes=1" in text
        assert re.search(r"(?m)^#SBATCH --ntasks=\d+$", text)
        assert "--exclusive" not in text
        assert "module load apps/cp2k" not in text
        assert "sbatch" not in text
        if not path.name.startswith("00_"):
            assert 'srun --mpi=pmix_v3 "$SCNET_CP2K_EXE"' in text


def test_h2_gate_is_before_h2_srun_and_blocks_initial_package():
    text = (PACKAGE / "scripts/40_H2.slurm").read_text(encoding="utf-8")
    assert 0 <= text.index("--gate-h2") < text.index("srun --mpi=pmix_v3")
    allowed, detail = gate_h2(read_config())
    assert allowed is False
    assert detail["h1_strict_success"] is False
    assert detail["h2_submission_allowed"] is False


def test_server_verifier_never_marks_missing_output_success():
    config = read_config()
    for task_id in config["tasks"]:
        result = verify_task(task_id, config)
        assert result["actually_run"] is False
        assert result["status"] == "not_run"
        assert result["strict_success"] is False
        assert result["energy_valid"] is False
        assert result["total_energy_hartree"] is None


def test_initial_server_metrics_are_blank_and_not_ready_for_paper():
    with (PACKAGE / "results/server_coverage_metrics.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert {row["metric_id"] for row in rows} == {
        "C50_fixed_geometry_relative_coverage_formation_energy",
        "H1_fixed_geometry_relative_coverage_formation_energy",
        "coverage_curvature_E_H1_plus_E_B0_minus_2E_C50",
    }
    assert all(row["status"] == "not_ready_for_paper" for row in rows)
    assert all(row["value_ev"] == "" for row in rows)


def test_old_coverage_energy_is_explicitly_not_paper_ready():
    with (ROOT / "results/relative_coverage_formation_energy.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["paper_eligibility_status"] == "not_ready_for_paper" for row in rows)


def test_upload_manifest_matches_all_listed_files():
    entries = []
    for line in (PACKAGE / "upload_manifest.txt").read_text(
        encoding="ascii"
    ).splitlines():
        expected, relative = line.split("  ", 1)
        entries.append(relative)
        assert digest(PACKAGE / relative) == expected
    assert "verify_server_outputs.py" in entries
    assert "scripts/40_H2.slurm" in entries
    assert not any(relative.startswith("runs/") for relative in entries)


def test_package_contains_no_secret_or_private_key_pattern():
    pattern = re.compile(
        r"ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|-----BEGIN .*PRIVATE KEY-----",
        re.I,
    )
    hits = []
    for path in PACKAGE.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                hits.append(path.relative_to(PACKAGE).as_posix())
    assert hits == []
