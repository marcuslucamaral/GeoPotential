# Third-party notices

The software in this repository is licensed under **Apache-2.0** (`LICENSE`).
**The data is not.** Every dataset under `data/` keeps the licence it was
published under, and those licences require attribution to travel with any
redistribution — including redistribution inside a packaged build, which
embeds the fixtures.

This file is the single place a redistributor needs to read. Each directory's
own `README.md` is the source, and carries the DOI, the checksum verified on
download, and what was changed.

---

## Data

### `data/britain_magnetic/` — airborne magnetic anomaly

| | |
|---|---|
| Source | British Geological Survey, GB aeromagnetic survey |
| Redistributed by | `fatiando-data/britain-magnetic` v1 |
| DOI | https://doi.org/10.5281/zenodo.5879260 |
| Licence | **CC BY 4.0** · original: Open Government Licence |

> **Contains British Geological Survey materials © UKRI 2021.**

Modified: a rectangular window, longitude −3.2…−1.6, latitude 53.2…54.2, of
the 541 509-point original. Nothing else changed.

### `data/bushveld_gravity/` — observed and preprocessed gravity

| | |
|---|---|
| Source | NOAA NCEI (gravity) and ETOPO1 (topography) |
| Redistributed by | `fatiando-data/bushveld-gravity` v1 |
| DOI | https://doi.org/10.5281/zenodo.6511942 |
| Licence | **CC BY 4.0** · original: public domain |

Unmodified, decompressed from `.csv.xz`.

### `data/southern_africa/` — regional gravity and topography

| | |
|---|---|
| Gravity | NOAA NCEI · DOI https://doi.org/10.5281/zenodo.5882430 · **CC BY 4.0** |
| Topography | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Mapzen), zoom 6 |
| Underlying topography | SRTM, GMTED2010, ETOPO1 and national sources |

Gravity: unmodified. Topography: sixteen tiles `6/34..37/35..38` merged into
one GeoTIFF, tiled with overviews, no resampling. The terrain tiles aggregate
several public-domain and permissively licensed sources without a single DOI,
so this is the weakest provenance in the repository and is marked as such.

### `data/conditioning_factors/` — landslide conditioning factors

| | |
|---|---|
| Source | Kim, J.-C.; Lee, S.; Yoon, H.-Y. — Wangpicheon catchment, Korea |
| Licence | **CC BY 4.0** |

Twenty 10 m `EPSG:5186` GeoTIFFs, unmodified. The associated landslide
inventory is **not** included here: its point coordinates remain with the
external data holder.

### `data/utah_forge/` — geothermal characterisation

| | |
|---|---|
| Source | US DOE, Utah FORGE, via the [Geothermal Data Repository](https://gdr.openei.org/) |
| Licence | as published by the GDR — consult the repository for each dataset |

Unmodified. The published analysis of these layers is the *Geothermics* paper
cited in `NOTICE`.

### `data/natural_earth/` — land polygons

| | |
|---|---|
| Source | [Natural Earth](https://www.naturalearthdata.com/), `ne_110m_land` |
| Licence | **public domain** — no restrictions, attribution appreciated |

Unmodified.

### `data/synthetic/` — generated

Produced by `tools/make_synthetic_data.py`, seeded and regenerable. Not
third-party, not committed, and covered by this repository's own licence.

---

## Runtime dependencies

Installed by the user through `conda` or `pip`, not redistributed here — except
inside a packaged build, where each library's own licence applies as shipped.
The principal ones:

| Package | Licence |
|---|---|
| PySide6 / Qt | LGPL-3.0 (PySide6); Qt under LGPL-3.0 |
| rasterio, GDAL | BSD-3-Clause; GDAL under MIT/X |
| GeoPandas, Shapely, Fiona | BSD-3-Clause |
| pyproj, PROJ | MIT; PROJ under MIT/X |
| NumPy, SciPy, pandas | BSD-3-Clause |
| affine | BSD-3-Clause |
| imageio-ffmpeg, FFmpeg | BSD-2-Clause; FFmpeg under LGPL-2.1+ (build-dependent) |

A packaged build bundles these. **Whoever redistributes such a build carries
their obligations** — notably Qt's LGPL, which requires that the recipient be
able to relink against a modified Qt.

---

## Basemap tiles

The optional basemap fetches tiles from a declared open source, off by default
and display only. Tiles are cached inside the project and are **never**
redistributed with this repository — `tile-cache/` is in `.gitignore` for that
reason. Attribution is drawn on the map whenever the basemap is on.
