"""
CATSupport.py
-------------
High-level wrapper around the CAT (Computer-Aided Topology) package for
nanocrystal quantum dot construction.

Designed to provide a simple, notebook-friendly interface similar to OgreInterface.

Usage
-----
from CATSupport import initialize_CAT, build_quantum_dot
"""

import os
import glob
import warnings
import shutil
from typing import Union, List, Optional

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")


# ─────────────────────────────────────────────
# 1.  Initialize
# ─────────────────────────────────────────────

def initialize_CAT() -> None:
    """Check that CAT and its dependencies are importable."""
    try:
        import CAT
        from scm.plams import Settings
        print(f"✓ CAT {CAT.__version__} loaded successfully")
    except ImportError as e:
        raise ImportError(
            f"CAT is not installed: {e}\n"
            "Install with: pip install nlesc-CAT --upgrade"
        )
    try:
        import rdkit
        print(f"✓ RDKit loaded successfully")
    except ImportError:
        raise ImportError("RDKit is required. Install with: pip install rdkit")


# ─────────────────────────────────────────────
# 2.  Ligand pre-processing (L/X-type helper)
# ─────────────────────────────────────────────

# Default M–X bond lengths (Å) for common Lewis-base atom / metal combinations
_BOND_LENGTHS = {
    ("P",  "Cd"): 2.50,
    ("P",  "Pb"): 2.60,
    ("N",  "Cd"): 2.30,
    ("N",  "Pb"): 2.40,
    ("S",  "Cd"): 2.50,
    ("O",  "Cd"): 2.30,
    ("Cl", "Cd"): 2.50,
    ("Cl", "Pb"): 2.80,
}
_DEFAULT_BOND_LENGTH = 2.50



def _add_anchor_metal(
    ligand_file: str,
    ligand_anchor_atom: str,
    metal: str,
    output_dir: str,
    bond_length: Optional[float] = None,
) -> str:
    """
    Add a metal atom to the lone-pair direction of ligand_anchor_atom.

    CAT's substitution mechanism replaces dummy_atom on the core with
    anchor_atom on the ligand.  For L-type ligands (e.g. PPh3) the
    binding atom (P) is not a metal, so a direct substitution would
    remove the surface cation.  This helper prepends the metal to the
    ligand so CAT sees Metal–P–(rest of PPh3) and substitutes
    Metal ↔ surface Metal, keeping the cation in place.

    Returns the path of the modified .mol file written to output_dir.
    """
    from rdkit import Chem

    mol = Chem.MolFromMolFile(ligand_file, removeHs=False)
    if mol is None:
        raise ValueError(f"RDKit could not read ligand file: {ligand_file}")

    conf = mol.GetConformer()

    anchor_idx = next(
        (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == ligand_anchor_atom),
        None,
    )
    if anchor_idx is None:
        raise ValueError(
            f"Atom '{ligand_anchor_atom}' not found in {os.path.basename(ligand_file)}"
        )

    anchor_pos = np.array(conf.GetAtomPosition(anchor_idx))

    # Lone-pair direction = opposite to the mean bond vector from anchor to neighbors.
    # This is a simple geometric estimate that works well for symmetric ligands
    # (e.g. NH3, simple phosphines).
    #
    # LIMITATION: For ligands whose mol file is 2D (e.g. PPh3 from ChemDraw), all
    # atoms share the same z-coordinate, so the mean bond vector is also in the z=0
    # plane and the metal ends up in-plane rather than perpendicular to the phenyl
    # rings.  In such cases the auto-added metal position will be incorrect.
    #
    # Recommended workflow for complex L-type ligands (e.g. PPh3):
    #   Prepare the metal-appended mol file manually in 3D (e.g. using Avogadro,
    #   GaussView, or any structure editor), save it as PPh3_Cd.mol, and pass it
    #   directly via ligand_files= without setting ligand_anchor_atom.  The manual
    #   file gives full control over the P–Cd bond direction and the initial
    #   orientation of the phenyl rings.
    neighbors = mol.GetAtomWithIdx(anchor_idx).GetNeighbors()
    bond_vecs = [
        np.array(conf.GetAtomPosition(n.GetIdx())) - anchor_pos
        for n in neighbors
    ]
    if bond_vecs:
        mean_vec = np.mean(bond_vecs, axis=0)
        norm     = np.linalg.norm(mean_vec)
        lp_dir   = (-mean_vec / norm) if norm > 0 else np.array([0.0, 0.0, 1.0])
    else:
        lp_dir = np.array([0.0, 0.0, 1.0])

    bl = bond_length or _BOND_LENGTHS.get((ligand_anchor_atom, metal), _DEFAULT_BOND_LENGTH)
    metal_pos = anchor_pos + lp_dir * bl

    rw = Chem.RWMol(mol)
    metal_idx = rw.AddAtom(Chem.Atom(metal))
    rw.AddBond(anchor_idx, metal_idx, Chem.BondType.SINGLE)

    new_conf = Chem.Conformer(rw.GetNumAtoms())
    for i in range(mol.GetNumAtoms()):
        new_conf.SetAtomPosition(i, conf.GetAtomPosition(i))
    new_conf.SetAtomPosition(metal_idx, metal_pos.tolist())
    rw.RemoveAllConformers()
    rw.AddConformer(new_conf, assignId=True)

    base = os.path.splitext(os.path.basename(ligand_file))[0]
    out_path = os.path.join(output_dir, f"{base}_{metal}.mol")
    Chem.MolToMolFile(rw.GetMol(), out_path)
    return out_path


