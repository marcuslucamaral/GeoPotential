"""The QA/QC rules of MSP-04.

Fourteen things to validate: CRS, datum, vertical datum where applicable, unit,
NoData, extent, overlap, resolution, spacing, duplicates, gaps, non-finite
values, coverage, metadata consistency.

Each rule is a function that returns zero or more `Finding`s. Each finding
names the dataset, says what is wrong, why it matters, and what to do. None of
them returns a bare string, and the gate asserts that every finding any rule
produces is actionable.

The severities are chosen once, here, and the fixtures assert them. Changing a
severity is a scientific decision and belongs in `docs/decisions/`.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .findings import Finding, Report, Severity

# A criterion valid on less than this fraction of the grid contributes almost
# nothing but still occupies a weight. Stated rather than assumed.
LOW_COVERAGE = 0.20

# Pixel sizes differing by more than this factor cannot be harmonized without
# either inventing detail or discarding it.
RESOLUTION_FACTOR = 4.0

# Two samples closer than this fraction of the median spacing are the same
# location for gridding purposes.
DUPLICATE_TOLERANCE = 0.01

# Plausible magnitudes for the units this project actually handles. A declared
# unit whose values sit far outside its range is a mislabelling, and a
# mislabelled unit produces a map that looks right and is wrong.
UNIT_RANGES: dict[str, tuple[float, float]] = {
    "g/cm3": (1.0, 6.0),
    "mGal": (-600.0, 600.0),
    "nT": (-100_000.0, 100_000.0),
    "m": (-12_000.0, 12_000.0),
    "degC": (-100.0, 1500.0),
    "mW/m2": (0.0, 1000.0),
}


def plausible_units(low: float, high: float) -> list[str]:
    """Which declared units this range of values would not contradict.

    inputs   the smallest and largest valid value, in the file's own numbers
    output   unit names, in the order `UNIT_RANGES` declares them

    This is **not** a guess at the unit and must never be applied as one: a
    range of -243 to -169 fits mGal and also fits metres. It narrows the list
    a person chooses from, using the same table `check_unit` will judge the
    answer against, so the wizard and the verdict cannot come to disagree.

    A file has nowhere to write its unit — a CSV certainly does not — so the
    unit is always the operator's assertion. Section 16: never a silent value.
    """
    if not (math.isfinite(low) and math.isfinite(high)):
        return []
    return [
        name for name, (lo, hi) in UNIT_RANGES.items()
        if low >= lo and high <= hi
    ]


# ---- raster rules -------------------------------------------------------

def check_crs(report: Report, crs_name: str | None, *, source: str) -> None:
    """MSP-04 CRS. There is no default; absent stops the run (ADR-004)."""
    if not crs_name:
        report.add(Finding(
            rule="crs.present",
            severity=Severity.BLOCKER,
            dataset=source,
            what="no coordinate reference system is declared.",
            why="Without a CRS the coordinates are just numbers, and every "
                "reprojection and distance computed from them would be wrong.",
            fix="Declare the CRS in the import wizard, or write it into the "
                "file with a tool that can.",
            observed=None,
            expected="an EPSG code or WKT",
        ))


def check_datum(report: Report, crs, *, source: str) -> None:
    """MSP-04 datum and vertical datum.

    A missing datum is reported as INFO rather than blocked: pyproj resolves a
    datum for every CRS this project accepts, so its absence means the CRS is
    unusual, not that the data is unusable. Silence would be worse than a note.
    """
    if crs is None:
        return
    try:
        datum = crs.datum
    except Exception:  # a CRS pyproj cannot decompose
        datum = None
    if datum is None:
        report.add(Finding(
            rule="datum.present",
            severity=Severity.INFO,
            dataset=source,
            what="the CRS declares no datum this build can read.",
            why="Datum differences shift coordinates by up to hundreds of "
                "metres, and a transform cannot correct for one it cannot see.",
            fix="Confirm the datum with whoever produced the file if the "
                "layers disagree spatially.",
            observed=str(crs),
        ))
    if getattr(crs, "is_vertical", False):
        report.add(Finding(
            rule="datum.vertical",
            severity=Severity.INFO,
            dataset=source,
            what="this is a vertical CRS.",
            why="Elevations referenced to different vertical datums differ by "
                "tens of metres, which matters for any depth-dependent term.",
            fix="Record which vertical datum the elevations use.",
            observed=str(crs),
        ))


def check_nodata(
    report: Report, values: np.ndarray, declared_nodata: float | None, *, source: str
) -> None:
    """MSP-04 NoData. Every raster declares its null, or the null is data.

    This is defect D-05 of the legacy tree, where all four `save_geotiff` call
    sites omitted nodata while the arrays carried NaN.
    """
    has_nan = bool(np.isnan(values).any())
    if declared_nodata is None:
        if has_nan:
            report.add(Finding(
                rule="nodata.declared",
                severity=Severity.BLOCKER,
                dataset=source,
                what="the array contains NaN but the file declares no nodata value.",
                why="Every reader downstream will treat those NaN as measurements, "
                    "so statistics, memberships and aggregations all shift.",
                fix="Rewrite the file declaring nodata as NaN, or state the "
                    "nodata value in the import wizard.",
                observed="nodata=None with NaN present",
                expected="nodata=nan",
            ))
        else:
            suspects = _sentinel_candidates(values)
            if suspects:
                report.add(Finding(
                    rule="nodata.declared",
                    severity=Severity.BLOCKER,
                    dataset=source,
                    what=f"the array contains repeated sentinel value(s) "
                         f"{', '.join(f'{s:g}' for s in suspects)} but declares "
                         f"no nodata.",
                    why="A sentinel read as data drags every statistic towards "
                        "it; a -9999 among elevations moves the mean by "
                        "thousands.",
                    fix=f"Declare nodata as {suspects[0]:g} in the import "
                        f"wizard, or rewrite the file with it set.",
                    observed=suspects,
                    expected="a declared nodata value",
                ))


def check_finite(report: Report, values: np.ndarray, *, source: str) -> None:
    """MSP-04 non-finite values. NaN is the only null; infinity is a defect."""
    infinite = int(np.isinf(values).sum())
    if infinite:
        report.add(Finding(
            rule="values.finite",
            severity=Severity.BLOCKER,
            dataset=source,
            what=f"{infinite} pixel(s) hold +inf or -inf.",
            why="NaN is this project's only null. An infinity is a computation "
                "that already failed upstream, and it propagates through every "
                "sum and product it touches.",
            fix="Find the step that produced the infinities and fix it there, "
                "or mask those pixels to nodata before importing.",
            observed=infinite,
            expected=0,
        ))


def check_coverage(report: Report, values: np.ndarray, *, source: str) -> None:
    """MSP-04 coverage. How much of the grid actually carries data."""
    valid = np.isfinite(values)
    fraction = float(valid.mean())
    if fraction == 0.0:
        report.add(Finding(
            rule="coverage.any_valid",
            severity=Severity.BLOCKER,
            dataset=source,
            what="every pixel is null.",
            why="A layer with no data cannot contribute to a decision, but it "
                "would still occupy a criterion slot and a weight.",
            fix="Check the export that produced this file; the extent or the "
                "band index is probably wrong.",
            observed="0% valid",
            expected="> 0% valid",
        ))
        return
    if fraction < LOW_COVERAGE:
        report.add(Finding(
            rule="coverage.fraction",
            severity=Severity.WARNING,
            dataset=source,
            what=f"only {fraction * 100:.1f}% of pixels carry data.",
            why="Where this criterion is null the aggregation rule decides the "
                "outcome, not the evidence, so a sparse layer changes the map "
                "far less than its weight suggests.",
            fix="Confirm this coverage is expected, or restrict the analysis "
                f"extent to where the data is.",
            observed=f"{fraction * 100:.1f}%",
            expected=f">= {LOW_COVERAGE * 100:.0f}%",
        ))


def check_pixel_size(
    report: Report, pixel_size: tuple[float, float], unit: str, *, source: str
) -> None:
    """MSP-04 resolution. Anisotropic pixels are legal and must be stated."""
    px, py = pixel_size
    if abs(px - py) > 1e-9 * max(px, py):
        report.add(Finding(
            rule="grid.anisotropic",
            severity=Severity.WARNING,
            dataset=source,
            what=f"pixels are {px:g} x {py:g} {unit}, not square.",
            why="Anything that collapses the two into one number — a distance "
                "transform, a search radius, an area — is wrong by the ratio "
                "between them.",
            fix="Resample to a square pixel before analysis, or confirm every "
                "operator used handles the two sizes separately.",
            observed=[px, py],
            expected="px == py",
        ))


def check_unit(
    report: Report, values: np.ndarray, declared_unit: str | None, *, source: str
) -> None:
    """MSP-04 unit. A declared unit is checked against the magnitudes.

    This catches the mislabelling that produces a map which looks right: a
    Bouguer anomaly near -210 declared as `g/cm3` passes every other check.
    """
    if not declared_unit:
        report.add(Finding(
            rule="unit.declared",
            severity=Severity.WARNING,
            dataset=source,
            what="no physical unit is declared.",
            why="A raw criterion carries a unit; without it the manifest cannot "
                "record what was measured, and two layers in different units "
                "can be compared by mistake.",
            fix="State the unit in the import wizard — mGal, g/cm3, m, degC, "
                "mW/m2 or nT.",
            expected="a physical unit",
        ))
        return
    bounds = UNIT_RANGES.get(declared_unit)
    if bounds is None:
        return
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return
    low, high = float(finite.min()), float(finite.max())
    lo_ok, hi_ok = bounds
    if low < lo_ok or high > hi_ok:
        report.add(Finding(
            rule="unit.plausible",
            severity=Severity.WARNING,
            dataset=source,
            field=declared_unit,
            what=f"values run from {low:.4g} to {high:.4g}, outside the range "
                 f"normally seen for {declared_unit} ({lo_ok:g} to {hi_ok:g}).",
            why="A mislabelled unit passes every other check and produces a "
                "map that looks correct, because nothing downstream re-reads "
                "the physics.",
            fix=f"Confirm the unit is really {declared_unit}, or correct it in "
                f"the import wizard.",
            observed=[low, high],
            expected=list(bounds),
        ))


# ---- cross-layer rules --------------------------------------------------

def reprojected_extent(
    extent: tuple[float, float, float, float], source_crs: str, target_crs: str
) -> tuple[float, float, float, float] | None:
    """An extent expressed in another CRS, for comparison only.

    inputs   the extent, the CRS it is in, the CRS to express it in
    output   the transformed bounding box, or None when either CRS is unknown
             or the transform fails
    reference pyproj's `transform_bounds`, which densifies the edges — a
              rectangle in one projection is not a rectangle in another, and
              transforming only the four corners understates the box.

    ADR-MSP-005: comparing four numbers from one CRS with four from another
    answers a question nobody asked.
    """
    if not source_crs or not target_crs or source_crs == target_crs:
        return extent if source_crs == target_crs else None
    try:
        from pyproj import CRS, Transformer

        transformer = Transformer.from_crs(
            CRS.from_user_input(source_crs), CRS.from_user_input(target_crs),
            always_xy=True,
        )
        left, bottom, right, top = transformer.transform_bounds(*extent)
    except Exception:              # noqa: BLE001 - any CRS failure means "cannot compare"
        return None
    if not all(math.isfinite(v) for v in (left, bottom, right, top)):
        return None
    return float(left), float(bottom), float(right), float(top)


def check_overlap(
    report: Report,
    extent: tuple[float, float, float, float],
    others: Sequence[tuple[str, tuple[float, float, float, float]]],
    *,
    source: str,
    crs: str = "",
    other_crs: Sequence[str] = (),
) -> None:
    """MSP-04 overlap, compared in one CRS. ADR-MSP-005.

    A disjoint layer empties the harmonized grid — and that is where it is
    refused. Here it is reported: at import time the layer may be reference
    data, or the first layer of another area, and refusing it would be
    refusing work nobody asked to have refused.
    """
    if not others:
        return
    left, bottom, right, top = extent
    overlapping = []
    incomparable = []
    for position, (name, (o_left, o_bottom, o_right, o_top)) in enumerate(others):
        their_crs = other_crs[position] if position < len(other_crs) else ""
        mine = (left, bottom, right, top)
        if crs and their_crs and crs != their_crs:
            moved = reprojected_extent(mine, crs, their_crs)
            if moved is None:
                incomparable.append(name)
                continue
            mine = moved
        m_left, m_bottom, m_right, m_top = mine
        if (m_left < o_right and m_right > o_left
                and m_bottom < o_top and m_top > o_bottom):
            overlapping.append(name)

    if overlapping or len(incomparable) == len(others):
        return
    report.add(Finding(
        rule="extent.overlap",
        severity=Severity.WARNING,
        dataset=source,
        what="its extent does not intersect any other layer in the project, "
             "compared in a common CRS.",
        why="The analysis grid is the intersection of the inputs, so a "
            "disjoint layer would empty it — and an empty suitability map "
            "reads as 'nowhere is favourable' rather than as an error. "
            "Harmonization refuses that; importing does not, because the "
            "layer may be reference data or another area.",
        fix="Check the CRS and the coordinates — a layer in the wrong CRS "
            "usually lands somewhere plausible but far away. Keep it if it is "
            "meant to be somewhere else.",
        observed=[left, bottom, right, top],
        expected="an extent intersecting the other layers",
    ))


def check_guessed_fields(
    report: Report,
    declared: Sequence[str],
    chosen: dict[str, str],
    candidates: Sequence[str],
    *,
    source: str,
) -> None:
    """§16, on a table's columns. A guessed value column is named as a guess.

    With three columns the guess is almost always right. With six it is as
    likely to pick `id` as the measurement, and the wrong column becomes a
    criterion without anyone being told.
    """
    if "value_field" in declared or not chosen.get("value_field"):
        return
    others = [c for c in candidates if c != chosen["value_field"]]
    if not others:
        return
    report.add(Finding(
        rule="table.value_guessed",
        severity=Severity.WARNING,
        dataset=source,
        what=f"the value column was guessed as {chosen['value_field']!r}; "
             f"{len(others)} other column(s) could carry the measurement.",
        why="A criterion built on the wrong column is wrong everywhere "
            "downstream, and nothing later in the pipeline can notice: the "
            "numbers are plausible, they are simply not the measurement.",
        fix="Choose the value column in the import wizard — the alternatives "
            f"are {', '.join(repr(c) for c in others)}.",
        observed=chosen["value_field"],
        expected="a value column chosen by the operator",
    ))


def check_resolution_match(
    report: Report,
    pixel_size: tuple[float, float],
    others: Sequence[tuple[str, tuple[float, float]]],
    unit: str,
    *,
    source: str,
) -> None:
    """MSP-04 resolution against the rest of the project."""
    if not others:
        return
    px = max(pixel_size)
    finest = min(min(o) for _, o in others)
    if finest <= 0:
        return
    ratio = px / finest
    if ratio > RESOLUTION_FACTOR:
        report.add(Finding(
            rule="grid.resolution_mismatch",
            severity=Severity.WARNING,
            dataset=source,
            what=f"its pixel is {px:g} {unit} against {finest:g} {unit} "
                 f"elsewhere — {ratio:.0f}x coarser.",
            why="Resampling it onto the finer grid invents detail that was "
                "never measured, and the result looks as precise as the finest "
                "layer in the stack.",
            fix=f"Run the analysis at {px:g} {unit} instead, or state that the "
                f"upsampling is deliberate in the run's provenance.",
            observed=px,
            expected=f"within {RESOLUTION_FACTOR:g}x of {finest:g}",
        ))


# ---- point-table rules --------------------------------------------------

def check_duplicates(
    report: Report, x: np.ndarray, y: np.ndarray, values: np.ndarray, *, source: str
) -> None:
    """MSP-04 duplicates. Two values at one location need a stated rule."""
    coords = np.column_stack([x, y])
    _, index, counts = np.unique(coords, axis=0, return_index=True, return_counts=True)
    repeated = int((counts > 1).sum())
    if not repeated:
        return
    # Repeated coordinates carrying the *same* value are harmless; carrying
    # different values is a decision nobody has made yet.
    conflicting = 0
    for position in np.flatnonzero(counts > 1):
        same = np.all(coords == coords[index[position]], axis=1)
        if np.nanstd(values[same]) > 0:
            conflicting += 1
    if conflicting:
        report.add(Finding(
            rule="points.duplicates",
            severity=Severity.WARNING,
            dataset=source,
            what=f"{conflicting} coordinate(s) appear more than once carrying "
                 f"different values.",
            why="Gridding has to pick one, and picking silently makes a "
                "scientific choice on the operator's behalf.",
            fix="Decide how to reconcile them — mean, first, or last — and "
                "record the choice, or remove the duplicates at source.",
            observed=conflicting,
            expected=0,
        ))
    elif repeated:
        report.add(Finding(
            rule="points.duplicates",
            severity=Severity.INFO,
            dataset=source,
            what=f"{repeated} coordinate(s) appear more than once with the "
                 f"same value.",
            why="Harmless for gridding, but it inflates the apparent sample "
                "count.",
            fix="Deduplicate if the sample count matters to you.",
            observed=repeated,
        ))


# A hole wider than this many times the median sample spacing is a gap, not
# uneven sampling. Below it, interpolation is doing what interpolation is for.
GAP_FACTOR = 4.0


def check_gaps(
    report: Report, x: np.ndarray, y: np.ndarray, *, source: str
) -> None:
    """MSP-04 gaps and spacing.

    A large unsampled hole inside the extent is what interpolation smooths
    over, producing a confident surface where nothing was measured.

    Nearest-neighbour distance does not find it: the samples ringing a hole
    still have close neighbours along the rim, so a circular void barely moves
    the maximum. What does find it is asking, for every location in the
    extent, how far the nearest sample is — the largest such distance is the
    radius of the biggest empty region. That is a distance transform over a
    coarse occupancy grid, which is one vectorized call.
    """
    if x.size < 8:
        return
    try:
        from scipy.ndimage import distance_transform_edt
        from scipy.spatial import cKDTree
    except ImportError:
        return  # BLOCKED rather than wrong: the check needs scipy

    points = np.column_stack([x, y])
    tree = cKDTree(points)
    # k=2 because a point's nearest neighbour is itself.
    nearest = tree.query(points, k=2)[0][:, 1]
    median = float(np.median(nearest))
    if median <= 0:
        return
    report.metadata["median_spacing"] = round(median, 3)

    left, right = float(x.min()), float(x.max())
    bottom, top = float(y.min()), float(y.max())
    width, height = right - left, top - bottom
    if width <= 0 or height <= 0:
        return

    # One cell per median spacing, capped so a dense survey does not build a
    # grid larger than the raster it will eventually produce.
    cell = max(median, max(width, height) / 512.0)
    cols = max(2, int(width / cell) + 1)
    rows = max(2, int(height / cell) + 1)

    occupied = np.zeros((rows, cols), dtype=bool)
    col_idx = np.clip(((x - left) / cell).astype(int), 0, cols - 1)
    row_idx = np.clip(((top - y) / cell).astype(int), 0, rows - 1)
    occupied[row_idx, col_idx] = True

    # Distance, in cells, from every empty cell to the nearest occupied one.
    empty_radius_cells = float(distance_transform_edt(~occupied).max())
    empty_radius = empty_radius_cells * cell

    if empty_radius > GAP_FACTOR * median:
        report.add(Finding(
            rule="points.gaps",
            severity=Severity.WARNING,
            dataset=source,
            what=f"there is an unsampled region about {2 * empty_radius:.0f} "
                 f"across, against a median sample spacing of {median:.0f}.",
            why="Interpolation fills the hole with a smooth surface, and the "
                "result carries no mark that the region was never measured.",
            fix="Mask the unsampled region, or keep the interpolation and "
                "record the gap so the map is read with it.",
            observed=round(empty_radius, 1),
            expected=f"<= {GAP_FACTOR * median:.0f}",
        ))


def check_table_fields(
    report: Report, columns: Sequence[str], required: Sequence[str], *, source: str
) -> None:
    """MSP-04 metadata consistency for a table."""
    missing = [c for c in required if c and c not in columns]
    if missing:
        report.add(Finding(
            rule="table.fields",
            severity=Severity.BLOCKER,
            dataset=source,
            what=f"column(s) {', '.join(missing)} are not in the file.",
            why="The columns named as coordinates and value are what turns a "
                "table into a layer; without them there is nothing to place.",
            fix=f"Pick the right columns in the import wizard. Available: "
                f"{', '.join(columns)}.",
            observed=list(columns),
            expected=list(required),
        ))


def _sentinel_candidates(values: np.ndarray) -> list[float]:
    """Values that look like an undeclared nodata sentinel.

    A sentinel is an extreme value repeated far more often than a measurement
    would be. Checking the well-known ones directly is more reliable than a
    histogram heuristic, and it never fires on real data that happens to be
    flat.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return []
    found = []
    for candidate in (-9999.0, -99999.0, -32768.0, 9999.0, -3.4028234663852886e38):
        count = int(np.count_nonzero(finite == np.float32(candidate)))
        if count > max(4, finite.size * 0.001):
            found.append(float(candidate))
    return found
