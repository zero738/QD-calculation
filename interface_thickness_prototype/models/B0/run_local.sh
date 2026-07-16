#!/usr/bin/env bash
set -euo pipefail
input=${1:-single_point.inp}
output=${input%.inp}.out
cmd=${CP2K_CMD:-}
if [[ -z "$cmd" ]]; then
  for candidate in cp2k.psmp cp2k.popt cp2k; do
    if command -v "$candidate" >/dev/null 2>&1; then cmd=$candidate; break; fi
  done
fi
if [[ -z "$cmd" ]]; then echo "ERROR: CP2K not found. Set CP2K_CMD." >&2; exit 127; fi
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
"$cmd" -i "$input" -o "$output"
"${PYTHON:-python}" ../../scripts/parse_cp2k_output.py "$output" --input "$input"
