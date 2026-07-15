from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
from ase import Atoms
from ase.build import make_supercell, surface
from ase.io import read, write

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, lateral_area, load_config, minimum_distance, model_counts, total_vacuum, z_layers


def matrix3(matrix2):
    return np.array([[matrix2[0][0], matrix2[0][1], 0], [matrix2[1][0], matrix2[1][1], 0], [0, 0, 1]])


def build_cdte_substrate(config: dict) -> tuple[Atoms, list[int]]:
    bulk_path = ROOT / "structures" / "bulk" / "CdTe_AFLOW_mp406.cif"
    conventional = read(bulk_path)
    if sorted(set(conventional.get_chemical_symbols())) != ["Cd", "Te"]:
        raise ValueError("CdTe reference CIF did not expand to Cd and Te atoms")
    # ASE surface accepts the conventional verified CIF directly.  Three (111)
    # repeats produce six alternating Cd/Te atomic planes.
    slab = surface(conventional, tuple(config["cdte"]["miller_index"]), config["cdte"]["bilayers"], vacuum=0.0, periodic=False)
    # The conventional cell creates four times the smallest surface cell. Reduce
    # to a primitive zinc-blende cell before the coincidence supercell search.
    from ase.build import bulk as ase_bulk
    primitive = ase_bulk("CdTe", "zincblende", a=config["cdte"]["lattice_a_angstrom"])
    slab = surface(primitive, tuple(config["cdte"]["miller_index"]), config["cdte"]["bilayers"], vacuum=0.0, periodic=False)
    slab = make_supercell(slab, matrix3(config["cdte"]["lateral_supercell"]))
    slab.pbc = (True, True, False)
    layers = z_layers(slab, config["validation"]["z_layer_tolerance_angstrom"])
    if slab[layers[-1][0]].symbol != "Te":
        slab.positions[:, 2] = slab.positions[:, 2].max() - slab.positions[:, 2]
        layers = z_layers(slab, config["validation"]["z_layer_tolerance_angstrom"])
    slab.positions[:, 2] -= slab.positions[:, 2].min()
    slab.positions[:, 2] += config["vacuum"]["bottom_angstrom"]
    fixed_planes = config["constraints"]["fixed_bottom_cdte_atomic_planes"]
    fixed_indices = sorted(i for layer in layers[:fixed_planes] for i in layer)
    return slab, fixed_indices


def build_cu2te_sheets(config: dict, target_cell, count: int) -> Atoms:
    if count == 0:
        return Atoms(cell=target_cell, pbc=(True, True, False))
    bulk = read(ROOT / "structures" / "bulk" / "Cu2Te_AFLOW_icsd655706.cif")
    scaled_z = bulk.get_scaled_positions(wrap=True)[:, 2]
    order = np.argsort(scaled_z)
    lower = [int(i) for i in order if scaled_z[i] < 0.5]
    upper = [int(i) for i in order if scaled_z[i] >= 0.5]
    if len(lower) != 3 or len(upper) != 3:
        raise ValueError("Cu2Te CIF did not expand into two Cu2Te structural sheets")
    selected = lower if count == 1 else lower + upper
    film = bulk[selected]
    # Convert the source 120-degree hexagonal basis to an equivalent 60-degree basis.
    film = make_supercell(film, np.array([[1, 0, 0], [1, 1, 0], [0, 0, 1]]))
    film = make_supercell(film, matrix3(config["cu2te"]["lateral_supercell"]))
    film.set_cell(target_cell, scale_atoms=True)
    film.positions[:, 2] -= film.positions[:, 2].min()
    film.pbc = (True, True, False)
    return film


def add_regions(atoms: Atoms, substrate_count: int, fixed_indices: list[int], cute_layers: int, tolerance: float):
    regions = np.full(len(atoms), "cdte_substrate", dtype="U24")
    cdte_layers = z_layers(atoms[:substrate_count], tolerance)
    regions[cdte_layers[-1]] = "interface_cdte_surface"
    if cute_layers:
        film = atoms[substrate_count:]
        film_layers = z_layers(film, tolerance)
        # Each Cu2Te structural sheet contains two nearby atomic planes.
        midpoint = len(film_layers) // cute_layers
        for sheet in range(cute_layers):
            start = sheet * midpoint
            end = len(film_layers) if sheet == cute_layers - 1 else (sheet + 1) * midpoint
            label = "interface_cute_layer" if sheet == 0 else f"cute_film_layer_{sheet + 1}"
            for layer in film_layers[start:end]:
                regions[np.array(layer) + substrate_count] = label
    atoms.new_array("region", regions)
    atoms.new_array("fixed", np.array([i in set(fixed_indices) for i in range(len(atoms))], dtype=bool))


