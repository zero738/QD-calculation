from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from parse_cp2k_output import HARTREE_TO_EV


BOHR_TO_ANGSTROM = 0.529177210903


def read_cube(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        raise ValueError("cube file is too short")
    atom_tokens = lines[2].split()
    atom_count = abs(int(atom_tokens[0]))
    origin = np.asarray([float(value) for value in atom_tokens[1:4]], dtype=float)
    counts = []
    vectors = []
    uses_angstrom = False
    for line in lines[3:6]:
        tokens = line.split()
        count = int(tokens[0])
        uses_angstrom = uses_angstrom or count < 0
        counts.append(abs(count))
        vectors.append([float(value) for value in tokens[1:4]])
    data_start = 6 + atom_count
    values = np.asarray([float(value) for line in lines[data_start:] for value in line.split()], dtype=float)
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
            # conventional physical electrostatic potential.
            conventional = -float(value)
            writer.writerow([f"{coordinate:.10f}", f"{value:.12e}", f"{conventional:.12e}", f"{conventional * HARTREE_TO_EV:.12e}"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute the xy-planar average of a CP2K cube")
    parser.add_argument("cube", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_planar_average(args.cube, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
