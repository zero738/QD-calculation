from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config, load_metadata, load_model, minimum_distance, total_vacuum


def validate() -> dict:
    config = load_config()
    errors, warnings = [], []
    models = {mid: load_model(mid) for mid in ("T0", "T1", "T2")}
    meta = {mid: load_metadata(mid) for mid in models}
    for mid, atoms in models.items():
        if set(atoms.get_chemical_symbols()) - {"Cd", "Te", "Cu"}:
            errors.append(f"{mid}: unexpected chemical element")
        if tuple(bool(x) for x in atoms.pbc) != (True, True, False):
            errors.append(f"{mid}: PBC must be True,True,False")
        if minimum_distance(atoms) < config["validation"]["minimum_distance_angstrom"]:
            errors.append(f"{mid}: atom overlap/short distance detected")
        if total_vacuum(atoms) + 1e-6 < config["vacuum"]["minimum_total_angstrom"]:
            errors.append(f"{mid}: total vacuum below configured minimum")
    if not (meta["T2"]["counts"].get("Cu", 0) > meta["T1"]["counts"].get("Cu", 0) > 0):
        errors.append("Cu atom count must increase from T1 to T2")
    if not meta["T2"]["initial_cute_thickness_angstrom"] > meta["T1"]["initial_cute_thickness_angstrom"] > 0:
        errors.append("Cu-Te thickness must increase from T1 to T2")
    nsub = meta["T0"]["substrate_atom_count"]
    ref = models["T0"][:nsub]
    for mid in ("T1", "T2"):
        trial = models[mid][:nsub]
        if ref.get_chemical_symbols() != trial.get_chemical_symbols() or not np.allclose(ref.positions, trial.positions, atol=1e-8):
            errors.append(f"{mid}: CdTe substrate differs from T0")
        if not np.allclose(ref.cell[:2], trial.cell[:2], atol=1e-8):
            errors.append(f"{mid}: lateral cell differs from T0")
    mismatch = abs(meta["T1"]["lattice_mismatch_percent_unstrained"])
    if mismatch > config["validation"]["maximum_warning_mismatch_percent"]:
        warnings.append(f"lattice mismatch {mismatch:.2f}% exceeds warning threshold")
    result = {"ok": not errors, "errors": errors, "warnings": warnings, "models": meta}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "validation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    result = validate()
    print(json.dumps({"ok": result["ok"], "errors": result["errors"], "warnings": result["warnings"]}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
