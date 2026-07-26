from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from ase.io import read

from common import load_config
from parse_cp2k_output import HARTREE_TO_EV


BOHR_TO_ANGSTROM = 0.529177210903


def read_cube(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        raise ValueError("cube file is too short")
    atom_tokens = lines[2].split()
    atom_count = abs(int(atom_tokens[0]))
    origin = np.asarray([float(value) for value in atom_tokens[1:4]], dtype=float)
    counts: list[int] = []
    vectors: list[list[float]] = []
    uses_angstrom = False
    for line in lines[3:6]:
        tokens = line.split()
        count = int(tokens[0])
        uses_angstrom = uses_angstrom or count < 0
        counts.append(abs(count))
        vectors.append([float(value) for value in tokens[1:4]])
    data_start = 6 + atom_count
    values = np.asarray(
        [float(value) for line in lines[data_start:] for value in line.split()],
        dtype=float,
    )
    expected = int(np.prod(counts))
    if values.size != expected:
        raise ValueError(f"cube contains {values.size} grid values; expected {expected}")
    grid = values.reshape(tuple(counts))
    planar = np.mean(grid, axis=(0, 1))
    z = origin[2] + np.arange(counts[2], dtype=float) * np.asarray(vectors)[2, 2]
    if not uses_angstrom:
        z *= BOHR_TO_ANGSTROM
    return z, planar


def write_planar_average(cube: Path, output: Path) -> None:
    z, raw = read_cube(cube)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "z_angstrom",
                "cp2k_v_hartree_raw_hartree",
                "conventional_electrostatic_potential_hartree",
                "conventional_electrostatic_potential_ev",
            ]
        )
        for coordinate, value in zip(z, raw):
            # CP2K documents V_HARTREE_CUBE with the opposite sign to the
            # conventional electrostatic potential.
            conventional = -float(value)
            writer.writerow(
                [
                    f"{coordinate:.10f}",
                    f"{value:.12e}",
                    f"{conventional:.12e}",
                    f"{conventional * HARTREE_TO_EV:.12e}",
                ]
            )


def _continuous_segments(mask: np.ndarray) -> list[np.ndarray]:
    indices = np.flatnonzero(mask)
    if not indices.size:
        return []
    breaks = np.where(np.diff(indices) > 1)[0] + 1
    return [segment for segment in np.split(indices, breaks) if segment.size]


def _plateau(
    side: str,
    z: np.ndarray,
    potential_ev: np.ndarray,
    density_au: np.ndarray,
    atom_z_min: float,
    atom_z_max: float,
    settings: dict,
) -> dict:
    exclusion = float(settings["vacuum_atom_exclusion_angstrom"])
    if side == "bottom":
        outside = z <= atom_z_min - exclusion
    else:
        outside = z >= atom_z_max + exclusion
    slope = np.abs(np.gradient(potential_ev, z))
    candidates = (
        outside
        & (density_au <= float(settings["vacuum_density_threshold_au"]))
        & (slope <= float(settings["vacuum_max_local_slope_ev_per_angstrom"]))
    )
    segments = sorted(
        _continuous_segments(candidates),
        key=lambda segment: float(z[segment[-1]] - z[segment[0]]),
        reverse=True,
    )
    minimum_width = float(settings["vacuum_min_plateau_width_angstrom"])
    maximum_std = float(settings["vacuum_max_plateau_std_ev"])
    for segment in segments:
        width = float(z[segment[-1]] - z[segment[0]])
        values = potential_ev[segment]
        std = float(np.std(values))
        if width >= minimum_width and std <= maximum_std:
            return {
                "side": side,
                "detection_status": "reliable",
                "plateau_width_angstrom": width,
                "plateau_mean_ev": float(np.mean(values)),
                "plateau_std_ev": std,
                "z_start_angstrom": float(z[segment[0]]),
                "z_end_angstrom": float(z[segment[-1]]),
                "grid_point_count": int(segment.size),
            }
    return {
        "side": side,
        "detection_status": "unreliable_or_not_found",
        "plateau_width_angstrom": None,
        "plateau_mean_ev": None,
        "plateau_std_ev": None,
        "z_start_angstrom": None,
        "z_end_angstrom": None,
        "grid_point_count": 0,
    }


