# Wangpicheon Landslide Susceptibility — Conditioning-Factor Data

Data accompanying:

**"Tabular Foundation Models (TabPFN) Meet Landslide Susceptibility: A Spatially
Leakage-Controlled, Explainable Benchmark in a Korean Mountain Catchment"**
Kim, J.-C., Lee, S., Yoon, H.-Y. *GIScience & Remote Sensing* (in review, 2026).

Nine models (Random Forest, XGBoost, LightGBM, CatBoost, **TabPFN**, ANN, ANN-K, CNN,
SE-CNN) are compared on a 10-m grid (EPSG:5186, Wangpicheon Ecosystem and Landscape
Conservation Area, Korea) under a single leakage-controlled **spatial block
cross-validation** scheme (4×4 blocks, 5-fold × 2-repeat). This repository archives
the input conditioning-factor rasters and the rasterized landslide response grid used
in that study; see the manuscript for the full analytical pipeline and results.

## Contents

```
conditioning_factors/       20 GeoTIFFs (10 m, EPSG:5186) — see DATA_DICTIONARY.csv

DATA_DICTIONARY.csv              per-layer provenance, source, native scale
LICENSE                          CC BY 4.0
```

## Data availability and restrictions

- **Conditioning-factor rasters** (`data/conditioning_factors/`): openly
  released under **CC BY 4.0**. Each of the 20 layers is a 10-m, EPSG:5186
  GeoTIFF (863 rows × 997 columns; nodata = -9999). Provenance, native scale,
  and source agency for every layer are listed in `DATA_DICTIONARY.csv`.
- **Landslide inventory** (`data/landslide_inventory/landslide_presence_10m.tif`):
  released **only as a rasterized 10-m presence/absence grid** (uint8; 1 =
  landslide, n = 116; 0 = background, n = 860,295), by agreement among the
  authors and the third-party data holder. The **exact point coordinates /
  original GPS survey records are withheld** and are not included in this
  release; they remain with the external data provider (not an author of the
  associated manuscript) and are available upon reasonable request, subject to
  the data holder's permission. This is consistent with Taylor & Francis's
  data-sharing policy, which permits withholding data that authors do not have
  the right to fully redistribute, provided the reason is stated (as here).

## Analysis code

The analysis code (preprocessing, model training, cross-validation, mapping)
is not included in this data release. The full methodology — model
architectures, spatial block cross-validation design, preprocessing steps, and
evaluation protocol — is described in the associated manuscript
(Section 3, "Materials and methods"). For questions about the implementation,
contact the corresponding author.

## Citation

If you use this data, please cite:

> Kim, J.-C., Lee, S., & Yoon, H.-Y. (2026). Wangpicheon landslide
> susceptibility: conditioning-factor data set [Data set]. Zenodo.
> https://doi.org/10.5281/zenodo.XXXXXXX

*(DOI to be finalized once this record is published on Zenodo — update this
line and the manuscript's Data Availability Statement / Reference list once
assigned.)*

## License

**CC BY 4.0** — attribution required; source agencies listed in
`DATA_DICTIONARY.csv` must also be credited when redistributing derived
products. See `LICENSE`.
