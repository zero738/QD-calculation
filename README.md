# QD-calculation

Computational workflow for ligand-passivated semiconductor nanocrystal quantum dots.
Covers structure assembly, DFT geometry optimization, and electronic property calculations.


## Workflow (QD Assembly)

Structure assembly uses [CAT](https://github.com/nlesc-nano/CAT) via a high-level Python wrapper.

```
Core (.xyz) + Ligand (.mol)  →  build_quantum_dot()  →  {core}_{ligand}_{n}lig.pdb
```

See `workflow/README.md` for full documentation.

### Environment setup

```bash
# Create environment
conda create -n nanocrystal python=3.11
conda activate nanocrystal

# Core dependencies
pip install nlesc-CAT
pip install "pandas<2.0"
pip install "numpy==1.26.4" --force-reinstall
conda install -c conda-forge h5py --force-reinstall  # fix numpy binary compatibility

# Post-build relaxation (optional)
conda install -c conda-forge xtb-python
pip install ase

# Jupyter
pip install jupyterlab ipykernel
python -m ipykernel install --user --name nanocrystal --display-name "nanocrystal"
```

### Launch

```bash
conda activate nanocrystal
jupyter lab
```

Open `workflow/cat_workflow.ipynb` with the **nanocrystal** kernel.

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

## License

See [LICENSE](LICENSE).