def analyze_vacuum_plateaus(
    run_dir: Path,
    fermi_energy_ev: float | None,
) -> dict:
    potential_path = run_dir / "hartree_potential.cube"
    density_path = run_dir / "electron_density.cube"
    structure_path = run_dir / "structure.extxyz"
    result = {
        "method": (
            "continuous low-density, low-slope xy-planar-average plateau; "
            "CP2K V_HARTREE sign inverted and hartree converted to eV"
        ),
        "top": {"detection_status": "not_analyzed"},
        "bottom": {"detection_status": "not_analyzed"},
        "vacuum_level_top_ev": None,
        "vacuum_level_bottom_ev": None,
        "work_function_top_ev": None,
        "work_function_bottom_ev": None,
        "work_function_scope_warning": (
            "Top/bottom values are prototype slab proxies. The polar CdTe(111) "
            "model and fixed initial geometry do not establish an absolute work function."
        ),
    }
    if not (potential_path.is_file() and density_path.is_file() and structure_path.is_file()):
        result["analysis_status"] = "missing_cube_or_structure"
        return result
    atoms = read(structure_path)
    if all(atoms.pbc):
        result["analysis_status"] = "not_applicable_to_3d_bulk"
        return result
    z_potential, raw_potential = read_cube(potential_path)
    z_density, density = read_cube(density_path)
    if not np.allclose(z_potential, z_density, atol=1.0e-8):
        density = np.interp(z_potential, z_density, density)
    conventional_potential_ev = -raw_potential * HARTREE_TO_EV
    settings = load_config()["cp2k"]["profiles"]["research_lite"]
    atom_z_min = float(np.min(atoms.positions[:, 2]))
    atom_z_max = float(np.max(atoms.positions[:, 2]))
    bottom = _plateau(
        "bottom",
        z_potential,
        conventional_potential_ev,
        density,
        atom_z_min,
        atom_z_max,
        settings,
    )
    top = _plateau(
        "top",
        z_potential,
        conventional_potential_ev,
        density,
        atom_z_min,
        atom_z_max,
        settings,
    )
    result.update(
        {
            "analysis_status": (
                "reliable_both_sides"
                if top["detection_status"] == bottom["detection_status"] == "reliable"
                else "one_or_more_plateaus_unreliable"
            ),
            "top": top,
            "bottom": bottom,
            "vacuum_level_top_ev": top.get("plateau_mean_ev"),
            "vacuum_level_bottom_ev": bottom.get("plateau_mean_ev"),
        }
    )
    if fermi_energy_ev is not None:
        if top.get("plateau_mean_ev") is not None:
            result["work_function_top_ev"] = (
                float(top["plateau_mean_ev"]) - float(fermi_energy_ev)
            )
        if bottom.get("plateau_mean_ev") is not None:
            result["work_function_bottom_ev"] = (
                float(bottom["plateau_mean_ev"]) - float(fermi_energy_ev)
            )
    combined = run_dir / "planar_average_potential_density.csv"
    with combined.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "z_angstrom",
                "conventional_electrostatic_potential_ev",
                "electron_density_au",
            ]
        )
        for coordinate, potential, density_value in zip(
            z_potential, conventional_potential_ev, density
        ):
            writer.writerow(
                [
                    f"{coordinate:.10f}",
                    f"{potential:.12e}",
                    f"{density_value:.12e}",
                ]
            )
    (run_dir / "vacuum_plateau_analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze CP2K xy-planar averages")
    parser.add_argument("cube", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_planar_average(args.cube, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
