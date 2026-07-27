#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --job-name=cu2te_k333
#SBATCH --output=cu2te_k333-%j.out
#SBATCH --error=cu2te_k333-%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment
TASK_ID=cu2te_bulk_k333
INPUT_SOURCE="$PACKAGE_ROOT/inputs/cu2te_bulk/input_k333.inp"
RUN_DIR="$(scnet_prepare_run "$PACKAGE_ROOT" "$TASK_ID" "$INPUT_SOURCE")"
INPUT_FILE="$RUN_DIR/input.executed.inp"
scnet_record_environment "$PACKAGE_ROOT" "$INPUT_FILE" "$RUN_DIR"
STARTED_AT="$(date --iso-8601=seconds)"; START_EPOCH="$(date +%s)"
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "" "" "pending" "false" "3x3x3"
set +e
scnet_run_cp2k "$RUN_DIR"
RC=$?
set -e
FINISHED_AT="$(date --iso-8601=seconds)"; WALL_SECONDS=$(( $(date +%s) - START_EPOCH ))
scnet_write_metadata "$RUN_DIR" "$TASK_ID" "$INPUT_FILE" "$STARTED_AT" "$FINISHED_AT" "$WALL_SECONDS" "$RC" "false" "3x3x3"
set +e
python3 "$PACKAGE_ROOT/verify_server_outputs.py" --task "$TASK_ID"
VERIFY_RC=$?
set -e
[[ $RC -eq 0 ]] || exit "$RC"
exit "$VERIFY_RC"
