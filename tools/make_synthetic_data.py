#!/usr/bin/env python3
"""Generate small synthetic fixtures with known content.

Written rather than downloaded so every gate can state what the answer should
be. A fixture whose correct result nobody can compute by hand tests that the
code runs, not that it is right — see `docs/conventions/test-data.md`.

The set deliberately spans the CRS cases that break GIS code:

  utm_field.tif        projected, metres, SIRGAS 2000 / UTM 22S, anisotropic
                       pixels (25 x 40 m) so an averaged pixel size is visible
  wgs84_field.tif      geographic, degrees, WGS 84, overlapping area
  blocks.shp           polygons, UTM 22S
  traverse.gpkg        lines, WGS 84
  stations.csv         point table, UTM 22S, comma separated
  stations_wgs84.txt   point table, WGS 84, whitespace separated

Every raster carries a nodata hole so null handling is exercised, and every
value is a closed-form function of position so a sampled value can be checked.

    python3 tools/make_synthetic_data.py [--out data/synthetic] [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# The synthetic survey area, in SIRGAS 2000 / UTM zone 22S (EPSG:31982).
UTM_CRS = "EPSG:31982"
WGS_CRS = "EPSG:4326"
ORIGIN_X, ORIGIN_Y = 600_000.0, 9_600_000.0
UTM_WIDTH, UTM_HEIGHT = 160, 120
PIXEL_X, PIXEL_Y = 25.0, 40.0  # deliberately not square


def analytic_field(xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    """A smooth signed field: two gaussians and a linear ramp.

    Signed on purpose - it is the case that needs a diverging colormap, and
    the case where a sequential ramp hides the zero crossing.
    """
    peak = 40.0 * np.exp(-(((xx - 0.35) ** 2 + (yy - 0.6) ** 2) / 0.03))
    trough = -30.0 * np.exp(-(((xx - 0.72) ** 2 + (yy - 0.3) ** 2) / 0.02))
    ramp = 12.0 * xx - 5.0 * yy
    return (peak + trough + ramp).astype("float32")


def write_utm_raster(path: Path) -> None:
    import rasterio
    from affine import Affine

    cols = np.arange(UTM_WIDTH)
    rows = np.arange(UTM_HEIGHT)
    grid_x, grid_y = np.meshgrid(cols / UTM_WIDTH, rows / UTM_HEIGHT)
    values = analytic_field(grid_x, grid_y)

    # A nodata hole, so null handling is exercised by every gate that reads it.
    values[20:35, 100:125] = np.nan

    transform = Affine(PIXEL_X, 0.0, ORIGIN_X, 0.0, -PIXEL_Y, ORIGIN_Y)
    profile = {
        "driver": "GTiff",
        "height": UTM_HEIGHT,
        "width": UTM_WIDTH,
        "count": 1,
        "dtype": "float32",
        "crs": UTM_CRS,
        "transform": transform,
        "nodata": np.nan,  # declared, always (ADR-004)
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(values, 1)
        dataset.set_band_description(1, "synthetic anomaly (mGal)")


def write_wgs84_raster(path: Path) -> None:
    """A second raster in degrees, overlapping the UTM one.

    Loading both proves the display reprojection: whichever is loaded first
    sets the project CRS and the other is warped for display only.
    """
    import rasterio
    from affine import Affine
    from pyproj import Transformer

    to_wgs = Transformer.from_crs(UTM_CRS, WGS_CRS, always_xy=True)
    lon_min, lat_min = to_wgs.transform(ORIGIN_X, ORIGIN_Y - UTM_HEIGHT * PIXEL_Y)
    lon_max, lat_max = to_wgs.transform(ORIGIN_X + UTM_WIDTH * PIXEL_X, ORIGIN_Y)

    width, height = 90, 70
    grid_x, grid_y = np.meshgrid(
        np.linspace(0.0, 1.0, width), np.linspace(1.0, 0.0, height)
    )
    values = (
        18.0 * np.sin(3.1 * grid_x) * np.cos(2.4 * grid_y) + 6.0 * grid_y
    ).astype("float32")
    values[0:8, 0:8] = np.nan

    transform = Affine(
        (lon_max - lon_min) / width, 0.0, lon_min,
        0.0, -(lat_max - lat_min) / height, lat_max,
    )
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": WGS_CRS,
        "transform": transform,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(values, 1)
        dataset.set_band_description(1, "synthetic magnetic residual (nT)")


def write_polygons(path: Path) -> None:
    import geopandas as gpd
    from shapely.geometry import box

    cells = []
    names = []
    classes = []
    for row in range(2):
        for col in range(3):
            x0 = ORIGIN_X + 200.0 + col * 1200.0
            y0 = ORIGIN_Y - 4400.0 + row * 1800.0
            cells.append(box(x0, y0, x0 + 900.0, y0 + 1300.0))
            names.append(f"block_{row}{col}")
            classes.append(["granite", "basalt", "sediment"][col])

    gpd.GeoDataFrame(
        {"name": names, "lithology": classes, "area_km2": [c.area / 1e6 for c in cells]},
        geometry=cells,
        crs=UTM_CRS,
    ).to_file(path)


def write_lines(path: Path) -> None:
    import geopandas as gpd
    from pyproj import Transformer
    from shapely.geometry import LineString

    to_wgs = Transformer.from_crs(UTM_CRS, WGS_CRS, always_xy=True)
    lines = []
    for index in range(4):
        xs = np.linspace(ORIGIN_X + 100.0, ORIGIN_X + UTM_WIDTH * PIXEL_X - 100.0, 25)
        ys = np.full_like(xs, ORIGIN_Y - 600.0 - index * 1100.0)
        ys = ys + 180.0 * np.sin(np.linspace(0, 3.14, xs.size))
        lon, lat = to_wgs.transform(xs, ys)
        lines.append(LineString(np.column_stack([lon, lat])))

    gpd.GeoDataFrame(
        {"line_id": [f"L{i + 1}" for i in range(len(lines))], "survey": "synthetic"},
        geometry=lines,
        crs=WGS_CRS,
    ).to_file(path, driver="GPKG", layer="traverses")


def write_point_table(path: Path, crs: str, delimiter: str) -> None:
    import pandas as pd

    rng = np.random.default_rng(20260831)  # seeded: the fixture is reproducible
    count = 220
    xs = ORIGIN_X + rng.uniform(0, UTM_WIDTH * PIXEL_X, count)
    ys = ORIGIN_Y - rng.uniform(0, UTM_HEIGHT * PIXEL_Y, count)
    values = analytic_field(
        (xs - ORIGIN_X) / (UTM_WIDTH * PIXEL_X),
        (ORIGIN_Y - ys) / (UTM_HEIGHT * PIXEL_Y),
    )

    if crs == WGS_CRS:
        from pyproj import Transformer

        lon, lat = Transformer.from_crs(UTM_CRS, WGS_CRS, always_xy=True).transform(xs, ys)
        frame = pd.DataFrame(
            {
                "station": [f"ST{i:04d}" for i in range(count)],
                "longitude": np.round(lon, 8),
                "latitude": np.round(lat, 8),
                "bouguer_mgal": np.round(values, 4),
            }
        )
    else:
        frame = pd.DataFrame(
            {
                "station": [f"ST{i:04d}" for i in range(count)],
                "easting": np.round(xs, 2),
                "northing": np.round(ys, 2),
                "bouguer_mgal": np.round(values, 4),
            }
        )

    if delimiter == r"\s+":
        path.write_text(
            frame.to_string(index=False, justify="left"), encoding="utf-8"
        )
    else:
        frame.to_csv(path, sep=delimiter, index=False)


#: What the directory holds, written beside the fixtures.
#:
#: `data/synthetic/` is gitignored — it is generated, not committed — so a
#: README kept only in the repository would vanish on a fresh clone. The
#: `data-coverage` gate requires every data directory to state its provenance,
#: and provenance for generated data is *which generator, with which seed*.
#: So the generator writes it, and regenerating restores it.
README = """# Synthetic fixtures

