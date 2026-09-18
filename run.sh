#!/usr/bin/env bash
#
# Launch GeoPotential Professional.
#
#   ./run.sh                       the workspace on the smoke dataset
#   ./run.sh FILE.tif              ... on a raster of your own
#   ./run.sh --self-test           the M1 vertical-slice gate, headless
#   ./run.sh --screenshot OUT.png  capture the running window
#   ./run.sh --help                every switch
#
# All this does that matters is put `app/` on PYTHONPATH and pick the project
# interpreter. Without it:  PYTHONPATH=app <python> -m geopotential_app
#
# The worker child gets `worker/` on its own PYTHONPATH from the supervisor;
# it is a separate process and does not share this one's.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="$("$here/tools/find_python.sh")"

if ! "$python_bin" -c "import PySide6" 2>/dev/null; then
    echo "ERROR: $python_bin cannot import PySide6." >&2
    echo "       Activate the project environment:  conda activate mcda_geo" >&2
    echo "       or point this script at one:       GEOPOTENTIAL_PYTHON=/path/to/python ./run.sh" >&2
    exit 2
fi

export PYTHONPATH="$here/app${PYTHONPATH:+:$PYTHONPATH}"
exec "$python_bin" -m geopotential_app "$@"
