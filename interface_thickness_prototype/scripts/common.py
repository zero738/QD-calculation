from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import yaml
from ase.io import read

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    with (ROOT / "config.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def active_model_ids() -> tuple[str, ...]:
    return tuple(load_config()["active_model_ids"])


def load_metadata(model_id: str) -> dict:
    with (ROOT / "models" / model_id / "model.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def load_model(model_id: str):
    return read(ROOT / "models" / model_id / "structure.extxyz")


def z_layers(atoms, tolerance: float) -> list[list[int]]:
    order = np.argsort(atoms.positions[:, 2])
    layers: list[list[int]] = []
    for idx in order:
        if not layers:
            layers.append([int(idx)])
            continue
        mean_z = float(np.mean(atoms.positions[layers[-1], 2]))
        if abs(float(atoms.positions[idx, 2]) - mean_z) <= tolerance:
            layers[-1].append(int(idx))
        else:
            layers.append([int(idx)])
    return layers


def minimum_distance(atoms) -> float:
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    return float(np.min(distances))


def model_counts(atoms) -> dict[str, int]:
    return dict(Counter(atoms.get_chemical_symbols()))


def total_vacuum(atoms) -> float:
    span = float(np.ptp(atoms.positions[:, 2])) if len(atoms) else 0.0
    return float(atoms.cell.lengths()[2] - span)


def lateral_area(atoms) -> float:
    return float(np.linalg.norm(np.cross(atoms.cell[0], atoms.cell[1])))


def minimum_pair_between(atoms, first: list[int], second: list[int]) -> tuple[float, int, int]:
    """Return the minimum-image distance and atom indices across two groups."""
    if not first or not second:
        raise ValueError("both atom-index groups must be non-empty")
    best = (float("inf"), -1, -1)
    second_array = np.asarray(second, dtype=int)
    for i in first:
        distances = np.asarray(atoms.get_distances(i, second_array, mic=True), dtype=float)
        j_local = int(np.argmin(distances))
        candidate = (float(distances[j_local]), int(i), int(second_array[j_local]))
        if candidate[0] < best[0]:
            best = candidate
    return best
