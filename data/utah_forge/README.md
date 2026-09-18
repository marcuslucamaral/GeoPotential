# Utah FORGE — geothermal characterisation data

The dataset this project developed against from M0 onward. Every gate before
the landslide suite arrived ran here, which is exactly why the landslide suite
had to arrive: a product verified on one survey is verified on one survey.

Utah FORGE is the US Department of Energy's Frontier Observatory for Research
in Geothermal Energy, near Milford, Utah. Data are distributed through the
**Geothermal Data Repository** (GDR), <https://gdr.openei.org/>.

## The published analysis of this data

These layers are the input to a peer-reviewed study, and the method this
application implements is the one that study describes. Read it for what the
criteria mean, how they were weighted, and what the resulting map does and does
not claim:

> do Amaral, M.L.A.; Caldeira, M.C.O.; de Figueiredo, J.J.S.;
> Da Silveira, J.R.B.S. (2026).
> **Integration of geophysical data and multicriteria decision analysis for
> geothermal assessment at Utah FORGE.**
> *Geothermics* **136**, 103590.
> <https://doi.org/10.1016/j.geothermics.2025.103590>

A gate that runs on this directory is therefore checking the software against
data whose analysis is published — which is a stronger position than a fixture
nobody has argued about in print.

All layers are in `EPSG:26912` (NAD83 / UTM zone 12N).

| File | What it is | Unit |
|---|---|---|
| `Distance_to_fault.tif` | Euclidean distance to mapped faults, 979×821 at 10 m, 83.9 % valid | m |
| `anomaly_bouger_easting_northin_bouger.csv` | Bouguer gravity anomaly, 3 735 scattered stations | mGal |
| `density_modified_500m.csv` | Modelled density at 500 m spacing | g/cm³ |
| `vp_500_m.csv` | P-wave and S-wave velocity at 500 m spacing | km/s |
| `top_basement_500m.csv` | Modelled depth to basement | m |
| `magtellu_min_depth_500m.csv` | Magnetotelluric minimum depth | m |

## Why the CSVs matter here

They are **scattered**, not gridded. A CSV cannot be harmonised: it becomes a
raster first, through `Data › Build a grid`, with an interpolator whose choice
is measured on the survey itself (`ADR-MSP-007`). The chain `.csv` + `.tif` in
one analysis is gated by `--only mixed-sources`.

Each carries **more than one value column**, and which one becomes the
criterion is a declaration, never a guess: `vp_500_m.csv` holds both Vp and Vs,
and choosing one produces a different raster from the other.

## What has no sidecar, and why that is the test

None of these CSVs has a `<name>.meta.json`. A table has nowhere to record its
CRS, so the project **reports the absence as a finding** rather than assuming
one — and these files are what that behaviour is checked against. The CRS is
supplied in the wizard, by the person, and recorded as their statement.
