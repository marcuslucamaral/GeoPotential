"""Point PROJ and GDAL at the data collected into the bundle.

A runtime hook and not application code, because **pyproj and rasterio resolve
their data directories at import**, which happens before any module of this
application runs. Setting these from `app.py` is already too late: the first
`CRS.from_user_input` fails with an error about a missing database, on a binary
that started, opened a window and looked fine.

`PROJ_DATA` as well as `PROJ_LIB`: PROJ 9 renamed the variable and honours both,
and which one is read depends on the version that ends up in the bundle.

This runs in **both** processes the binary can be — the application and the
`--worker` child — because a runtime hook runs before the entry point chooses,
and the worker is the one that does most of the CRS work.
"""
from __future__ import annotations

import os
import sys

if getattr(sys, "frozen", False):
    root = sys._MEIPASS  # type: ignore[attr-defined]

    proj = os.path.join(root, "share", "proj")
    if os.path.isdir(proj):
        os.environ["PROJ_LIB"] = proj
        os.environ["PROJ_DATA"] = proj

    gdal = os.path.join(root, "share", "gdal")
    if os.path.isdir(gdal):
        os.environ["GDAL_DATA"] = gdal
