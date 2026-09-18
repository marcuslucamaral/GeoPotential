"""Describing a dataset without importing it.

Section 9.2: the Import Wizard detects format, CRS, unit, fields, NoData,
extent and problems **before** the dataset enters the project. So describing
must be a read-only operation that creates nothing — no row in `dataset`, no
copy, no side effect. `Description.imported` does not exist, because describing
is not a step towards importing; it is how you decide whether to.

Six formats (MSP-03): CSV, XYZ, GeoTIFF, COG, GeoPackage, Shapefile.

A table carries no CRS of its own, so the project reads one from a sidecar
`<name>.meta.json`. Absent, the table is refused by name — never assumed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import preview

RASTER_SUFFIXES = {".tif", ".tiff", ".gtiff", ".cog", ".vrt", ".img"}
TABLE_SUFFIXES = {".csv", ".xyz", ".txt", ".dat"}
VECTOR_SUFFIXES = {".shp", ".gpkg", ".geojson", ".json", ".gml", ".kml"}

# Column names that usually mean a coordinate, in the order they are tried.
X_CANDIDATES = ("easting", "x", "lon", "longitude", "east", "utm_e", "coord_x")
Y_CANDIDATES = ("northing", "y", "lat", "latitude", "north", "utm_n", "coord_y")

# How many distinct codes may still be scored one by one on screen. Past this
# the raster is reported as having classes but none are listed: a table with
# 300 rows is not a table anybody fills in, and offering it would turn the
# refusal in `membership.categorical` into a wall of typing.
MAX_CLASSES = 64

# A class code raster does not span a hundred thousand codes. The bound exists
# so an integer-typed elevation model is rejected by arithmetic instead of by
# a sort over every pixel.
MAX_CODE_SPAN = 100_000


class UnsupportedFormat(ValueError):
    """The file is not one of the six formats, and is named as such."""


@dataclass
class Description:
    """What is known about a dataset before deciding to import it."""

    path: Path
    kind: str                     # raster | vector | table
    driver: str = ""
    crs: str | None = None
    crs_unit: str | None = None
    geographic: bool = False
    unit: str | None = None
    extent: tuple[float, float, float, float] | None = None
    fields: list[str] = field(default_factory=list)
    nodata: float | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """The serializable form. This crosses the IPC boundary as JSON.

        `detail` carries the arrays the QA/QC rules work on under underscore
        keys, and those are excluded here. Including them would put a numpy
        array into a protocol message — which fails to encode, and which the
        protocol forbids anyway: a raster travels as a file and a hash, never
        as JSON.
        """
        public = {k: v for k, v in self.detail.items() if not k.startswith("_")}
        return {
            "path": str(self.path),
            "name": self.path.name,
            "kind": self.kind,
            "driver": self.driver,
            "crs": self.crs,
            "crs_unit": self.crs_unit,
            "geographic": self.geographic,
            "unit": self.unit,
            "extent": list(self.extent) if self.extent else None,
            "fields": self.fields,
            "nodata": self.nodata,
            "statistics": self.statistics,
            "size_bytes": self.size_bytes,
            **public,
        }


def classify(path: Path) -> str:
    """Which of the three kinds a file is, from its suffix.

    raises  UnsupportedFormat naming what is supported
    """
    suffix = path.suffix.lower()
    if suffix in RASTER_SUFFIXES:
        return "raster"
    if suffix in VECTOR_SUFFIXES:
        return "vector"
    if suffix in TABLE_SUFFIXES:
        return "table"
    raise UnsupportedFormat(
        f"{path.name}: {suffix or 'no extension'} is not a format this build "
        f"reads. Supported: GeoTIFF/COG (.tif, .cog), GeoPackage (.gpkg), "
        f"Shapefile (.shp), CSV/XYZ (.csv, .xyz, .txt)."
    )


def sidecar_metadata(path: Path) -> dict[str, Any]:
    """Read `<name>.meta.json` beside a table, if present.

    A CSV has no place to record its CRS, its unit, or which columns are
    coordinates. Rather than guess, the project reads a sidecar; rather than
    require one, it reports its absence as a finding.
    """
    sidecar = path.with_suffix(".meta.json")
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{sidecar.name}: is not readable JSON ({exc})") from exc


def describe(path: str | Path, *, overrides: dict[str, Any] | None = None) -> Description:
    """Read everything the wizard shows, and nothing else.

    path       the file to look at
    overrides  what the operator declared in the wizard — `crs`, `unit`,
               `x_field`, `y_field`, `value_field`, `nodata`. These are the
               correction path of gate G3: a file with no CRS becomes usable
               when the operator states one, and the statement is recorded.
    returns    Description
    raises     UnsupportedFormat, FileNotFoundError

    Nothing here writes anything. Describing is not importing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    overrides = dict(overrides or {})
    kind = classify(path)
    if kind == "raster":
        return _describe_raster(path, overrides)
    if kind == "vector":
        return _describe_vector(path, overrides)
    return _describe_table(path, overrides)


