"""A bounded, declared preview of what a file contains. ADR-MSP-004.

The Import Wizard has to show what a file holds *before* it enters the project:
the rows of a table, the shape of a point cloud, the outline of a vector. Those
are coordinates, and `P-63` forbids the description carrying arrays across the
IPC boundary — a shapefile with 50 000 vertices would turn a description into a
data transfer.

So a preview is three things at once:

- **bounded**, by a ceiling that lives here and not in the caller's good
  intentions;
- **decimated on purpose**, evenly across the file so the silhouette survives;
- **declared**, carrying `decimated` and the true count, so the screen can say
  it is showing a part.

And it is never an input. Nothing computes from a preview: the statistics, the
QA/QC verdict and every operator read the file itself.
"""
from __future__ import annotations

from typing import Any

import numpy as np

# The ceilings. They are numbers, in one place, and the contract test reads
# them from here rather than restating them.
MAX_POINTS = 5000        # a table's points
MAX_VERTICES = 2000      # a vector's coordinates, across all features
MAX_ROWS = 50            # rows of the table shown as a table
MAX_FEATURES = 500       # features whose geometry is sampled at all


def _stride(count: int, ceiling: int) -> int:
    """Take every nth element so the sample spans the whole file.

    Taking the first n instead would preview one corner of the survey and call
    it the survey.
    """
    return max(1, int(np.ceil(count / ceiling)))


def points(x: np.ndarray, y: np.ndarray, values: np.ndarray | None = None,
           *, ceiling: int = MAX_POINTS) -> dict[str, Any]:
    """A point cloud, thinned to the ceiling.

    inputs   x, y in the file's own coordinates; values in the file's own unit
    output   {'points': [[x, y, v], …], 'decimated': bool, 'source_rows': int}
    """
    finite = np.isfinite(x) & np.isfinite(y)
    total = int(finite.sum())
    xs, ys = x[finite], y[finite]
    vs = (values[finite] if values is not None and values.size == x.size
          else np.full(total, np.nan, dtype=np.float64))

    step = _stride(total, ceiling)
    xs, ys, vs = xs[::step], ys[::step], vs[::step]
    sample = np.column_stack([
        xs, ys, np.where(np.isfinite(vs), vs, np.nan)
    ]).astype(float)

    return {
        "points": [
            [float(px), float(py), (None if np.isnan(pv) else float(pv))]
            for px, py, pv in sample
        ],
        "decimated": step > 1,
        "source_rows": total,
        "shown": int(sample.shape[0]),
    }


def rows(frame, *, ceiling: int = MAX_ROWS) -> dict[str, Any]:
    """The first rows of a table, as strings, for a table view.

    inputs   a pandas DataFrame
    output   {'columns': [...], 'rows': [[...], …], 'truncated': bool,
              'source_rows': int}

    Strings, deliberately: this is shown, never computed with, and formatting a
    float here would invent a precision the file does not have.
    """
    head = frame.head(ceiling)
    return {
        "columns": [str(c) for c in frame.columns],
        "rows": [[("" if v is None else str(v)) for v in record]
                 for record in head.itertuples(index=False, name=None)],
        "truncated": bool(len(frame) > ceiling),
        "source_rows": int(len(frame)),
    }


def geometry(frame, *, ceiling: int = MAX_VERTICES,
             features: int = MAX_FEATURES) -> dict[str, Any]:
    """The outline of a vector layer, simplified to fit the ceiling.

    inputs   a GeoDataFrame
    output   {'parts': [[[x, y], …], …], 'decimated': bool,
              'source_features': int}

    A part is one ring or one line, in the layer's own CRS. Polygons give their
    exterior ring only: an interior ring is detail a silhouette does not carry,
    and the wizard's question is "is this the right file".
    """
    import shapely

    total = int(len(frame))
    step = _stride(total, features)
    sampled = frame.geometry.iloc[::step]

    parts: list[list[list[float]]] = []
    budget = ceiling
    decimated = step > 1
    for geom in sampled:
        if geom is None or geom.is_empty or budget <= 0:
            continue
        for piece in getattr(geom, "geoms", [geom]):
            coords = _outline(piece, shapely)
            if coords is None or len(coords) < 2:
                continue
            if len(coords) > budget:
                keep = _stride(len(coords), max(2, budget))
                coords = coords[::keep]
                decimated = True
            parts.append([[float(px), float(py)] for px, py in coords])
            budget -= len(coords)
            if budget <= 0:
                decimated = decimated or total > len(parts)
                break

    return {
        "parts": parts,
        "decimated": decimated,
        "source_features": total,
        "shown": len(parts),
    }


def _outline(geom, shapely) -> np.ndarray | None:  # noqa: ANN001
    """The coordinates that draw a geometry's silhouette."""
    if geom.geom_type == "Polygon":
        return np.asarray(geom.exterior.coords)
    if geom.geom_type in ("LineString", "LinearRing"):
        return np.asarray(geom.coords)
    if geom.geom_type == "Point":
        return np.asarray([geom.coords[0], geom.coords[0]])
    return None