# ─────────────────────────────────────────────
# 3.  Build Settings object (internal helper)
# ─────────────────────────────────────────────

def _build_settings(
    working_dir: str,
    core_file: str,
    ligand_files: List[str],
    attachment_indices: List[int],
    dummy_atom: str,
    anchor_atom: str,
    alignment: str,
    subset_f: Optional[float],
    subset_mode: str,
    optimize_ligand: bool,
    optimize_qd: bool,
    overwrite: bool,
) -> "scm.plams.Settings":
    """Convert user parameters into a plams.Settings object for CAT."""
    from scm.plams import Settings

    s = Settings()
    s.path = working_dir

    core_opts = Settings()
    core_opts.guess_bonds = True
    core_opts.indices = attachment_indices
    core_entry = Settings()
    core_entry[core_file] = core_opts
    s.input_cores = [core_entry]

    s.input_ligands = list(ligand_files)

    s.optional.database.dirname    = "database"
    s.optional.database.read       = True
    s.optional.database.write      = True
    s.optional.database.overwrite  = overwrite
    s.optional.database.mol_format = ["pdb"]
    s.optional.database.mongodb    = False

    s.optional.core.dirname    = "core"
    s.optional.core.dummy      = dummy_atom
    s.optional.core.allignment = alignment

    # Partial surface coverage: replace only a fraction f of anchor atoms
    if subset_f is not None:
        s.optional.core.subset = Settings()
        s.optional.core.subset.f    = subset_f
        s.optional.core.subset.mode = subset_mode

    s.optional.ligand.anchor      = anchor_atom
    s.optional.ligand.dirname     = "ligand"
    s.optional.ligand.optimize    = optimize_ligand
    s.optional.ligand.split       = False
    s.optional.ligand["cosmo-rs"] = False

    s.optional.qd.dirname           = "qd"
    s.optional.qd.construct_qd      = True
    s.optional.qd.optimize          = optimize_qd
    s.optional.qd.bulkiness         = False
    s.optional.qd.activation_strain = False

    return s


# ─────────────────────────────────────────────
# 4.  Output collection and cleanup
# ─────────────────────────────────────────────

