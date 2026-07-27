#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f pipeline_jobs.json ]] || { echo "pipeline_jobs.json not found" >&2; exit 2; }
mapfile -t JOB_IDS < <(python3 -c 'import json; d=json.load(open("pipeline_jobs.json", encoding="utf-8")); print("\n".join(str(x["job_id"]) for x in d["jobs"].values()))')
[[ ${#JOB_IDS[@]} -gt 0 ]] || { echo "No recorded job IDs" >&2; exit 2; }
echo "Only these jobs from the current pipeline will be cancelled: ${JOB_IDS[*]}"
read -r -p "Type CANCEL_CURRENT_PIPELINE to confirm: " answer
[[ "$answer" == "CANCEL_CURRENT_PIPELINE" ]] || { echo "Cancelled by user; no Slurm jobs changed."; exit 1; }
scancel "${JOB_IDS[@]}"
echo "Cancellation requested. Existing run evidence was not deleted."
