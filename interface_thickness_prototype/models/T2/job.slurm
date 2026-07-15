#!/usr/bin/env bash
#SBATCH --job-name=T2_cute_proto
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%j.out
# Add site-specific account/partition/module or container settings before use.
set -euo pipefail
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8}
CP2K_CMD=${CP2K_CMD:-cp2k.psmp}
srun "$CP2K_CMD" -i single_point.inp -o single_point.out
