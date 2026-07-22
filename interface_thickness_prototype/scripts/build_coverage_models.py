from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
from ase.io import read, write

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_models import build_metadata
from common import ROOT, load_config


PALETTE = {"Cd": "#E0A000", "Te": "#C73E3A", "Cu": "#3977B8"}


def _load_active(model_id: str):
    model_dir = ROOT / "models" / model_id
    atoms = read(model_dir / "structure.extxyz")
    meta = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
    return atoms, meta


def _unit_labels(film, divisions: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Map the 4x4 Cu2Te film to complete lateral source-cell labels."""
    fractional = np.mod(film.get_scaled_positions(wrap=False), 1.0)
    i = np.floor((fractional[:, 0] + 1.0e-8) * divisions).astype(int) % divisions
    j = np.floor((fractional[:, 1] + 1.0e-8) * divisions).astype(int) % divisions
    return i, j


def build_coverage_series(config: dict) -> dict[str, tuple]:
    b0, b0_meta = _load_active("B0")
    h1, h1_meta = _load_active("H1")
    substrate_count = h1_meta["substrate_atom_count"]
    if len(b0) != substrate_count:
        raise ValueError("B0 is not the same substrate atom count recorded by H1")
    if not np.allclose(b0.positions, h1.positions[:substrate_count], atol=1.0e-10):
        raise ValueError("B0 and H1 CdTe substrate coordinates differ")

    film = h1[substrate_count:]
    unit_i, unit_j = _unit_labels(film)
    symbols = np.asarray(film.get_chemical_symbols())
    for i in range(4):
        for j in range(4):
            mask = (unit_i == i) & (unit_j == j)
            if int(mask.sum()) != 6:
                raise ValueError(f"lateral Cu2Te unit ({i},{j}) does not contain six atoms")
            selected = symbols[mask]
            if int(np.sum(selected == "Cu")) != 4 or int(np.sum(selected == "Te")) != 2:
                raise ValueError(f"lateral Cu2Te unit ({i},{j}) is not Cu4Te2")

    # Keep two adjacent columns of whole 4x4 source cells.  This is a 50%-area
    # stripe, continuous and periodic along cell vector B; its two edges run
    # parallel to B and repeat along cell vector A.
    # Columns 1 and 2 preserve the same 2.600 A nearest interface contact as
    # the full H1/C100 film; columns 0 and 1 would remove that contact pair.
    keep_film = np.isin(unit_i, (1, 2))
    c50 = h1[list(range(substrate_count)) + list(substrate_count + np.flatnonzero(keep_film))]
    c50.cell = h1.cell.copy()
    c50.pbc = h1.pbc.copy()

    models = {
        "C0": (b0.copy(), b0_meta, 0.0, 0),
        "C50": (c50, h1_meta, 50.0, 8),
        "C100": (h1.copy(), h1_meta, 100.0, 16),
    }
    output = {}
    tolerance = config["validation"]["z_layer_tolerance_angstrom"]
    for model_id, (atoms, source_meta, coverage, lateral_units) in models.items():
        meta = build_metadata(
            atoms=atoms,
            model_id=model_id,
            repeat_count=0 if model_id == "C0" else 1,
            substrate_count=substrate_count,
            fixed=source_meta["fixed_atom_indices_0based"],
            mismatch=source_meta["lattice_mismatch_percent_unstrained"],
            strain=source_meta["applied_cu2te_biaxial_strain_percent"],
            tolerance=tolerance,
        )
        meta.update(
            {
                "coverage_percent": coverage,
                "coverage_definition": "fraction of 16 complete lateral Cu2Te source cells retained",
                "lateral_cu2te_units_present": lateral_units,
                "lateral_cu2te_units_total_at_full_coverage": 16,
                "lateral_unit_composition": "Cu4Te2 (two Cu2Te formula units)",
                "film_morphology": "none" if coverage == 0 else ("periodic half-area stripe" if coverage == 50 else "continuous full film"),
                "stripe_edge_direction": "parallel to lateral cell vector B" if coverage == 50 else "not applicable",
                "stripe_periodicity": "continuous/periodic along B; stripe and vacuum gap repeat along A" if coverage == 50 else "not applicable",
                "source_equivalence": "exact B0 copy" if model_id == "C0" else ("whole-unit subset of H1" if model_id == "C50" else "exact H1 copy"),
            }
        )
        output[model_id] = (atoms, meta)
    return output


def _draw_atoms(ax, atoms, first: int, second: int, size: float, alpha: float = 0.9) -> None:
    symbols = np.asarray(atoms.get_chemical_symbols())
    for element in ("Cd", "Te", "Cu"):
        mask = symbols == element
        if np.any(mask):
            ax.scatter(
                atoms.positions[mask, first],
                atoms.positions[mask, second],
                s=size,
                c=PALETTE[element],
                edgecolors="black",
                linewidths=0.4,
                alpha=alpha,
                zorder=3,
            )


def preview_side(atoms, meta: dict, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 5.4), dpi=170)
    n_sub = meta["substrate_atom_count"]
    _draw_atoms(ax, atoms, 0, 2, 72)
    x0 = float(atoms.positions[:, 0].min())
    x1 = float(atoms.positions[:, 0].max())
    sub_top = float(atoms.positions[:n_sub, 2].max())
    sub_bottom = float(atoms.positions[:n_sub, 2].min())
    ax.text(x0, 0.5 * (sub_bottom + sub_top), "CdTe substrate", color="#6D4D00", weight="bold")
    if len(atoms) > n_sub:
        film_z = atoms.positions[n_sub:, 2]
        film_bottom, film_top = float(film_z.min()), float(film_z.max())
        interface_z = 0.5 * (sub_top + film_bottom)
        ax.axhline(interface_z, color="#5A2A82", linestyle="--", linewidth=1.7)
        ax.text(x0, interface_z + 0.25, "interface", color="#5A2A82", weight="bold")
        ax.text(x0, 0.5 * (film_bottom + film_top), "Cu2Te film", color="#234F7D", weight="bold")
        ax.annotate("", xy=(x1 + 0.8, film_top), xytext=(x1 + 0.8, film_bottom), arrowprops=dict(arrowstyle="<->", color="#234F7D", linewidth=1.6))
        ax.text(x1 + 1.05, 0.5 * (film_bottom + film_top), f"z-span\n{meta['cu2te_z_span_angstrom']:.3f} A", va="center", color="#234F7D")
        ax.annotate(f"top: {meta['top_termination']}", xy=(x1 * 0.70, film_top), xytext=(x1 * 0.55, film_top + 1.7), arrowprops=dict(arrowstyle="->"), ha="center")
    else:
        ax.text(x0, sub_top + 1.5, "Cu2Te absent", color="#555555", weight="bold")
    ax.set_title(f"{meta['model_id']}: {meta['coverage_percent']:.0f}% Cu2Te coverage")
    ax.set_xlabel("projected x (A)")
    ax.set_ylabel("z (A)")
    ax.set_ylim(0, float(atoms.cell.lengths()[2]) + 0.5)
    ax.set_xlim(x0 - 0.7, x1 + 4.0)
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    present = [e for e in ("Cd", "Te", "Cu") if e in atoms.get_chemical_symbols()]
    ax.legend(handles=[Patch(facecolor=PALETTE[e], edgecolor="black", label=e) for e in present], loc="upper right")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def preview_top(atoms, meta: dict, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 6.5), dpi=170)
    n_sub = meta["substrate_atom_count"]
    # Draw the substrate faintly, then the film at full opacity.
    _draw_atoms(ax, atoms[:n_sub], 0, 1, 30, alpha=0.25)
    if len(atoms) > n_sub:
        _draw_atoms(ax, atoms[n_sub:], 0, 1, 74, alpha=0.92)
    origin = np.zeros(2)
    a, b = np.asarray(atoms.cell[0, :2]), np.asarray(atoms.cell[1, :2])
    outline = np.vstack([origin, a, a + b, b])
    ax.add_patch(Polygon(outline, closed=True, fill=False, edgecolor="black", linewidth=1.5))
    ax.annotate("A", xy=a, xytext=a * 0.78, arrowprops=dict(arrowstyle="->", color="#444444"), color="#444444", weight="bold")
    ax.annotate("B", xy=b, xytext=b * 0.78, arrowprops=dict(arrowstyle="->", color="#444444"), color="#444444", weight="bold")
    if meta["model_id"] == "C50":
        ax.text(*(0.50 * a + 0.45 * b), "periodic stripe\ncontinuous along B", ha="center", color="#234F7D", weight="bold")
        ax.text(*(0.77 * a + 0.50 * b), "uncovered area", ha="center", color="#666666", weight="bold")
    ax.set_aspect("equal")
    ax.set_title(f"{meta['model_id']} top view: {meta['coverage_percent']:.0f}% coverage")
    ax.set_xlabel("x (A)")
    ax.set_ylabel("y (A)")
    ax.grid(color="0.92", linewidth=0.5)
    present = [e for e in ("Cd", "Te", "Cu") if e in atoms.get_chemical_symbols()]
    ax.legend(handles=[Patch(facecolor=PALETTE[e], edgecolor="black", label=e) for e in present], loc="best")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def main() -> int:
    config = load_config()
    coverage_models = build_coverage_series(config)
    for model_id in config["coverage_model_ids"]:
        atoms, meta = coverage_models[model_id]
        model_dir = ROOT / "coverage_models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        write(model_dir / "structure.extxyz", atoms)
        write(model_dir / "structure.xyz", atoms, format="xyz")
        write(model_dir / "structure.cif", atoms, format="cif")
        (model_dir / "model.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        preview_side(atoms, meta, model_dir / "preview_side.png")
        preview_top(atoms, meta, model_dir / "preview_top.png")
        print(f"{model_id}: atoms={len(atoms)}, coverage={meta['coverage_percent']:.0f}%, Cu={meta['counts'].get('Cu', 0)}, Te={meta['counts'].get('Te', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
