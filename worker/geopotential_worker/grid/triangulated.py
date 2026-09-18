"""Interpolation over a Delaunay triangulation. The two methods QGIS offers.

    linear  barycentric inside each triangle          C0, never overshoots
    cubic   Clough-Tocher, C1 across triangle edges    smooth, may overshoot

inputs   sample coordinates and values, a target grid
output   float32 on the grid, NaN outside the convex hull of the samples
unit     the samples' own unit; interpolation does not change it
reference  Delaunay, B. (1934), "Sur la sphère vide", Bull. Acad. Sci. URSS;
           Clough, R. & Tocher, J. (1965), "Finite element stiffness matrices
           for analysis of plates in bending", Proc. Conf. Matrix Methods in
           Structural Mechanics; Alfeld, P. (1984), "A trivariate Clough-Tocher
           scheme for tetrahedral data", Computer Aided Geometric Design 1(2).

**Why this exists next to `idw.py`.** IDW is a weighted mean, so every estimate
is pulled toward the local average: it flattens a gradient and it cannot
reproduce a value it never saw. On samples that sit on a lattice — which is
what a modelled section or a resampled survey usually is — that shows up as the
mottled "bullseye" texture around each sample, and measurably: on
`vp_500_m.csv` the held-out RMSE is 0.0766 km/s for IDW against 0.0411 for
Clough-Tocher, better by a factor of 1.9
(`docs/validation/V-M5_7-interpolation.md`).

That is one file. Across the project's four sample tables each of the three
methods wins somewhere, and the geometry of the samples does not predict which
— two regular lattices have two different winners. So neither method is the
right default, the operator chooses, and `grid.cross_validate` measures rather
than any of this being hard-coded.

**Outside the convex hull the answer is NaN**, not the nearest sample. The
triangulation is only defined where the samples enclose the cell; beyond it
there is no survey, and the same rule `idw.py` states about its radius applies
here for the same reason.

**Clough-Tocher may leave the samples' interval**, because a C1 surface has to
bend to meet its neighbours' derivatives and a cubic can overshoot at a sharp
step. That is a property of the method, not a defect, and `ADR-MSP-007` records
the decision not to clamp it: a clamped cubic is neither the method nor
reproducible against QGIS. It is measured and reported instead — `statistics`
returns `overshoot`, and the manifest carries it.

**No Python loop over cells or over samples.** SciPy's Qhull triangulation and
its interpolators are C; the whole block is one call.
"""
from __future__ import annotations

import numpy as np

#: The methods this module implements, as the operator and the manifest name
#: them. `cubic` is Clough-Tocher, which is what QGIS calls "Clough-Toucher".
METHODS = ("linear", "cubic")


class TriangulationFailed(ValueError):
    """The samples cannot be triangulated, and the message says why."""


def build(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    *,
    method: str = "linear",
):
    """A callable surface fitted to the samples.

    x, y, values  the samples, in the grid's CRS; non-finite ones are dropped
    method        `linear` or `cubic`
    returns       f(cell_x, cell_y) -> (n,) float64, NaN outside the hull
    raises        TriangulationFailed when the samples cannot make triangles

    Built once and called per block: the triangulation costs O(n log n) and
    rebuilding it for every band of rows would pay that once per block.
    """
    from scipy.interpolate import CloughTocher2DInterpolator, LinearNDInterpolator
    from scipy.spatial import QhullError

    if method not in METHODS:
        raise TriangulationFailed(
            f"unknown method {method!r}; this module implements "
            f"{' and '.join(METHODS)}."
        )

    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    values = np.asarray(values, dtype=np.float64).ravel()
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    x, y, values = x[keep], y[keep], values[keep]

    # Three points make one triangle; two make none. Said here rather than
    # letting Qhull answer it in its own vocabulary.
    if x.size < 3:
        raise TriangulationFailed(
            f"a triangulation needs at least 3 samples with a finite "
            f"coordinate and value; got {x.size}."
        )

    points = np.column_stack([x, y])
    interpolator = (
        LinearNDInterpolator if method == "linear"
        else CloughTocher2DInterpolator
    )
    try:
        surface = interpolator(points, values)
    except QhullError as failure:
        # Collinear samples — a single survey line — have no area to
        # triangulate. The person can act on that; a Qhull traceback is not
        # something anyone can act on.
        raise TriangulationFailed(
            f"the {x.size} samples cannot be triangulated: they are collinear "
            f"or coincident, so they enclose no area. A triangulated method "
            f"needs samples spread in two dimensions; for a single line of "
            f"samples use grid.idw."
        ) from failure

    def evaluate(cell_x: np.ndarray, cell_y: np.ndarray) -> np.ndarray:
        return np.asarray(
            surface(np.column_stack([np.asarray(cell_x, dtype=np.float64).ravel(),
                                     np.asarray(cell_y, dtype=np.float64).ravel()])),
            dtype=np.float64,
        )

    evaluate.sample_interval = (  # type: ignore[attr-defined]
        float(values.min()), float(values.max()))
    evaluate.samples = int(x.size)  # type: ignore[attr-defined]
    return evaluate


def interpolate(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    cell_x: np.ndarray,
    cell_y: np.ndarray,
    *,
    method: str = "linear",
    max_distance: float | None = None,
) -> np.ndarray:
    """Estimate the field at a set of cell centres. One shot, one block.

    max_distance  cells farther than this from every sample stay null. Absent,
                  the convex hull is the only limit, which is what QGIS does.
                  Present, it keeps a wide empty triangle from being filled
                  across a gap nobody surveyed.
    returns       (n,) float32, NaN where the cell was not estimated
    """
    surface = build(x, y, values, method=method)
    out = surface(cell_x, cell_y)
    if max_distance is not None:
        out = np.where(
            distance_to_nearest(x, y, cell_x, cell_y) <= float(max_distance),
            out, np.nan)
    return out.astype(np.float32)


def distance_to_nearest(x, y, cell_x, cell_y) -> np.ndarray:  # noqa: ANN001
    """How far each cell centre is from the closest sample. One tree query."""
    from scipy.spatial import cKDTree

    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    keep = np.isfinite(x) & np.isfinite(y)
    tree = cKDTree(np.column_stack([x[keep], y[keep]]))
    distances, _ = tree.query(
        np.column_stack([np.asarray(cell_x, dtype=np.float64).ravel(),
                         np.asarray(cell_y, dtype=np.float64).ravel()]), k=1)
    return distances


def statistics(
    values: np.ndarray, sample_interval: tuple[float, float] | None = None
) -> dict[str, float | int | None]:
    """What the manifest records about the field that came out.

    sample_interval  (min, max) of the samples. Given, the result reports how
                     far outside it the surface went — zero for `linear`, and
                     for `cubic` the number a reader needs in order to know
                     whether the overshoot mattered (ADR-MSP-007).
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"valid": 0, "valid_fraction": 0.0,
                "min": None, "max": None, "mean": None, "overshoot": None}
    summary: dict[str, float | int | None] = {
        "valid": int(finite.size),
        "valid_fraction": float(finite.size / values.size),
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean(dtype=np.float64)),
    }
    if sample_interval is None:
        summary["overshoot"] = None
        return summary
    low, high = float(sample_interval[0]), float(sample_interval[1])
    below = float(max(0.0, low - finite.min()))
    above = float(max(0.0, finite.max() - high))
    span = high - low
    summary["overshoot"] = {
        "sample_min": low,
        "sample_max": high,
        "below": below,
        "above": above,
        "fraction_of_range": (float((below + above) / span) if span > 0
                              else 0.0),
    }
    return summary
