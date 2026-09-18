"""Fuzzy membership functions.

Every function returns values in [0, 1] on valid pixels and NaN on invalid
pixels. Both properties are tested, on every function.

Zadeh (1965), Information and Control 8(3), sec. 2 for the membership notion;
the Small/Large forms follow the ESRI/Zimmermann parameterization used
throughout the MCDA literature.

The maths is the legacy tree's `core/fuzzy.py`, which is clean: pure numpy, no
I/O, no Qt, formula in the docstring. What is new here is that a degenerate
range no longer silently returns 0.5 — see `DEGENERATE_RANGE_POLICY`.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12

# A range narrower than this is degenerate: every pixel carries the same value,
# so no ordering exists to map onto [0, 1]. The legacy tree returned 0.5
# everywhere and said nothing. That is a scientific decision, so it is made
# explicitly and recorded: the operator refuses, and the caller decides.
DEGENERATE_RANGE_POLICY = "refuse"


class DegenerateRangeError(ValueError):
    """The value range is too narrow to define a membership over."""


def _finite(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out = values.astype(np.float32, copy=True)
    return out, np.isfinite(out)


def _bounds(
    vals: np.ndarray,
    x_min: float | None,
    x_max: float | None,
    clamp_percentiles: tuple[float, float] | None,
    name: str,
) -> tuple[float, float]:
    """Resolve the low and high anchors, from arguments or from the data.

    Percentile clamping changes the result. A map made with [2, 98] is not the
    map made with the full range, so the percentiles used are returned to the
    caller for the manifest.
    """
    if clamp_percentiles is not None:
        p_lo, p_hi = clamp_percentiles
        lo = float(np.percentile(vals, p_lo)) if x_min is None else float(x_min)
        hi = float(np.percentile(vals, p_hi)) if x_max is None else float(x_max)
    else:
        lo = float(vals.min()) if x_min is None else float(x_min)
        hi = float(vals.max()) if x_max is None else float(x_max)
    if hi - lo < EPS:
        raise DegenerateRangeError(
            f"{name}: the value range [{lo:.6g}, {hi:.6g}] is degenerate; "
            f"no membership is defined over it. Give explicit x_min/x_max, or "
            f"drop the criterion."
        )
    return lo, hi


def linear_increasing(
    values: np.ndarray,
    x_min: float | None = None,
    x_max: float | None = None,
    clamp_percentiles: tuple[float, float] | None = None,
) -> np.ndarray:
    """Membership rising linearly with the value.

    values             raw field, any unit; NaN is the null
    x_min, x_max       anchors in the same unit; taken from the data if absent
    clamp_percentiles  (p_lo, p_hi) to take the anchors from instead
    returns            float32 membership in [0, 1], NaN where values were NaN

    mu = 0 for x <= x_min; (x - x_min)/(x_max - x_min) between; 1 for x >= x_max.
    """
    out, mask = _finite(values)
    if not mask.any():
        return out
    lo, hi = _bounds(out[mask], x_min, x_max, clamp_percentiles, "linear_increasing")
    out[mask] = np.clip((out[mask] - lo) / (hi - lo), 0.0, 1.0)
    return out


def linear_decreasing(
    values: np.ndarray,
    x_min: float | None = None,
    x_max: float | None = None,
    clamp_percentiles: tuple[float, float] | None = None,
) -> np.ndarray:
    """Membership falling linearly with the value.

    values             raw field, any unit; NaN is the null
    x_min, x_max       anchors in the same unit; taken from the data if absent
    clamp_percentiles  (p_lo, p_hi) to take the anchors from instead
    returns            float32 membership in [0, 1], NaN where values were NaN

    mu = 1 for x <= x_min; (x_max - x)/(x_max - x_min) between; 0 for x >= x_max.
    This is the form a distance-to-structure criterion takes: near is good.
    """
    out, mask = _finite(values)
    if not mask.any():
        return out
    lo, hi = _bounds(out[mask], x_min, x_max, clamp_percentiles, "linear_decreasing")
    out[mask] = np.clip((hi - out[mask]) / (hi - lo), 0.0, 1.0)
    return out


def sigmoidal(
    values: np.ndarray,
    center: float | None = None,
    slope: float = 1.0,
    direction: str = "increasing",
) -> np.ndarray:
    """Logistic membership, a smooth S between 0 and 1.

    values     raw field, any unit; NaN is the null
    center     inflection point in the value's unit; the median if absent
    slope      steepness, per unit of `values`
    direction  'increasing' or 'decreasing'
    returns    float32 membership in [0, 1], NaN where values were NaN

    mu = 1 / (1 + exp(-slope * (x - center))).
    """
    if direction not in ("increasing", "decreasing"):
        raise ValueError(
            f"direction must be 'increasing' or 'decreasing', got {direction!r}"
        )
    out, mask = _finite(values)
    if not mask.any():
        return out
    c = float(np.median(out[mask])) if center is None else float(center)
    s = float(slope) if direction == "increasing" else -float(slope)
    # exp overflows past ~709; clipping the exponent leaves the result exact
    # to float32 well before the clip bites.
    z = np.clip(s * (out[mask] - c), -60.0, 60.0)
    out[mask] = np.clip(1.0 / (1.0 + np.exp(-z)), 0.0, 1.0)
    return out


def gaussian(
    values: np.ndarray,
    mean: float | None = None,
    std: float | None = None,
) -> np.ndarray:
    """Membership peaking at an optimum and falling off both ways.

    values   raw field, any unit; NaN is the null
    mean     the optimum, in the value's unit; the sample mean if absent
    std      the spread, in the value's unit; the sample std if absent
    returns  float32 membership in [0, 1], NaN where values were NaN

    mu = exp(-(x - mean)^2 / (2 std^2)). Use where a mid-range value is the
    favourable one, not where more or less is simply better.
    """
    out, mask = _finite(values)
    if not mask.any():
        return out
    vals = out[mask]
    m = float(vals.mean()) if mean is None else float(mean)
    s = float(vals.std()) if std is None else float(std)
    if s < EPS:
        raise DegenerateRangeError(
            f"gaussian: std is {s:.3g}; a Gaussian membership needs a spread. "
            f"Give an explicit std, or drop the criterion."
        )
    out[mask] = np.clip(np.exp(-0.5 * ((vals - m) / s) ** 2), 0.0, 1.0)
    return out


def small(values: np.ndarray, midpoint: float, spread: float = 5.0) -> np.ndarray:
    """Membership favouring small values, asymptotic at both ends.

    values    raw field, any unit; NaN is the null
    midpoint  value receiving membership 0.5, in the value's unit
    spread    shape exponent; larger is a sharper transition
    returns   float32 membership in [0, 1], NaN where values were NaN

    mu = 1 / (1 + (x / midpoint)^spread). Defined for x >= 0.
    """
    if midpoint <= 0:
        raise ValueError(f"small: midpoint must be positive, got {midpoint}")
    out, mask = _finite(values)
    if not mask.any():
        return out
    x = np.maximum(out[mask], 0.0)
    out[mask] = np.clip(1.0 / (1.0 + (x / midpoint) ** spread), 0.0, 1.0)
    return out


def large(values: np.ndarray, midpoint: float, spread: float = 5.0) -> np.ndarray:
    """Membership favouring large values, asymptotic at both ends.

    values    raw field, any unit; NaN is the null
    midpoint  value receiving membership 0.5, in the value's unit
    spread    shape exponent; larger is a sharper transition
    returns   float32 membership in [0, 1], NaN where values were NaN

    mu = 1 / (1 + (x / midpoint)^-spread). Defined for x >= 0.
    """
    if midpoint <= 0:
        raise ValueError(f"large: midpoint must be positive, got {midpoint}")
    out, mask = _finite(values)
    if not mask.any():
        return out
    x = np.maximum(out[mask], EPS)
    out[mask] = np.clip(1.0 / (1.0 + (x / midpoint) ** (-spread)), 0.0, 1.0)
    return out


def categorical(values: np.ndarray, mapping: dict[float, float]) -> np.ndarray:
    """Membership from a class code to a declared score.

    values   raster of class codes; NaN is the null
    mapping  {class code: membership in [0, 1]}; every code must be listed
    returns  float32 membership in [0, 1], NaN where values were NaN
    raises   ValueError naming any code present in the data but not in mapping

    Refusing an unmapped class is deliberate: silently scoring it zero turns a
    data gap into a scientific claim.
    """
    for code, score in mapping.items():
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"categorical: class {code} maps to {score}, outside [0, 1]")
    out, mask = _finite(values)
    if not mask.any():
        return out
    present = set(np.unique(out[mask]).tolist())
    unmapped = sorted(present - set(float(c) for c in mapping))
    if unmapped:
        raise ValueError(
            "categorical: classes present in the data but not mapped: "
            + ", ".join(f"{c:g}" for c in unmapped)
        )
    result = np.full(out[mask].shape, np.nan, dtype=np.float32)
    for code, score in mapping.items():
        result[out[mask] == float(code)] = np.float32(score)
    out[mask] = result
    return out


def circular(values: np.ndarray, preferred: float,
             spread: float = 90.0) -> np.ndarray:
    """Membership for a **direction**. Aspect, strike, flow azimuth.

    values     azimuths in degrees; NaN is the null
    preferred  the direction receiving membership 1
    spread     angular distance, in degrees, receiving membership 0.5;
               must be in (0, 180]
    returns    float32 in [0, 1], NaN where values were NaN
    reference  the raised-cosine on angular distance; the same construction
               used for circular kernels in directional statistics —
               Mardia & Jupp (2000), Directional Statistics, section 3.5.

    **Why a direction cannot use a linear membership.** 359 degrees and 1
    degree are two degrees apart, and every function in this module would put
    them at opposite ends of the range. On an aspect raster that is not a
    rounding error: it says a north-facing slope is the opposite of a
    north-facing slope.

    The angular distance is taken the short way round, so it is never more
    than 180 degrees, and the membership falls from 1 at `preferred` to 0 at
    `preferred + 180`.

    **A negative azimuth is refused, and not wrapped.** An azimuth is in
    [0, 360). A negative value is ambiguous: it may be an angle written the
    other way round, or a sentinel. Terrain tools code a **flat cell** as -1,
    and -1 is not an azimuth near zero — it is "this question does not apply
    here", and wrapping it to 359 would give a directionless cell nearly full
    membership on a north-preferring criterion. Wrapping silently would pick
    one reading and be wrong on the other, so the caller decides.
    """
    if not 0.0 < spread <= 180.0:
        raise ValueError(
            f"circular: spread={spread} is outside (0, 180]. It is an angular "
            f"distance in degrees, and beyond 180 there is no further to go."
        )
    out, mask = _finite(values)
    if not mask.any():
        return out

    present = out[mask]
    below = present[present < 0.0]
    if below.size:
        raise ValueError(
            f"circular: {below.size} cell(s) carry a negative azimuth "
            f"(minimum {float(below.min()):g}). An azimuth is in [0, 360), and "
            f"a negative one is ambiguous — it is either an angle someone "
            f"wrote the other way round, or a sentinel. Terrain tools write "
            f"-1 for a **flat cell**, which has no aspect at all and is not an "
            f"azimuth near zero: passing it through would give it nearly full "
            f"membership on a north-preferring criterion. Wrap a genuine angle "
            f"into [0, 360) yourself, or set the sentinel to the raster's "
            f"nodata so it stays null. Guessing which one it is here is not "
            f"this function's decision to make."
        )

    # The short way round: never more than 180 degrees.
    delta = np.abs((present - float(preferred) + 180.0) % 360.0 - 180.0)
    # Raised cosine, scaled so `spread` is the half-membership distance.
    scaled = np.minimum(delta / float(spread), 2.0)
    out[mask] = (0.5 * (1.0 + np.cos(np.pi * scaled / 2.0))).astype(np.float32)
    return out


#: The membership family exposed to the operator registry. Every default is
#: documented, editable, visible and versioned (section 16).
FAMILY = {
    "linear_increasing": linear_increasing,
    "linear_decreasing": linear_decreasing,
    "sigmoidal": sigmoidal,
    "gaussian": gaussian,
    "small": small,
    "large": large,
    "categorical": categorical,
    "circular": circular,
}
