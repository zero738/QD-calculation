from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT
from parse_research_lite_output import parse_research_run


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize strict metadata from an already completed CP2K run "
            "without rerunning or replacing raw evidence"
        )
    )
    parser.add_argument("task_id")
    args = parser.parse_args()
    run_dir = ROOT / "research_lite" / "runs" / args.task_id
    metadata_path = run_dir / "run_metadata.json"
    parsed_path = run_dir / "output.parsed.json"
    metadata = _read_json(metadata_path)
    if not metadata.get("attempted"):
        raise SystemExit("run metadata does not record a real attempt")
    if metadata.get("finished_at_utc") is None or metadata.get("return_code") is None:
        raise SystemExit("run is not finalized by the launcher; refusing to infer a stop")

    result = parse_research_run(run_dir)
    expected_outputs = bool(metadata.get("expected_electronic_outputs", True))
    strict_success = bool(
        result.get("energy_valid")
        and (
            result.get("electronic_outputs_complete")
            if expected_outputs
            else True
        )
    )
    if metadata.get("timed_out"):
        metadata["termination_reason"] = "runner_timeout"
        metadata["confirmed_stop_cause"] = (
            f"runner enforced the configured {metadata.get('timeout_seconds')}-second hard limit"
        )
    elif metadata.get("return_code") != 0:
        metadata["termination_reason"] = "nonzero_launcher_exit"
        metadata["confirmed_stop_cause"] = (
            "launcher returned a nonzero code; raw launcher stderr and CP2K output "
            "are retained, but the originating OS/container cause is not inferred"
        )
    elif strict_success:
        metadata["termination_reason"] = "strict_success"
        metadata["confirmed_stop_cause"] = (
            "normal CP2K end marker, explicit SCF convergence, valid energy"
            + (
                ", and complete requested electronic outputs"
                if expected_outputs
                else ""
            )
        )
    else:
        metadata["termination_reason"] = "strict_validation_failed"
        metadata["confirmed_stop_cause"] = (
            "process returned zero but one or more strict CP2K success/output "
            "criteria were not met"
        )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = parse_research_run(run_dir)
    parsed_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if args.task_id != "cu2te_bulk_k222":
        manifest_path = ROOT / "research_lite" / "manifest.json"
        manifest = _read_json(manifest_path)
        if isinstance(manifest, list):
            for task in manifest:
                if task.get("calculation_id") == args.task_id:
                    task["actually_run"] = True
                    task["run_directory"] = f"research_lite/runs/{args.task_id}"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    print(
        json.dumps(
            {
                "calculation_id": args.task_id,
                "energy_valid": result.get("energy_valid"),
                "electronic_outputs_complete": result.get(
                    "electronic_outputs_complete"
                ),
                "scf_steps": result.get("scf_steps"),
                "total_energy_hartree": result.get("total_energy_hartree"),
                "cp2k_warning_count": result.get("cp2k_warning_count"),
                "termination_reason": metadata.get("termination_reason"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if strict_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
