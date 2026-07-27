#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=24
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --job-name=scnet_H2
#SBATCH --output=scnet_H2-%j.out
#SBATCH --error=scnet_H2-%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment

# Revalidate H1 and dynamically write runs/H2/input.executed.inp before srun.
python3 "$PACKAGE_ROOT/verify_server_outputs.py" --gate-h2
python3 "$PACKAGE_ROOT/prepare_h2_input.py"

TASK_ID=H2
RUN_DIR="$PACKAGE_ROOT/runs/H2"
INPUT_FILE="$RUN_DIR/input.executed.inp"
scnet_record_environment "$PACKAGE_ROOT" "$INPUT_FILE" "$RUN_DIR"
STARTED_AT="$(date --iso-8601=seconds)"; START_EPOCH="$(date +%s)"
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "" "" "pending" "true" "Gamma"
set +e
scnet_run_cp2k "$RUN_DIR"
RC=$?
set -e
FINISHED_AT="$(date --iso-8601=seconds)"; WALL_SECONDS=$(( $(date +%s) - START_EPOCH ))
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "$FINISHED_AT" "$WALL_SECONDS" "$RC" "true" "Gamma"
set +e
python3 "$PACKAGE_ROOT/verify_server_outputs.py" --task H2
VERIFY_RC=$?
set -e
[[ $RC -eq 0 ]] || exit "$RC"
exit "$VERIFY_RC"
