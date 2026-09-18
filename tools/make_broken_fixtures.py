#!/usr/bin/env python3
"""Generate the deliberately defective datasets the M3 gate needs.

Section 20 M3 asks for "datasets propositalmente defeituosos". They are
**derived** from `../data/`, not downloaded: derivation keeps the gate
reproducible on any checkout and keeps `../data/` the only dataset directory.

Output goes to `../data/synthetic/msp/broken/`, which is seeded, regenerable
and unversioned — the same rule the rest of `data/synthetic/` follows.

Each fixture encodes exactly one defect, and the defect is named in a sidecar
`MANIFEST.json` alongside the severity the QA/QC rules must return for it. A
fixture whose expected severity is not what the rules produce is a failing
gate, not a fixture to adjust.

    tools/make_broken_fixtures.py            write them
    tools/make_broken_fixtures.py --force    overwrite existing
    tools/make_broken_fixtures.py --check    report whether they are present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS

ROOT = Path(__file__).resolve().parent.parent
def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
OUT = DATA / "synthetic" / "msp" / "broken"
SOURCE = DATA / "utah_forge" / "Distance_to_fault.tif"

SEED = 20260901  # every stochastic step is seeded and the seed is recorded

# A small window of the real dataset. Small enough that the suite is fast,
# real enough that the CRS, pixel size and value range are not invented.
WINDOW = (256, 256)


def _base() -> tuple[np.ndarray, Affine, CRS]:
    """A clean window of the real raster, to break in one way each."""
    with rasterio.open(SOURCE) as src:
        values = src.read(1, window=((0, WINDOW[0]), (0, WINDOW[1]))).astype(np.float32)
        nodata = src.nodata
        if nodata is not None and not np.isnan(nodata):
            values = np.where(values == np.float32(nodata), np.nan, values)
        transform = src.window_transform(((0, WINDOW[0]), (0, WINDOW[1])))
        crs = src.crs
    return np.ascontiguousarray(values), transform, crs


def _write(
    path: Path,
    values: np.ndarray,
    transform: Affine,
    crs: CRS | None,
    nodata: float | None,
) -> None:
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": values.shape[0],
        "width": values.shape[1],
        "transform": transform,
        "crs": crs,
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values.astype(np.float32), 1)


def build(force: bool = False) -> list[dict[str, object]]:
    OUT.mkdir(parents=True, exist_ok=True)
    values, transform, crs = _base()
    rng = np.random.default_rng(SEED)
    made: list[dict[str, object]] = []

    def record(name: str, defect: str, severity: str, rule: str) -> None:
        made.append({"file": name, "defect": defect,
                     "expected_severity": severity, "expected_rule": rule})

    # ---- rasters --------------------------------------------------------

    # No CRS at all. ADR-004: refused by name, never assumed.
    _write(OUT / "no_crs.tif", values, transform, None, float("nan"))
    record("no_crs.tif", "no CRS declared", "BLOCKER", "crs.present")

    # A geographic CRS, with coordinates to match. Metric operations on it are
    # meaningless, so the refusal belongs to the operation, not to the read.
    geo_transform = Affine(0.0001, 0, -112.85, 0, -0.0001, 38.52)
    _write(OUT / "geographic.tif", values, geo_transform,
           CRS.from_epsg(4326), float("nan"))
    record("geographic.tif", "geographic CRS where a metric operation is asked",
           "BLOCKER", "crs.metric_required")

    # A sentinel in the array with nothing declaring it. Every downstream
    # reader then treats -9999 as a measurement.
    sentinel = np.where(np.isnan(values), np.float32(-9999.0), values)
    _write(OUT / "nodata_undeclared.tif", sentinel, transform, crs, None)
    record("nodata_undeclared.tif", "sentinel -9999 in the array, nodata=None",
           "BLOCKER", "nodata.declared")

    # NaN in the array with nodata=None. Defect D-05 of the legacy tree, at
    # all four of its save_geotiff call sites.
    _write(OUT / "nodata_is_nan_undeclared.tif", values, transform, crs, None)
    record("nodata_is_nan_undeclared.tif", "NaN in the array, nodata=None",
           "BLOCKER", "nodata.declared")

    # Nothing valid at all. A criterion with no data is not a criterion.
    _write(OUT / "all_null.tif", np.full(values.shape, np.nan, np.float32),
           transform, crs, float("nan"))
    record("all_null.tif", "every pixel null", "BLOCKER", "coverage.any_valid")

    # Infinities among the valid pixels. NaN is the only null; +/-inf is a
    # computation that went wrong upstream and must not propagate.
    non_finite = values.copy()
    finite_idx = np.flatnonzero(np.isfinite(non_finite))
    picked = rng.choice(finite_idx, size=12, replace=False)
    non_finite.flat[picked[:6]] = np.inf
    non_finite.flat[picked[6:]] = -np.inf
    _write(OUT / "non_finite.tif", non_finite, transform, crs, float("nan"))
    record("non_finite.tif", "+inf and -inf among the valid pixels",
           "BLOCKER", "values.finite")

    # Anisotropic pixels. Legal, but everything that averages px and py is
    # silently wrong on it, so it has to be stated.
    aniso = Affine(30.0, 0, transform.c, 0, -10.0, transform.f)
    _write(OUT / "anisotropic.tif", values, aniso, crs, float("nan"))
    record("anisotropic.tif", "pixel 30 x 10 m", "WARNING", "grid.anisotropic")

    # An extent that does not intersect the others: harmonization would
    # produce an empty grid, which reads as "no favourable area anywhere".
    far = Affine(10.0, 0, transform.c + 500_000.0, 0, -10.0, transform.f + 500_000.0)
    _write(OUT / "disjoint.tif", values, far, crs, float("nan"))
    # ADR-MSP-005: reported at import, refused at harmonization — where an
    # empty intersection actually produces the wrong map.
    record("disjoint.tif", "extent disjoint from the other layers",
           "WARNING", "extent.overlap")

    # Ten times coarser than its neighbours. Resampling it up invents detail.
    coarse = Affine(100.0, 0, transform.c, 0, -100.0, transform.f)
    _write(OUT / "coarse.tif", values[:64, :64], coarse, crs, float("nan"))
    record("coarse.tif", "100 m pixels against 10 m elsewhere",
           "WARNING", "grid.resolution_mismatch")

    # Sparse coverage. A criterion valid on 4% of the grid dominates nothing
    # and is dominated by the null-handling rule instead.
    sparse = np.full(values.shape, np.nan, dtype=np.float32)
    keep = rng.choice(values.size, size=int(values.size * 0.04), replace=False)
    sparse.flat[keep] = values.flat[keep]
    _write(OUT / "mostly_empty.tif", sparse, transform, crs, float("nan"))
    record("mostly_empty.tif", "about 4% of pixels valid",
           "WARNING", "coverage.fraction")

    # ---- tables ---------------------------------------------------------

    left, top = transform.c, transform.f
    n = 400
    easting = left + rng.uniform(0, 2000, n)
    northing = top - rng.uniform(0, 2000, n)
    gravity = -210.0 + rng.normal(0, 3.0, n)

    # Duplicated coordinates carrying different values: which one wins is a
    # scientific decision, and picking silently makes it for the operator.
    dup_e = np.concatenate([easting, easting[:20]])
    dup_n = np.concatenate([northing, northing[:20]])
    dup_v = np.concatenate([gravity, gravity[:20] + 5.0])
    _write_csv(
        OUT / "duplicated_points.csv",
        ["easting", "northing", "gCBGA"],
        [dup_e, dup_n, dup_v],
        source_crs="EPSG:26912",
    )
    record("duplicated_points.csv", "20 coordinates repeated with different values",
           "WARNING", "points.duplicates")

    # A hole in the sampling. Interpolating across it produces a smooth
    # surface over a region where nothing was measured.
    centre_e, centre_n = left + 1000, top - 1000
    outside = (np.hypot(easting - centre_e, northing - centre_n) > 600)
    _write_csv(
        OUT / "gapped_points.csv",
        ["easting", "northing", "gCBGA"],
        [easting[outside], northing[outside], gravity[outside]],
        source_crs="EPSG:26912",
    )
    record("gapped_points.csv", "a 1.2 km sampling hole inside the extent",
           "WARNING", "points.gaps")

    # A table with no source_crs. Coordinates without a CRS are two columns
    # of numbers.
    _write_csv(
        OUT / "no_source_crs.csv",
        ["easting", "northing", "gCBGA"],
        [easting, northing, gravity],
        source_crs=None,
    )
    record("no_source_crs.csv", "no source_crs declared", "BLOCKER", "crs.present")

    # A unit that contradicts the magnitude: Bouguer anomaly in the hundreds
    # is mGal, not g/cm3. Declared units are checked against plausibility.
    _write_csv(
        OUT / "wrong_unit.csv",
        ["easting", "northing", "density"],
        [easting, northing, gravity],
        source_crs="EPSG:26912",
        unit="g/cm3",
    )
    record("wrong_unit.csv", "values near -210 declared as g/cm3",
           "WARNING", "unit.plausible")

    manifest = {
        "generated_from": str(SOURCE.relative_to(DATA.parent)),
        "seed": SEED,
        "window": list(WINDOW),
        "note": "Derived, seeded and regenerable. Each file carries exactly one "
                "defect. `expected_severity` and `expected_rule` are what the "
                "QA/QC rules must return; a mismatch is a failing gate, not a "
                "fixture to adjust.",
        "fixtures": made,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return made


def _write_csv(
    path: Path,
    columns: list[str],
    arrays: list[np.ndarray],
    *,
    source_crs: str | None,
    unit: str | None = None,
) -> None:
    """Write a table, with its CRS and unit in a sidecar rather than guessed.

    A CSV carries no CRS of its own, so the project reads one from a sidecar
    `.meta.json`. Absent, the table is refused by name — never assumed.
    """
    lines = [",".join(columns)]
    for row in zip(*arrays):
        lines.append(",".join(f"{v:.6f}" for v in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sidecar: dict[str, object] = {}
    if source_crs is not None:
        sidecar["source_crs"] = source_crs
    if unit is not None:
        sidecar["unit"] = unit
    sidecar["x_field"] = columns[0]
    sidecar["y_field"] = columns[1]
    sidecar["value_field"] = columns[2]
    path.with_suffix(".meta.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )


def main() -> int:
    if "--check" in sys.argv:
        manifest = OUT / "MANIFEST.json"
        if not manifest.exists():
            print(f"broken fixtures: ABSENT — run {Path(__file__).name}")
            return 1
        entries = json.loads(manifest.read_text())["fixtures"]
        missing = [e["file"] for e in entries if not (OUT / e["file"]).exists()]
        if missing:
            print(f"broken fixtures: INCOMPLETE — missing {', '.join(missing)}")
            return 1
        print(f"broken fixtures: PRESENT — {len(entries)} defective datasets")
        return 0

    if not SOURCE.exists():
        print(f"cannot derive fixtures: {SOURCE} is absent", file=sys.stderr)
        return 2
    if (OUT / "MANIFEST.json").exists() and "--force" not in sys.argv:
        print(f"already present in {OUT}; use --force to regenerate")
        return 0
    made = build(force="--force" in sys.argv)
    print(f"wrote {len(made)} defective datasets to {OUT}")
    for entry in made:
        print(f"  {entry['expected_severity']:8s} {entry['file']:32s} {entry['defect']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
