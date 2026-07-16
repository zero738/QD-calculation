from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
from ase import Atoms
from ase.build import bulk as ase_bulk
from ase.build import make_supercell, surface
from ase.io import read, write

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    ROOT,
    lateral_area,
    load_config,
    minimum_distance,
    minimum_pair_between,
    model_counts,
    total_vacuum,
    z_layers,
)


def matrix3(matrix2):
    return np.array(
        [[matrix2[0][0], matrix2[0][1], 0], [matrix2[1][0], matrix2[1][1], 0], [0, 0, 1]],
        dtype=int,
    )


def build_cdte_substrate(config: dict) -> tuple[Atoms, list[int]]:
    """Build the shared CdTe(111) substrate from the verified zinc-blende source."""
    conventional = read(ROOT / "structures" / "bulk" / "CdTe_AFLOW_mp406.cif")
    if sorted(set(conventional.get_chemical_symbols())) != ["Cd", "Te"]:
        raise ValueError("CdTe reference CIF did not expand to Cd and Te atoms")
    source_a = float(conventional.cell.lengths()[0])
    if not np.isclose(source_a, config["cdte"]["lattice_a_angstrom"], atol=1e-8):
        raise ValueError("CdTe CIF lattice constant disagrees with config.yaml")
    primitive = ase_bulk("CdTe", "zincblende", a=source_a)
    slab = surface(
        primitive,
        tuple(config["cdte"]["miller_index"]),
        config["cdte"]["bilayers"],
        vacuum=0.0,
        periodic=False,
    )
    slab = make_supercell(slab, matrix3(config["cdte"]["lateral_supercell"]))
    slab.pbc = (True, True, False)
    layers = z_layers(slab, config["validation"]["z_layer_tolerance_angstrom"])
    if {slab[i].symbol for i in layers[-1]} != {"Te"}:
        slab.positions[:, 2] = slab.positions[:, 2].max() - slab.positions[:, 2]
        layers = z_layers(slab, config["validation"]["z_layer_tolerance_angstrom"])
    if {slab[i].symbol for i in layers[-1]} != {"Te"}:
        raise ValueError("CdTe substrate could not be made Te-terminated")
    slab.positions[:, 2] -= slab.positions[:, 2].min()
    slab.positions[:, 2] += config["vacuum"]["bottom_angstrom"]
    fixed_planes = config["constraints"]["fixed_bottom_cdte_atomic_planes"]
    fixed_indices = sorted(i for layer in layers[:fixed_planes] for i in layer)
    return slab, fixed_indices


def build_cu2te_repeats(config: dict, target_xy_cell, repeat_count: int) -> Atoms:
    """Build whole crystallographic c repeats; never slice or delete boundary planes."""
    if repeat_count == 0:
        return Atoms(cell=target_xy_cell, pbc=(True, True, False))
    source = read(ROOT / "structures" / "bulk" / "Cu2Te_AFLOW_icsd655706.cif")
    if source.get_chemical_formula() != "Cu4Te2" or len(source) != 6:
        raise ValueError("Cu2Te CIF did not expand to the expected six-atom conventional cell")
    tolerance = config["validation"]["z_layer_tolerance_angstrom"]
    source_layers = z_layers(source, tolerance)
    if len(source_layers) != 4:
        raise ValueError("Cu2Te full c repeat must contain four atomic planes")
    bottom = {source[i].symbol for i in source_layers[0]}
    top = {source[i].symbol for i in source_layers[-1]}
    if bottom != top:
        raise ValueError(
            f"Cu2Te full c repeat changes termination ({sorted(bottom)} -> {sorted(top)}); "
            "refusing to force a thickness series"
        )

    # Equivalent 60-degree in-plane basis, followed by the 4x4 coincidence cell
    # and an integer number of complete crystallographic c repeats.
    film = make_supercell(source, np.array([[1, 0, 0], [1, 1, 0], [0, 0, 1]], dtype=int))
    lateral = config["cu2te"]["lateral_supercell"]
    repeat_matrix = matrix3(lateral)
    repeat_matrix[2, 2] = repeat_count
    film = make_supercell(film, repeat_matrix)
    target = target_xy_cell.copy()
    target[2] = [0.0, 0.0, repeat_count * config["cu2te"]["bulk_c_angstrom"]]
    film.set_cell(target, scale_atoms=True)
    film.positions[:, 2] -= film.positions[:, 2].min()
    film.pbc = (True, True, False)
    return film