def _describe_raster(path: Path, overrides: dict[str, Any]) -> Description:
    import rasterio

    with rasterio.open(path) as src:
        crs = overrides.get("crs") or (str(src.crs) if src.crs else None)
        crs_obj = _crs_object(crs)
        band = int(overrides.get("band", 1))
        values = src.read(band).astype(np.float32)
        declared = overrides.get("nodata", src.nodata)
        if declared is not None and not (
            isinstance(declared, float) and np.isnan(declared)
        ):
            values = np.where(values == np.float32(declared), np.nan, values)
        left, bottom, right, top = src.bounds
        description = Description(
            path=path,
            kind="raster",
            driver=src.driver,
            crs=crs,
            crs_unit=_crs_unit(crs_obj),
            geographic=bool(crs_obj.is_geographic) if crs_obj is not None else False,
            # Declared, else the file's own. Every artefact this project
            # writes carries `GEOPOTENTIAL_UNIT`, so a raster it produced
            # knows what its numbers mean — and a value shown with no unit is
            # a number nobody can check.
            unit=overrides.get("unit") or _tagged_unit(src),
            extent=(left, bottom, right, top),
            fields=[f"band {i}" for i in range(1, src.count + 1)],
            nodata=None if declared is None else float(declared),
            statistics=_statistics(values, path),
            size_bytes=path.stat().st_size,
            detail={
                "width": src.width,
                "height": src.height,
                "bands": src.count,
                "dtype": src.dtypes[band - 1],
                "pixel_size_x": abs(src.transform.a),
                "pixel_size_y": abs(src.transform.e),
                "is_tiled": bool(src.profile.get("tiled", False)),
                "overviews": len(src.overviews(band)),
                # A COG is a GeoTIFF that is tiled and carries overviews. Saying
                # which it is matters for how it will be read at scale.
                "cloud_optimized": bool(src.profile.get("tiled", False))
                and len(src.overviews(band)) > 0,
            },
        )
        description.detail["_values"] = values
        # The *effective* nodata: what the operator declared, else what the
        # file declares. Passing the file's value here would make a declared
        # override invisible to the rules, so declaring one could never clear
        # the finding it exists to clear — gate G3 depends on this line.
        description.detail["_declared_nodata"] = declared
        description.detail["_file_nodata"] = src.nodata
    return description


def _describe_vector(path: Path, overrides: dict[str, Any]) -> Description:
    import geopandas as gpd

    layer = overrides.get("layer")
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    crs = overrides.get("crs") or (str(gdf.crs) if gdf.crs is not None else None)
    crs_obj = _crs_object(crs)
    # Plain Python, not numpy scalars. `json.dumps` accepts a `numpy.float64`
    # because it subclasses `float`, so this leak survived every encoding
    # test — and then arrived in QML as an opaque wrapper with no `toFixed`,
    # which is where a description of a shapefile stopped being readable.
    bounds = tuple(float(v) for v in gdf.total_bounds) if len(gdf) else None
    geometry_kinds = (sorted(str(k) for k in gdf.geom_type.dropna().unique())
                      if len(gdf) else [])
    value_field = overrides.get("value_field")
    values = (
        gdf[value_field].to_numpy(dtype=np.float32, na_value=np.nan)
        if value_field and value_field in gdf.columns
        else np.array([], dtype=np.float32)
    )
    return Description(
        path=path,
        kind="vector",
        driver=path.suffix.lstrip(".").upper(),
        crs=crs,
        crs_unit=_crs_unit(crs_obj),
        geographic=bool(crs_obj.is_geographic) if crs_obj is not None else False,
        unit=overrides.get("unit"),
        extent=bounds,
        fields=[c for c in gdf.columns if c != gdf.geometry.name],
        nodata=None,
        statistics=_statistics(values, path) if values.size else {},
        size_bytes=path.stat().st_size,
        detail={
            "features": int(len(gdf)),
            "geometry_kinds": geometry_kinds,
            "layers": _gpkg_layers(path),
            # ADR-MSP-004: a silhouette and the first rows of the attribute
            # table, both bounded and both declaring what they left out.
            "preview": {
                "kind": "geometry",
                **preview.geometry(gdf),
                **preview.rows(gdf.drop(columns=[gdf.geometry.name])),
            },
        },
    )


