"""Coordinates, for the screen only. ADR-MSP-003.

Showing a cursor position in degrees while the layer is in UTM needs a
transformation, and doing it in the worker would cost one JSON-Lines round trip
per mouse move. So it happens here, behind a named seam, under three rules the
architecture gate holds:

- **display only.** Nothing here reads a file, writes a file, registers an
  artefact or commits a run.
- **unreachable from the record.** `project/`, `commands/` and the job
  submission path may not import this module.
- **a stored value is never changed.** A layer read in UTM stays in UTM; only
  what is drawn and what is printed under the cursor move (ADR-006).

Reprojecting the *data* is a different act with a different price: it is a run,
it writes a file, and it carries a manifest. The interface names the three
things separately — declare a CRS, reproject the data, reproject the view — and
this module is only the third.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

# The formats a coordinate can be written in. `native` means the layer's own
# CRS, which is the only one that needs no transformation at all.
NATIVE = "native"
UTM = "utm"
DECIMAL = "decimal"
DMS = "dms"
FORMATS = (NATIVE, UTM, DECIMAL, DMS)

# What a geographic readout is expressed in. WGS 84 is the one CRS a reader can
# be assumed to know, and naming it beats implying it.
GEOGRAPHIC = "EPSG:4326"


class CrsUnknown(ValueError):
    """A CRS that pyproj cannot make sense of, named."""


@lru_cache(maxsize=64)
def _crs(name: str):  # noqa: ANN202 - pyproj type
    from pyproj import CRS

    try:
        return CRS.from_user_input(name)
    except Exception as exc:                        # noqa: BLE001
        raise CrsUnknown(f"{name!r} is not a CRS this build can read: {exc}") from exc


@lru_cache(maxsize=64)
def _transformer(source: str, target: str):  # noqa: ANN202 - pyproj type
    """A cached transformer. Building one costs milliseconds; the cursor moves
    hundreds of times a second."""
    from pyproj import Transformer

    return Transformer.from_crs(_crs(source), _crs(target), always_xy=True)


def canonical(crs: str) -> str:
    """A CRS written the way every library reads it.

    inputs   whatever the person typed: `26912`, `EPSG:26912`, a WKT
    output   `EPSG:<code>` when there is one, else the CRS's WKT
    raises   CrsUnknown, naming what could not be read

    pyproj accepts `26912`; rasterio does not, and the failure surfaces deep
    inside a warp as "The WKT could not be parsed". A declaration is normalised
    once, at the boundary, rather than in every place that consumes it.
    """
    if not crs:
        return ""
    obj = _crs(crs)
    code = obj.to_epsg()
    return f"EPSG:{code}" if code else obj.to_wkt()


def is_geographic(crs: str) -> bool:
    """Whether a CRS measures in degrees."""
    if not crs:
        return False
    try:
        return bool(_crs(crs).is_geographic)
    except CrsUnknown:
        return False


def linear_unit(crs: str) -> str:
    """The CRS's own linear unit, for labelling a distance or a pixel size."""
    if not crs:
        return ""
    try:
        axis = _crs(crs).axis_info
    except CrsUnknown:
        return ""
    return str(axis[0].unit_name) if axis else ""


def transform(x: float, y: float, source: str, target: str) -> tuple[float, float]:
    """One point, from one CRS to another. Display only.

    inputs   x, y in `source`
    output   the pair in `target`
    raises   CrsUnknown when either CRS cannot be read
    """
    if not source or not target or source == target:
        return float(x), float(y)
    tx, ty = _transformer(source, target).transform(float(x), float(y))
    return float(tx), float(ty)


def transform_arrays(
    x: np.ndarray, y: np.ndarray, source: str, target: str
) -> tuple[np.ndarray, np.ndarray]:
    """Many points at once, vectorised.

    A Python loop over a point cloud in a draw path is the defect ADR-007
    measures; pyproj transforms whole arrays in one call.
    """
    if not source or not target or source == target:
        return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    tx, ty = _transformer(source, target).transform(
        np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    )
    return np.asarray(tx, dtype=np.float64), np.asarray(ty, dtype=np.float64)


