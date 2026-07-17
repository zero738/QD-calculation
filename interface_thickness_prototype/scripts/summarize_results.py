from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, active_model_ids, load_metadata
from parse_cp2k_output import parse_output

MODEL_FIELDS = [
    "model_id",
    "Cu2Te_repeat_count",
    "Cu2Te_atomic_plane_count",
    "top_termination",
    "interface_contact_elements",
    "Cd_atoms",
    "Te_atoms",
    "Cu_atoms",
    "total_atoms",
    "Cu2Te_z_span_A",
    "interface_minimum_distance_A",
    "nearest_interface_atom_pair",
    "total_vacuum_A",
    "applied_Cu2Te_strain_percent",
    "prototype_only",
]

SMOKE_FIELDS = [
    "calculation_id",
    "input_file",
    "output_file",
    "CP2K_version",
    "actually_run",
    "normal_program_end",
    "SCF_converged",
    "geometry_converged",
    "SCF_steps",
    "total_energy_hartree",
    "wall_time_seconds",
    "timeout_seconds",
    "timed_out",
    "termination_reason",
    "return_code",
    "warning_or_error",
]


def write_model_summary() -> Path:
    rows = []
    for model_id in active_model_ids():
        metadata = load_metadata(model_id)
        counts = metadata["counts"]
        rows.append(
            {
                "model_id": model_id,
                "Cu2Te_repeat_count": metadata["cu2te_repeat_count"],
                "Cu2Te_atomic_plane_count": metadata["cu2te_atomic_plane_count"],
                "top_termination": metadata["top_termination"],
                "interface_contact_elements": metadata["interface_contact_elements"],
                "Cd_atoms": counts.get("Cd", 0),
                "Te_atoms": counts.get("Te", 0),
                "Cu_atoms": counts.get("Cu", 0),
                "total_atoms": metadata["total_atoms"],
                "Cu2Te_z_span_A": f"{metadata['cu2te_z_span_angstrom']:.6f}",
                "interface_minimum_distance_A": (
                    ""
                    if metadata["interface_minimum_distance_angstrom"] is None
                    else f"{metadata['interface_minimum_distance_angstrom']:.6f}"
                ),
                "nearest_interface_atom_pair": metadata["nearest_interface_atom_pair"],
                "total_vacuum_A": f"{metadata['total_vacuum_angstrom']:.6f}",
                "applied_Cu2Te_strain_percent": f"{metadata['applied_cu2te_biaxial_strain_percent']:.6f}",
                "prototype_only": metadata["prototype_only"],
            }
        )
    output = ROOT / "results" / "model_summary.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def write_smoke_summary() -> Path:
    manifest_path = ROOT / "smoke_tests" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else []
    rows = []
    for task in manifest:
        task_dir = ROOT / "smoke_tests" / task["id"]
        executed_input = task_dir / "input.executed.inp"
        parsed = parse_output(
            task_dir / "output.out",
            task_dir / "input.inp",
            task_dir / "run_metadata.json",
        )
        rows.append(
            {
                "calculation_id": task["id"],
                "input_file": (
                    str(executed_input.relative_to(ROOT)).replace("\\", "/")
                    if executed_input.is_file()
                    else task["input_file"]
                ),
                "output_file": task["output_file"],
                "CP2K_version": parsed["cp2k_version"] or "",
                "actually_run": parsed["actually_run"],
                "normal_program_end": parsed["normal_program_end"],
                "SCF_converged": parsed["scf_converged"],
                "geometry_converged": parsed["geometry_optimization_converged"],
                "SCF_steps": parsed["scf_steps"] or "",
                "total_energy_hartree": parsed["total_energy_hartree"] or "",
                "wall_time_seconds": parsed["wall_time_seconds"] or "",
                "timeout_seconds": parsed["timeout_seconds"] or "",
                "timed_out": parsed["timed_out"],
                "termination_reason": parsed["termination_reason"] or "",
                "return_code": (
                    "" if parsed["return_code"] is None else parsed["return_code"]
                ),
                "warning_or_error": parsed["warning_or_error"] or "",
            }
        )
    output = ROOT / "results" / "smoke_test_summary.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SMOKE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def main() -> int:
    (ROOT / "results").mkdir(exist_ok=True)
    print(write_model_summary())
    print(write_smoke_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