def _collect_output(
    output_dir: str,
    core_file: str,
    original_ligand_files: List[str],
    auto_ligand_files: List[str],
    n_ligands: int,
) -> Optional[str]:
    """
    Find CAT's output .pdb, rename with clean convention, remove intermediates.

    Naming convention:  {core}_{ligand}_{n}lig.pdb
    Examples:
      Cd68Te55Cl26_PPh3_4lig.pdb
      Cd68Te55Cl26_OA_8lig.pdb
      Cd68Te55Cl26_PPh3+OA_6lig.pdb   (multiple ligands)
    """
    # Find output PDB(s) in CAT's qd/ subdirectory
    qd_dir = os.path.join(output_dir, "qd")
    pdbs = [f for f in glob.glob(os.path.join(qd_dir, "*.pdb"))
            if not os.path.basename(f).startswith(".")]
    if not pdbs:
        return None

    # Build clean output name
    core_stem = os.path.splitext(os.path.basename(core_file))[0]

    lig_stems = []
    for orig, effective in zip(original_ligand_files, effective_or_original(
            original_ligand_files, auto_ligand_files)):
        # Use the original file's name (before auto-metal-addition) for labeling
        stem = os.path.splitext(os.path.basename(orig))[0]
        lig_stems.append(stem)
    lig_part = "+".join(lig_stems)

    clean_name = f"{core_stem}_{lig_part}_{n_ligands}lig.pdb"
    dst = os.path.join(output_dir, clean_name)
    shutil.copy2(pdbs[0], dst)

    # Remove CAT's intermediate directories
    for d in ("qd", "ligand", "database", "core"):
        full = os.path.join(output_dir, d)
        if os.path.isdir(full):
            shutil.rmtree(full)

    # Remove auto-generated ligand mol files written to output_dir
    for f in auto_ligand_files:
        if os.path.dirname(f) == output_dir and os.path.exists(f):
            os.remove(f)

    return dst


def effective_or_original(original: List[str], auto: List[str]) -> List[str]:
    """Return auto list if non-empty, else original."""
    return auto if auto else original


# ─────────────────────────────────────────────
# 5.  Main workflow function
# ─────────────────────────────────────────────