def add_classification_arrays(
    atoms: Atoms,
    substrate_count: int,
    fixed_indices: list[int],
    tolerance: float,
) -> None:
    regions = np.full(len(atoms), "cdte_substrate", dtype="U32")
    components = np.full(len(atoms), "cdte_substrate", dtype="U20")
    substrate_layers = z_layers(atoms[:substrate_count], tolerance)
    regions[np.asarray(substrate_layers[-1], dtype=int)] = "interface_cdte_surface"
    if len(atoms) > substrate_count:
        film_layers = z_layers(atoms[substrate_count:], tolerance)
        components[substrate_count:] = "cu2te_film"
        regions[substrate_count:] = "cu2te_film"
        contact = np.asarray(film_layers[0], dtype=int) + substrate_count
        regions[contact] = "interface_cu2te_contact"
        top = np.asarray(film_layers[-1], dtype=int) + substrate_count
        regions[top] = "cu2te_top_termination"
    atoms.new_array("component", components)
    atoms.new_array("region", regions)
    fixed_set = set(fixed_indices)
    atoms.new_array("fixed", np.array([i in fixed_set for i in range(len(atoms))], dtype=bool))


def preview(atoms: Atoms, output: Path, meta: dict) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 5.5), dpi=170)
    palette = {"Cd": "#E0A000", "Te": "#C73E3A", "Cu": "#3977B8"}
    symbols = np.array(atoms.get_chemical_symbols())
    x_min, x_max = float(atoms.positions[:, 0].min()), float(atoms.positions[:, 0].max())
    substrate_top = float(atoms.positions[: meta["substrate_atom_count"], 2].max())
    substrate_bottom = float(atoms.positions[: meta["substrate_atom_count"], 2].min())
    film_present = meta["cu2te_repeat_count"] > 0
    if film_present:
        film_bottom = float(atoms.positions[meta["substrate_atom_count"] :, 2].min())
        film_top = float(atoms.positions[meta["substrate_atom_count"] :, 2].max())
        interface_z = 0.5 * (substrate_top + film_bottom)
        ax.axhline(interface_z, color="#5A2A82", linestyle="--", linewidth=1.8)
        ax.text(x_min, interface_z + 0.25, "interface", color="#5A2A82", weight="bold")
        ax.text(x_min, 0.5 * (film_bottom + film_top), "Cu2Te film", color="#234F7D", weight="bold")
        arrow_x = x_max + 1.0
        ax.annotate(
            "",
            xy=(arrow_x, film_top),
            xytext=(arrow_x, film_bottom),
            arrowprops=dict(arrowstyle="<->", color="#234F7D", linewidth=1.8),
        )
        ax.text(
            arrow_x + 0.25,
            0.5 * (film_bottom + film_top),
            f"Cu2Te z-span\n{meta['cu2te_z_span_angstrom']:.3f} A",
            va="center",
            color="#234F7D",
        )
        ax.annotate(
            f"top termination: {meta['top_termination']}",
            xy=(x_max * 0.75, film_top),
            xytext=(x_max * 0.55, film_top + 2.0),
            arrowprops=dict(arrowstyle="->", color="black"),
            ha="center",
        )
    else:
        interface_z = substrate_top + 1.3
        ax.axhline(interface_z, color="#777777", linestyle="--", linewidth=1.2)
        ax.text(x_min, interface_z + 0.25, "no interface / no Cu2Te film", color="#555555")
        ax.text(x_min, interface_z + 1.5, "Cu2Te film: absent (B0 control)", color="#555555", weight="bold")
    ax.text(x_min, 0.5 * (substrate_bottom + substrate_top), "CdTe substrate", color="#6D4D00", weight="bold")

    for element in ("Cd", "Te", "Cu"):
        mask = symbols == element
        if np.any(mask):
            ax.scatter(
                atoms.positions[mask, 0],
                atoms.positions[mask, 2],
                s=105,
                c=palette[element],
                edgecolors="black",
                linewidths=0.55,
                alpha=0.90,
                label=element,
                zorder=3,
            )
    ax.set_title(
        f"{meta['model_id']}: CdTe/Cu2Te thickness prototype "
        f"({meta['cu2te_repeat_count']} complete c repeat(s))"
    )
    ax.set_xlabel("projected in-plane x (A)")
    ax.set_ylabel("z (A)")
    ax.set_ylim(0.0, atoms.cell.lengths()[2] + 0.8)
    ax.set_xlim(x_min - 0.8, x_max + 5.2)
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    present = [element for element in ("Cd", "Te", "Cu") if element in symbols]
    ax.legend(
        handles=[Patch(facecolor=palette[e], edgecolor="black", label=e) for e in present],
        loc="upper right",
    )
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def build_metadata(
    atoms: Atoms,
    model_id: str,
    repeat_count: int,
    substrate_count: int,
    fixed: list[int],
    mismatch: float,
    strain: float,
    tolerance: float,
) -> dict:
    film_indices = list(range(substrate_count, len(atoms)))
    substrate_indices = list(range(substrate_count))
    if film_indices:
        film = atoms[film_indices]
        film_layers = z_layers(film, tolerance)
        z_span = float(np.ptp(film.positions[:, 2]))
        bottom_symbols = sorted({film[i].symbol for i in film_layers[0]})
        top_symbols = sorted({film[i].symbol for i in film_layers[-1]})
        interface_distance, substrate_i, film_i = minimum_pair_between(atoms, substrate_indices, film_indices)
        substrate_surface = sorted(
            {atoms[i].symbol for i in z_layers(atoms[:substrate_count], tolerance)[-1]}
        )
        contact = f"{'+'.join(substrate_surface)}(CdTe)/{'+'.join(bottom_symbols)}(Cu2Te)"
        pair = f"{atoms[substrate_i].symbol}{substrate_i + 1}-{atoms[film_i].symbol}{film_i + 1}"
        first_contact = "+".join(bottom_symbols)
        top_termination = "+".join(top_symbols)
    else:
        film_layers = []
        z_span = 0.0
        interface_distance = None
        pair = ""
        contact = "none"
        first_contact = "none"
        top_termination = "none"
    return {
        "model_id": model_id,
        "cu2te_repeat_count": repeat_count,
        "cu2te_atomic_plane_count": len(film_layers),
        "cu2te_z_span_angstrom": z_span,
        "cu2te_z_span_nm": z_span / 10.0,
        "top_termination": top_termination,
        "interface_first_contact_element": first_contact,
        "interface_contact_elements": contact,
        "interface_minimum_distance_angstrom": interface_distance,
        "nearest_interface_atom_pair": pair,
        "substrate_atom_count": substrate_count,
        "fixed_atom_indices_0based": fixed,
        "fixed_atom_indices_cp2k_1based": [i + 1 for i in fixed],
        "counts": model_counts(atoms),
        "total_atoms": len(atoms),
        "minimum_distance_angstrom": minimum_distance(atoms),
        "total_vacuum_angstrom": total_vacuum(atoms),
        "lateral_area_angstrom2": lateral_area(atoms),
        "lattice_mismatch_percent_unstrained": mismatch,
        "applied_cu2te_biaxial_strain_percent": strain,
        "prototype_only": True,
        "scientific_status": "verified-source structural prototype; not a converged interface prediction",
    }


