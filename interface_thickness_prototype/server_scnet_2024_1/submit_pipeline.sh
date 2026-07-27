#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(pwd -P)" == "$SCRIPT_DIR" ]] || { echo "ERROR: cd to server_scnet_2024_1 before submitting" >&2; exit 2; }
[[ "$(basename "$SCRIPT_DIR")" == "server_scnet_2024_1" ]] || exit 2
[[ ! -e pipeline_jobs.json ]] || { echo "ERROR: pipeline_jobs.json already exists; refusing duplicate submission" >&2; exit 3; }
if [[ -d runs ]] && find runs -mindepth 1 -print -quit | grep -q .; then
    echo "ERROR: runs/ contains evidence; archive it instead of overwriting" >&2
    exit 3
fi
for required in upload_manifest.txt package_config.json pipeline_state.py scripts/00_check_environment.slurm scripts/30_H1.slurm scripts/40_H2.slurm; do
    [[ -f "$required" ]] || { echo "ERROR: missing $required" >&2; exit 2; }
done
sha256sum -c upload_manifest.txt
python3 pipeline_state.py budget

submitted_ids=()
cleanup_partial_submission() {
    local rc=$?
    if [[ $rc -ne 0 && ${#submitted_ids[@]} -gt 0 ]]; then
        echo "Submission failed; cancelling only jobs submitted by this invocation: ${submitted_ids[*]}" >&2
        scancel "${submitted_ids[@]}" || true
    fi
    exit "$rc"
}
trap cleanup_partial_submission ERR

submit_job() {
    local dependency="$1" script="$2" job
    if [[ -n "$dependency" ]]; then
        job="$(sbatch --parsable --dependency="$dependency" "$script")"
    else
        job="$(sbatch --parsable "$script")"
    fi
    job="${job%%;*}"
    [[ "$job" =~ ^[0-9]+$ ]] || { echo "ERROR: invalid sbatch job id: $job" >&2; return 2; }
    submitted_ids+=("$job")
    LAST_JOB_ID="$job"
    echo "submitted $script as $job" >&2
}

submit_job '' scripts/00_check_environment.slurm; env_id="$LAST_JOB_ID"
submit_job "afterok:$env_id" scripts/01_cu2te_bulk_gamma.slurm; gamma_id="$LAST_JOB_ID"
submit_job "afterok:$gamma_id" scripts/02_cu2te_bulk_k222.slurm; k222_id="$LAST_JOB_ID"
submit_job "afterok:$k222_id" scripts/03_cu2te_bulk_k333.slurm; k333_id="$LAST_JOB_ID"
submit_job "afterok:$k333_id" scripts/04_cu2te_bulk_k444.slurm; k444_id="$LAST_JOB_ID"
submit_job "afterok:$k444_id" scripts/10_B0.slurm; b0_id="$LAST_JOB_ID"
submit_job "afterok:$b0_id" scripts/20_C50.slurm; c50_id="$LAST_JOB_ID"
submit_job "afterok:$c50_id" scripts/30_H1.slurm; h1_id="$LAST_JOB_ID"
submit_job "afterok:$h1_id" scripts/40_H2.slurm; h2_id="$LAST_JOB_ID"
submit_job "afterany:$h2_id" scripts/90_finalize_after_H2.slurm; final_h2_id="$LAST_JOB_ID"
submit_job "afterany:$h1_id" scripts/91_finalize_if_H1_failed.slurm; final_h1_id="$LAST_JOB_ID"

pipeline_id="scnet-$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-login}"
git_commit="$(git -C ../.. rev-parse HEAD 2>/dev/null || echo unavailable)"
python3 pipeline_state.py record --pipeline-id "$pipeline_id" --git-commit "$git_commit" \
  --entry "environment|$env_id||scripts/00_check_environment.slurm" \
  --entry "bulk_gamma|$gamma_id|afterok:$env_id|scripts/01_cu2te_bulk_gamma.slurm" \
  --entry "bulk_k222|$k222_id|afterok:$gamma_id|scripts/02_cu2te_bulk_k222.slurm" \
  --entry "bulk_k333|$k333_id|afterok:$k222_id|scripts/03_cu2te_bulk_k333.slurm" \
  --entry "bulk_k444|$k444_id|afterok:$k333_id|scripts/04_cu2te_bulk_k444.slurm" \
  --entry "B0|$b0_id|afterok:$k444_id|scripts/10_B0.slurm" \
  --entry "C50|$c50_id|afterok:$b0_id|scripts/20_C50.slurm" \
  --entry "H1|$h1_id|afterok:$c50_id|scripts/30_H1.slurm" \
  --entry "H2|$h2_id|afterok:$h1_id|scripts/40_H2.slurm" \
  --entry "finalize_after_H2|$final_h2_id|afterany:$h2_id|scripts/90_finalize_after_H2.slurm" \
  --entry "finalize_if_H1_failed|$final_h1_id|afterany:$h1_id|scripts/91_finalize_if_H1_failed.slurm"
trap - ERR
echo "Pipeline submitted. Monitor with: bash monitor_pipeline.sh"
echo "Do not edit inputs or submit H1/H2 separately."
