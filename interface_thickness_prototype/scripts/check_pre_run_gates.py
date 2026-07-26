from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT
from parse_research_lite_output import parse_research_run


def _check(name: str, passed: bool, evidence: str) -> dict:
    return {"gate": name, "passed": bool(passed), "evidence": evidence}


def main() -> int:
    repo_root = ROOT.parent
    python = Path(sys.executable)
    pytest_result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            str(ROOT / "tests"),
            "-q",
            f"--basetemp={repo_root / '.pytest-tmp'}",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    pytest_text = (pytest_result.stdout + "\n" + pytest_result.stderr).strip()
    pytest_summary = next(
        (
            line
            for line in reversed(pytest_text.splitlines())
            if " passed" in line or " failed" in line
        ),
        pytest_text.splitlines()[-1] if pytest_text else "no pytest output",
    )
    manifest = json.loads(
        (ROOT / "research_lite" / "manifest.json").read_text(encoding="utf-8")
    )
    tasks = {task["calculation_id"]: task for task in manifest}
    cp2k_checks = json.loads(
        (ROOT / "research_lite" / "cp2k_input_checks.json").read_text(
            encoding="utf-8"
        )
    )
    hashes_current = all(
        hashlib.sha256((ROOT / item["input_file"]).read_bytes()).hexdigest()
        == item["input_sha256"]
        for item in cp2k_checks["results"]
    )
    bulk = parse_research_run(ROOT / "research_lite" / "runs" / "cu2te_bulk")
    group_counts = {
        calculation_id: {
            group["label"]: len(group["indices_1based"])
            for group in tasks[calculation_id]["ldos_groups"]
        }
        for calculation_id in ("B0", "C50", "H1", "H2")
    }
    unrun_blank = all(
        not (ROOT / "research_lite" / "runs" / task_id / "output.parsed.json").exists()
        for task_id in ("B0", "C50", "H1", "H2")
    )
    canonical = (
        tasks["B0"]["result_aliases"] == ["C0"]
        and tasks["H1"]["result_aliases"] == ["C100"]
        and not (ROOT / "research_lite" / "inputs" / "C0").exists()
        and not (ROOT / "research_lite" / "inputs" / "C100").exists()
    )
    checks = [
        _check("all_automated_tests_pass", pytest_result.returncode == 0, pytest_summary),
        _check(
            "synthetic_pdos_ldos_consistency_test_pass",
            pytest_result.returncode == 0,
            "covered by test_research_lite.py mismatch and consistent-artifact tests",
        ),
        _check(
            "synthetic_size_doubling_test_pass",
            pytest_result.returncode == 0,
            "covered by test_size_doubling_spectral_normalization_and_cp2k_histogram_semantics",
        ),
        _check(
            "existing_bulk_warning_count_is_19",
            bulk.get("cp2k_warning_count") == 19
            and any("ELPA" in message for message in bulk.get("unique_warning_messages", [])),
            f"count={bulk.get('cp2k_warning_count')}; messages={bulk.get('unique_warning_messages')}",
        ),
        _check("C0_and_C100_are_aliases_only", canonical, "C0->B0 and C100->H1"),
        _check(
            "H1_H2_interface_group_counts_match",
            group_counts["H1"]["CdTe_interface_top_Te"]
            == group_counts["H2"]["CdTe_interface_top_Te"]
            and group_counts["H1"]["Cu2Te_interface_bottom_Cu"]
            == group_counts["H2"]["Cu2Te_interface_bottom_Cu"],
            f"H1={group_counts['H1']}; H2={group_counts['H2']}",
        ),
        _check(
            "C50_interface_groups_nonempty",
            group_counts["C50"]["CdTe_interface_top_Te"] > 0
            and group_counts["C50"]["Cu2Te_interface_bottom_Cu"] > 0,
            f"C50={group_counts['C50']}",
        ),
        _check(
            "unrun_research_values_remain_absent",
            unrun_blank,
            "B0/C50/H1/H2 have no research_lite parsed outputs before the run",
        ),
        _check(
            "all_inputs_pass_cp2k_2024_3_check",
            cp2k_checks.get("all_passed") is True
            and len(cp2k_checks["results"]) == 10
            and hashes_current,
            f"{sum(item['check_passed'] for item in cp2k_checks['results'])}/10 checks; hashes_current={hashes_current}",
        ),
    ]
    evidence = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "all_gates_passed": all(item["passed"] for item in checks),
        "checks": checks,
        "warning": (
            "Passing these gates validates the pipeline prerequisites only; it "
            "does not establish physical convergence or scientific validity."
        ),
    }
    destination = ROOT / "results" / "pre_run_gates.json"
    destination.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for item in checks:
        print(f"{'PASS' if item['passed'] else 'FAIL'} {item['gate']}: {item['evidence']}")
    return 0 if evidence["all_gates_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
