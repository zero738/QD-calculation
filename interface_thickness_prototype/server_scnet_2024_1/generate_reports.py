#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(name: str) -> list[dict]:
    path = ROOT / "results" / name
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    status = rows("final_model_status.csv")
    run_count = sum(row.get("actually_run", "").lower() == "true" for row in status)
    strict_count = sum(row.get("strict_success", "").lower() == "true" for row in status)
    gate_path = ROOT / "results/final_scientific_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else {}
    task_table = ["| Task | Status | Strict success | Energy (Ha) |", "|---|---|---:|---:|"]
    for row in status:
        task_table.append(f"| {row['task_id']} | {row['status']} | {row['strict_success']} | {row['total_energy_hartree'] or ''} |")
    report = f"""# SCNet server run report

SCNet CP2K 2024.1 tasks actually represented by evidence: **{run_count}/8**. Strict successes: **{strict_count}/8**.

{chr(10).join(task_table)}

## Interpretation boundary

- Energies are fixed-geometry proxies under the unified 500 K electronic smearing setup; they are not silently described as strict 0 K energies.
- Work function fields remain blank unless both top/bottom platform tests independently satisfy the documented density, width, standard-deviation and slope gates.
- `EF_minus_CdTe_reference_potential_ev` is a CdTe-internal-reference aligned relative Fermi-level proxy, not an absolute Fermi energy.
- The electronic indicators are theoretical proxies for interface charge transport, energy-level matching and contact-barrier changes. Real contact resistance still requires experimental TLM, series-resistance or other electrical measurements.
- H1/H2 provide only a thinner-versus-thicker comparison, not a continuous thickness function, optimal film thickness or optimal concentration.
- CdTe(111) is polar and all interface structures are fixed initial geometries.

Paper-ready gate: `{gate.get('paper_ready', False)}`. Missing values are not replaced by zero.
"""
    (ROOT / "SERVER_RUN_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    paper = """# Paper results boundary

This package does not make a paper-ready claim by itself. Old CP2K 2024.3 B0/C50 values are `historical_prototype_evidence`; the old C50 value -0.662188 eV/Å² remains `not_ready_for_paper`.

The only permitted coverage-energy name is **fixed-initial-geometry relative coverage formation energy**. It is not an absolute surface energy. It remains blank until CP2K 2024.1 B0/model strict success and the 3×3×3→4×4×4 Cu2Te bulk threshold are both satisfied. C50 is one periodic stripe morphology, not every 50% island morphology.

Raw CP2K Fermi energies are never compared directly across models. CP2K `total_dos.dat` is only a normalized histogram spectral-shape fraction, not raw total DOS or states/eV. No theoretical contact resistance in Ω·cm² is produced.
"""
    (ROOT / "PAPER_RESULTS_SUMMARY.md").write_text(paper, encoding="utf-8", newline="\n")
    checklist = """# User review checklist

1. `results/server_cp2k_2024_1_input_checks.json`: all eight checks must pass before any dependent job starts.
2. `pipeline_jobs.json`: verify the afterok chain and the two afterany finalizers.
3. `runs/H1/H1_SUCCESS.json`: absent means H2 must stay blocked; at most attempt_A and attempt_B may exist.
4. `results/final_model_status.csv`: missing/failed tasks must have blank energies.
5. `results/bulk_kpoint_convergence.csv`: only a <0.01 eV/formula-unit 3×3×3→4×4×4 delta permits the current bulk reference.
6. `results/relative_fermi_alignment.csv` and `results/work_function_status.csv`: unreliable fields must be blank, not zero.
7. `large_optional_files_manifest.txt`: cubes/WFN/restarts stay on the server and are not placed in the default tar bundle.

Static checks cannot prove that H1 or H2 will converge, that the prototype phase is the experimental phase, or that any proxy predicts real contact resistance or optimal thickness.
"""
    (ROOT / "USER_REVIEW_CHECKLIST.md").write_text(checklist, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
