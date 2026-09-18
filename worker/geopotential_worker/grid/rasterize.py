"""Burning a feature's own value into the cells it covers.

inputs   geometries paired with the value each carries, and a target grid
output   float32 on the grid, NaN where no feature is
reference  IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06, "rasterização".

**This is not interpolation and must never be called one.** A polygon that
says "granite, density 2.67" gives 2.67 to the cells it covers and says
nothing about the cells it does not. Nothing between features is estimated;
those cells stay null, and a null is what they are.

Where features overlap, the last one drawn wins — which is why the order is
the caller's and is recorded, rather than being decided here by area or by
accident of file order.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ..domain.grid import TargetGrid


def burn(
    shapes: Sequence[tuple[Any, float]],
    grid: TargetGrid,
    *,
    all_touched: bool = False,
) -> np.ndarray:
    """Draw geometries onto the grid, each carrying its own value.

    shapes       (geometry, value) pairs, in the grid's CRS, in draw order
    grid         the target grid
    all_touched  True gives a cell to any feature that touches it; False
                 (the default) only to features covering the cell's centre.
                 The two differ along every boundary, and thin features can
                 vanish entirely under the second — so the choice is the
                 caller's and lands in the manifest
    returns      (h, w) float32, NaN outside every feature

    A feature with a non-finite value is dropped rather than burning NaN over
    a cell another feature had already filled.
    """
    from rasterio import features

    usable = [
        (geometry, float(value)) for geometry, value in shapes
        if geometry is not None and value is not None
        and np.isfinite(float(value))
    ]
    if not usable:
        return np.full(grid.shape, np.nan, dtype=np.float32)

    return features.rasterize(
        usable,
        out_shape=grid.shape,
        transform=grid.transform,
        fill=np.nan,
        all_touched=bool(all_touched),
        dtype="float32",
    )


def mask(
    geometries: Sequence[Any],
    grid: TargetGrid,
    *,
    all_touched: bool = True,
) -> np.ndarray:
    """Which cells a set of geometries occupies, as booleans.

    `all_touched` defaults to True here and False in `burn`, and the
    difference is deliberate: a mask feeding a distance transform must not
    lose a thin feature that crosses no cell centre — a fault line one metre
    wide on a 40 m grid would disappear, and every distance measured from it
    would be a distance to something else.
    """
    from rasterio import features

    usable = [g for g in geometries if g is not None]
    if not usable:
        return np.zeros(grid.shape, dtype=bool)

    burned = features.rasterize(
        ((geometry, 1) for geometry in usable),
        out_shape=grid.shape,
        transform=grid.transform,
        fill=0,
        all_touched=bool(all_touched),
        dtype="uint8",
    )
    return burned.astype(bool)


def points_mask(
    x: np.ndarray, y: np.ndarray, grid: TargetGrid
) -> np.ndarray:
    """Which cells hold at least one of these points.

    Computed with the inverse transform and one `add.at`, not by rasterising
    a geometry per point: a survey of 50 000 points would otherwise build
    50 000 shapely objects to answer a question about cell indices.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    finite = np.isfinite(x) & np.isfinite(y)
    out = np.zeros(grid.shape, dtype=bool)
    if not finite.any():
        return out

    inverse = ~grid.transform
    a, b, c, d, e, f = tuple(inverse)[:6]
    columns = np.floor(a * x[finite] + b * y[finite] + c).astype(np.int64)
    rows = np.floor(d * x[finite] + e * y[finite] + f).astype(np.int64)
    inside = (
        (columns >= 0) & (columns < grid.width)
        & (rows >= 0) & (rows < grid.height)
    )
    out[rows[inside], columns[inside]] = True
    return out


def statistics(values: np.ndarray) -> dict[str, float | int | None]:
    """What the manifest records about the burned field."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"valid": 0, "valid_fraction": 0.0,
                "min": None, "max": None, "mean": None}
    return {
        "valid": int(finite.size),
        "valid_fraction": float(finite.size / values.size),
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean(dtype=np.float64)),
    }
