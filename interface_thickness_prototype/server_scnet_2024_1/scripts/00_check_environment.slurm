#!/bin/bash
#SBATCH --partition=kshctest02
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:10:00
#SBATCH --job-name=scnet_env_check
#SBATCH --output=scnet_env_check-%j.out
#SBATCH --error=scnet_env_check-%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PACKAGE_ROOT/env_scnet.sh"
scnet_activate_environment

echo "date=$(date --iso-8601=seconds)"
echo "hostname=$(hostname)"
echo "job_id=${SLURM_JOB_ID:-unknown}"
echo "partition=${SLURM_JOB_PARTITION:-unknown}"
echo "ntasks=${SLURM_NTASKS:-unknown}"
echo "cp2k_executable=$SCNET_CP2K_EXE"
echo "cp2k_data_dir=$SCNET_CP2K_DATA_DIR"
module list 2>&1 || true
CP2K_VERSION_OUTPUT="$("$SCNET_CP2K_EXE" --version)"
echo "$CP2K_VERSION_OUTPUT"
grep -q "CP2K version 2024.1" <<< "$CP2K_VERSION_OUTPUT" || {
    echo "ERROR: expected CP2K version 2024.1" >&2
    exit 2
}
LDD_OUTPUT="$(ldd "$SCNET_CP2K_EXE")"
echo "$LDD_OUTPUT"
if grep -q "not found" <<< "$LDD_OUTPUT"; then
    echo "ERROR: CP2K has a missing dynamic library" >&2
    exit 2
fi
[[ "${SLURM_JOB_PARTITION:-}" == "kshctest02" ]] || {
    echo "ERROR: environment check is not running in kshctest02" >&2
    exit 2
}
python3 --version
sha256sum -c "$PACKAGE_ROOT/upload_manifest.txt"
python3 "$PACKAGE_ROOT/check_server_inputs.py" --cp2k "$SCNET_CP2K_EXE"
git -C "$PACKAGE_ROOT/../.." rev-parse HEAD 2>/dev/null || echo "git_commit=unavailable"
ulimit -a
grep -E 'MemTotal|MemAvailable' /proc/meminfo || true
free -h || true

echo "ENVIRONMENT_CHECK_COMPLETE"