def _describe_table(path: Path, overrides: dict[str, Any]) -> Description:
    import pandas as pd

    meta = sidecar_metadata(path)
    separator = overrides.get("separator") or meta.get("separator")
    frame = (
        pd.read_csv(path, sep=separator)
        if separator
        else pd.read_csv(path, sep=None, engine="python")
    )
    columns = [str(c) for c in frame.columns]

    x_field = overrides.get("x_field") or meta.get("x_field") or _guess(columns, X_CANDIDATES)
    y_field = overrides.get("y_field") or meta.get("y_field") or _guess(columns, Y_CANDIDATES)
    # Which columns hold numbers at all. `pandas` already parsed the file, so
    # this is a dtype check and not a second pass over the rows.
    numeric = [str(c) for c in frame.columns
               if pd.api.types.is_numeric_dtype(frame[c])]
    declared_value = overrides.get("value_field") or meta.get("value_field")
    value_field = declared_value or _guess_value(columns, x_field, y_field,
                                                 numeric)
    if declared_value and declared_value in columns \
            and declared_value not in numeric:
        # Declared, and it cannot be a measurement. Refusing by name beats
        # dying inside a float conversion three frames down.
        raise ValueError(
            f"{path.name}: value_field={declared_value!r} holds text, not "
            f"numbers, so it cannot be a measurement. Numeric columns: "
            + (", ".join(numeric) if numeric else "none")
        )
    crs = overrides.get("crs") or meta.get("source_crs")
    crs_obj = _crs_object(crs)

    extent = None
    x = y = values = np.array([], dtype=np.float64)
    if x_field in columns and y_field in columns:
        x = frame[x_field].to_numpy(dtype=np.float64, na_value=np.nan)
        y = frame[y_field].to_numpy(dtype=np.float64, na_value=np.nan)
        good = np.isfinite(x) & np.isfinite(y)
        if good.any():
            extent = (
                float(x[good].min()), float(y[good].min()),
                float(x[good].max()), float(y[good].max()),
            )
    if value_field and value_field in columns:
        values = frame[value_field].to_numpy(dtype=np.float32, na_value=np.nan)

    description = Description(
        path=path,
        kind="table",
        driver="XYZ" if path.suffix.lower() == ".xyz" else "CSV",
        crs=crs,
        crs_unit=_crs_unit(crs_obj),
        geographic=bool(crs_obj.is_geographic) if crs_obj is not None else False,
        unit=overrides.get("unit") or meta.get("unit"),
        extent=extent,
        fields=columns,
        nodata=None,
        statistics=_statistics(values, path) if values.size else {},
        size_bytes=path.stat().st_size,
        detail={
            "rows": int(len(frame)),
            "x_field": x_field,
            "y_field": y_field,
            "value_field": value_field,
            # §16: never a silent value. The screen shows which columns were
            # chosen and by whom, and the QA/QC warns when it was a guess.
            "fields_declared": sorted(
                key for key in ("x_field", "y_field", "value_field")
                if overrides.get(key) or meta.get(key)
            ),
            "value_candidates": value_candidates(columns, x_field, y_field,
                                                 numeric),
            "sidecar": str(path.with_suffix(".meta.json").name) if meta else None,
        },
    )
    # ADR-MSP-004: bounded, decimated and declared. Never an input to anything.
    description.detail["preview"] = {
        "kind": "points",
        **preview.rows(frame),
        **preview.points(x, y, values.astype(np.float64) if values.size else None),
    }
    # How far apart the samples actually are. It is the one number that says
    # what a search radius has to be: a radius below the sample spacing leaves
    # most of the grid empty, and nobody can guess it from the file's name.
    description.detail["median_spacing"] = _median_spacing(x, y)
    description.detail["_x"] = x
    description.detail["_y"] = y
    description.detail["_values"] = values
    return description


