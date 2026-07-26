from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

HARTREE_TO_EV = 27.211386245988
ENERGY_RE = re.compile(r"ENERGY\|.*?energy\s*\[a\.u\.\]\s*:\s*([-+0-9.Ee]+)", re.I)
SCF_CONVERGED_RE = re.compile(r"SCF\s+run\s+converged\s+in\s+(\d+)\s+steps", re.I)
SCF_ITERATION_RE = re.compile(
    r"^\s*(\d+)\s+(?:NoMix|Broy\.)/Diag\.", re.I | re.M
)
VERSION_RE = re.compile(r"CP2K\|\s*version string:\s*(.+)", re.I)
FERMI_RE = re.compile(r"Fermi\s+energy\s*:\s*([-+0-9.Ee]+)", re.I)
CP2K_WARNING_LINE_RE = re.compile(
    r"^\s*\*{3}\s*(WARNING\s+in\s+.*?)\s*\*{3}\s*$", re.I
)
CP2K_WARNING_CONTINUATION_RE = re.compile(
    r"^\s*\*{3}\s*(?!WARNING\b)(.*?)\s*\*{3}\s*$", re.I
)
FATAL_WARNING_TOKENS = (
    "scf run not converged",
    "projected density of states is not implemented for k points",
    "requested electronic output was not written",
)


