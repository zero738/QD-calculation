#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/verify_server_outputs.py" --all --write-results

echo "Server result tables are in: $SCRIPT_DIR/results"