def build_quantum_dot(
    core_file: str,
    ligand_files: Union[str, List[str]],
    attachment_indices: List[int],
    ligand_type: str               = "L",
    ligand_anchor_atom: Optional[str] = None,
    dummy_atom: str                = "Cd",
    anchor_atom: Optional[str]     = None,
    alignment: str                 = "surface",
    subset_f: Optional[float]      = None,
    subset_mode: str               = "uniform",
    optimize_ligand: bool          = True,
    optimize_qd: bool              = False,
    output_dir: str                = "./QD_output",
    overwrite: bool                = False,
) -> str:
    """
    Build a ligand-passivated quantum dot using CAT.

    Parameters
    ----------
    core_file : str
        Path to the core nanocrystal structure file (.xyz).
    ligand_files : str or list of str
        Path(s) to ligand structure file(s) (.mol).
    attachment_indices : list of int
        Atom indices on the core where ligands will be attached.
    ligand_type : str
        Ligand binding type: "L", "X", or "Z" (default: "L").
          L  Lewis base (RNH2, PR3)   : binds surface cation  → dummy_atom = cation (e.g. "Cd")
          X  X-type (Cl⁻, RCOO⁻)     : binds surface cation  → dummy_atom = cation (e.g. "Cd")
          Z  Z-type (Cd(OOCR)2, etc.) : binds surface anion   → dummy_atom = anion  (e.g. "Te")
    ligand_anchor_atom : str, optional
        For L/X-type ligands: the coordinating atom on the ligand (e.g. "P" for PPh3).
        When set, a dummy_atom is auto-appended so the surface cation is preserved.
        Leave None if the ligand file already includes the anchor metal (e.g. PPh3_Cd.mol).
    dummy_atom : str
        Atom on the core used as the attachment site by CAT (default: "Cd").
    anchor_atom : str, optional
        Atom on the ligand that replaces dummy_atom. Defaults to dummy_atom.
    alignment : str
        How ligands are aligned to the core surface (default: "surface").
          "surface"        : vectors orthogonal to the convex-hull surface (recommended)
          "sphere"         : vectors from anchor atoms toward the core center
          "surface_invert" : same as "surface" but inverted
          "sphere_invert"  : same as "sphere" but inverted
        For a flat surface patch "surface" gives the correct outward normal,
        ensuring the P-Cd axis is perpendicular to the local surface.
    subset_f : float, optional
        Fraction of anchor atoms to replace with ligands (default: None = all).
        E.g. 0.5 replaces 50% of surface Cd atoms. Useful to avoid over-crowding.
    subset_mode : str
        How to select the subset of anchor atoms (default: "uniform").
          "uniform" : maximise nearest-neighbour distances → evenly spread ligands
          "cluster" : minimise distances → grouped ligands
          "random"  : random selection
    optimize_ligand : bool
        Optimize ligand geometry before attachment (default: True).
    optimize_qd : bool
        Optimize full QD geometry after construction (default: False).
    output_dir : str
        Directory for output (default: "./QD_output").
    overwrite : bool
        Overwrite existing database entries (default: False).

    Returns
    -------
    str
        Path to the output .pdb file.

    Output naming convention
    ------------------------
    {core}_{ligand}_{n}lig.pdb
    e.g.  Cd68Te55Cl26_PPh3_4lig.pdb
          Cd68Te55Cl26_OA_8lig.pdb
          Cd68Te55Cl26_PPh3+OA_6lig.pdb   (mixed ligands)

    Examples
    --------
    # Plain PPh3 — auto-adds Cd anchor:
    >>> build_quantum_dot(
    ...     core_file          = "structures/core/Cd68Te55Cl26.xyz",
    ...     ligand_files       = "structures/ligand/PPh3.mol",
    ...     attachment_indices = [45, 49, 56, 39],
    ...     ligand_type        = "L",
    ...     ligand_anchor_atom = "P",
    ...     dummy_atom         = "Cd",
    ... )

    # Pre-built PPh3_Cd.mol — backward-compatible:
    >>> build_quantum_dot(
    ...     core_file          = "structures/core/Cd68Te55Cl26.xyz",
    ...     ligand_files       = "structures/ligand/PPh3_Cd.mol",
    ...     attachment_indices = [45, 49, 56, 39],
    ...     dummy_atom         = "Cd",
    ...     anchor_atom        = "Cd",
    ... )
    """
    if ligand_type not in ("L", "X", "Z"):
        raise ValueError(f"ligand_type must be 'L', 'X', or 'Z', got '{ligand_type}'")

    from CAT.base import prep

    # ── Resolve paths ──────────────────────────────────────────────
    core_file = os.path.abspath(core_file)
    if isinstance(ligand_files, str):
        ligand_files = [ligand_files]
    original_ligands = [os.path.abspath(f) for f in ligand_files]
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # ── Auto-add anchor metal for L/X-type with bare ligand ───────
    auto_ligands: List[str] = []
    if ligand_anchor_atom is not None:
        if ligand_type == "Z":
            raise ValueError(
                "ligand_anchor_atom is for L/X-type only. "
                "Z-type ligands should already contain the metal anchor."
            )
        auto_ligands = [
            _add_anchor_metal(f, ligand_anchor_atom, dummy_atom, output_dir)
            for f in original_ligands
        ]
        effective_ligands = auto_ligands
    else:
        effective_ligands = original_ligands

    effective_anchor = anchor_atom or dummy_atom

    # ── Print summary ─────────────────────────────────────────────
    _print_summary(core_file, original_ligands, attachment_indices, ligand_type,
                   dummy_atom, effective_anchor, alignment, subset_f, subset_mode,
                   optimize_ligand, optimize_qd, output_dir)

    # ── Build Settings and run CAT ────────────────────────────────
    s = _build_settings(
        working_dir        = output_dir,
        core_file          = core_file,
        ligand_files       = effective_ligands,
        attachment_indices = attachment_indices,
        dummy_atom         = dummy_atom,
        anchor_atom        = effective_anchor,
        alignment          = alignment,
        subset_f           = subset_f,
        subset_mode        = subset_mode,
        optimize_ligand    = optimize_ligand,
        optimize_qd        = optimize_qd,
        overwrite          = overwrite,
    )

    import logging
    logging.getLogger("CAT").setLevel(logging.CRITICAL)

    print("\n⚙  Running CAT...", end=" ", flush=True)
    try:
        prep(s)
    except Exception as e:
        print(f"\n✗ CAT failed: {e}")
        raise

    # ── Collect output and clean up intermediates ─────────────────
    out_path = _collect_output(
        output_dir           = output_dir,
        core_file            = core_file,
        original_ligand_files = original_ligands,
        auto_ligand_files    = auto_ligands,
        n_ligands            = len(attachment_indices),
    )
    print(f"done.\n✓ Output: {out_path}")
    return out_path


