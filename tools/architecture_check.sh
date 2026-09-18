#!/usr/bin/env bash
# Three-line wrapper. Fix tools/architecture_check.py, never this file.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${GEOPOTENTIAL_PYTHON:-$("$here/../tools/find_python.sh")}" "$here/architecture_check.py" "$@"
