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
import warnings
import shutil
from pathlib import Path
from typing import Union, List, Optional

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
# 2.  Build Settings object (internal helper)
# ─────────────────────────────────────────────

def _build_settings(
    working_dir: str,
    core_file: str,
    ligand_files: Union[str, List[str]],
    attachment_indices: List[int],
    dummy_atom: str,
    anchor_atom: str,
    optimize_ligand: bool,
    optimize_qd: bool,
    overwrite: bool,
) -> "scm.plams.Settings":
    """Convert user parameters into a plams.Settings object for CAT."""
    from scm.plams import Settings

    s = Settings()
    s.path = working_dir

    # Core: single core file with attachment indices
    core_name = os.path.basename(core_file)
    s.input_cores = [{core_name: {"guess_bonds": True, "indices": attachment_indices}}]

    # Ligands: accept single string or list
    if isinstance(ligand_files, str):
        ligand_files = [ligand_files]
    s.input_ligands = [os.path.basename(f) for f in ligand_files]

    # Database settings
    s.optional.database.dirname   = "database"
    s.optional.database.read      = True
    s.optional.database.write     = True
    s.optional.database.overwrite = overwrite
    s.optional.database.mol_format = ["pdb"]
    s.optional.database.mongodb   = False

    # Core settings
    s.optional.core.dirname    = "core"
    s.optional.core.dummy      = dummy_atom
    s.optional.core.allignment = "sphere"

    # Ligand settings
    s.optional.ligand.anchor     = anchor_atom
    s.optional.ligand.dirname    = "ligand"
    s.optional.ligand.optimize   = optimize_ligand
    s.optional.ligand.split      = False
    s.optional.ligand["cosmo-rs"] = False

    # Quantum dot settings
    s.optional.qd.dirname           = "QD"
    s.optional.qd.construct_qd      = True
    s.optional.qd.optimize          = optimize_qd
    s.optional.qd.bulkiness         = False
    s.optional.qd.activation_strain = False

    return s


# ─────────────────────────────────────────────
# 3.  Main workflow function
# ─────────────────────────────────────────────

def build_quantum_dot(
    core_file: str,
    ligand_files: Union[str, List[str]],
    attachment_indices: List[int],
    dummy_atom: str       = "Cd",
    anchor_atom: str      = "Cd",
    optimize_ligand: bool = True,
    optimize_qd: bool     = False,
    output_dir: str       = "./QD_output",
    overwrite: bool       = False,
) -> None:
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
    dummy_atom : str
        Atom type used as dummy/anchor on the core surface (default: "Cd").
    anchor_atom : str
        Atom type on the ligand that binds to the core (default: "Cd").
    optimize_ligand : bool
        Whether to optimize the ligand geometry before attachment (default: True).
    optimize_qd : bool
        Whether to optimize the full QD geometry after construction (default: False).
    output_dir : str
        Directory where all output files will be written (default: "./QD_output").
    overwrite : bool
        Whether to overwrite existing database entries (default: False).

    Returns
    -------
    None
        Output structures are written to output_dir/QD/.

    Examples
    --------
    >>> build_quantum_dot(
    ...     core_file    = "./core/Cd68Te55Cl26.xyz",
    ...     ligand_files = "./ligand/PPh3_Cd.mol",
    ...     attachment_indices = [45, 49, 56, 39],
    ...     dummy_atom   = "Cd",
    ...     anchor_atom  = "Cd",
    ... )
    """
    from CAT.base import prep

    # ── Resolve paths ──────────────────────────────────────────────
    core_file = os.path.abspath(core_file)
    if isinstance(ligand_files, str):
        ligand_files = [ligand_files]
    ligand_files = [os.path.abspath(f) for f in ligand_files]
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # ── Copy input files to output_dir so CAT can find them ───────
    _copy_inputs(core_file, ligand_files, output_dir)

    # ── Print summary ─────────────────────────────────────────────
    _print_summary(core_file, ligand_files, attachment_indices,
                   dummy_atom, anchor_atom, optimize_ligand, optimize_qd, output_dir)

    # ── Build Settings and run CAT ────────────────────────────────
    s = _build_settings(
        working_dir       = output_dir,
        core_file         = core_file,
        ligand_files      = ligand_files,
        attachment_indices = attachment_indices,
        dummy_atom        = dummy_atom,
        anchor_atom       = anchor_atom,
        optimize_ligand   = optimize_ligand,
        optimize_qd       = optimize_qd,
        overwrite         = overwrite,
    )

    print("\n⚙  Running CAT...\n")
    try:
        prep(s)
        print(f"\n✓ Done! Output written to: {output_dir}/QD/")
    except Exception as e:
        print(f"\n✗ CAT failed: {e}")
        raise


# ─────────────────────────────────────────────
# 4.  Utility helpers
# ─────────────────────────────────────────────

def _copy_inputs(core_file: str, ligand_files: List[str], output_dir: str) -> None:
    """Copy core and ligand files into output_dir so CAT can find them."""
    dst_core = os.path.join(output_dir, os.path.basename(core_file))
    if not os.path.exists(dst_core):
        shutil.copy2(core_file, dst_core)

    for lig in ligand_files:
        dst_lig = os.path.join(output_dir, os.path.basename(lig))
        if not os.path.exists(dst_lig):
            shutil.copy2(lig, dst_lig)


def _print_summary(core_file, ligand_files, indices, dummy, anchor,
                   opt_lig, opt_qd, output_dir) -> None:
    """Print a human-readable summary of the job."""
    print("=" * 55)
    print("  Quantum Dot Build Summary")
    print("=" * 55)
    print(f"  Core structure  : {os.path.basename(core_file)}")
    print(f"  Ligand(s)       : {[os.path.basename(f) for f in ligand_files]}")
    print(f"  Attach indices  : {indices}")
    print(f"  Dummy atom      : {dummy}")
    print(f"  Anchor atom     : {anchor}")
    print(f"  Optimize ligand : {opt_lig}")
    print(f"  Optimize QD     : {opt_qd}")
    print(f"  Output dir      : {output_dir}")
    print("=" * 55)
