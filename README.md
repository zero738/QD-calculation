# CdTe-NCs-calculation

This repository contains computational studies of Cadmium Telluride (CdTe) nanocrystals, including both molecular modeling and quantum chemical calculations.

[中文版本](#中文版本)

## Project Overview

The project is organized into two main components:
- **Modeling**: Molecular structure preparation and nanocrystal assembly using CAT
- **Calculation**: Quantum chemical calculations using CP2K

## Directory Structure

```
├── model/                    # Molecular modeling with CAT
│   └── CdTe_PPh3/          # CdTe nanocrystal with PPh3 ligands
│       ├── core/            # Core nanocrystal structure
│       │   └── Cd68Te55Cl26.xyz  # Core structure file
│       ├── ligand/          # Ligand molecules
│       │   ├── PPh3_Cd.mol  # PPh3 ligand molecule
│       │   └── ligand_opt/  # Optimized ligand structures
│       ├── qd/              # Assembled quantum dot structures
│       │   └── Cd68Cl26Te55__PPh3.pdb  # Final QD structure
│       ├── database/        # Molecular database
│       └── input_settings.yaml  # CAT configuration file
├── calculation/             # CP2K quantum chemical calculations
│   ├── CdTe/               # Pure CdTe nanocrystal calculations
│   │   ├── opt/            # Geometry optimization
│   │   │   ├── Cd68Te55Cl26.inp  # CP2K input file
│   │   │   ├── job.slurm   # SLURM job script
│   │   │   └── *.out       # Output files
│   │   └── sq/             # Single point calculations
│   │       ├── Cd68Te55Cl26.inp  # CP2K input file
│   │       ├── dos.ipynb   # DOS analysis notebook
│   │       ├── DOS_*.txt   # DOS data files
│   │       └── *.out       # Output files
│   └── CdTe_PPh3/          # CdTe with PPh3 ligand calculations
└── README.md               # This file
```

## Modeling (CAT)

The modeling section uses CAT (Computer-Aided Topology) for molecular structure preparation and nanocrystal assembly.

### Features
- **Core Structure**: Cd68Te55Cl26 nanocrystal core with 68 Cd, 55 Te, and 26 Cl atoms
- **Ligand Attachment**: PPh3 (triphenylphosphine) ligands with Cd anchoring
- **Quantum Dot Assembly**: Complete nanocrystal structures with ligands
- **Database Management**: Molecular structure database with PDB format support
- **Ligand Optimization**: Automatic ligand structure optimization

### Configuration Details
The modeling process is controlled by `input_settings.yaml`:

```yaml
input_cores:
    - Cd68Te55Cl26.xyz:
        guess_bonds: True
        indices: [45,49,56,39]  # Anchor points for ligand attachment

input_ligands:
    - PPh3_Cd.mol

optional:
    core:
        dirname: core
        dummy: Cd
        allignment: sphere
    
    ligand:
        anchor: Cd
        dirname: ligand
        optimize: True
        split: False
        cosmo-rs: False
    
    qd:
        dirname: QD
        construct_qd: True
        optimize: False
        bulkiness: False
        activation_strain: False
```

### Key Files
- `model/CdTe_PPh3/core/Cd68Te55Cl26.xyz`: Core nanocrystal structure (152 atoms)
- `model/CdTe_PPh3/ligand/PPh3_Cd.mol`: PPh3 ligand molecule with Cd anchor
- `model/CdTe_PPh3/qd/Cd68Cl26Te55__PPh3.pdb`: Assembled quantum dot structure (427 atoms)

## Calculation (CP2K)

The calculation section uses CP2K for quantum chemical calculations on the modeled structures.

### Calculation Types
- **Geometry Optimization**: Structure relaxation and energy minimization using BFGS optimizer
- **Single Point Calculations**: Electronic structure analysis and property calculations
- **Density of States (DOS)**: Electronic property calculations with orbital analysis

### Computational Setup
- **Method**: Quickstep (DFT) with PBE functional
- **Basis Sets**: 
  - Cd: DZVP-MOLOPT-SR-GTH-q12
  - Te: DZVP-MOLOPT-SR-GTH-q6  
  - Cl: DZVP-MOLOPT-SR-GTH-q7
- **Pseudopotentials**: GTH-PBE for all elements
- **Periodic Boundary Conditions**: Applied for bulk-like calculations
- **Parallel Computing**: MPI-based parallelization
- **SCF Convergence**: 1.0E-06 threshold with OT (Orbital Transformation) method

### Key CP2K Parameters
```fortran
&DFT
  CHARGE    0
  MULTIPLICITY    1
  &XC
    &XC_FUNCTIONAL PBE
    &END XC_FUNCTIONAL
  &END XC
  &MGRID
    CUTOFF  400
    REL_CUTOFF  55
  &END MGRID
  &SCF
    MAX_SCF 25
    EPS_SCF 1.0E-06
    &OT
      PRECONDITIONER FULL_ALL
      MINIMIZER DIIS
      ALGORITHM STRICT
    &END OT
  &END SCF
&END DFT

&MOTION
  &GEO_OPT
    TYPE MINIMIZATION
    OPTIMIZER BFGS
    MAX_ITER 500
    MAX_DR 3E-3
    RMS_DR 1.5E-3
    MAX_FORCE 4.5E-4
    RMS_FORCE 3E-4
  &END GEO_OPT
&END MOTION
```

### Key Files
- `calculation/CdTe/opt/Cd68Te55Cl26.inp`: CP2K input for geometry optimization
- `calculation/CdTe/sq/Cd68Te55Cl26.inp`: CP2K input for single point calculations
- `calculation/CdTe/sq/dos.ipynb`: Jupyter notebook for DOS analysis and visualization
- `calculation/CdTe/sq/DOS_line.txt`: DOS data for analysis
- `job.slurm`: SLURM job submission scripts

### Job Submission
```bash
# Example job submission for optimization
cd calculation/CdTe/opt
sbatch job.slurm

# Example job submission for single point
cd calculation/CdTe/sq
sbatch job.slurm
```

## Results and Analysis

### Electronic Properties
- **Band Gap**: 1.54 eV (HOMO: -3.96 eV, LUMO: -2.41 eV)
- **DOS Analysis**: Projected density of states for CdTe and Cl components
- **Orbital Analysis**: Molecular orbital visualization and analysis

### Structural Properties
- **Optimized Geometry**: Relaxed nanocrystal structure
- **Bond Lengths**: Optimized Cd-Te and Cd-Cl bond distances
- **Surface Properties**: Ligand coverage and surface passivation

## Usage

### Modeling Workflow
1. Prepare core structure in `model/CdTe_PPh3/core/`
2. Define ligands in `model/CdTe_PPh3/ligand/`
3. Configure settings in `input_settings.yaml`
4. Run CAT to assemble quantum dot structures
5. Export structures to calculation directories

### Calculation Workflow
1. Export structures from modeling to calculation directories
2. Prepare CP2K input files with appropriate parameters
3. Submit jobs using SLURM job scheduler
4. Monitor job progress and check output files
5. Analyze results using provided notebooks and data files

### Analysis Workflow
1. Run DOS calculations to obtain electronic properties
2. Use `dos.ipynb` notebook for visualization
3. Analyze orbital contributions and band structure
4. Extract structural and electronic properties

## Requirements

### Modeling
- CAT molecular modeling software
- Python environment for configuration
- Molecular structure files (XYZ, MOL, PDB formats)

### Calculation
- CP2K quantum chemistry package (version 2022.1+)
- SLURM job scheduler
- Jupyter notebook for analysis
- Python packages: numpy, matplotlib

### System Requirements
- HPC cluster with MPI support
- Sufficient memory for large nanocrystal calculations
- Storage for output files and restart data

## Performance Notes

- **System Size**: 149 atoms (Cd68Te55Cl26)
- **Computational Cost**: ~2.5 hours on 128 cores for optimization
- **Memory Usage**: ~8-16 GB per node
- **Output Files**: Large trajectory and restart files

## Troubleshooting

### Common Issues
1. **SCF Convergence**: Adjust EPS_SCF or use different SCF methods
2. **Geometry Optimization**: Check force convergence criteria
3. **Memory Issues**: Reduce parallel processes or increase memory allocation
4. **File I/O**: Ensure sufficient disk space for output files

## License

This project is licensed under the terms specified in the LICENSE file.

## Contact

For questions about this project, please refer to the repository maintainers.

---

## 中文版本

本仓库包含碲化镉(CdTe)纳米晶的计算研究，包括分子建模和量子化学计算。

### 项目概述

项目分为两个主要部分：
- **建模**: 使用CAT进行分子结构准备和纳米晶组装
- **计算**: 使用CP2K进行量子化学计算

### 建模部分 (CAT)

建模部分使用CAT（计算机辅助拓扑）进行分子结构准备和纳米晶组装。

#### 主要特点
- **核心结构**: Cd68Te55Cl26纳米晶核心（68个Cd、55个Te、26个Cl原子）
- **配体附着**: PPh3（三苯基膦）配体，以Cd为锚定点
- **量子点组装**: 完整的纳米晶结构，包含配体
- **数据库管理**: 支持PDB格式的分子结构数据库
- **配体优化**: 自动配体结构优化

#### 配置详情
建模过程由`input_settings.yaml`控制，包括：
- 核心结构规格（锚定点索引：[45,49,56,39]）
- 配体优化设置
- 量子点构建参数
- 数据库管理选项

### 计算部分 (CP2K)

计算部分使用CP2K对建模结构进行量子化学计算。

#### 计算类型
- **几何优化**: 使用BFGS优化器进行结构弛豫和能量最小化
- **单点计算**: 电子结构分析和性质计算
- **态密度(DOS)**: 电子性质计算和轨道分析

#### 计算设置
- **方法**: Quickstep (DFT)，使用PBE泛函
- **基组**: 
  - Cd: DZVP-MOLOPT-SR-GTH-q12
  - Te: DZVP-MOLOPT-SR-GTH-q6
  - Cl: DZVP-MOLOPT-SR-GTH-q7
- **赝势**: 所有元素使用GTH-PBE
- **周期性边界条件**: 用于体相计算
- **并行计算**: 基于MPI的并行化
- **SCF收敛**: 1.0E-06阈值，使用OT（轨道变换）方法

#### 主要结果
- **带隙**: 1.54 eV (HOMO: -3.96 eV, LUMO: -2.41 eV)
- **态密度分析**: CdTe和Cl组分的投影态密度
- **轨道分析**: 分子轨道可视化和分析

### 使用说明

#### 建模工作流程
1. 在`model/CdTe_PPh3/core/`中准备核心结构
2. 在`model/CdTe_PPh3/ligand/`中定义配体
3. 在`input_settings.yaml`中配置设置
4. 运行CAT组装量子点结构
5. 将结构导出到计算目录

#### 计算工作流程
1. 将建模结构导出到计算目录
2. 准备具有适当参数的CP2K输入文件
3. 使用SLURM作业调度器提交作业
4. 监控作业进度并检查输出文件
5. 使用提供的笔记本和数据文件分析结果

### 系统要求

#### 建模
- CAT分子建模软件
- Python配置环境
- 分子结构文件（XYZ、MOL、PDB格式）

#### 计算
- CP2K量子化学软件包（版本2022.1+）
- SLURM作业调度器
- 用于分析的Jupyter notebook
- Python包：numpy、matplotlib

#### 系统要求
- 支持MPI的HPC集群
- 大型纳米晶计算的足够内存
- 输出文件和重启数据的存储空间

### 性能说明

- **系统大小**: 149个原子（Cd68Te55Cl26）
- **计算成本**: 优化约需128核2.5小时
- **内存使用**: 每节点约8-16 GB
- **输出文件**: 大型轨迹和重启文件