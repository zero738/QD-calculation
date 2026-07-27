#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --job-name=scnet_finalize_H2
#SBATCH --output=scnet_finalize_H2-%j.out
#SBATCH --error=scnet_finalize_H2-%j.err
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
python3 "$PACKAGE_ROOT/finalize_pipeline.py" --mode after-h2
