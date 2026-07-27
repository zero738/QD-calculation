#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --job-name=scnet_finalize_H1_fail
#SBATCH --output=scnet_finalize_H1_fail-%j.out
#SBATCH --error=scnet_finalize_H1_fail-%j.err
set -euo pipefail
PACKAGE_ROOT="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment
python3 "$PACKAGE_ROOT/finalize_pipeline.py" --mode h1-failure
