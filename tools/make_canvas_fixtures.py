#!/usr/bin/env python3
"""Generate the fixtures the M4 canvas gate needs.

Gate M4 asks that "raster grande abre sem bloquear UI". Proving that needs a
raster genuinely larger than a screen: the real Utah FORGE grid is 979 x 821,
which a canvas can read whole without noticing, so it cannot demonstrate
anything about level of detail.

Two fixtures, both seeded, both derived and regenerable, both written to
`../data/synthetic/msp/canvas/` — `../data/` stays the only dataset directory.

  `large_field.tif`     4096 x 4096, tiled, with internal overviews. Big enough
                        that reading it whole to fill an 800 x 600 window would
                        be reading 35 times more pixels than the screen can
                        show, which is exactly the waste the gate measures.
  `large_field_b.tif`   the same grid, a different field. For the split view
                        and the difference map, which need two rasters that
                        actually align.

Both are smooth synthetic fields, not noise: a decimated read of noise looks
like different noise, and nothing about level of detail would be visible.

    tools/make_canvas_fixtures.py            write them
    tools/make_canvas_fixtures.py --force    overwrite
    tools/make_canvas_fixtures.py --check    report whether they are present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling

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


_DATA = _data_dir()
OUT = _DATA / "synthetic" / "msp" / "canvas"

SEED = 20260901
SIZE = 4096
PIXEL = 10.0
ORIGIN_X, ORIGIN_Y = 330_000.0, 4_270_000.0
EPSG = 26912  # the same zone as the real dataset, so extents are comparable

OVERVIEWS = (2, 4, 8, 16, 32)


def _field(seed: int, features: int) -> np.ndarray:
    """A smooth field built from a few Gaussian bumps.

    Smooth on purpose: a decimated read of a smooth field still looks like the
    field, so a level-of-detail change is visible as detail appearing rather
    than as the picture changing entirely.
    """
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    field = np.zeros((SIZE, SIZE), dtype=np.float32)
    for _ in range(features):
        cx, cy = rng.uniform(0, SIZE, 2)
        sigma = rng.uniform(SIZE / 24, SIZE / 6)
        amplitude = rng.uniform(-40.0, 60.0)
        field += amplitude * np.exp(
            -((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2)
        )
    # A hole of nodata, so nulls are exercised at every level of detail.
    hole = ((x - SIZE * 0.72) ** 2 + (y - SIZE * 0.28) ** 2) < (SIZE * 0.06) ** 2
    field[hole] = np.nan
    return field


def _write(path: Path, values: np.ndarray) -> None:
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": SIZE,
        "width": SIZE,
        "crs": CRS.from_epsg(EPSG),
        "transform": Affine(PIXEL, 0, ORIGIN_X, 0, -PIXEL, ORIGIN_Y),
        "nodata": float("nan"),
        "compress": "deflate",
        "predictor": 3,
        # Tiled, because a windowed read of a striped GeoTIFF reads whole rows:
        # the level-of-detail work would be undone by the file layout.
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values, 1)
    # Internal overviews: with them a decimated read is a lookup instead of a
    # resampling, which is the difference `Level.native` reports.
    with rasterio.open(path, "r+") as dst:
        dst.build_overviews(OVERVIEWS, Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")


def build() -> list[dict[str, object]]:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for name, seed, features, note in (
        ("large_field.tif", SEED, 14, "the layer under test"),
        ("large_field_b.tif", SEED + 1, 14,
         "a second field on the same grid, for split view and difference"),
    ):
        _write(OUT / name, _field(seed, features))
        with rasterio.open(OUT / name) as src:
            made.append({
                "file": name,
                "note": note,
                "width": src.width,
                "height": src.height,
                "pixels": src.width * src.height,
                "overviews": src.overviews(1),
                "tiled": bool(src.profile.get("tiled")),
                "size_mb": round((OUT / name).stat().st_size / (1 << 20), 1),
            })
    (OUT / "MANIFEST.json").write_text(
        json.dumps({
            "seed": SEED,
            "crs": f"EPSG:{EPSG}",
            "pixel_size": PIXEL,
            "note": "Derived, seeded and regenerable. Large enough that reading "
                    "the whole raster to fill a screen would read tens of times "
                    "more pixels than the screen can show — which is what the "
                    "M4 gate measures.",
            "fixtures": made,
        }, indent=2),
        encoding="utf-8",
    )
    return made


def main() -> int:
    if "--check" in sys.argv:
        manifest = OUT / "MANIFEST.json"
        if not manifest.exists():
            print(f"canvas fixtures: ABSENT — run {Path(__file__).name}")
            return 1
        entries = json.loads(manifest.read_text())["fixtures"]
        missing = [e["file"] for e in entries if not (OUT / e["file"]).exists()]
        if missing:
            print(f"canvas fixtures: INCOMPLETE — missing {', '.join(missing)}")
            return 1
        print(f"canvas fixtures: PRESENT — {len(entries)} rasters, "
              f"{entries[0]['width']}x{entries[0]['height']}")
        return 0

    if (OUT / "MANIFEST.json").exists() and "--force" not in sys.argv:
        print(f"already present in {OUT}; use --force to regenerate")
        return 0
    made = build()
    print(f"wrote {len(made)} canvas fixtures to {OUT}")
    for entry in made:
        print(f"  {entry['file']:22s} {entry['width']}x{entry['height']} "
              f"({entry['pixels']:,} px), overviews {entry['overviews']}, "
              f"{entry['size_mb']} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
