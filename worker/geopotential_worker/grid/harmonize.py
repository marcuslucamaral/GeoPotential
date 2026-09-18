"""Bringing every layer onto one grid.

The step the whole pipeline rests on: after it, a stack of criteria is a single
array and every pixel of every layer is in the same place. Before it, nothing
downstream is defined — a difference, a weighted sum and a correlation all
assume the pixel at (row, col) means the same location in every layer.

MSP-06. What is *not* here is as deliberate as what is:

  - **no default CRS.** The target CRS is chosen once, by the caller, and
    carried by the `TargetGrid` (ADR-004).
  - **no silent resampling method.** Averaging a categorical raster invents
    classes that do not exist; nearest-neighbour on a continuous field
    aliases it. The method is a declared parameter, per layer.
  - **no invented extent.** The grid comes from the intersection or the union
    of the inputs, and which one was used is recorded — they give different
    maps and the difference is not cosmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import Resampling, reproject

from ..domain.crs import CrsInfo
from ..domain.grid import TargetGrid
from ..io.readers import RasterSource, read_raster

# Resampling by name. `average` and `mode` are the ones that matter for
# scientific correctness: `average` for a continuous field being coarsened,
# `mode` for a class raster, where averaging would produce class 2.7.
RESAMPLING = {
    "nearest": Resampling.nearest,
    "bilinear": Resampling.bilinear,
    "cubic": Resampling.cubic,
    "average": Resampling.average,
    "mode": Resampling.mode,
    "min": Resampling.min,
    "max": Resampling.max,
}

CONTINUOUS_DEFAULT = "bilinear"
CATEGORICAL_DEFAULT = "mode"


class ExtentPolicy(str, Enum):
    """How the target extent is derived. Recorded, because it changes the map."""

    INTERSECTION = "intersection"  # only where every layer has data
    UNION = "union"                # everywhere any layer has data


@dataclass(frozen=True)
class LayerSpec:
    """One input to harmonize, and how it should be resampled.

    path         the raster to bring onto the grid
    name         the criterion name it will carry
    unit         the physical unit of its values
    resampling   a key of RESAMPLING; declared, never assumed
    categorical  True for a class raster — averaging one invents classes
    """

    path: str
    name: str
    unit: str
    resampling: str = CONTINUOUS_DEFAULT
    categorical: bool = False

    def method(self) -> Resampling:
        key = self.resampling or (
            CATEGORICAL_DEFAULT if self.categorical else CONTINUOUS_DEFAULT
        )
        if key not in RESAMPLING:
            raise ValueError(
                f"layer {self.name!r}: resampling {key!r} is not known; use one "
                f"of {', '.join(sorted(RESAMPLING))}"
            )
        if self.categorical and key in ("bilinear", "cubic", "average"):
            raise ValueError(
                f"layer {self.name!r} is categorical and cannot be resampled by "
                f"{key!r}: averaging class codes produces classes that do not "
                f"exist. Use 'nearest' or 'mode'."
            )
        return RESAMPLING[key]


def build_target_grid(
    sources: Sequence[RasterSource],
    target_crs: CrsInfo,
    pixel_size: tuple[float, float],
    *,
    policy: ExtentPolicy = ExtentPolicy.INTERSECTION,
) -> TargetGrid:
    """Derive the analysis grid from the inputs.

    sources      the layers, each on its own grid and CRS
    target_crs   chosen by the caller; there is no default
    pixel_size   (px, py) in the target CRS's unit, both positive
    policy       intersection or union of the input extents

    returns  TargetGrid
    raises   ValueError when the inputs do not intersect under INTERSECTION

    Which policy was used is the caller's decision and lands in the manifest:
    an intersection answers "where do we know everything", a union answers
    "where do we know anything", and they are different maps.
    """
    if not sources:
        raise ValueError("no layers to harmonize")
    px, py = pixel_size
    if px <= 0 or py <= 0:
        raise ValueError(f"pixel size must be positive, got {px} x {py}")

    boxes = []
    for source in sources:
        left, bottom, right, top = source.grid.bounds
        transformed = rasterio.warp.transform_bounds(
            source.grid.crs.crs, target_crs.crs, left, bottom, right, top,
            densify_pts=21,
        )
        boxes.append(transformed)

    if policy is ExtentPolicy.INTERSECTION:
        left = max(b[0] for b in boxes)
        bottom = max(b[1] for b in boxes)
        right = min(b[2] for b in boxes)
        top = min(b[3] for b in boxes)
        if right <= left or top <= bottom:
            raise ValueError(
                "the layers do not overlap in the target CRS, so an "
                "intersection grid would be empty. Check each layer's CRS — a "
                "layer in the wrong one usually lands somewhere plausible but "
                "far away — or harmonize with the union policy instead."
            )
    else:
        left = min(b[0] for b in boxes)
        bottom = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        top = max(b[3] for b in boxes)

    width = max(1, int(np.floor((right - left) / px)))
    height = max(1, int(np.floor((top - bottom) / py)))
    transform = Affine(px, 0.0, left, 0.0, -py, top)
    return TargetGrid(transform=transform, crs=target_crs,
                      width=width, height=height)


def harmonize(
    spec: LayerSpec, grid: TargetGrid
) -> tuple[np.ndarray, dict[str, Any]]:
    """Bring one layer onto the target grid.

    spec   what to read and how to resample it
    grid   the run's target grid

    returns  ((grid.height, grid.width) float32 with NaN nulls, provenance)

    Reprojection, resampling and clipping happen in one `reproject` call rather
    than as three passes: each pass would resample again, and resampling twice
    smooths a field by more than either step describes.
    """
    source = read_raster(spec.path)
    destination = np.full(grid.shape, np.nan, dtype=np.float32)

    reproject(
        source=source.values,
        destination=destination,
        src_transform=source.grid.transform,
        src_crs=source.grid.crs.crs,
        src_nodata=np.nan,
        dst_transform=grid.transform,
        dst_crs=grid.crs.crs,
        dst_nodata=np.nan,
        resampling=spec.method(),
    )

    provenance = {
        "name": spec.name,
        "source_path": str(spec.path),
        "source_crs": source.grid.crs.name,
        "source_pixel_size": list(source.grid.pixel_size),
        "source_nodata": source.nodata,
        "unit": spec.unit,
        "categorical": spec.categorical,
        "resampling": spec.resampling,
        "target_crs": grid.crs.name,
        "target_pixel_size": list(grid.pixel_size),
        "valid_fraction": float(np.isfinite(destination).mean()),
    }
    return destination, provenance


def common_validity_mask(layers: Sequence[np.ndarray]) -> np.ndarray:
    """Where every layer has data.

    MSP-09's "máscara comum de validade". Aggregation is defined only here:
    a pixel where one criterion is unknown has no defensible score, and giving
    it one — by treating the null as zero, or by renormalizing the weights
    silently — states a confidence nobody has.
    """
    if not layers:
        raise ValueError("no layers")
    mask = np.isfinite(layers[0])
    for layer in layers[1:]:
        mask &= np.isfinite(layer)
    return mask
