#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path

from server_analysis import group_atom_counts, parse_extxyz, patch_keyword, scf_signature, sha256, write_json
from verify_server_outputs import gate_h2, read_config, verify_task

ROOT = Path(__file__).resolve().parent


def cdte_signature(path: Path) -> list[tuple]:
    return [
        (atom["element"], round(atom["x"], 8), round(atom["y"], 8), round(atom["z"], 8), atom["region"], atom["fixed"])
        for atom in parse_extxyz(path) if atom["component"] == "cdte_substrate"
    ]


def main() -> int:
    config = read_config()
    allowed, detail = gate_h2(config)
    if not allowed:
        print(json.dumps(detail, indent=2, ensure_ascii=False))
        return 3
    success_path = ROOT / "runs/H1/H1_SUCCESS.json"
    success = json.loads(success_path.read_text(encoding="utf-8"))
    h1 = verify_task("H1", config)
    if not h1["strict_success"]:
        return 3
    h2_dir = ROOT / "runs/H2"
    if h2_dir.exists() and any(h2_dir.iterdir()):
        raise SystemExit(f"refusing to overwrite H2 evidence: {h2_dir}")
    h2_dir.mkdir(parents=True, exist_ok=True)
    base_input = ROOT / "inputs/H2/input.inp"
    h2_structure = ROOT / "inputs/H2/structure.extxyz"
    h1_structure = ROOT / "inputs/H1/structure.extxyz"
    text = base_input.read_text(encoding="utf-8")
    mapping = {
        "EPS_SCF": success["EPS_SCF"], "MAX_SCF": success["MAX_SCF"],
        "ADDED_MOS": success["ADDED_MOS"], "NLUMO": success["NLUMO"],
        "ALPHA": success["ALPHA"], "NBROYDEN": success["NBROYDEN"],
        "ELECTRONIC_TEMPERATURE": success["electronic_temperature_K"],
    }
    for keyword, value in mapping.items():
        text = patch_keyword(text, keyword, str(value))
    executed = h2_dir / "input.executed.inp"
    executed.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    shutil.copy2(h2_structure, h2_dir / "structure.extxyz")
    counts = group_atom_counts(h2_structure)
    geometry_checks = {
        "CdTe_interface_top_Te_count": counts["CdTe_interface_top_Te"],
        "Cu2Te_interface_bottom_Cu_count": counts["Cu2Te_interface_bottom_Cu"],
        "CdTe_substrate_identical_to_H1": cdte_signature(h1_structure) == cdte_signature(h2_structure),
        "substrate_area_angstrom2": config["tasks"]["H2"]["substrate_area_angstrom2"],
        "same_substrate_area_as_H1": config["tasks"]["H2"]["substrate_area_angstrom2"] == config["tasks"]["H1"]["substrate_area_angstrom2"],
    }
    signature_match = scf_signature(executed) == success["scf_signature"]
    geometry_valid = bool(
        geometry_checks["CdTe_interface_top_Te_count"] == 13
        and geometry_checks["Cu2Te_interface_bottom_Cu_count"] == 32
        and geometry_checks["CdTe_substrate_identical_to_H1"]
        and geometry_checks["same_substrate_area_as_H1"]
    )
    payload = {
        "status": "ready" if signature_match and geometry_valid else "blocked",
        "source_H1_success_json": success_path.relative_to(ROOT).as_posix(),
        "successful_H1_attempt": success["successful_attempt"],
        "H1_success_reverified": h1["strict_success"],
        "H1_H2_scf_signature_match": signature_match,
        "H2_scf_signature": scf_signature(executed),
        "H2_base_template_sha256": sha256(base_input),
        "H2_executed_input_sha256": sha256(executed),
        "H2_structure_sha256": sha256(h2_dir / "structure.extxyz"),
        "geometry_checks": geometry_checks,
        "physical_model_changes": "none; only successful H1 SCF-control parameters were substituted",
    }
    write_json(h2_dir / "H2_PREPARATION.json", payload)
    if payload["status"] != "ready":
        return 4
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
