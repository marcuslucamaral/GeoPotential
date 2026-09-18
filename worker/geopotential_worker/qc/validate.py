"""Running the QA/QC rules over a described dataset.

One entry point, `validate`, so that "impede operação inválida" is decided in
one place. The Import Wizard consults `Report.usable`, and so does job
submission; two code paths asking the same question of the same function
cannot disagree about the answer.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ..io.describe import Description
from . import rules
from .findings import Report, Severity


def validate(
    description: Description,
    *,
    context: Sequence[dict[str, Any]] = (),
    require_metric: bool = False,
) -> Report:
    """Run every applicable rule and return the verdict.

    description     what `io.describe` read; nothing is re-read from disk
    context         the other layers already in the project, each as
                    {"name", "extent", "pixel_size"} — for overlap and
                    resolution, which are only answerable across layers
    require_metric  True when the intended operation needs metres. A
                    geographic CRS is fine to hold and wrong to compute
                    distances in, so the refusal belongs to the operation.
    returns         Report
    """
    source = description.path.name
    report = Report(dataset=source, metadata=description.as_dict())
    # The private arrays never reach the report's metadata: they would go into
    # a JSON message and the protocol forbids serializing a raster.
    for key in ("_values", "_x", "_y", "_declared_nodata"):
        report.metadata.pop(key, None)

    crs_obj = _crs_object(description.crs)
    rules.check_crs(report, description.crs, source=source)
    rules.check_datum(report, crs_obj, source=source)

    if require_metric and crs_obj is not None and crs_obj.is_geographic:
        report.add(
            rules.Finding(
                rule="crs.metric_required",
                severity=Severity.BLOCKER,
                dataset=source,
                what=f"the CRS {description.crs} is geographic, and this "
                     f"operation measures in {description.crs_unit or 'degrees'}.",
                why="Distances, pixel sizes and search radii in degrees are not "
                    "lengths: a degree of longitude is 111 km at the equator "
                    "and 0 km at the pole.",
                fix="Reproject to a projected CRS — UTM for the survey's zone — "
                    "before running this operation.",
                observed=description.crs,
                expected="a projected CRS",
            )
        )

    if description.kind == "raster":
        _validate_raster(report, description, context, source)
    elif description.kind == "table":
        _validate_table(report, description, source)
    else:
        _validate_vector(report, description, context, source)

    return report


def _validate_raster(
    report: Report,
    description: Description,
    context: Sequence[dict[str, Any]],
    source: str,
) -> None:
    values = description.detail.get("_values")
    if values is None:
        return
    rules.check_nodata(
        report, values, description.detail.get("_declared_nodata"), source=source
    )
    rules.check_finite(report, values, source=source)
    rules.check_coverage(report, values, source=source)

    pixel_size = (
        float(description.detail.get("pixel_size_x", 0.0)),
        float(description.detail.get("pixel_size_y", 0.0)),
    )
    unit = description.crs_unit or "units"
    rules.check_pixel_size(report, pixel_size, unit, source=source)
    rules.check_unit(report, values, description.unit, source=source)

    if description.extent and context:
        with_extent = [c for c in context if c.get("extent")]
        rules.check_overlap(
            report,
            description.extent,
            [(c["name"], tuple(c["extent"])) for c in with_extent],
            source=source,
            crs=description.crs or "",
            other_crs=[str(c.get("crs") or "") for c in with_extent],
        )
        rules.check_resolution_match(
            report,
            pixel_size,
            [(c["name"], tuple(c["pixel_size"])) for c in context if c.get("pixel_size")],
            unit,
            source=source,
        )


def _validate_table(report: Report, description: Description, source: str) -> None:
    detail = description.detail
    rules.check_table_fields(
        report,
        description.fields,
        [detail.get("x_field", ""), detail.get("y_field", ""),
         detail.get("value_field", "")],
        source=source,
    )
    rules.check_guessed_fields(
        report,
        detail.get("fields_declared", []),
        {"x_field": detail.get("x_field", ""),
         "y_field": detail.get("y_field", ""),
         "value_field": detail.get("value_field", "")},
        detail.get("value_candidates", []),
        source=source,
    )
    x = detail.get("_x")
    y = detail.get("_y")
    values = detail.get("_values")
    if x is None or y is None or x.size == 0:
        return
    good = np.isfinite(x) & np.isfinite(y)
    if values is not None and values.size == x.size:
        rules.check_finite(report, values, source=source)
        rules.check_coverage(report, values, source=source)
        rules.check_unit(report, values, description.unit, source=source)
        rules.check_duplicates(report, x[good], y[good], values[good], source=source)
    rules.check_gaps(report, x[good], y[good], source=source)


def _validate_vector(
    report: Report,
    description: Description,
    context: Sequence[dict[str, Any]],
    source: str,
) -> None:
    if description.detail.get("features", 0) == 0:
        report.add(
            rules.Finding(
                rule="coverage.any_valid",
                severity=Severity.BLOCKER,
                dataset=source,
                what="the layer has no features.",
                why="An empty vector layer contributes nothing but still "
                    "occupies a criterion slot and a weight.",
                fix="Check the layer name — a GeoPackage often holds several, "
                    "and the wrong one reads as empty.",
                observed=0,
                expected="> 0 features",
            )
        )
    if description.extent and context:
        rules.check_overlap(
            report,
            description.extent,
            [(c["name"], tuple(c["extent"])) for c in context if c.get("extent")],
            source=source,
        )


def _crs_object(crs: str | None):
    if not crs:
        return None
    try:
        from pyproj import CRS as PyprojCRS

        return PyprojCRS.from_user_input(crs)
    except Exception:
        return None
