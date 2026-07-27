#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00
#SBATCH --job-name=scnet_B0
#SBATCH --output=scnet_B0-%j.out
#SBATCH --error=scnet_B0-%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment
TASK_ID=B0
INPUT_SOURCE="$PACKAGE_ROOT/inputs/B0/input.inp"
RUN_DIR="$(scnet_prepare_run "$PACKAGE_ROOT" "$TASK_ID" "$INPUT_SOURCE")"
INPUT_FILE="$RUN_DIR/input.executed.inp"
scnet_record_environment "$PACKAGE_ROOT" "$INPUT_FILE" "$RUN_DIR"
STARTED_AT="$(date --iso-8601=seconds)"; START_EPOCH="$(date +%s)"
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "" "" "pending" "true" "Gamma"
set +e
srun --mpi=pmix_v3 "$SCNET_CP2K_EXE" -i "$INPUT_FILE" -o "$RUN_DIR/output.out"
RC=$?
set -e
FINISHED_AT="$(date --iso-8601=seconds)"; WALL_SECONDS=$(( $(date +%s) - START_EPOCH ))
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "$FINISHED_AT" "$WALL_SECONDS" "$RC" "true" "Gamma"
set +e
python3 "$PACKAGE_ROOT/verify_server_outputs.py" --task "$TASK_ID"
VERIFY_RC=$?
set -e
[[ $RC -eq 0 ]] || exit "$RC"
exit "$VERIFY_RC"