def preview(atoms: Atoms, output: Path):
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=160)
    palette = {"Cd": "#E0A000", "Te": "#C73E3A", "Cu": "#3977B8"}
    symbols = np.array(atoms.get_chemical_symbols())
    for element in ("Cd", "Te", "Cu"):
        mask = symbols == element
        if np.any(mask):
            ax.scatter(atoms.positions[mask, 0], atoms.positions[mask, 2], s=120,
                       c=palette[element], edgecolors="black", linewidths=0.7,
                       alpha=0.90, label=element)
    ax.set_title(output.parent.name + " side view")
    ax.set_xlabel("projected in-plane x (A)")
    ax.set_ylabel("z (A)")
    ax.set_ylim(0.0, atoms.cell.lengths()[2])
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    present = [element for element in ("Cd", "Te", "Cu") if element in atoms.get_chemical_symbols()]
    ax.legend(handles=[Patch(facecolor=palette[e], edgecolor="black", label=e) for e in present], loc="upper right")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def main() -> int:
    config = load_config()
    substrate, fixed = build_cdte_substrate(config)
    substrate_count = len(substrate)
    cd_length = float(np.linalg.norm(substrate.cell[0]))
    cu_length = config["cu2te"]["lateral_supercell"][0][0] * 4.237
    mismatch = 100.0 * (cu_length - cd_length) / cd_length
    strain = 100.0 * (cd_length - cu_length) / cu_length
    for model_id, count in config["cu2te"]["layer_counts"].items():
        film_cell = substrate.cell.copy()
        film_cell[2] = [0.0, 0.0, 7.24700717]
        film = build_cu2te_sheets(config, film_cell, count)
        atoms = substrate.copy()
        if count:
            film.positions[:, 2] += atoms.positions[:, 2].max() + config["interface"]["initial_gap_angstrom"]
            shift = np.dot(config["interface"]["lateral_shift_fractional"], atoms.cell[:2, :2])
            film.positions[:, :2] += shift
            atoms += film
        top = float(atoms.positions[:, 2].max())
        atoms.set_cell([atoms.cell[0], atoms.cell[1], [0.0, 0.0, top + config["vacuum"]["top_angstrom"]]])
        atoms.pbc = (True, True, False)
        add_regions(atoms, substrate_count, fixed, count, config["validation"]["z_layer_tolerance_angstrom"])
        model_dir = ROOT / "models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        write(model_dir / "structure.extxyz", atoms)
        write(model_dir / "structure.xyz", atoms, format="xyz")
        write(model_dir / "structure.cif", atoms, format="cif")
        cute_z = atoms.positions[substrate_count:, 2]
        thickness = float(np.ptp(cute_z)) if len(cute_z) else 0.0
        metadata = {
            "model_id": model_id,
            "cu_te_layers": count,
            "substrate_atom_count": substrate_count,
            "fixed_atom_indices_0based": fixed,
            "fixed_atom_indices_cp2k_1based": [i + 1 for i in fixed],
            "counts": model_counts(atoms),
            "total_atoms": len(atoms),
            "initial_cute_thickness_angstrom": thickness,
            "initial_cute_thickness_nm": thickness / 10.0,
            "minimum_distance_angstrom": minimum_distance(atoms),
            "total_vacuum_angstrom": total_vacuum(atoms),
            "lateral_area_angstrom2": lateral_area(atoms),
            "lattice_mismatch_percent_unstrained": mismatch,
            "applied_cute_biaxial_strain_percent": strain,
            "scientific_status": "verified-source structural prototype; not a converged interface prediction",
        }
        (model_dir / "model.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        preview(atoms, model_dir / "preview_side.png")
        print(f"{model_id}: {len(atoms)} atoms, Cu-Te thickness={thickness:.3f} A, dmin={metadata['minimum_distance_angstrom']:.3f} A")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
