# CdTe-NCs-calculation

This repository contains computational studies of Cadmium Telluride (CdTe) nanocrystals, including both molecular modeling and quantum chemical calculations.

## Project Overview

The project is organized into two main components:
- **Modeling**: Molecular structure preparation and nanocrystal assembly using CAT
- **Calculation**: Quantum chemical calculations using CP2K

## Directory Structure

```
├── model/                    # Molecular modeling with CAT
│   └── CdTe_PPh3/          # CdTe nanocrystal with PPh3 ligands
│       ├── core/            # Core nanocrystal structure
│       ├── ligand/          # Ligand molecules
│       ├── qd/              # Assembled quantum dot structures
│       ├── database/        # Molecular database
│       └── input_settings.yaml  # CAT configuration file
├── calculation/             # CP2K quantum chemical calculations
│   ├── CdTe/               # Pure CdTe nanocrystal calculations
│   │   ├── opt/            # Geometry optimization
│   │   └── sq/             # Single point calculations
│   └── CdTe_PPh3/          # CdTe with PPh3 ligand calculations
└── README.md               # This file
```

## Modeling (CAT)

The modeling section uses CAT (Computer-Aided Topology) for molecular structure preparation and nanocrystal assembly.

### Features
- **Core Structure**: Cd68Te55Cl26 nanocrystal core
- **Ligand Attachment**: PPh3 (triphenylphosphine) ligands
- **Quantum Dot Assembly**: Complete nanocrystal structures with ligands
- **Database Management**: Molecular structure database with PDB format support

### Configuration
The modeling process is controlled by `input_settings.yaml` which includes:
- Core structure specifications
- Ligand optimization settings
- Quantum dot construction parameters
- Database management options

### Key Files
- `model/CdTe_PPh3/core/Cd68Te55Cl26.xyz`: Core nanocrystal structure
- `model/CdTe_PPh3/ligand/PPh3_Cd.mol`: PPh3 ligand molecule
- `model/CdTe_PPh3/qd/Cd68Cl26Te55__PPh3.pdb`: Assembled quantum dot structure

## Calculation (CP2K)

The calculation section uses CP2K for quantum chemical calculations on the modeled structures.

### Calculation Types
- **Geometry Optimization**: Structure relaxation and energy minimization
- **Single Point Calculations**: Electronic structure analysis
- **Density of States (DOS)**: Electronic property calculations

### Computational Setup
- **Method**: Quickstep (DFT)
- **Basis Sets**: Optimized for Cd, Te, and ligand atoms
- **Periodic Boundary Conditions**: Applied for bulk-like calculations
- **Parallel Computing**: MPI-based parallelization

### Key Files
- `calculation/CdTe/opt/Cd68Te55Cl26.inp`: CP2K input for geometry optimization
- `calculation/CdTe/sq/Cd68Te55Cl26.inp`: CP2K input for single point calculations
- `calculation/CdTe/sq/dos.ipynb`: Jupyter notebook for DOS analysis
- `job.slurm`: SLURM job submission scripts

### Job Submission
```bash
# Example job submission
sbatch job.slurm
```

## Usage

### Modeling Workflow
1. Prepare core structure in `model/CdTe_PPh3/core/`
2. Define ligands in `model/CdTe_PPh3/ligand/`
3. Configure settings in `input_settings.yaml`
4. Run CAT to assemble quantum dot structures

### Calculation Workflow
1. Export structures from modeling to calculation directories
2. Prepare CP2K input files
3. Submit jobs using SLURM
4. Analyze results using provided notebooks

## Requirements

### Modeling
- CAT molecular modeling software
- Python environment for configuration

### Calculation
- CP2K quantum chemistry package
- SLURM job scheduler
- Jupyter notebook for analysis

## Results

The calculations provide:
- Optimized nanocrystal geometries
- Electronic structure properties
- Density of states analysis
- Energy landscapes for nanocrystal-ligand interactions

## License

This project is licensed under the terms specified in the LICENSE file.

## Contact

For questions about this project, please refer to the repository maintainers.