# QD Construction Workflow

CAT-based workflow for building ligand-passivated nanocrystal quantum dots.

```
Core (.xyz) + Ligand (.mol)  →  build_quantum_dot()  →  {core}_{ligand}_{n}lig.pdb
```

---

## Directory Structure

```
workflow/
├── CATSupport.py           # Python wrapper around CAT
├── cat_workflow.ipynb      # Interactive notebook
├── README.md               # This file
│
├── structures/
│   ├── core/               # Core NC structures (.xyz)
│   └── ligand/             # Ligand structures (.mol)
│
└── QD_output/              # Output directory (auto-created)
    └── {core}_{ligand}_{n}lig.pdb
```

---

## Output Naming Convention

```
{core}_{ligand}_{n}lig.pdb
```

| Part | Description | Example |
|------|-------------|---------|
| `{core}` | Core filename stem | `Cd68Te55Cl26` |
| `{ligand}` | Ligand filename stem | `PPh3`, `OA` |
| `{n}lig` | Number of attachment sites | `4lig` |

**Examples:**
```
Cd68Te55Cl26_PPh3_4lig.pdb          single ligand
Cd68Te55Cl26_OA_8lig.pdb            oleic acid
Cd68Te55Cl26_PPh3+OA_6lig.pdb       mixed ligands
```

Only the final `.pdb` is kept; CAT's intermediate directories (`qd/`, `ligand/`, `database/`, `core/`) are removed automatically.

---

## Ligand Types

| Type | Description | Examples | Binds to | `dummy_atom` |
|------|-------------|----------|----------|--------------|
| **L** | Lewis base (2 lone pairs) | PR₃, RNH₂ | surface cation | cation (e.g. `Cd`) |
| **X** | X-type (1 lone electron) | Cl⁻, RCOO⁻, RPO₄²⁻ | surface cation | cation (e.g. `Cd`) |
| **Z** | Z-type (Lewis acid) | Cd(OOCR)₂, Cd(RPO₃) | surface anion | anion (e.g. `Te`) |

### CAT anchor convention

CAT replaces `dummy_atom` on the core with `anchor_atom` from the ligand.

For **L/X-type** ligands (e.g. PPh₃), the coordinating atom (P) is not a metal. Using P as anchor would remove the surface Cd. Two options:

1. **Auto mode** — provide plain `PPh3.mol` and set `ligand_anchor_atom="P"`. The code adds a Cd atom at P's lone-pair direction before passing to CAT.
2. **Manual mode** — provide a pre-built `PPh3_Cd.mol` with Cd already attached to P.

For **Z-type** ligands the mol file should already contain the metal anchor (e.g. `Cd` in `CdOA2.mol`).

---

## Usage

### Notebook

Open `cat_workflow.ipynb` with the **`nanocrystal`** Jupyter kernel.

### Python API

```python
from workflow.CATSupport import initialize_CAT, build_quantum_dot

initialize_CAT()

# L-type, plain ligand (auto-adds Cd anchor)
out = build_quantum_dot(
    core_file          = "structures/core/Cd68Te55Cl26.xyz",
    ligand_files       = "structures/ligand/PPh3.mol",
    attachment_indices = [45, 49, 56, 39],
    ligand_type        = "L",
    ligand_anchor_atom = "P",
    dummy_atom         = "Cd",
)

# L-type, pre-built PPh3_Cd.mol
out = build_quantum_dot(
    core_file          = "structures/core/Cd68Te55Cl26.xyz",
    ligand_files       = "structures/ligand/PPh3_Cd.mol",
    attachment_indices = [45, 49, 56, 39],
    ligand_type        = "L",
    dummy_atom         = "Cd",
    anchor_atom        = "Cd",
)

# Z-type (cadmium oleate binds surface Te)
out = build_quantum_dot(
    core_file          = "structures/core/Cd68Te55.xyz",
    ligand_files       = "structures/ligand/CdOA2.mol",
    attachment_indices = [12, 18, 24],
    ligand_type        = "Z",
    dummy_atom         = "Te",
    anchor_atom        = "Cd",
)
```

### Key parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ligand_type` | `"L"`, `"X"`, or `"Z"` | `"L"` |
| `ligand_anchor_atom` | Coordinating atom on bare ligand (e.g. `"P"`) | `None` |
| `dummy_atom` | Attachment atom on core (L/X→cation, Z→anion) | `"Cd"` |
| `anchor_atom` | Atom on ligand that replaces dummy_atom | same as `dummy_atom` |
| `attachment_indices` | Core atom indices for ligand placement | required |
| `optimize_ligand` | UFF geometry optimization before attachment | `True` |
| `optimize_qd` | Full QD geometry optimization after build | `False` |
| `overwrite` | Overwrite CAT database entries | `False` |

---

## Environment

```bash
conda activate nanocrystal
jupyter lab
```

Required packages: `nlesc-CAT`, `rdkit`, `pandas<2.0`