def _tagged_unit(src) -> str | None:  # noqa: ANN001
    """The unit a GeoTIFF records for itself, if it records one."""
    try:
        tags = src.tags()
    except Exception:                                # noqa: BLE001
        return None
    unit = tags.get("GEOPOTENTIAL_UNIT")
    return str(unit) if unit else None


def _median_spacing(x: np.ndarray, y: np.ndarray) -> float | None:
    """The median distance from a sample to its nearest neighbour.

    inputs   coordinates in the file's own CRS
    output   the distance in that CRS's unit, or None when it cannot be said

    A survey's own spacing is a fact about the survey, and it is what makes a
    search radius choosable: below it, an interpolation leaves most of the
    grid null; far above it, every cell averages half the dataset.
    """
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.sum() < 2:
        return None
    try:
        from scipy.spatial import cKDTree
    except ImportError:                              # pragma: no cover
        return None
    points = np.column_stack([x[finite], y[finite]])
    # k=2 because the nearest neighbour of a point is itself, at distance 0.
    distances, _ = cKDTree(points).query(points, k=2)
    nearest = distances[:, 1]
    nearest = nearest[np.isfinite(nearest) & (nearest > 0)]
    return float(np.median(nearest)) if nearest.size else None


def _statistics(values: np.ndarray,
                source: Path | None = None) -> dict[str, Any]:
    """Min, max, mean, std, valid fraction and a histogram, over valid pixels.

    `source` is the file the values came from, and is only used to look up
    the legend of a class raster. Without it the codes are still listed;
    they just have no names.

    The histogram is what the Data Inspector (§9.3) draws, and what the
    Membership Editor will need at M5, so it is computed once here.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"valid": 0, "valid_fraction": 0.0}
    counts, edges = np.histogram(finite, bins=32)
    classes = _classes(finite, source)
    return {
        "valid": int(finite.size),
        "total": int(values.size),
        "valid_fraction": float(finite.size / values.size),
        "min": float(finite.min()),
        "max": float(finite.max()),
        # Accumulated in float64. A float32 sum overflows to infinity on a
        # large raster of large values — an undeclared -3.4e38 sentinel does it
        # in under a million pixels — and the inspector would then report an
        # infinite mean for a file that merely has a nodata problem.
        "mean": float(finite.mean(dtype=np.float64)),
        "std": float(finite.std(dtype=np.float64)),
        "p2": float(np.percentile(finite.astype(np.float64), 2)),
        "p98": float(np.percentile(finite.astype(np.float64), 98)),
        "histogram": {"counts": counts.tolist(), "edges": edges.tolist()},
        # Which units these magnitudes would not contradict. A shortlist for
        # the person to choose from, never a value applied on their behalf:
        # a file has nowhere to state its unit, so the unit is an assertion.
        #
        # Imported here and not at module scope: `qc` imports `describe` for
        # `Description`, so a top-level import closes a cycle. The table is
        # still read from the one place that owns it, which is the point.
        "unit_candidates": _plausible_units(
            float(finite.min()), float(finite.max())),
        # How many units the table knows. A shortlist that excluded nothing is
        # not a shortlist, and the screen needs to be able to tell.
        "unit_count": _unit_count(),
        # The class codes, when the values are codes at all. Absent for a
        # continuous field, which is how the Membership Editor knows whether
        # `categorical` is even offerable.
        **({"classes": classes} if classes else {}),
    }


def _classes(finite: np.ndarray,
             source: Path | None = None) -> dict[str, Any] | None:
    """The distinct class codes and their counts, or None for a continuous field.

    finite   the valid values only, already free of NaN
    returns  {distinct, codes, counts, limit}, or None when the values are not
             class codes; `codes` is empty when `distinct` exceeds `limit`
    reference  IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 9.5, MSP-07.

    Codes are recognized by being integral and few. Geology, land use and soil
    arrive as integer rasters whose values name a class, and `categorical`
    refuses any code it was not given a score for — so the screen has to be
    able to list them, and the file is the only thing that knows what they are.

    A field of 0.5, 1.5, 2.5 is not offered: three distinct values do not make
    a code, and guessing here would put a scientific claim in a heuristic.
    """
    if finite.size == 0:
        return None
    if not bool(np.all(finite == np.rint(finite))):
        return None
    low, high = float(finite.min()), float(finite.max())
    if high - low > MAX_CODE_SPAN:
        return None
    # Counted with bincount over the shifted range: one pass over the pixels
    # plus one over the span, where `unique` would sort 16 million values on
    # every describe.
    shifted = (finite - low).astype(np.int64)
    counts = np.bincount(shifted, minlength=int(high - low) + 1)
    present = np.flatnonzero(counts)
    distinct = int(present.size)
    listed = distinct <= MAX_CLASSES
    codes = [float(low + int(i)) for i in present] if listed else []
    found = {
        "distinct": distinct,
        "limit": MAX_CLASSES,
        "codes": codes,
        "counts": [int(counts[i]) for i in present] if listed else [],
    }
    if codes and source is not None:
        found.update(_legend(source, codes))
    return found


def _legend(source: Path, codes: list[float]) -> dict[str, Any]:
    """The name of each code, when a legend beside the file states one.

    source   the raster, whose sidecar or `.aux.xml` may carry the legend
    codes    the codes actually present, in the order the table lists them
    returns  {labels, label_source, labelled} — empty when nothing states one

    `labels` is positional, one entry per code, so the screen pairs them
    without re-deriving the order. A code the legend does not mention gets an
    empty string: it stays scoreable, and stays visibly unnamed, which is the
    honest state — inventing "class 3" as a name would make a missing legend
    look like a present one.
    """
    from .class_labels import read_labels

    found = read_labels(source)
    if not found:
        return {}
    labels, origin = found
    named = [labels.get(code, "") for code in codes]
    if not any(named):
        # A legend that names none of the codes in this raster is a legend for
        # a different raster. Reporting it would be worse than reporting none.
        return {}
    return {
        "labels": named,
        # Where the names came from. A label asserts what a code means, and an
        # assertion without a source is not checkable.
        "label_source": origin,
        "labelled": sum(1 for name in named if name),
    }


def _plausible_units(low: float, high: float) -> list[str]:
    """The QC table's own answer, reached without a circular import."""
    from ..qc.rules import plausible_units

    return plausible_units(low, high)


