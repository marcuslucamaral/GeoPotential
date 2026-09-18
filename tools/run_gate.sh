#!/usr/bin/env bash
# Three-line wrapper. Fix tools/run_gate.py, never this file.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${GEOPOTENTIAL_PYTHON:-$("$here/../tools/find_python.sh")}" "$here/run_gate.py" "$@"
