#!/usr/bin/env bash
#SBATCH --job-name=cdte_cu2te_smoke
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --output=smoke-tests-%j.out
# Add site-specific account, partition and module commands before submitting.
set -euo pipefail
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8}
python scripts/run_smoke_tests.py --mode native --cp2k-command "${CP2K_CMD:-cp2k.psmp}"