# ─────────────────────────────────────────────
# 6.  Post-build geometry relaxation
# ─────────────────────────────────────────────

def relax_qd(
    pdb_file: str,
    method: str    = "GFN-FF",
    fmax: float    = 0.05,
    max_steps: int = 500,
) -> str:
    """
    Relax a QD structure to remove steric clashes using xTB + ASE.

    Uses GFN-FF (Grimme's general force field) which supports all elements
    including heavy metals (Cd, Te, Pb, Hg, Zn, ...).

    Parameters
    ----------
    pdb_file : str
        Path to the QD .pdb file (output of build_quantum_dot).
    method : str
        xTB method: "GFN-FF" (default, fast), "GFN1-xTB", "GFN2-xTB" (more accurate).
    fmax : float
        Convergence criterion: max force per atom in eV/Å (default: 0.05).
    max_steps : int
        Maximum number of optimization steps (default: 500).

    Returns
    -------
    str
        Path to the relaxed .pdb file (saved alongside input as *_relaxed.pdb).
    """
    from ase.io import read, write
    from ase.optimize import LBFGS
    from xtb.ase.calculator import XTB

    pdb_file = os.path.abspath(pdb_file)
    atoms = read(pdb_file)

    atoms.calc = XTB(method=method)

    base = os.path.splitext(pdb_file)[0]
    out_path = f"{base}_relaxed.pdb"

    print(f"⚙  Relaxing QD with xTB {method}...", end=" ", flush=True)
    opt = LBFGS(atoms, logfile=None)
    opt.run(fmax=fmax, steps=max_steps)
    write(out_path, atoms)
    print(f"done ({opt.get_number_of_steps()} steps).\n✓ Relaxed structure: {out_path}")
    return out_path


# ─────────────────────────────────────────────
# 7.  Utility helpers
# ─────────────────────────────────────────────

def _print_summary(core_file, ligand_files, indices, ligand_type,
                   dummy, anchor, alignment, subset_f, subset_mode,
                   opt_lig, opt_qd, output_dir) -> None:
    _type_desc = {
        "L": "L-type (Lewis base, binds surface cation)",
        "X": "X-type (1e donor, binds surface cation)",
        "Z": "Z-type (Lewis acid, binds surface anion)",
    }
    subset_str = f"{subset_f} ({subset_mode})" if subset_f is not None else "all"
    print("=" * 55)
    print("  Quantum Dot Build Summary")
    print("=" * 55)
    print(f"  Core structure  : {os.path.basename(core_file)}")
    print(f"  Ligand(s)       : {[os.path.basename(f) for f in ligand_files]}")
    print(f"  Ligand type     : {ligand_type}  ({_type_desc[ligand_type]})")
    print(f"  Attach indices  : {indices}")
    print(f"  Dummy atom      : {dummy}")
    print(f"  Anchor atom     : {anchor}")
    print(f"  Alignment       : {alignment}")
    print(f"  Surface coverage: {subset_str}")
    print(f"  Optimize ligand : {opt_lig}")
    print(f"  Optimize QD     : {opt_qd}")
    print(f"  Output dir      : {output_dir}")
    print("=" * 55)
