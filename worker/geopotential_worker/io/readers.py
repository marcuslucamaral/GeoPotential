"""Reading a source into the domain, with its CRS and its nulls intact.

A source with no CRS is refused by name. Its declared nodata becomes NaN, the
single in-memory null, so no stage downstream has to know what the file's
sentinel was.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from ..domain.crs import CrsInfo
from ..domain.grid import TargetGrid


@dataclass(frozen=True)
class RasterSource:
    """One raster read onto its own grid, nulls already NaN.

    values  (height, width) float32, NaN where the file declared nodata
    grid    the file's own grid, in the file's own CRS
    nodata  the sentinel the file declared, kept for provenance
    """

    values: np.ndarray
    grid: TargetGrid
    nodata: float | None
    path: Path


def read_raster(path: str | Path, *, band: int = 1) -> RasterSource:
    """Read one band as float32 with NaN nulls.

    path     a GDAL-readable raster
    band     1-based band index
    returns  RasterSource on the file's own grid
    raises   MissingCrsError when the file declares no CRS

    The declared nodata is converted to NaN here and nowhere else. Leaving a
    -9999 in the array means every downstream statistic is wrong by a number
    that looks like data.
    """
    path = Path(path)
    with rasterio.open(path) as src:
        crs = CrsInfo.from_user_input(src.crs, source=path.name)
        values = src.read(band, masked=False).astype(np.float32, copy=False)
        nodata = src.nodata
        if nodata is not None and not np.isnan(nodata):
            values = np.where(values == np.float32(nodata), np.nan, values)
        values = np.ascontiguousarray(values, dtype=np.float32)
        grid = TargetGrid(
            transform=src.transform, crs=crs, width=src.width, height=src.height
        )
    return RasterSource(values=values, grid=grid, nodata=nodata, path=path)


def describe_raster(path: str | Path) -> dict[str, object]:
    """Metadata a Data Inspector shows, without reading the pixels.

    Used by the Import Wizard (MSP-03) to diagnose before a dataset enters a
    project: format, CRS, unit, extent, nodata, band count, size.
    """
    path = Path(path)
    with rasterio.open(path) as src:
        crs = CrsInfo.from_user_input(src.crs, source=path.name)
        left, bottom, right, top = src.bounds
        return {
            "path": str(path),
            "driver": src.driver,
            "crs": crs.name,
            "crs_unit": crs.unit,
            "geographic": crs.is_geographic,
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtype": src.dtypes[0],
            "nodata": None if src.nodata is None else float(src.nodata),
            "pixel_size_x": abs(src.transform.a),
            "pixel_size_y": abs(src.transform.e),
            "bounds": [left, bottom, right, top],
        }
