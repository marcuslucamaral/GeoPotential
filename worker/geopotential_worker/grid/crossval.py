"""Which interpolator fits *these* samples. Measured, not preferred.

inputs   the samples, and the parameters each method would run with
output   per method: RMSE, MAE, coverage — in the samples' own unit
reference  Stone, M. (1974), "Cross-validatory choice and assessment of
           statistical predictions", J. R. Stat. Soc. B 36(2), 111-147.

k-fold: the samples are split into `folds` groups, each group is held out in
turn, the remaining ones fit the surface, and the surface predicts the points
it never saw. The error is then over every sample, each predicted once.

**No method is right in general.** Across the project's four sample tables
each of the three wins somewhere: Clough-Tocher on `vp_500_m.csv` (0.0411
against IDW's 0.0766), IDW on `density_modified_500m.csv`, and the linear
triangulation on `anomaly_bouger...csv`. The first two are both regular
lattices, so not even the sampling geometry predicts the winner. A default
chosen once, in code, would be wrong most of the time; this is why
`GriddingDialog` offers to measure first.

**The comparison is on the samples every method predicted.** IDW's search
radius leaves a held-out point null where the triangulated methods, bounded
only by the convex hull, still answer. Scoring each method on its own subset
would reward the one that answered least — the easiest points are the ones
with the most neighbours. So `rmse` is over the common subset and `coverage`
reports separately what each method could answer at all. Both are needed: a
method that wins on 60 % of the points has not won.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import idw as idw_grid
from . import triangulated as tin_grid

#: The split is seeded, so the same samples give the same verdict. A
#: recommendation that moves between two runs on one dataset is not a
#: measurement, and nobody could act on it.
SEED = 20260903


def _folds(n: int, folds: int, seed: int) -> list[np.ndarray]:
    order = np.random.default_rng(seed).permutation(n)
    return [order[i::folds] for i in range(folds)]


def _predict_idw(train, query, *, radius, power, min_points, max_points):  # noqa: ANN001
    xt, yt, vt = train
    xq, yq = query
    return idw_grid.interpolate(
        xt, yt, vt, xq, yq, radius=radius, power=power,
        min_points=min_points, max_points=max_points,
    ).astype(np.float64)


def _predict_tin(train, query, *, method, max_distance):  # noqa: ANN001
    xt, yt, vt = train
    xq, yq = query
    try:
        return tin_grid.interpolate(
            xt, yt, vt, xq, yq, method=method, max_distance=max_distance,
        ).astype(np.float64)
    except tin_grid.TriangulationFailed:
        # A fold that cannot be triangulated is not a score of infinity; it is
        # a method that does not apply to these samples, and it says so.
        return None


def compare(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    *,
    radius: float,
    power: float = 2.0,
    min_points: int = 1,
    max_points: int = 16,
    max_distance: float | None = None,
    folds: int = 5,
    max_samples: int = 20000,
    seed: int = SEED,
) -> dict[str, Any]:
    """Score every interpolation method on these samples.

    radius, power, min_points, max_points  what `grid.idw` would run with, so
        the comparison scores the run the person is about to make and not a
        textbook default
    max_distance  what a triangulated method would run with, same reason
    folds         k in k-fold; 5 holds out 20 % at a time
    max_samples   above this the samples are subsampled, seeded, because the
        comparison is a decision aid and must answer while the dialog is open
    returns  {"methods": [...], "recommended": name|None, "samples": n, ...}
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    values = np.asarray(values, dtype=np.float64).ravel()
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    x, y, values = x[keep], y[keep], values[keep]

    n = x.size
    if n < 12:
        return {
            "samples": int(n), "folds": 0, "methods": [], "recommended": None,
            "reason": (f"{n} usable samples is too few to hold any out; "
                       f"cross-validation needs at least 12."),
        }

    subsampled = False
    if n > max_samples:
        pick = np.random.default_rng(seed).choice(n, max_samples, replace=False)
        x, y, values, n, subsampled = x[pick], y[pick], values[pick], max_samples, True

    candidates = {
        "grid.idw": lambda tr, q: _predict_idw(
            tr, q, radius=radius, power=power,
            min_points=min_points, max_points=max_points),
        "grid.tin_linear": lambda tr, q: _predict_tin(
            tr, q, method="linear", max_distance=max_distance),
        "grid.tin_cubic": lambda tr, q: _predict_tin(
            tr, q, method="cubic", max_distance=max_distance),
    }

    predicted = {name: np.full(n, np.nan) for name in candidates}
    applies = {name: True for name in candidates}
    for hold in _folds(n, folds, seed):
        mask = np.zeros(n, dtype=bool)
        mask[hold] = True
        train = (x[~mask], y[~mask], values[~mask])
        query = (x[mask], y[mask])
        for name, predict in candidates.items():
            if not applies[name]:
                continue
            answer = predict(train, query)
            if answer is None:
                applies[name] = False
                continue
            predicted[name][mask] = answer

    usable = {name: np.isfinite(predicted[name])
              for name in candidates if applies[name]}
    if not usable:
        return {"samples": int(n), "folds": int(folds), "methods": [],
                "recommended": None,
                "reason": "no method could be fitted to these samples."}

    # Every method scored on the same points, so the scores can be compared.
    common = np.ones(n, dtype=bool)
    for mask in usable.values():
        common &= mask

    results = []
    for name in candidates:
        if not applies[name]:
            results.append({
                "method": name, "applies": False, "rmse": None, "mae": None,
                "coverage": 0.0,
                "note": "these samples cannot be triangulated",
            })
            continue
        mask = usable[name]
        row: dict[str, Any] = {
            "method": name,
            "applies": True,
            "coverage": float(mask.mean()),
            "predicted": int(mask.sum()),
        }
        if common.any():
            error = predicted[name][common] - values[common]
            row["rmse"] = float(np.sqrt(np.mean(error ** 2)))
            row["mae"] = float(np.mean(np.abs(error)))
        else:
            row["rmse"] = row["mae"] = None
        results.append(row)

    scored = [r for r in results if r["rmse"] is not None]
    best = min(scored, key=lambda r: r["rmse"])["method"] if scored else None
    return {
        "samples": int(n),
        "subsampled": subsampled,
        "folds": int(folds),
        "scored_on": int(common.sum()),
        "unit_note": "rmse and mae are in the samples' own unit",
        "methods": sorted(results, key=lambda r: (r["rmse"] is None, r["rmse"])),
        "recommended": best,
        "seed": int(seed),
    }