def main() -> int:
    config = load_config()
    substrate, fixed = build_cdte_substrate(config)
    substrate_count = len(substrate)
    cd_length = float(np.linalg.norm(substrate.cell[0]))
    cu_length = config["cu2te"]["lateral_supercell"][0][0] * 4.237
    mismatch = 100.0 * (cu_length - cd_length) / cd_length
    strain = 100.0 * (cd_length - cu_length) / cu_length
    tolerance = config["validation"]["z_layer_tolerance_angstrom"]
    for model_id, repeat_count in config["cu2te"]["repeat_counts"].items():
        film = build_cu2te_repeats(config, substrate.cell.copy(), repeat_count)
        atoms = substrate.copy()
        if repeat_count:
            film.positions[:, 2] += atoms.positions[:, 2].max() + config["interface"]["initial_gap_angstrom"]
            shift = np.dot(config["interface"]["lateral_shift_fractional"], atoms.cell[:2, :2])
            film.positions[:, :2] += shift
            atoms += film
        top = float(atoms.positions[:, 2].max())
        atoms.set_cell(
            [atoms.cell[0], atoms.cell[1], [0.0, 0.0, top + config["vacuum"]["top_angstrom"]]]
        )
        atoms.pbc = (True, True, False)
        add_classification_arrays(atoms, substrate_count, fixed, tolerance)
        metadata = build_metadata(
            atoms,
            model_id,
            repeat_count,
            substrate_count,
            fixed,
            mismatch,
            strain,
            tolerance,
        )
        model_dir = ROOT / "models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        write(model_dir / "structure.extxyz", atoms)
        write(model_dir / "structure.xyz", atoms, format="xyz")
        write(model_dir / "structure.cif", atoms, format="cif")
        (model_dir / "model.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        preview(atoms, model_dir / "preview_side.png", metadata)
        print(
            f"{model_id}: {len(atoms)} atoms, repeats={repeat_count}, "
            f"planes={metadata['cu2te_atomic_plane_count']}, "
            f"Cu2Te z-span={metadata['cu2te_z_span_angstrom']:.3f} A, "
            f"top={metadata['top_termination']}, dmin={metadata['minimum_distance_angstrom']:.3f} A"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
