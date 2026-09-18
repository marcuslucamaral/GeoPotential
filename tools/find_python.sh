#!/usr/bin/env bash
#
# Print the interpreter that carries the project stack. The environment is the
# existing conda env `mcda_geo` (Python 3.11, PySide6, rasterio, geopandas,
# pyproj, shapely). Do not create another one.
set -euo pipefail
if [[ -n "${GEOPOTENTIAL_PYTHON:-}" ]]; then echo "$GEOPOTENTIAL_PYTHON"; exit 0; fi
for candidate in \
    "$HOME/anaconda3/envs/mcda_geo/bin/python" \
    "$HOME/miniconda3/envs/mcda_geo/bin/python"
do
    if [[ -x "$candidate" ]]; then echo "$candidate"; exit 0; fi
done
command -v python3
