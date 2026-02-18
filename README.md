# QD-calculation

Computational workflow for ligand-passivated semiconductor nanocrystal quantum dots.
Covers structure assembly, DFT geometry optimization, and electronic property calculations.


## Workflow (QD Assembly)

Structure assembly uses [CAT](https://github.com/nlesc-nano/CAT) via a high-level Python wrapper.

```
Core (.xyz) + Ligand (.mol)  →  build_quantum_dot()  →  {core}_{ligand}_{n}lig.pdb
```

See `workflow/README.md` for full documentation.

### Quick start

```bash
conda activate nanocrystal
jupyter lab
```

Open `workflow/cat_workflow.ipynb` and run the cells.

---

## Calculation (CP2K DFT)

Single-point and geometry optimization calculations using CP2K.

- **Functional**: PBE / HLE17
- **Basis sets**: DZVP-MOLOPT-SR-GTH
- **Pseudopotentials**: GTH-PBE
- **Job scheduler**: SLURM

Each calculation directory contains a CP2K `.inp` file, a `job.slurm` submission script,
and analysis notebooks (`dos.ipynb`) with output data.

---

## Environment

| Component | Package |
|-----------|---------|
| QD assembly | `nlesc-CAT`, `rdkit`, `pandas<2.0` |
| Post-build relaxation | `xtb-python`, `ase` |
| DFT | CP2K 2022.1+ |
| Analysis | `numpy`, `matplotlib` |

---

## License

See [LICENSE](LICENSE).
