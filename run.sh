#!/usr/bin/env bash
# Compile and execute only the captured snapshot, with retained evidence.
set -euo pipefail
SCRIPT_DIR=$(cd -P -- "$(dirname -- "$0")" && pwd)
exec python3 -B "$SCRIPT_DIR/tools/evidence.py" "$@"