def _read_metadata(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _extract_cp2k_warnings(text: str) -> list[str]:
    lines = text.splitlines()
    warnings: list[str] = []
    index = 0
    while index < len(lines):
        match = CP2K_WARNING_LINE_RE.match(lines[index])
        if not match:
            index += 1
            continue
        parts = [" ".join(match.group(1).split())]
        cursor = index + 1
        while cursor < len(lines):
            continuation = CP2K_WARNING_CONTINUATION_RE.match(lines[cursor])
            if not continuation:
                break
            content = " ".join(continuation.group(1).split())
            if content:
                parts.append(content)
            cursor += 1
        warnings.append(" ".join(parts))
        index = cursor
    return warnings


def parse_output(
    path: Path,
    input_path: Path | None = None,
    run_metadata_path: Path | None = None,
) -> dict:
    metadata = _read_metadata(run_metadata_path)
    metadata_present = bool(metadata)
    display_path = path.as_posix() if not path.is_absolute() else path.name
    result = {
        "output_file": display_path,
        "exists": path.is_file(),
        "actually_run": bool(metadata.get("attempted", path.is_file())),
        "cp2k_version": metadata.get("cp2k_version"),
        "execution_command": metadata.get("execution_command"),
        "cpu_threads": metadata.get("cpu_threads"),
        "wall_time_seconds": metadata.get("wall_time_seconds"),
        "timeout_seconds": metadata.get("timeout_seconds"),
        "timed_out": bool(metadata.get("timed_out", False)),
        "termination_reason": metadata.get("termination_reason"),
        "confirmed_stop_cause": metadata.get("confirmed_stop_cause"),
        "return_code": metadata.get("return_code"),
        "normal_program_end": False,
        "energy_valid": False,
        "program_completed": False,
        "scf_converged": False,
        "geometry_optimization_converged": None,
        "scf_steps": None,
        "scf_steps_per_run": [],
        "scf_iterations_observed": 0,
        "last_scf_iteration_index": None,
        "total_energy_hartree": None,
        "total_energy_ev": None,
        "fermi_energy_hartree": None,
        "fermi_energy_ev": None,
        "cp2k_warning_count": 0,
        "unique_warning_messages": [],
        "warning_message_counts": {},
        "warning_review_required": False,
        "fatal_warning_detected": False,
        "warning_or_error": None,
    }
    if not path.is_file():
        result["warning_or_error"] = "output file does not exist; calculation was not run"
        return result

    text = path.read_text(encoding="utf-8", errors="replace")
    upper = text.upper()
    warning_messages = _extract_cp2k_warnings(text)
    warning_counts = Counter(warning_messages)
    fatal_warning_detected = any(
        token in message.lower()
        for message in warning_messages
        for token in FATAL_WARNING_TOKENS
    )
    result.update(
        {
            "cp2k_warning_count": len(warning_messages),
            "unique_warning_messages": list(warning_counts),
            "warning_message_counts": dict(warning_counts),
            "warning_review_required": bool(warning_messages),
            "fatal_warning_detected": fatal_warning_detected,
        }
    )
    # A normal CP2K footer contains "PROGRAM STOPPED IN <directory>" even on
    # success, so that phrase must never be treated as an abort marker.
    aborted = any(
        token in upper
        for token in (
            "ABORT|",
            "[ABORT]",
            "*** ERROR",
            "SCF RUN NOT CONVERGED",
            "SCF_NOT_CONVERGED",
        )
    )
    result["normal_program_end"] = "PROGRAM ENDED AT" in upper
    step_counts = [int(value) for value in SCF_CONVERGED_RE.findall(text)]
    iteration_indices = [int(value) for value in SCF_ITERATION_RE.findall(text)]
    result["scf_steps_per_run"] = step_counts
    result["scf_steps"] = sum(step_counts) if step_counts else None
    result["scf_iterations_observed"] = len(iteration_indices)
    result["last_scf_iteration_index"] = (
        iteration_indices[-1] if iteration_indices else None
    )
    result["scf_converged"] = bool(step_counts) and not aborted
    versions = VERSION_RE.findall(text)
    if versions and not result["cp2k_version"]:
        result["cp2k_version"] = versions[-1].strip()
    energies = ENERGY_RE.findall(text)
    if energies:
        energy = float(energies[-1])
        result["total_energy_hartree"] = energy
        result["total_energy_ev"] = energy * HARTREE_TO_EV
    fermi_values = FERMI_RE.findall(text)
    if fermi_values:
        fermi = float(fermi_values[-1])
        result["fermi_energy_hartree"] = fermi
        result["fermi_energy_ev"] = fermi * HARTREE_TO_EV

    is_geo = False
    if input_path and input_path.is_file():
        is_geo = "RUN_TYPE GEO_OPT" in input_path.read_text(
            encoding="utf-8", errors="replace"
        ).upper()
    if is_geo or "GEOMETRY OPTIMIZATION" in upper:
        result["geometry_optimization_converged"] = (
            "GEOMETRY OPTIMIZATION COMPLETED" in upper and not aborted
        )
    geo_ok = (not is_geo) or bool(result["geometry_optimization_converged"])
    return_code_ok = (not metadata_present) or result["return_code"] == 0
    result["energy_valid"] = bool(
        result["actually_run"]
        and not result["timed_out"]
        and return_code_ok
        and result["normal_program_end"]
        and result["scf_converged"]
        and not aborted
        and not fatal_warning_detected
        and energies
    )
    result["program_completed"] = bool(result["energy_valid"] and geo_ok)

    if result["timed_out"]:
        result["warning_or_error"] = (
            f"runner-enforced timeout after {result['timeout_seconds']} seconds"
        )
    elif aborted:
        result["warning_or_error"] = "CP2K reported an abort, stop, or unconverged SCF"
    elif fatal_warning_detected:
        result["warning_or_error"] = (
            "CP2K emitted a warning classified as fatal for the requested outputs"
        )
    elif metadata_present and result["return_code"] is None:
        result["warning_or_error"] = (
            "run metadata has no final return code; termination is not confirmed"
        )
    elif result["return_code"] not in (None, 0):
        result["warning_or_error"] = (
            f"launcher exited with code {result['return_code']}; originating cause is unclassified"
        )
    elif not result["normal_program_end"]:
        result["warning_or_error"] = "normal CP2K end marker is missing"
    elif not result["scf_converged"]:
        result["warning_or_error"] = "explicit SCF convergence marker is missing"
    elif not energies:
        result["warning_or_error"] = "no total FORCE_EVAL energy was found"
    elif is_geo and not result["geometry_optimization_converged"]:
        result["warning_or_error"] = (
            "short geometry optimization ended normally but did not reach geometry convergence"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict CP2K output parser")
    parser.add_argument("output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--run-metadata", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = parse_output(args.output, args.input, args.run_metadata)
    destination = args.json or args.output.with_suffix(".parsed.json")
    destination.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["program_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
