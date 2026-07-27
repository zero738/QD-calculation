#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
#SBATCH --time=16:00:00
#SBATCH --job-name=scnet_H1
#SBATCH --output=scnet_H1-%j.out
#SBATCH --error=scnet_H1-%j.err

set -euo pipefail
PACKAGE_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment

# run_h1_controlled.py creates attempt_A and, only for an allowed diagnostic,
# attempt_B.  Each subprocess uses cwd=that attempt directory and relative
# input/output names.  The job never submits another job and never exceeds two runs.
python3 "$PACKAGE_ROOT/run_h1_controlled.py" --cp2k "$SCNET_CP2K_EXE"
