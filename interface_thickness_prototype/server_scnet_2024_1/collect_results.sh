#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/verify_server_outputs.py" --all --write-results
python3 "$SCRIPT_DIR/generate_reports.py"
python3 "$SCRIPT_DIR/plot_results.py"
python3 "$SCRIPT_DIR/package_results.py"

echo "Server result tables are in: $SCRIPT_DIR/results"
echo "Download bundle: $SCRIPT_DIR/scnet_results_bundle.tar.gz"
echo "Large cubes/WFN/restarts stay on the server and are listed in large_optional_files_manifest.txt"
