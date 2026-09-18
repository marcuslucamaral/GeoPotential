"""Vector silhouettes to RGBA, in numpy. No Qt, no I/O.

A shapefile has to be *visible* before anyone can decide whether it is the
right file, and until now it was the one thing the canvas could not draw: a
raster arrived as a windowed read, a table as a point cloud, and a vector as
nothing at all. This draws the outline the worker sampled under ADR-MSP-004 —
a silhouette, bounded and declared, never the data.

**No per-vertex and no per-pixel Python loop.** The only Python-level
iteration is over *parts*, which ADR-MSP-004 caps at 500; every segment is
rasterised at once by one `repeat`/`arange` construction, and the stroke's
thickness is applied as at most `(2t+1)^2` whole-array writes. A loop over
2 000 vertices in a draw path is the defect ADR-007 measures at 90-169x.
"""
from __future__ import annotations

import numpy as np

from .colormap import lookup_table

#: The most samples the rasteriser will place in one call. A segment never
#: needs more samples than the pixels it crosses, so this is only reached by a
#: pathological preview; when it is, the density is scaled down uniformly
#: rather than dropping the far end of the geometry.
MAX_SAMPLES = 1_000_000

#: The stroke's colour is taken from this position along the layer's ramp.
#: Three quarters up reads on both a pale and a dark ground, which the ramp's
#: own extremes do not.
STROKE_STOP = 0.75


def stroke_colour(colormap: str, invert: bool = False) -> np.ndarray:
    """The colour a silhouette is drawn in, taken from the layer's ramp.

    inputs   the ramp's name and whether it is reversed
    output   (3,) uint8 RGB

    A vector preview carries no per-vertex value, so there is nothing to map
    through a ramp. Taking one colour *from* the ramp keeps the layer panel's
    colormap control meaningful for a vector layer instead of leaving it inert.
    """
    table = lookup_table(colormap, invert=invert)
    return table[int(round(STROKE_STOP * (table.shape[0] - 1)))]


def _flatten(parts) -> tuple[np.ndarray, np.ndarray] | None:  # noqa: ANN001
    """All vertices in one array, plus the index of each segment's first.

    inputs   [[[x, y], …], …] — one list of coordinates per ring or line
    output   (vertices (v, 2) float64, segment starts (s,) int64), or None

    The segment starts are every vertex index except the last of each part, so
    no segment ever joins the end of one ring to the start of the next.
    """
    arrays = []
    for part in parts or []:
        array = np.asarray(part, dtype=np.float64)
        if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] >= 2:
            arrays.append(array[:, :2])
    if not arrays:
        return None
    counts = np.array([a.shape[0] for a in arrays], dtype=np.int64)
    vertices = np.concatenate(arrays, axis=0)
    keep = np.ones(vertices.shape[0], dtype=bool)
    keep[np.cumsum(counts) - 1] = False              # the last of each part
    starts = np.flatnonzero(keep)
    if starts.size == 0:
        return None
    return vertices, starts


