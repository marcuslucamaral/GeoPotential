# Britain — aeromagnetic total-field anomaly (Pennines window)

The first **real magnetic survey** in this repository. Until it arrived, every
gate on the potential-field module — reduction to the pole, analytic signal,
tilt, upward continuation — ran on a synthetic field this project generated
itself, which tests the arithmetic and not the data.

| | |
|---|---|
| Source | British Geological Survey, GB aeromagnetic survey |
| Redistributed by | [`fatiando-data/britain-magnetic`](https://github.com/fatiando-data/britain-magnetic) v1 |
| DOI | https://doi.org/10.5281/zenodo.5879260 |
| Licence | CC-BY 4.0. *Contains British Geological Survey materials © UKRI 2021.* |
| Original licence | Open Government Licence |
| Upstream SHA256 | `4e00894c2e0fa5b9c547719c8ac08adb6e788a7074c0dae9fb1b2767cf494b38` (`britain-magnetic.csv.xz`) |

The upstream checksum was **verified on download**, against the value the
source publishes, before anything here was written.

## What this file is, and what was changed

`britain_magnetic_pennines.csv` — 4 102 points on 99 flight-line segments,
surveyed 1955-1965, digitised where flight lines crossed contours on the
archive maps.

The upstream file is 21 MB and 541 509 points covering all of Britain. This is
a **window**, not a sample:

    longitude  -3.2 .. -1.6
    latitude   53.2 .. 54.2

Taken as a rectangle and not by random selection, because in potential-field
work the geometry *is* the data: a scattered subset of flight lines would have
a spectrum the original survey does not have, and the radial spectrum and the
continuation operators would then be gated against an artefact.

Nothing else was changed. Columns, values, units and datum are upstream's.

## Reading it

`britain_magnetic_pennines.meta.json` declares the CRS, the unit and which
columns are coordinates — a CSV has nowhere to say any of that, and this
project refuses to guess.

**The coordinates are geographic** (`EPSG:4326`), which is deliberate: a
metric operation on degrees is refused by name, so this file is also what
proves that refusal against real data rather than against a fixture written to
trigger it.

| Column | Meaning |
|---|---|
| `line_and_segment` | flight line and segment identifier |
| `year` | survey year |
| `longitude`, `latitude` | WGS 84 degrees |
| `height_m` | flight height, metres |
| `total_field_anomaly_nt` | total-field magnetic anomaly, nT |
