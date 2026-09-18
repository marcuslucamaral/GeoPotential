"""Point clouds to RGBA, in numpy. No Qt, no I/O.

A table is a set of measurements at coordinates, and it has to be *visible*
before anyone can decide whether it is the right file. Drawing it is the same
kind of work as drawing a raster — values in, pixels out — so it lives beside
`colormap.py` and is gated the same way.

**No per-point Python loop.** Screen positions, colours and the marker's
footprint are all computed with array operations; a loop over 5 000 points on
every repaint is the defect ADR-007 measures at 90-169x, and it would be in a
draw path, which is the worst place for it.
"""
from __future__ import annotations

import numpy as np

from .colormap import lookup_table

# The shapes a point can be drawn as. They are masks over the marker's
# footprint, not images: a scatter of 5 000 markers is array work, and loading
# an icon per point would be a file read in a draw path.
CIRCLE = "circle"
SQUARE = "square"
TRIANGLE = "triangle"
DIAMOND = "diamond"
CROSS = "cross"
X = "x"
SYMBOLS = (CIRCLE, SQUARE, TRIANGLE, DIAMOND, CROSS, X)


def footprint(symbol: str, radius: int) -> list[tuple[int, int]]:
    """Which offsets from a point's centre the marker covers.

    inputs   the symbol's name and its half-size in pixels
    output   [(row offset, column offset), …]

    Computed once per repaint and applied to every point at once, so the cost
    is the shape's area and not the number of points.
    """
    if radius <= 0:
        return [(0, 0)]
    offsets: list[tuple[int, int]] = []
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if symbol == SQUARE:
                inside = True
            elif symbol == DIAMOND:
                inside = abs(dr) + abs(dc) <= radius
            elif symbol == TRIANGLE:
                # Apex up: the row's half-width grows towards the base.
                half = (dr + radius) / 2.0
                inside = dr >= -radius and abs(dc) <= half
            elif symbol == CROSS:
                inside = dr == 0 or dc == 0
            elif symbol == X:
                inside = abs(abs(dr) - abs(dc)) <= 0
            else:                                    # circle, and the default
                inside = dr * dr + dc * dc <= radius * radius
            if inside:
                offsets.append((dr, dc))
    return offsets


def to_rgba(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray | None,
    *,
    width: int,
    height: int,
    extent: tuple[float, float, float, float],
    colormap: str = "viridis",
    invert: bool = False,
    vmin: float | None = None,
    vmax: float | None = None,
    radius: int = 2,
    symbol: str = CIRCLE,
    outline: bool = False,
    opacity: float = 1.0,
) -> np.ndarray:
    """Draw points into an (h, w, 4) uint8 RGBA buffer.

    x, y      point coordinates, in the same CRS as `extent`
    values    what colours each point; NaN and absent both draw as the
              layer's neutral marker rather than as the ramp's low end
    width     buffer size in pixels
    height
    extent    (left, bottom, right, top) of the buffer, in map coordinates
    colormap  ramp name, resolved by `colormap.lookup_table`
    vmin/vmax colour limits in the value's own unit; the finite range if absent
    radius    marker half-size in pixels; 0 draws single pixels
    symbol    one of `SYMBOLS`: the marker's shape. Shape carries meaning on a
              map — two datasets on one screen are told apart by it before any
              colour is read
    outline   draw a pale ring under the marker, so a dark point stays visible
              on a dark ground — the ground is the viewer's choice, and a
              symbol that vanishes on it is a layer that reads as absent
    opacity   0..1, applied to drawn markers only
    returns   (h, w, 4) uint8, C-contiguous, transparent where nothing is drawn

    Points outside the extent are dropped, not clamped: clamping would pile a
    survey's outliers onto the edge of the picture and invent a cluster.
    """
    buffer = np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.size == 0 or x.size != y.size:
        return buffer

    left, bottom, right, top = extent
    span_x = right - left
    span_y = top - bottom
    if span_x <= 0 or span_y <= 0:
        return buffer

    finite = np.isfinite(x) & np.isfinite(y)
    # Screen coordinates: y grows downwards, so north is up.
    columns = ((x - left) / span_x * (width - 1)).round()
    rows = ((top - y) / span_y * (height - 1)).round()
    inside = (
        finite
        & (columns >= 0) & (columns < width)
        & (rows >= 0) & (rows < height)
    )
    if not inside.any():
        return buffer

    columns = columns[inside].astype(np.int64)
    rows = rows[inside].astype(np.int64)

    table = lookup_table(colormap, invert=invert)
    if values is not None and np.asarray(values).size == finite.size:
        v = np.asarray(values, dtype=np.float64).ravel()[inside]
        valid = np.isfinite(v)
        low = float(np.nanmin(v)) if vmin is None and valid.any() else (vmin or 0.0)
        high = float(np.nanmax(v)) if vmax is None and valid.any() else (vmax or 1.0)
        span = high - low
        scaled = np.zeros(v.shape, dtype=np.float64)
        if span > 0:
            np.subtract(v, low, out=scaled, where=valid)
            np.divide(scaled, span, out=scaled, where=valid)
        np.clip(scaled, 0.0, 1.0, out=scaled)
        indices = np.rint(scaled * (table.shape[0] - 1)).astype(np.int64)
        colours = table[indices]
        # A point with no value is not a point at the bottom of the ramp.
        colours[~valid] = np.array([160, 160, 160], dtype=np.uint8)
    else:
        colours = np.broadcast_to(
            np.array([160, 160, 160], dtype=np.uint8), (columns.size, 3)
        )

    alpha = np.uint8(round(max(0.0, min(1.0, opacity)) * 255))

    if outline and radius > 0:
        ring = np.array([235, 235, 235], dtype=np.uint8)
        for dr, dc in footprint(symbol, radius + 1):
            rr, cc = rows + dr, columns + dc
            keep = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < width)
            buffer[rr[keep], cc[keep], :3] = ring
            buffer[rr[keep], cc[keep], 3] = alpha

    # The marker's footprint: one vectorised write per offset, at most
    # (2r+1)^2 of them, instead of one Python iteration per point.
    for dr, dc in footprint(symbol, radius):
        rr = rows + dr
        cc = columns + dc
        keep = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < width)
        buffer[rr[keep], cc[keep], :3] = colours[keep]
        buffer[rr[keep], cc[keep], 3] = alpha

    return np.ascontiguousarray(buffer)


def bounds(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float] | None:
    """The extent a point cloud occupies, or None when nothing is finite."""
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return None
    xs, ys = x[finite], y[finite]
    left, right = float(xs.min()), float(xs.max())
    bottom, top = float(ys.min()), float(ys.max())
    # A single point, or a perfectly straight line of them, has no area. Give
    # it one, so the viewport has something to fit.
    if right - left <= 0:
        left, right = left - 1.0, right + 1.0
    if top - bottom <= 0:
        bottom, top = bottom - 1.0, top + 1.0
    return left, bottom, right, top
