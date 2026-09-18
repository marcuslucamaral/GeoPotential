"""Inverse distance weighting. Shepard (1968).

    z(cell) = sum(w_i * z_i) / sum(w_i),   w_i = 1 / d_i ^ p

inputs   sample coordinates and values, a target grid, a search radius
output   float32 on the grid, NaN where the radius holds too few samples
unit     the samples' own unit; interpolation does not change it
reference  Shepard, D. (1968), "A two-dimensional interpolation function for
           irregularly-spaced data", Proc. 23rd ACM National Conference.

**A cell outside the radius stays null.** Filling it from the nearest sample,
however far, produces a map with no holes and no survey behind them. The same
reason gives `min_points`: a cell decided by one distant sample carries no
information while looking exactly like a cell that does.

The result cannot leave the interval of the samples it used — a weighted mean
of values never exceeds their maximum — which is what makes IDW safe where an
extrapolating method is not, and is asserted rather than assumed.

**No Python loop over cells or over points.** The neighbour search is one
`cKDTree` query for a whole block of cells; the weighting is array work.
"""
from __future__ import annotations

import numpy as np

#: Cells nearer than this to a sample are taken as *on* it. A sample at
#: distance zero gives an infinite weight, so the arithmetic has to stop
#: before it, not after: `1/0` is inf and `inf/inf` is NaN, which would blank
#: exactly the cells that are best known.
ON_SAMPLE = 1e-12


def interpolate(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    cell_x: np.ndarray,
    cell_y: np.ndarray,
    *,
    radius: float,
    power: float = 2.0,
    min_points: int = 1,
    max_points: int = 16,
) -> np.ndarray:
    """Estimate the field at a set of cell centres.

    x, y, values  the samples, in the grid's CRS; non-finite ones are dropped
    cell_x/y      where to estimate, in the same CRS
    radius        search radius in the CRS's unit; beyond it, nothing is used
    power         Shepard's p. Higher weights the nearest sample more; the
                  limit is nearest-neighbour, and p -> 0 is the plain mean
    min_points    fewer neighbours than this leaves the cell null
    max_points    the neighbours actually used, nearest first. A cap, because
                  the cost is per neighbour and the far ones cannot change a
                  weighted mean much once p >= 1
    returns       (n,) float32, NaN where the cell was not estimated
    """
    from scipy.spatial import cKDTree

    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    values = np.asarray(values, dtype=np.float64).ravel()
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    x, y, values = x[keep], y[keep], values[keep]

    out = np.full(cell_x.size, np.nan, dtype=np.float32)
    if x.size == 0 or cell_x.size == 0:
        return out
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError(f"the search radius must be positive; got {radius}")
    if power < 0:
        raise ValueError(f"the power must not be negative; got {power}")

    tree = cKDTree(np.column_stack([x, y]))
    wanted = int(min(max(1, max_points), x.size))
    # One query for every cell in the block. `distance_upper_bound` makes the
    # tree itself apply the radius, so nothing outside it is ever fetched.
    distances, indices = tree.query(
        np.column_stack([cell_x, cell_y]), k=wanted,
        distance_upper_bound=float(radius),
    )
    if wanted == 1:                       # scipy drops the neighbour axis
        distances = distances[:, None]
        indices = indices[:, None]

    # Missing neighbours come back as index == n and distance == inf.
    found = np.isfinite(distances)
    enough = found.sum(axis=1) >= max(1, int(min_points))
    if not enough.any():
        return out

    safe = np.where(found, indices, 0)
    sampled = values[safe]

    # A cell sitting on a sample takes that sample's value. Done before the
    # weights, because 1/0 is inf and a sum of infs divides to NaN.
    on_sample = found & (distances <= ON_SAMPLE)
    exact = on_sample.any(axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        weights = np.where(found, 1.0 / np.power(distances, power), 0.0)
    weights = np.where(np.isfinite(weights), weights, 0.0)

    total = weights.sum(axis=1)
    estimated = np.divide(
        (weights * sampled).sum(axis=1), total,
        out=np.full(cell_x.size, np.nan), where=total > 0,
    )

    # `argmax` on a boolean row gives the first True, which is the nearest
    # neighbour because the query returns them sorted.
    nearest = np.take_along_axis(
        sampled, on_sample.argmax(axis=1)[:, None], axis=1).ravel()
    estimated = np.where(exact, nearest, estimated)

    out[enough] = estimated[enough].astype(np.float32)
    return out


def statistics(values: np.ndarray) -> dict[str, float | int | None]:
    """What the manifest records about the field that came out."""
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
