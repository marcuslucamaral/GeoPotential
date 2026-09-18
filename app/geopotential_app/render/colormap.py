"""Colormaps and raster-to-RGBA, in numpy. No Qt, no I/O.

Rendering is pure array work so it can be gated without a window, and so a
per-pixel Python loop can never creep in unnoticed — that loop costs a measured
90x (`../docs/validation/PERF-backend.md`, ADR-007).

Colormap choice carries domain meaning:
  - sequential for non-negative magnitude, distance and membership
  - diverging, centred on zero, for a signed field (Bouguer anomaly, residuals)
  - categorical for classes and masks
`RdBu` under a [0, 1] suitability map implies a midpoint that does not exist.
"""
from __future__ import annotations

import numpy as np

# Control points as (position, R, G, B), 0-255. Kept short and explicit rather
# than pulled from matplotlib: `render/` may not import a plotting library.
_RAMPS: dict[str, tuple[tuple[float, int, int, int], ...]] = {
    # perceptually ordered, dark low to bright high; for membership and magnitude
    "viridis": (
        (0.00, 68, 1, 84), (0.25, 59, 82, 139), (0.50, 33, 145, 140),
        (0.75, 94, 201, 98), (1.00, 253, 231, 37),
    ),
    # for distance: near is dark, far is pale
    "magma": (
        (0.00, 0, 0, 4), (0.25, 81, 18, 124), (0.50, 183, 55, 121),
        (0.75, 252, 137, 97), (1.00, 252, 253, 191),
    ),
    # diverging, white at the midpoint; only for a signed field
    "rdbu": (
        (0.00, 5, 48, 97), (0.25, 67, 147, 195), (0.50, 247, 247, 247),
        (0.75, 214, 96, 77), (1.00, 103, 0, 31),
    ),
    # same family as viridis, warmer; for a second layer that must read as a
    # different quantity at a glance
    "plasma": (
        (0.00, 13, 8, 135), (0.25, 126, 3, 168), (0.50, 204, 71, 120),
        (0.75, 248, 149, 64), (1.00, 240, 249, 33),
    ),
    "inferno": (
        (0.00, 0, 0, 4), (0.25, 87, 16, 110), (0.50, 188, 55, 84),
        (0.75, 249, 142, 9), (1.00, 252, 255, 164),
    ),
    # colour-vision-safe throughout; the safe default when a map is printed or
    # read by someone with a colour deficiency
    "cividis": (
        (0.00, 0, 32, 76), (0.25, 61, 76, 107), (0.50, 124, 123, 120),
        (0.75, 188, 175, 111), (1.00, 255, 233, 69),
    ),
    # high contrast, poor perceptual order: for spotting structure, never for
    # reading a magnitude off the colour
    "turbo": (
        (0.00, 48, 18, 59), (0.20, 70, 134, 251), (0.40, 27, 229, 181),
        (0.60, 164, 252, 60), (0.80, 251, 133, 42), (1.00, 122, 4, 3),
    ),
    "grey": ((0.00, 0, 0, 0), (1.00, 255, 255, 255)),
}

SEQUENTIAL = ("viridis", "magma", "plasma", "inferno", "cividis", "turbo", "grey")
DIVERGING = ("rdbu",)

# The order the layer panel offers them in. Sequential first, because a
# suitability map in [0,1] has no midpoint and a diverging ramp under it would
# imply one.
AVAILABLE = SEQUENTIAL + DIVERGING


def names() -> tuple[str, ...]:
    """Every ramp, in the order the interface offers them."""
    return AVAILABLE


