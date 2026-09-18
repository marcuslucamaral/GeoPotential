# Southern Africa — different data types over one region

This directory exists for the case the product is built for and had nowhere to
exercise: **several kinds of measurement over the same ground**, which is what
a multicriteria prospectivity analysis actually consumes.

Utah FORGE has that too, but it is six scattered tables and one raster in one
CRS, all geothermal. The landslide dataset has twenty layers, all rasters, all
on one grid. Neither makes the product cross a raster and a scattered survey in
two different CRSs over one area — which is the ordinary case.

Together with `../bushveld_gravity/`, whose 3 877 stations fall **100 % inside**
the topography raster here, this region carries:

| Layer | Kind | Format | CRS | Quantity |
|---|---|---|---|---|
| `southern_africa_topography.tif` | raster, 2048² with overviews | GeoTIFF | `EPSG:3857` | elevation, m |
| `southern_africa_gravity.csv` | scattered, 14 359 points | CSV + sidecar | `EPSG:4326` | observed gravity, mGal |
| `../bushveld_gravity/` | scattered, 3 877 stations | CSV + sidecar | `EPSG:4326` | Bouguer and disturbance, mGal |

Three things at once that no other directory here forces: a **projected CRS
against a geographic one**, a **raster against scattered points**, and a
**regional survey against a local one over the same rock**.

The Bushveld Complex is the world's largest layered mafic intrusion and hosts
the largest platinum-group reserves known, so the gravity signature and the
topography here are not decoration for each other — they are two views of the
same body.

## Gravity — `southern_africa_gravity.csv`

| | |
|---|---|
| Source | NOAA NCEI, marine and land gravity |
| Redistributed by | [`fatiando-data/southern-africa-gravity`](https://github.com/fatiando-data/southern-africa-gravity) v1 |
| DOI | https://doi.org/10.5281/zenodo.5882430 |
| Licence | CC-BY 4.0 · original: public domain |
| Upstream SHA256 | `f5f8e5eb6cd97f104fbb739cf389113cbf28ca8ee003043fab720a0fa7262cac` |

**Verified on download** against the published value. Whole and unmodified,
decompressed from `.csv.xz`.

Columns: `longitude`, `latitude`, `height_sea_level_m`, `gravity_mgal`. The
value here is **observed gravity**, around 978 000 mGal — not an anomaly. That
is deliberate: `../bushveld_gravity/` carries the corrected fields over the
same region, so the pair is what shows that a raw observation and an anomaly
are different criteria and not two spellings of one.

## Topography — `southern_africa_topography.tif`

| | |
|---|---|
| Source | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Mapzen), zoom 6, `geotiff` endpoint |
| Underlying data | SRTM, GMTED2010, ETOPO1 and national sources, as that project documents |
| Licence | the sources are public domain or permissively licensed; attribution as the registry asks |

### What was changed, and why

The obvious source for this region is
[`fatiando-data/southern-africa-topography`](https://github.com/fatiando-data/southern-africa-topography)
(DOI `10.5281/zenodo.6481379`), and it was downloaded and its SHA256 verified —
`3e3878a4bdf5e2e71cb85bab9d97e4e9733caf7ab5f74c0d799154fad1b41bef`. It is
**netCDF4**, which is HDF5 underneath, and **nothing in the project's declared
environment reads it**: rasterio's GDAL has no HDF5 plugin, `osgeo` exposes no
netCDF driver, and `scipy.io.netcdf` reads netCDF3 only. Installing a driver
would change the environment this project pins, so the file is not here.

What is here instead is a mosaic of the **16 tiles** `6/34..37/35..38`,
downloaded from AWS Terrain Tiles and merged into one GeoTIFF:

* merged with `rasterio.merge`, no resampling — the tiles share a grid;
* written tiled 256×256, deflate with predictor 2, and given overviews
  `2, 4, 8`, so this is also the directory's proof that the canvas reads a
  pyramid instead of a whole raster;
* tagged `GEOPOTENTIAL_UNIT=m`;
* **no nodata declared**, because there is none: values below zero are
  bathymetry, and declaring a sentinel would punch a hole the data does not
  have.

Extent `11.25..33.75` by `-36.60..-16.64` degrees, elevation −5 684 to
+3 389 m — the Cape Basin through the Drakensberg.
