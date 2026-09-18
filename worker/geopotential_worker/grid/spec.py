"""The analysis grid, declared rather than inferred. MSP-06.

Three operators build a grid out of sparse data — `grid.idw`,
`grid.euclidean_distance`, `grid.rasterize` — and all three ask the same three
questions:

  **which CRS**   there is no default (ADR-004);
  **which pixel** it decides what the whole analysis resolves;
  **which area**  the data's own extent, or a smaller one that was chosen.

One place answers them, so the three cannot come to disagree about what "40 m
over this area" means. And one place consults the planner, so no operator
allocates a grid before its cost has been estimated: a grid too large is
refused *here*, with the message naming what to reduce, rather than becoming a
process the operating system kills half way through a run (§18.1).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from affine import Affine

from ..domain.crs import CrsInfo
from ..domain.grid import TargetGrid
from .planner import Plan, Policy, plan_operation


class GridRefused(ValueError):
    """The requested grid cannot be built, and the message says why."""


def bounds_in(
    box: tuple[float, float, float, float],
    source: CrsInfo,
    target: CrsInfo,
) -> tuple[float, float, float, float]:
    """A bounding box moved from one CRS to another.

    inputs   (left, bottom, right, top), the CRS it is written in, the target
    output   the same box in the target CRS

    Densified before transforming: a projected box's edges are not straight in
    another CRS, and transforming only the four corners clips whatever bulges
    past them.
    """
    import rasterio.warp

    if source == target:
        return box
    left, bottom, right, top = box
    return tuple(rasterio.warp.transform_bounds(
        source.crs, target.crs, left, bottom, right, top, densify_pts=21,
    ))


def build(
    *,
    target_crs: CrsInfo,
    pixel_size: tuple[float, float],
    data_bounds: tuple[float, float, float, float],
    bounds: tuple[float, float, float, float] | None = None,
    bounds_crs: CrsInfo | None = None,
    operation: str = "gridding",
    output_dir=None,  # noqa: ANN001 - path-like
    require_metric: bool = True,
) -> tuple[TargetGrid, Plan, dict[str, Any]]:
    """The grid an operator will write into, and what it will cost.

    target_crs   chosen by the caller; there is no default
    pixel_size   (px, py) in the target CRS's unit, both positive
    data_bounds  the extent of the input, already in the target CRS
    bounds       the area to grid, when it is not the whole input
    bounds_crs   the CRS `bounds` was written in, when not the target
    operation    named in the plan's message
    require_metric  refuse a geographic CRS — true for anything that measures

    returns  (grid, plan, provenance) — provenance is what the manifest records
    raises   GridRefused

    The area is the cheapest thing a person can change when a grid does not
    fit, and the most consequential thing they can get wrong, so it is
    reported either way: the manifest says whether the extent came from the
    data or was chosen, and which CRS it was written in.
    """
    px, py = (float(pixel_size[0]), float(pixel_size[1]))
    if not (np.isfinite(px) and np.isfinite(py)) or px <= 0 or py <= 0:
        raise GridRefused(
            f"pixel size must be two positive numbers; got {px} x {py}. It is "
            f"in the unit of {target_crs.name}."
        )

    # A radius, a distance and a pixel in metres are all meaningless in
    # degrees. The refusal names the CRS rather than silently approximating.
    if require_metric and target_crs.is_geographic:
        raise GridRefused(
            f"{target_crs.name} is a geographic CRS, so a pixel of {px} is in "
            f"degrees and a distance in it is not a distance. Choose a "
            f"projected CRS for the analysis grid."
        )

    chosen = bounds is not None
    if chosen:
        box = tuple(float(v) for v in bounds)
        if len(box) != 4:
            raise GridRefused("bounds must be (left, bottom, right, top)")
        if bounds_crs is not None and bounds_crs != target_crs:
            box = bounds_in(box, bounds_crs, target_crs)
    else:
        box = tuple(float(v) for v in data_bounds)

    left, bottom, right, top = box
    if not all(np.isfinite(v) for v in box):
        raise GridRefused(f"the extent is not finite: {box}")
    if right <= left or top <= bottom:
        raise GridRefused(
            f"the extent is empty or inverted: left={left:g} right={right:g}, "
            f"bottom={bottom:g} top={top:g}. It is written "
            f"(left, bottom, right, top)."
        )

    width = max(1, int(np.floor((right - left) / px)))
    height = max(1, int(np.floor((top - bottom) / py)))

    # Before allocating anything. A grid that does not fit is a decision the
    # person can act on — a coarser pixel, a smaller area — and finding out
    # after the allocation is not a decision, it is a crash.
    plan = plan_operation(
        operation, width=width, height=height, layers=1,
        output_layers=1, output_dir=output_dir,
    )
    if plan.policy is Policy.REFUSE:
        raise GridRefused(
            f"{width} x {height} pixels at {px:g} x {py:g}: {plan.reason} "
            f"Reduce the resolution, or grid a smaller area with `bounds`."
        )

    grid = TargetGrid(
        transform=Affine(px, 0.0, left, 0.0, -py, top),
        crs=target_crs, width=width, height=height,
    )
    provenance = {
        "extent_source": "chosen" if chosen else "data",
        "bounds_crs": (bounds_crs.name if chosen and bounds_crs is not None
                       else target_crs.name),
        "requested_bounds": list(bounds) if chosen else None,
        "data_bounds": list(data_bounds),
        "plan": plan.as_dict(),
    }
    return grid, plan, provenance


def cell_centres(grid: TargetGrid, row_start: int, row_stop: int):
    """The map coordinates of every cell centre in a band of rows.

    inputs   the grid and a half-open row range
    output   (x, y) each (n,) float64, row-major over the band

    Built with `meshgrid` and one affine application: a loop over cells here
    would be a loop over pixels, which is the defect ADR-007 measures.
    """
    columns = np.arange(grid.width, dtype=np.float64) + 0.5
    rows = np.arange(row_start, row_stop, dtype=np.float64) + 0.5
    cc, rr = np.meshgrid(columns, rows)
    a, b, c, d, e, f = tuple(grid.transform)[:6]
    x = a * cc + b * rr + c
    y = d * cc + e * rr + f
    return x.ravel(), y.ravel()


def row_blocks(grid: TargetGrid, plan: Plan):
    """The row ranges to process, one at a time.

    A plan that fits gives one block; a plan that does not gives the row count
    the planner chose. Either way the caller writes the same loop, and the
    loop is over blocks — never over pixels.
    """
    step = grid.height if plan.policy is Policy.IN_MEMORY else max(
        1, int(plan.block_rows or 1))
    for start in range(0, grid.height, step):
        yield start, min(start + step, grid.height)
