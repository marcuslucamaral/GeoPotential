# Bushveld, Southern Africa — observed and preprocessed gravity

Real gravity, in a geological setting that is not Utah and not Korea. The
Bushveld Complex is a layered mafic intrusion, so the Bouguer anomaly here has
an amplitude and a shape the Utah FORGE survey does not: **-113 to +129 mGal**
against Utah's narrow geothermal window.

| | |
|---|---|
| Source | NOAA NCEI (gravity) and ETOPO1 (topography) |
| Redistributed by | [`fatiando-data/bushveld-gravity`](https://github.com/fatiando-data/bushveld-gravity) v1 |
| DOI | https://doi.org/10.5281/zenodo.6511942 |
| Licence | CC-BY 4.0 |
| Original licence | public domain (both sources) |
| Upstream SHA256 | `3fc1daf74a2fc3bcc3cf7f72a632518f8c6b6e306ce12fddf4055d7cb44945c8` (`bushveld-gravity.csv.xz`) |

The upstream checksum was **verified on download**, against the value the
source publishes.

## What this file is

`bushveld_gravity.csv` — 3 877 stations, **whole and unmodified**. It is small
enough that no window was needed, so nothing here is derived: what upstream
distributes is what is in this directory, decompressed.

## Reading it

`bushveld_gravity.meta.json` declares `EPSG:4326`, mGal, and the three columns
that matter. The sidecar names `gravity_bouguer_mgal` as the value, but the
file carries four measurements of the same stations and **which one is the
criterion is a decision**:

| Column | Meaning |
|---|---|
| `longitude`, `latitude` | WGS 84 degrees |
| `height_sea_level_m` | station height above sea level |
| `height_geometric_m` | geometric height above the ellipsoid |
| `gravity_mgal` | observed gravity |
| `gravity_disturbance_mgal` | observed minus normal gravity |
| `gravity_bouguer_mgal` | Bouguer anomaly |

That is the point of having it: `gravity_disturbance_mgal` and
`gravity_bouguer_mgal` are different fields over the same stations, and a
product that let someone pick one by accident would produce a different map
without saying so.