Generated, seeded and regenerable: `python tools/make_synthetic_data.py`.
**Do not edit anything here by hand**, and do not commit it: the directory is
gitignored and rebuilt from the generator.

Nothing here is a measurement of anything. These files exist so a behaviour can
be exercised without a survey being present, and so it can be exercised on a
file built to have the property under test.

Regenerating must reproduce them byte for byte. A fixture that changes when you
rebuild it is a fixture whose gate measures the generator.

| File | What it carries | CRS |
|---|---|---|
| `utm_field.tif` | raster in a metric CRS | `EPSG:31982` |
| `wgs84_field.tif` | raster in a **geographic** CRS — the pair with the one above is what makes a reprojection test a test | `EPSG:4326` |
| `blocks.shp` (+ `.dbf`, `.shx`, `.prj`, `.cpg`) | polygons; the Shapefile path, which is five files and not one | `EPSG:31982` |
| `traverse.gpkg` | lines; the GeoPackage path, which can hold several layers | `EPSG:4326` |
| `stations.csv` | gravity stations, comma-separated, **with a text `station` column** | declared in the wizard |
| `stations_wgs84.txt` | the same stations, whitespace-separated, in degrees | declared in the wizard |

## The two that are not decoration

`stations.csv` leads with `station`, holding `ST0000`. That column is why the
value-column guess **excludes text**: before `0.8.06` the first non-coordinate
column was guessed as the measurement, and reading the file died converting
`ST0000` to a float, with a bare `ValueError` and no column named. A survey
table with an identifier column is ordinary, and this is the fixture that says
so.

`stations_wgs84.txt` is the same data in the other shape: whitespace-separated,
`.txt`, and in degrees rather than metres. It exercises the separator sniff and
the geographic branch on a table.

## Subdirectories

`msp/broken/` and `msp/canvas/` carry their own `MANIFEST.json`, which is the
contract for what each file is supposed to be wrong about or large about. Read
those, not this file.
"""


def write_readme(path: Path) -> None:
    """The directory's own provenance. See `README` above for why."""
    path.write_text(README, encoding="utf-8")


FIXTURES = {
    "utm_field.tif": write_utm_raster,
    "wgs84_field.tif": write_wgs84_raster,
    "blocks.shp": write_polygons,
    "traverse.gpkg": write_lines,
    "stations.csv": lambda p: write_point_table(p, UTM_CRS, ","),
    "stations_wgs84.txt": lambda p: write_point_table(p, WGS_CRS, r"\s+"),
    "README.md": write_readme,
}


def generate(out_dir: Path, force: bool = False) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, writer in FIXTURES.items():
        path = out_dir / filename
        if path.exists() and not force:
            continue
        writer(path)
        written.append(path)
    return written


def ensure(out_dir: Path) -> Path:
    """Generate the fixtures if they are missing. Used by the test suite."""
    generate(out_dir, force=False)
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "synthetic",
    )
    parser.add_argument("--force", action="store_true", help="rewrite existing fixtures")
    args = parser.parse_args(argv)

    written = generate(args.out, args.force)
    if written:
        for path in written:
            print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    else:
        print(f"fixtures already present in {args.out} (use --force to rewrite)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