def transform_extent(
    extent: tuple[float, float, float, float], source: str, target: str
) -> tuple[float, float, float, float]:
    """A bounding box in another CRS.

    reference pyproj's `transform_bounds`, which densifies the edges: a
              rectangle in one projection is not a rectangle in another, and
              transforming four corners understates the box.
    """
    if not source or not target or source == target:
        return tuple(float(v) for v in extent)      # type: ignore[return-value]
    left, bottom, right, top = _transformer(source, target).transform_bounds(
        *[float(v) for v in extent], densify_pts=21
    )
    return float(left), float(bottom), float(right), float(top)


# ---- writing a coordinate down ------------------------------------------

def format_native(x: float, y: float, crs_unit: str) -> str:
    """The layer's own coordinates, at a precision that is not noise.

    Six decimals of a UTM metre is a micrometre, which no survey carries.
    """
    if crs_unit in ("degree", "degrees"):
        return f"{x:.6f}, {y:.6f}"
    return f"{x:,.1f}, {y:,.1f}"


def format_decimal(longitude: float, latitude: float) -> str:
    """Decimal degrees with hemispheres, so the sign is never the only clue."""
    ns = "N" if latitude >= 0 else "S"
    ew = "E" if longitude >= 0 else "W"
    return f"{abs(latitude):.6f}° {ns}, {abs(longitude):.6f}° {ew}"


def format_dms(longitude: float, latitude: float) -> str:
    """Degrees, minutes and seconds, with hemispheres."""
    return f"{_dms(latitude, 'N', 'S')}, {_dms(longitude, 'E', 'W')}"


def _dms(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    magnitude = abs(value)
    degrees = int(magnitude)
    minutes_full = (magnitude - degrees) * 60.0
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60.0
    # 59.999… seconds is 60, and 60 seconds is the next minute.
    if seconds >= 59.9995:
        seconds = 0.0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1
    return f"{degrees}° {minutes:02d}' {seconds:05.2f}\" {hemisphere}"


def format_utm(x: float, y: float, crs: str) -> str:
    """UTM easting and northing with the zone, when the CRS is a UTM one.

    A UTM pair without its zone is a pair of numbers: the same easting exists
    in sixty places. When the CRS is not UTM this says so rather than inventing
    a zone.
    """
    zone = utm_zone(crs)
    if zone is None:
        return format_native(x, y, linear_unit(crs))
    number, north = zone
    return f"{x:,.1f} m E, {y:,.1f} m N (UTM {number}{'N' if north else 'S'})"


def utm_zone(crs: str) -> tuple[int, bool] | None:
    """The UTM zone a CRS is in, or None when it is not a UTM CRS.

    Asked of pyproj rather than parsed out of the CRS's name: `NAD83 / UTM zone
    12N` contains two numbers, and reading the first one gives zone 83.
    """
    if not crs:
        return None
    try:
        zone = getattr(_crs(crs), "utm_zone", None)
    except CrsUnknown:
        return None
    if not zone:
        return None
    text = str(zone).strip().upper()
    digits = "".join(c for c in text if c.isdigit())
    if not digits:
        return None
    return int(digits), not text.endswith("S")


def format_position(
    x: float, y: float, crs: str, crs_unit: str, style: str
) -> str:
    """A cursor position, written the way the person asked for it.

    inputs   x, y in `crs`; the CRS and its linear unit; one of `FORMATS`
    output   the text, always carrying what it is in — a coordinate without its
             CRS or its hemisphere is a pair of numbers

    A style that cannot be produced falls back to the layer's own coordinates
    and says so by showing the native CRS, rather than printing a number that
    is not the one asked for.
    """
    if style == NATIVE or not crs:
        return format_native(x, y, crs_unit)
    if style == UTM:
        return format_utm(x, y, crs)
    try:
        longitude, latitude = transform(x, y, crs, GEOGRAPHIC)
    except CrsUnknown:
        return format_native(x, y, crs_unit)
    if not (math.isfinite(longitude) and math.isfinite(latitude)):
        return format_native(x, y, crs_unit)
    if style == DMS:
        return format_dms(longitude, latitude)
    return format_decimal(longitude, latitude)


def label_for(style: str, crs: str) -> str:
    """What the readout is in, for the label beside it."""
    if style in (DECIMAL, DMS):
        return GEOGRAPHIC
    return crs
