from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    ROOT,
    active_model_ids,
    load_config,
    load_metadata,
    load_model,
    minimum_distance,
    total_vacuum,
    z_layers,
)
from generate_cp2k_inputs import SMOKE_BASIS


def layer_signature(atoms, indices: list[int]) -> list[tuple[str, float, float, float]]:
    return sorted(
        (
            atoms[index].symbol,
            round(float(atoms.positions[index, 0]), 8),
            round(float(atoms.positions[index, 1]), 8),
            round(float(atoms.positions[index, 2]), 8),
        )
        for index in indices
    )


def validate_cp2k_inputs(errors: list[str], config: dict) -> None:
    expected_basis = {element: values[:2] for element, values in SMOKE_BASIS.items()}
    for path in sorted((ROOT / "models").glob("[BH][012]/*.inp")) + sorted(
        (ROOT / "smoke_tests").glob("*/input.inp")
    ):
        text = path.read_text(encoding="utf-8")
        upper = text.upper()
        if "BASIS_SET_FILE_NAME BASIS_MOLOPT" not in upper:
            errors.append(f"{path.relative_to(ROOT)}: smoke input must use BASIS_MOLOPT")
        if "POTENTIAL_FILE_NAME GTH_POTENTIALS" not in upper:
            errors.append(f"{path.relative_to(ROOT)}: missing GTH_POTENTIALS")
        for element in set(line.split()[0] for line in text.splitlines() if line.strip()[:2] in {"Cd", "Te", "Cu"}):
            if element not in expected_basis:
                continue
            basis, potential = expected_basis[element]
            if basis not in text or potential not in text:
                errors.append(f"{path.relative_to(ROOT)}: missing matching {element} basis/potential")
        is_bulk = "PERIODIC XYZ" in upper
        required_periodicity = "PERIODIC XYZ" if is_bulk else "PERIODIC XY"
        if upper.count(required_periodicity) < 2:
            errors.append(f"{path.relative_to(ROOT)}: inconsistent cell/Poisson periodicity")
        if not is_bulk and "PSOLVER ANALYTIC" not in upper:
            errors.append(f"{path.relative_to(ROOT)}: slab input lacks ANALYTIC Poisson solver")
    manifest_path = ROOT / "smoke_tests" / "manifest.json"
    if not manifest_path.is_file():
        errors.append("smoke_tests/manifest.json is missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if [item["id"] for item in manifest] != config["smoke_tests"]["ordered_calculation_ids"]:
            errors.append("smoke-test execution order disagrees with config.yaml")


def validate() -> dict:
    config = load_config()
    errors: list[str] = []
    warnings: list[str] = []
    model_ids = active_model_ids()
    models = {model_id: load_model(model_id) for model_id in model_ids}
    metadata = {model_id: load_metadata(model_id) for model_id in model_ids}
    for model_id, atoms in models.items():
        if set(atoms.get_chemical_symbols()) - {"Cd", "Te", "Cu"}:
            errors.append(f"{model_id}: unexpected chemical element")
        if tuple(bool(value) for value in atoms.pbc) != (True, True, False):
            errors.append(f"{model_id}: PBC must be True,True,False")
        if minimum_distance(atoms) < config["validation"]["minimum_distance_angstrom"]:
            errors.append(f"{model_id}: atom overlap/short distance detected")
        if total_vacuum(atoms) + 1e-6 < config["vacuum"]["minimum_total_angstrom"]:
            errors.append(f"{model_id}: total vacuum below configured minimum")
        if not {"component", "region", "fixed"}.issubset(atoms.arrays):
            errors.append(f"{model_id}: atom classification arrays are incomplete")

    if not metadata["H2"]["total_atoms"] > metadata["H1"]["total_atoms"]:
        errors.append("H2 must contain more atoms than H1")
    if not metadata["H2"]["cu2te_z_span_angstrom"] > metadata["H1"]["cu2te_z_span_angstrom"] > 0:
        errors.append("H2 Cu2Te z-span must be greater than H1")
    if metadata["H1"]["top_termination"] != metadata["H2"]["top_termination"]:
        errors.append("H1 and H2 top terminations differ")
    if metadata["H1"]["interface_first_contact_element"] != metadata["H2"]["interface_first_contact_element"]:
        errors.append("H1 and H2 first Cu2Te contact elements differ")
    if metadata["H1"]["interface_contact_elements"] != metadata["H2"]["interface_contact_elements"]:
        errors.append("H1 and H2 interface contact chemistry differs")
    if metadata["H1"]["cu2te_atomic_plane_count"] != 4:
        errors.append("H1 must contain four Cu2Te atomic planes from one full c repeat")
    if metadata["H2"]["cu2te_atomic_plane_count"] != 8:
        errors.append("H2 must contain eight Cu2Te atomic planes from two full c repeats")

    substrate_count = metadata["B0"]["substrate_atom_count"]
    reference = models["B0"][:substrate_count]
    for model_id in ("H1", "H2"):
        trial = models[model_id][:substrate_count]
        if reference.get_chemical_symbols() != trial.get_chemical_symbols() or not np.allclose(
            reference.positions, trial.positions, atol=1e-8
        ):
            errors.append(f"{model_id}: CdTe substrate differs from B0")
        if not np.allclose(reference.cell[:2], trial.cell[:2], atol=1e-8):
            errors.append(f"{model_id}: lateral cell differs from B0")

    tolerance = config["validation"]["z_layer_tolerance_angstrom"]
    interface_signatures = {}
    for model_id in ("H1", "H2"):
        film = models[model_id][substrate_count:]
        first_layer = z_layers(film, tolerance)[0]
        interface_signatures[model_id] = layer_signature(film, first_layer)
    if interface_signatures["H1"] != interface_signatures["H2"]:
        errors.append("H1 and H2 first Cu2Te contact-plane coordinates differ")

    interface_distances = [
        metadata[model_id]["interface_minimum_distance_angstrom"] for model_id in ("H1", "H2")
    ]
    if not np.isclose(interface_distances[0], interface_distances[1], atol=1e-8):
        errors.append("H1 and H2 interface minimum distances differ")
    mismatch = abs(metadata["H1"]["lattice_mismatch_percent_unstrained"])
    if mismatch > config["validation"]["maximum_warning_mismatch_percent"]:
        warnings.append(f"lattice mismatch {mismatch:.2f}% exceeds warning threshold")
    validate_cp2k_inputs(errors, config)
    warnings.append(
        "CdTe(111) is a thin polar slab; no energy, DOS, work-function or thickness conclusion is reliable"
    )
    result = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "termination_check": {
            "H1_top": metadata["H1"]["top_termination"],
            "H2_top": metadata["H2"]["top_termination"],
            "H1_first_contact": metadata["H1"]["interface_first_contact_element"],
            "H2_first_contact": metadata["H2"]["interface_first_contact_element"],
            "same_top_termination": metadata["H1"]["top_termination"] == metadata["H2"]["top_termination"],
            "same_interface_contact": interface_signatures["H1"] == interface_signatures["H2"],
        },
        "models": metadata,
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "validation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    result = validate()
    print(
        json.dumps(
            {"ok": result["ok"], "errors": result["errors"], "warnings": result["warnings"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