def lookup_table(name: str, size: int | None = None, *,
                 invert: bool = False) -> np.ndarray:
    """Build a (size, 3) uint8 table by interpolating the ramp's control points.

    name     one of `_RAMPS`
    size     entries; 257 for a diverging ramp, 256 otherwise, when absent
    invert   reverse the ramp; the entry count and the centre are unchanged, so
             an inverted diverging ramp still puts zero on its middle entry
    returns  uint8 RGB table
    raises   KeyError naming the available ramps

    A diverging ramp gets an odd size on purpose. With 256 entries the centre
    falls at index 127.5, so zero has no entry of its own and the two halves
    differ in length by one — the midpoint of a Bouguer anomaly map would sit
    half a step off centre, and equal departures either side would not get
    equal colours.
    """
    if name not in _RAMPS:
        raise KeyError(f"unknown colormap {name!r}; available: {', '.join(sorted(_RAMPS))}")
    if size is None:
        size = 257 if name in DIVERGING else 256
    stops = _RAMPS[name]
    positions = np.array([s[0] for s in stops], dtype=np.float64)
    channels = np.array([s[1:] for s in stops], dtype=np.float64)
    x = np.linspace(0.0, 1.0, size)
    table = np.empty((size, 3), dtype=np.uint8)
    for c in range(3):
        table[:, c] = np.interp(x, positions, channels[:, c]).round().astype(np.uint8)
    return table[::-1].copy() if invert else table


def default_colormap(values: np.ndarray) -> str:
    """Pick a ramp from the data's sign, not from taste.

    values   the field to be shown
    returns  'rdbu' when the field spans zero in both directions, else 'viridis'

    A signed field gets a diverging ramp centred on zero; everything else gets
    a sequential one.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return "viridis"
    return "rdbu" if finite.min() < 0.0 < finite.max() else "viridis"


def to_rgba(
    values: np.ndarray,
    *,
    colormap: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    invert: bool = False,
    opacity: float = 1.0,
    nodata_transparent: bool = True,
) -> np.ndarray:
    """Map a float field to (h, w, 4) uint8 RGBA.

    values             (h, w) float array; NaN is the null
    colormap           ramp name; chosen from the data's sign if absent
    vmin, vmax         stretch limits in the value's own unit; the finite
                       min/max if absent
    invert             reverse the ramp; display only, like the ramp itself
    opacity            0..1, applied to valid pixels only
    nodata_transparent nulls get alpha 0; never the low end of the ramp
    returns            (h, w, 4) uint8, C-contiguous

    Nodata renders as nodata. Painting a null as the ramp's low colour states a
    measurement that was never made.
    """
    values = np.asarray(values, dtype=np.float32)
    valid = np.isfinite(values)
    name = colormap or default_colormap(values)

    if valid.any():
        finite = values[valid]
        lo = float(finite.min()) if vmin is None else float(vmin)
        hi = float(finite.max()) if vmax is None else float(vmax)
    else:
        lo, hi = 0.0, 1.0

    if name in DIVERGING:
        # A diverging ramp is only honest when its midpoint is zero.
        bound = max(abs(lo), abs(hi)) or 1.0
        lo, hi = -bound, bound

    span = hi - lo
    scaled = np.zeros(values.shape, dtype=np.float32)
    if span > 0:
        np.subtract(values, lo, out=scaled, where=valid)
        np.divide(scaled, span, out=scaled, where=valid)
    np.clip(scaled, 0.0, 1.0, out=scaled)

    table = lookup_table(name, invert=invert)
    # Nearest entry, not truncation. Truncating puts the midpoint of a
    # diverging ramp one step off centre, which is exactly the entry a
    # zero-valued pixel must land on.
    indices = np.rint(scaled * (table.shape[0] - 1)).astype(np.uint16)
    rgba = np.empty(values.shape + (4,), dtype=np.uint8)
    rgba[..., :3] = table[indices]
    alpha = np.uint8(round(max(0.0, min(1.0, opacity)) * 255))
    rgba[..., 3] = np.where(valid, alpha, 0) if nodata_transparent else alpha
    if not nodata_transparent:
        rgba[..., :3][~valid] = 0
    return np.ascontiguousarray(rgba)


def stretch_limits(
    values: np.ndarray, percentiles: tuple[float, float] = (2.0, 98.0)
) -> tuple[float, float]:
    """Display stretch from percentiles of the valid pixels.

    Display-only. Changing it repaints; it never rewrites a value.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(finite, percentiles)
    return (float(lo), float(hi)) if hi > lo else (float(finite.min()), float(finite.max()))
