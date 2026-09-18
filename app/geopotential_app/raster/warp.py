"""Warping a tile for display. ADR-006, ADR-MSP-003.

Two layers in two CRSs cannot share a view unless one of them is transformed.
**The source is never touched**: a layer read in UTM stays in UTM, and what is
warped is the tile that was about to be painted. Nothing here writes a file.

It lives in `raster/` because it needs `rasterio.warp`, and `render/` is numpy
in, pixels out — the separation that lets rendering be gated without a window.

Reprojecting the *data* is a different act: it is a run in the worker, it
writes a GeoTIFF, and it carries a manifest. This is the picture only.
"""
from __future__ import annotations

import numpy as np


def reproject_tile(
    values: np.ndarray,
    transform,                    # noqa: ANN001 - affine.Affine
    source_crs,                   # noqa: ANN001 - rasterio CRS or str
    *,
    target_crs,                   # noqa: ANN001
    extent: tuple[float, float, float, float],
    width: int,
    height: int,
    categorical: bool = False,
) -> np.ndarray:
    """Resample a tile onto a screen-shaped grid in another CRS.

    values      (rows, cols) float32; NaN is the null
    transform   the tile's affine, in `source_crs`
    source_crs  what the tile is in
    target_crs  what the view is in
    extent      (left, bottom, right, top) of the view, in `target_crs`
    width       the output grid, in pixels
    height
    categorical nearest-neighbour instead of bilinear: averaging class codes
                invents classes that do not exist
    returns     (height, width) float32, NaN outside the source

    NaN stays NaN: `dst_nodata` is NaN, so a pixel with no source lands as a
    null and is drawn transparent, never as the low end of the ramp.
    """
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, reproject

    left, bottom, right, top = extent
    if width <= 0 or height <= 0 or right <= left or top <= bottom:
        return np.full((max(1, height), max(1, width)), np.nan, dtype=np.float32)

    destination = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=np.ascontiguousarray(values, dtype=np.float32),
        destination=destination,
        src_transform=transform,
        src_crs=source_crs,
        src_nodata=np.nan,
        dst_transform=from_bounds(left, bottom, right, top, width, height),
        dst_crs=target_crs,
        dst_nodata=np.nan,
        resampling=Resampling.nearest if categorical else Resampling.bilinear,
    )
    return destination


def source_window(
    extent: tuple[float, float, float, float], target_crs, source_crs
):  # noqa: ANN001, ANN201
    """The part of the source a view covers, in the source's own CRS.

    The view is a rectangle in the target CRS; in the source CRS it is not a
    rectangle, so the box that contains it is what has to be read. pyproj
    densifies the edges, which is why the box is not just four corners.
    """
    from rasterio.warp import transform_bounds

    left, bottom, right, top = transform_bounds(
        target_crs, source_crs, *[float(v) for v in extent], densify_pts=21
    )
    return float(left), float(bottom), float(right), float(top)