def to_rgba(
    parts,  # noqa: ANN001
    *,
    width: int,
    height: int,
    extent: tuple[float, float, float, float],
    colormap: str = "viridis",
    invert: bool = False,
    opacity: float = 1.0,
    thickness: int = 1,
    outline: bool = False,
) -> np.ndarray:
    """Draw polylines into an (h, w, 4) uint8 RGBA buffer.

    parts     [[[x, y], …], …] in the same CRS as `extent`; one list per ring
              or line, as `io/preview.py:geometry` produces them
    width     buffer size in pixels
    height
    extent    (left, bottom, right, top) of the buffer, in map coordinates
    colormap  ramp the stroke's colour is taken from
    opacity   0..1, applied to drawn pixels only
    thickness stroke half-width in pixels; 0 draws single pixels
    outline   draw a pale halo under the stroke, so a dark silhouette stays
              visible on a dark ground
    returns   (h, w, 4) uint8, C-contiguous, transparent where nothing is drawn

    Vertices outside the extent are dropped after rasterisation, not clamped:
    clamping would fold a survey's outlying features onto the edge and draw a
    boundary that is not in the file.
    """
    buffer = np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    flat = _flatten(parts)
    if flat is None:
        return buffer
    vertices, starts = flat

    left, bottom, right, top = extent
    span_x = right - left
    span_y = top - bottom
    if span_x <= 0 or span_y <= 0:
        return buffer

    # Map to screen. y grows downwards, so north is up.
    sx = (vertices[:, 0] - left) / span_x * (width - 1)
    sy = (top - vertices[:, 1]) / span_y * (height - 1)

    x0, y0 = sx[starts], sy[starts]
    x1, y1 = sx[starts + 1], sy[starts + 1]
    dx, dy = x1 - x0, y1 - y0

    finite = np.isfinite(x0) & np.isfinite(y0) & np.isfinite(x1) & np.isfinite(y1)
    if not finite.any():
        return buffer
    x0, y0, dx, dy = x0[finite], y0[finite], dx[finite], dy[finite]

    # One sample per pixel the segment crosses. No segment needs more than the
    # buffer's diagonal, whatever its length in map units.
    diagonal = int(np.ceil(np.hypot(width, height))) + 1
    steps = np.maximum(np.abs(dx), np.abs(dy))
    counts = np.clip(np.ceil(steps), 1, diagonal).astype(np.int64) + 1

    total = int(counts.sum())
    if total > MAX_SAMPLES:
        # Thin every segment by the same factor. Dropping whole segments
        # instead would erase one end of the geometry and keep the other.
        scale = MAX_SAMPLES / total
        counts = np.maximum(2, (counts * scale).astype(np.int64))
        total = int(counts.sum())

    # The whole rasterisation, without a loop over segments: `repeat` expands
    # each segment into its own samples, and `k` is the position within each.
    segment = np.repeat(np.arange(counts.size), counts)
    offsets = np.concatenate(([0], np.cumsum(counts)[:-1]))
    k = np.arange(total, dtype=np.float64) - np.repeat(offsets, counts)
    t = k / np.maximum(1.0, np.repeat(counts, counts) - 1.0)

    columns = np.rint(x0[segment] + t * dx[segment]).astype(np.int64)
    rows = np.rint(y0[segment] + t * dy[segment]).astype(np.int64)

    inside = (
        (columns >= 0) & (columns < width) & (rows >= 0) & (rows < height)
    )
    if not inside.any():
        return buffer
    columns, rows = columns[inside], rows[inside]

    colour = stroke_colour(colormap, invert)
    alpha = np.uint8(round(max(0.0, min(1.0, opacity)) * 255))
    radius = max(0, int(thickness))

    if outline:
        halo = np.array([245, 245, 245], dtype=np.uint8)
        for dr, dc in _footprint(radius + 1):
            rr, cc = rows + dr, columns + dc
            keep = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < width)
            buffer[rr[keep], cc[keep], :3] = halo
            buffer[rr[keep], cc[keep], 3] = alpha

    for dr, dc in _footprint(radius):
        rr, cc = rows + dr, columns + dc
        keep = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < width)
        buffer[rr[keep], cc[keep], :3] = colour
        buffer[rr[keep], cc[keep], 3] = alpha

    return np.ascontiguousarray(buffer)


def _footprint(radius: int) -> list[tuple[int, int]]:
    """The offsets a stroke of this half-width covers, as a filled disc."""
    if radius <= 0:
        return [(0, 0)]
    offsets = []
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dr * dr + dc * dc <= radius * radius:
                offsets.append((dr, dc))
    return offsets


def bounds(parts) -> tuple[float, float, float, float] | None:  # noqa: ANN001
    """The extent a set of parts occupies, or None when nothing is finite."""
    flat = _flatten(parts)
    if flat is None:
        return None
    vertices = flat[0]
    finite = np.isfinite(vertices[:, 0]) & np.isfinite(vertices[:, 1])
    if not finite.any():
        return None
    xs, ys = vertices[finite, 0], vertices[finite, 1]
    left, right = float(xs.min()), float(xs.max())
    bottom, top = float(ys.min()), float(ys.max())
    # A single vertical or horizontal line has no area. Give it one, so the
    # viewport has something to fit.
    if right - left <= 0:
        left, right = left - 1.0, right + 1.0
    if top - bottom <= 0:
        bottom, top = bottom - 1.0, top + 1.0
    return left, bottom, right, top