def _unit_count() -> int:
    from ..qc.rules import UNIT_RANGES

    return len(UNIT_RANGES)


def _crs_object(crs: str | None):
    if not crs:
        return None
    try:
        from pyproj import CRS as PyprojCRS

        return PyprojCRS.from_user_input(crs)
    except Exception:
        return None


def _crs_unit(crs_obj) -> str | None:  # noqa: ANN001
    if crs_obj is None:
        return None
    axis = crs_obj.axis_info
    return axis[0].unit_name if axis else None


def _guess(columns: list[str], candidates: tuple[str, ...]) -> str:
    lowered = {c.lower().strip().rstrip("]").split("[")[0].strip(): c for c in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return ""


def _guess_value(columns: list[str], x_field: str, y_field: str,
                 numeric: Sequence[str] | None = None) -> str:
    """The first column that is not a coordinate and could hold a measurement.

    It is a guess and is recorded as one: with six columns the first
    non-coordinate is as likely to be `id` as the measurement, and a silently
    chosen value column would put the wrong numbers into a criterion.

    `numeric` narrows it to the columns that hold numbers. That is not a better
    guess, it is an exclusion: a column of text cannot be a measurement in any
    reading. Without it, a survey table whose first column is a station name —
    `ST0000` — was guessed as the value and the read died converting it to
    float, with a bare `ValueError` and no column named.
    """
    for column in columns:
        if column in (x_field, y_field):
            continue
        if numeric is not None and column not in numeric:
            continue
        return column
    return ""


def value_candidates(columns: list[str], x_field: str, y_field: str,
                     numeric: Sequence[str] | None = None) -> list[str]:
    """Every column that could carry the measurement.

    A text column is excluded, not ranked lower: it cannot be a measurement,
    and offering it in the wizard's list is offering a choice that fails.
    """
    return [c for c in columns
            if c not in (x_field, y_field)
            and (numeric is None or c in numeric)]


def _gpkg_layers(path: Path) -> list[str]:
    if path.suffix.lower() != ".gpkg":
        return []
    try:
        import fiona

        return list(fiona.listlayers(path))
    except Exception:
        return []
