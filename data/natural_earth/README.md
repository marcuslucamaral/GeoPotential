# Natural Earth — land polygons, 1:110m

The first **GeoJSON** in this repository. `describe` has declared `.geojson`
readable since M3 and nothing here ever held one, so the branch was reachable
only through `.shp` and `.gpkg`.

| | |
|---|---|
| Source | [Natural Earth](https://www.naturalearthdata.com/), `ne_110m_land` |
| Fetched from | [`nvkelso/natural-earth-vector`](https://github.com/nvkelso/natural-earth-vector) |
| Licence | public domain — Natural Earth imposes no restrictions |
| SHA256 | `9e0729ee253ca7d7…` (see `tests/integration/test_data_coverage.py`) |

## What this file is

`ne_110m_land.geojson` — 127 land polygons, WGS 84, whole and unmodified.

It is **not** a criterion and is not meant to become one: there is no value
field, and a coastline is not a measurement. It is here so that the vector
path — reading, extent, geometry kinds, the bounded silhouette the canvas
draws — is exercised on the third of the three vector formats the product
claims to read, in a file nobody in this project wrote.
