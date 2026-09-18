# Project State — GeoPotential Professional (MSP)

Updated: `2026-09-18`
Version: app `0.8.10`, worker `0.5.06`, protocol `1.0.0`, project schema `1.3.0`
Tree: `geopotencial_msp/`
Target: `./run.sh` — Qt Quick shell over a separate Python scientific worker

## Active milestone

ID: `M8` — Hardening e Release Candidate
Plan: `docs/milestones/` — **not written yet**; it is the next thing to write.
Status: `NOT STARTED`
Entry gate: `OPEN` — M7's exit gate is green, 34/34. The Linux build already
exists and gates itself (`V-BUILD-linux.md`); M8 is what turns it into a
release: `.deb`, CI, SBOM, notices, clean-machine install.
Exit gate: `NOT_RUN`

Exactly one milestone may be active.

Completed: `M0` (reality check and baseline), `M1` (vertical slice), `M2`
(runtime, Project Store and recovery), `M3` (Data Manager and QA/QC), `M4`
(native GeoCanvas), `M5` (Decision Engine), **`M5.5` (professional interface,
closed `2026-09-03`, `V-M5_5-interface.md`)** and **`M5.6` (gridding: sparse
data becomes a criterion, closed `2026-09-03`, `V-M5_6-gridding.md`)** and
**`M5.7` (the interpolator is measured, not supposed, closed `2026-09-03`,
`V-M5_7-interpolation.md`)** and **`M5.8` (the shell repaginated: icons, a
rail, a Processing menu, closed `2026-09-03`, `V-M5_8-shell.md`)** and **`M6` (scenarios, sensitivity and
explainability, closed `2026-09-04`, `V-M6-scenarios.md`)** and **`M7` (potential fields essentials, closed
`2026-09-04`, `V-M7-potential-fields.md`)**. What each
did not deliver is listed below and carried forward.

Decisions in force: `ADR-MSP-001` (the application layer is Python),
`ADR-MSP-002` (the display stack derives from the registry and is not a domain
representation), `ADR-MSP-003` (display-only coordinate transformation),
`ADR-MSP-004` (preview crosses the IPC bounded, decimated and declared),
`ADR-MSP-005` (overlap is compared in one CRS), `ADR-MSP-006` (an open-source
basemap, off by default, attributed, never an input), `ADR-MSP-007` (three
interpolators, and the choice between them is measured on the survey itself).

## Last known good baseline

| Item | Value |
|---|---|
| Environment | conda `mcda_geo`, Python 3.11.14, PySide6 6.10.1, numpy 2.4.1, rasterio 1.4.4, geopandas 1.1.2, pyproj 3.7.2, shapely 2.1.2, scipy 1.17.0 |
| Dataset | **Four sources, and every file under `../data/` is gated by `--only data-coverage`.** `../data/britain_magnetic/` — real BGS aeromagnetic, 4 102 points, CC-BY, DOI `10.5281/zenodo.5879260`; `../data/bushveld_gravity/` — real NOAA gravity, 3 877 stations, CC-BY, DOI `10.5281/zenodo.6511942`; `../data/natural_earth/` — the tree's only GeoJSON; `../data/southern_africa/` — **one region, several kinds**: a 2048² topography raster in `EPSG:3857` against 14 359 scattered gravity points in `EPSG:4326`, with the Bushveld stations 100 % inside them. `../data/conditioning_factors/` — 20 landslide-susceptibility layers, EPSG:5186, exercised by `--only other-domain` and the `other_domain` storyboard, which is what proves the MCDA path is not geothermal-only. `../data/utah_forge/Distance_to_fault.tif` — EPSG:26912, 10 m, 979x821, 83.9% valid; 14 derived defective datasets in `../data/synthetic/msp/broken/`; two 4096x4096 rasters with overviews in `../data/synthetic/msp/canvas/` |
| Regression result | `PASS` — **37 of 37** checks: 1000 unit/contract/integration tests plus 59 interface checks, 12 storyboards (61 frames), and a real-window interaction check |
| Architecture gate | `PASS` — 84 modules; **negative-tested 11/11** |
| Validation report | `V-M0-M1-vertical-slice.md`, `V-M2-runtime-recovery.md`, `V-M3-data-manager-qc.md`, `V-M4-geocanvas.md`, `V-M5-decision-engine.md`, `V-M5_5-interface.md`, `V-M5_6-gridding.md`, `V-M5_7-interpolation.md`, `V-M5_8-shell.md`, `V-M6-scenarios.md`, `V-M7-potential-fields.md`, `V-DOMAIN-landslide.md`, `V-BUILD-linux.md` in `docs/validation/` |
| Visual evidence | storyboards `images/flow/` (5), `images/gridding/` (4), `images/interpolation/` (5), `images/m4/` (8), `images/m5/` (6), `images/m55/` (6), `images/other_domain/` (5), `images/potential_fields/` (4), `images/scenarios/` (4), `images/shell/` (4) and `images/themes/` (4) and `images/demo/` (5), each with a contact sheet and a checked report |
| Build artefact | `dist/geopotential/` — **`0.8.07`, rebuilt `2026-09-17`**, Linux x86_64, 617 MB installed, 258 MB compressed, `geopotential-0.8.07-linux-x86_64-20260917.tar.gz`, sha256 `6b37ac27…78e0`. **Gated by its own `--self-test`, 59/59, in `env -i`**; 27 operators announced by the worker inside the bundle. `V-BUILD-linux.md` |

Reproduce with `./tools/run_gate.sh` from `geopotencial_msp/`. The
`interaction` check needs a display and reports `BLOCKED` without one.

## Protected contracts

These must stay green through every milestone.

| ID | Contract | Gate |
|---|---|---|
| P-01 | The worker imports no Qt, in any form | `architecture_check.sh` |
| P-02 | The app imports no worker package (`self_test.py` exempted, named) | `architecture_check.sh` |
| P-03 | The two copies of `protocol.py` are byte-identical | `architecture_check.sh`, `--only protocol` |
| P-04 | `viewmodels/`, `models/`, `controllers/`, `ipc/`, `project/` are QtCore-only | `architecture_check.sh` |
| P-05 | The Project Store imports no Qt | `architecture_check.sh` |
| P-06 | `render/` reads no files (one named seam in `map_item.py`) | `architecture_check.sh` |
| P-07 | No server, no listening port, no WebView, no web framework. Network only for a declared basemap source, chosen by the operator (ADR-MSP-006) | `architecture_check.sh`, `--only basemap`, `--self-test` 18/19 |
| P-08 | No seismic vocabulary | `architecture_check.sh` |
| P-09 | One software-version source per package | `architecture_check.sh` |
| P-10 | Every membership returns `[0,1]` on valid pixels and NaN elsewhere | `--only membership` |
| P-11 | A degenerate range is refused, never silently mapped to 0.5 | `--only membership` |
| P-12 | An unmapped categorical class is refused by code | `--only membership` |
| P-13 | No default CRS; a source without one is refused by name | `--only domain`, `--self-test` 16 |
| P-14 | A metric operation on a geographic CRS is refused | `--only domain` |
| P-15 | Pixel size is two numbers, never averaged | `--only domain` |
| P-16 | `NORMALIZED` carries no unit and is checked in `[0,1]` at construction | `--only domain` |
| P-17 | A RAW criterion cannot be aggregated; the refusal names it | `--only domain`, `--self-test` 15 |
| P-18 | `CriterionStack.names` is the canonical criterion order | `--only domain` |
| P-19 | Criteria on different grids cannot be stacked | `--only domain` |
| P-20 | A message is exactly one JSON line; the envelope is never shadowed | `--only protocol` |
| P-21 | A protocol major mismatch blocks; it never degrades | `--only protocol` |
| P-22 | `Succeeded` is reachable only from `Committing` | `--only protocol` |
| P-23 | A committed run cannot be updated or deleted | `--only store`, `--self-test` 9 |
| P-24 | An output is never silently overwritten | `--only store` |
| P-25 | An artefact cannot exist without a run | `--only store` |
| P-26 | Parameters enter the content key, canonically serialized | `--only store` |
| P-27 | Deleting the cache never destroys a run | `--only store` |
| P-28 | Every GeoTIFF declares `nodata=NaN`; the hash matches the bytes | `--only io-render`, `--self-test` 8/10 |
| P-29 | A failed write leaves no temporary file | `--only io-render` |
| P-30 | A sentinel nodata becomes NaN on read | `--only io-render` |
| P-31 | Nodata renders transparent, never as a ramp value | `--only io-render`, `--self-test` 14 |
| P-32 | A signed field gets a diverging ramp centred exactly on zero | `--only io-render` |
| P-33 | Screen/map round-trip is exact; north is up; scale is uniform | `--only io-render` |
| P-34 | The worker is a separate process, started once, shut down cleanly | `--self-test` 3/4/34 |
| P-35 | Progress is real and monotonic per stage | `--self-test` 6 |
| P-36 | Cancellation commits no run and registers no artefact | `--self-test` 17 |
| P-37 | The value under the cursor equals the stored pixel | `--self-test` 13 |
| P-38 | An interrupted job becomes `Interrupted`, never `Succeeded` | `--only recovery`, `--self-test` 24/28 |
| P-39 | An orphan file is listed, never adopted or registered | `--only recovery`, `--self-test` 30 |
| P-40 | A surviving `.tmp` is discarded and the removal recorded | `--only recovery`, `--self-test` 31 |
| P-41 | A session that did not close is visible to the next open | `--only recovery`, `--self-test` 29 |
| P-42 | The job journal is write-ahead and closes only after commit | `--only recovery` |
| P-43 | Recovery is idempotent | `--only recovery`, `--self-test` 33 |
| P-44 | Closing the window terminates the child, even when wedged | `--self-test` 34 |
| P-45 | A killed worker is detected and can be restarted; the project survives | `--self-test` 25/26/27 |
| P-46 | Undo never reverts a committed run; the barrier says why | `--only commands`, `--self-test` 23 |
| P-47 | A refused command changes nothing and is not logged as done | `--only commands` |
| P-48 | An import cannot be undone once a run references it | `--only commands` |
| P-49 | The four log channels are separate; a `detail_ref` resolves | `--only recovery`, `--self-test` 21 |
| P-50 | The exported diagnostic contains no scientific data | `--only recovery`, `--self-test` 22 |
| P-51 | Relink reports whether content still matches; it never enforces | `--only recovery` |
| P-52 | A registered artefact can never be discarded as an orphan | `--only recovery` |
| P-53 | Describing a dataset creates no row and commits no run | `--only import`, `--self-test` 20 |
| P-54 | Each defective fixture raises its declared rule and severity | `--only qc`, `--self-test` 21 |
| P-55 | Every finding names the dataset, the reason and the correction | `--only qc`, `--self-test` 22 |
| P-56 | A BLOCKER refuses the import; the refusal quotes the verdict | `--only import`, `--self-test` 23 |
| P-57 | A declared value clears its blocker and is recorded as an assertion | `--only qc`, `--only import`, `--self-test` 24 |
| P-58 | Every verdict is recorded, refusals included | `--only import`, `--self-test` 25 |
| P-59 | A raster operation carries a resource estimate with its assumptions | `--only describe`, `--self-test` 26 |
| P-60 | A WARNING informs without blocking | `--only qc`, `--self-test` 27 |
| P-61 | An unvalidated dataset cannot be imported | `--only import` |
| P-62 | The six MSP-03 formats are read and described | `--only describe` |
| P-63 | The description carries no arrays across the IPC boundary | `--only describe` |
| P-64 | Severity is ranked explicitly, never by string order | `--only qc` |
| P-65 | Values from QML are coerced before reaching the protocol | `--only import`, `--self-test` 20-27 |
| P-66 | Filling a screen reads a fraction of a large raster | `--only canvas`, `--self-test` 28 |
| P-67 | The level of detail follows the scale, monotone and deterministic | `--only canvas`, `--self-test` 29 |
| P-68 | The chosen level never under-resolves the screen | `--only canvas` |
| P-69 | The coordinate round-trip is exact under pan, zoom and resize | `--only canvas`, `--self-test` 30 |
| P-70 | **The value under the cursor comes from the source, not the tile** | `--only canvas`, `--self-test` 31 |
| P-71 | A null reads as absent, never as zero, at every level | `--only canvas` |
| P-72 | The tile cache is bounded by bytes and is discardable | `--only canvas`, `--self-test` 34 |
| P-73 | The same view renders identically; nulls stay transparent at every level | `--only canvas` |
| P-74 | An AOI survives close and reopen with its version and CRS | `--only aoi-diff`, `--self-test` 32 |
| P-75 | Editing an AOI creates a version and preserves the previous one | `--only aoi-diff` |
| P-76 | An AOI without a CRS or with fewer than three vertices is refused | `--only aoi-diff` |
| P-77 | A difference is A−B pixel by pixel, checked against numpy | `--only aoi-diff` |
| P-78 | A difference against a null is null, never zero | `--only aoi-diff` |
| P-79 | Mismatched grids are refused by name, and commit nothing | `--only aoi-diff` |
| P-80 | `render/` reads no files; `raster/` does no painting | `architecture_check.sh` |
| P-81 | Harmonization brings every layer onto one target grid | `--only pipeline`, `--self-test` 37 |
| P-82 | The extent policy is chosen and recorded, never assumed | `--only pipeline` |
| P-83 | A categorical layer cannot be resampled by averaging | `--only pipeline` |
| P-84 | A geographic target CRS is refused for a metric grid | `--only pipeline` |
| P-85 | AHP weights are the principal eigenvector and sum to 1 | `--only decision`, `--self-test` 39 |
| P-86 | Row `i` of the matrix binds to criterion `i` of the stack | `--only decision` |
| P-87 | `CR >= threshold` refuses; only a recorded override proceeds | `--only decision`, `--self-test` 40/41 |
| P-88 | Beyond 10 criteria Saaty's RI table is refused, not extrapolated | `--only decision` |
| P-89 | A non-reciprocal matrix or an off-scale judgment is refused | `--only decision` |
| P-90 | Gamma 0 is the product, 1 the sum, and it lies between them | `--only decision` |
| P-91 | Gamma outside `[0,1]` is refused | `--only decision` |
| P-92 | Every operator agrees about nulls: a score needs every criterion | `--only decision` |
| P-93 | Weights must sum to 1; renormalizing silently is refused | `--only decision`, `--only pipeline` |
| P-94 | A constraint is boolean and multiplies; a factor is weighted | `--only decision` |
| P-95 | Outside a mask the result is null, never zero | `--only decision` |
| P-96 | Correlated criteria are named, with what to do about them | `--only decision`, `--only pipeline` |
| P-97 | A shared hierarchical group silences the double-counting warning | `--only decision` |
| P-98 | The aggregation matches an independent numpy calculation | `--self-test` 42 |
| P-99 | The manifest reproduces the run: inputs, hashes, grid, order, params | `--only pipeline`, `--self-test` 43 |
| P-100 | Every interface storyboard captures and passes its frame checks | `--only storyboards` |
| P-101 | The display stretch belongs to the layer, not to the view | `storyboards` (m4 `back_to_fit`) |
| P-102 | The membership curve is drawn over its histogram | `storyboards` (m5 `membership_editor`) |
| P-103 | The state of every workflow step derives from the store, never written by hand | `--only workflow`, `--only menus` |
| P-104 | A blocked step names what is missing and executes nothing | `--only workflow` |
| P-105 | Every enabled menu entry has an action; every disabled one carries its reason on the label | `--only menus` |
| P-106 | The display stack enters no manifest and no aggregation | `--only layers` |
| P-107 | Hiding or reordering layers changes no value read from the source | `--only layers`, `--self-test` 13 |
| P-108 | Removing a layer from the view removes nothing from the project | `--only layers` |
| P-109 | The AOI is drawn only while its tool is on | `--only tools`, storyboard `m55` |
| P-110 | Cancelling a drawing records nothing | `--only tools` |
| P-111 | A colormap or a style limit never rewrites an artefact | `--only layers` |
| P-112 | Every ramp keeps nodata transparent; a diverging ramp has an odd count centred on zero | `--only layers`, `--only io-render` |
| P-113 | Exactly one tool mode is active, and the toolbar reads the canvas | `--only tools` |
| P-114 | A measurement is refused on a geographic CRS and matches an independent calculation | `--only tools` |
| P-115 | A failure belongs to its own job, never to a panel-wide banner | `--only menus` |
| P-116 | Repeating a job creates a child run and records its parent | `--only commands`, `--only store` |
| P-117 | The `preview` block is bounded, declares decimation, and is never an operator input | `--only preview`, `--only describe` |
| P-118 | Previewing creates no row in the store and commits no run | `--only preview`, `--only import` |
| P-127 | Extents are compared in one CRS; a disjoint layer is reported at import and refused at harmonization | `--only qc`, `--only import` |
| P-128 | A point layer is drawn without a Python loop over its points | `--only preview` |
| P-119 | Declaring a CRS, reprojecting data and reprojecting the view are three separate acts | `--only coordinates` |
| P-120 | The display transform is unreachable from `project/` and `commands/` | `architecture_check.sh`, `--only coordinates` |
| P-121 | Every coordinate is shown with what it is in, in the chosen format | `--only coordinates` |
| P-129 | A warped view leaves the file byte-identical, and the cursor still reads the source | `--only coordinates` |
| P-122 | No interface path depends on an input only a gate supplies | `--only menus`, storyboard `flow` |
| P-123 | A theme change only repaints: every panel keeps its rectangle | `--only theme`, storyboard `themes` |
| P-130 | Every basemap source is open, and carries the attribution its licence obliges | `--only basemap` |
| P-131 | With no basemap chosen, nothing on the network is touched | `--only basemap` |
| P-132 | A basemap is a picture: no operator accepts one, and the worker never hears of it | `--only basemap` |
| P-133 | No server, no listening port, no WebView, no web framework | `--only basemap`, `architecture_check.sh` |
| P-134 | A basemap is never the active layer: the Inspector and the colour bar read a layer that has values | `--only basemap` |
| P-135 | The basemap mosaic is drawn at the extent it was warped for, so it moves with the data | `--only basemap` |
| P-136 | A basemap with no data still gets a view, and a small pan asks for no new tiles | `--only basemap` |
| P-137 | Every basemap source was verified by fetching a tile, not by reading its licence | `tools/verify_sources.py` |
| P-138 | A point's shape is a mask over the marker, never a file read per point | `--only preview`, `--only layers` |
| P-139 | A vector silhouette is drawn without a Python loop over its vertices | `--only preview` |
| P-140 | Exactly one map in the shell is `mapCanvas`, and none is anonymous | `--only menus` |
| P-141 | The description carries only plain Python types across the IPC | `--only describe` |
| P-142 | An artefact is labelled by the operator that produced it, never by a fixed unit | `--only menus` |
| P-143 | High contrast reaches 7:1 on text and borders, measured | `--only theme` |
| P-144 | Preferences are stored outside every project, and an unknown value falls back | `--only theme` |
| P-145 | No catalogue key is written twice | `--only theme` |
| P-146 | The output grid is declared — CRS, pixel and area — and recorded in the manifest | `--only gridding` |
| P-147 | A grid that cannot fit is refused before allocating, naming what to reduce | `--only gridding` |
| P-148 | IDW does not extrapolate: the result stays inside the samples' interval | `--only gridding` |
| P-149 | A cell without enough samples in the radius is null, never filled | `--only gridding` |
| P-150 | A radius and a distance are refused on a geographic CRS | `--only gridding` |
| P-151 | The euclidean distance honours an anisotropic pixel | `--only gridding` |
| P-152 | Rasterizing transfers an existing value and never estimates one | `--only gridding` |
| P-153 | No Python loop iterates cells or samples in the gridding path | `--only gridding` |
| P-154 | The Inspector shows the active layer's own statistics, not the last dataset described | `--only menus`, storyboard `gridding` |
| P-124 | Every visible string comes from the catalogue, in both languages | `--only i18n` |
| P-125 | A toolbar glyph the font cannot draw fails the gate | `--only tools` |
| P-126 | A language change only re-letters: the geometry is identical | storyboard `m55` |
| P-155 | A linear interpolant reproduces a linear field exactly | `--only interpolation` |
| P-156 | Outside the convex hull the result is null, never the nearest sample | `--only interpolation`, storyboard `interpolation` |
| P-157 | The cubic's overshoot is measured and recorded, never clamped (ADR-MSP-007) | `--only interpolation`, storyboard `interpolation` |
| P-158 | Collinear samples are refused by name, and the refusal names the method that works | `--only interpolation` |
| P-159 | The comparison scores every method on the same samples, and is deterministic | `--only interpolation` |
| P-160 | Comparing methods commits no run and registers no artefact | `--only interpolation`, storyboard `interpolation` |
| P-161 | Every icon button carries a tooltip; an empty one fails the gate | `--only tools`, storyboard `shell` |
| P-162 | Every icon named in the shell is a file that exists | `--only tools` |
| P-163 | The icon set matches its generator; no icon is edited by hand | `--only tools` |
| P-164 | An icon is tinted on the CPU, so it draws under the offscreen platform | `--only tools`, storyboard `shell` |
| P-165 | The rail is a panel: it hides, it is remembered, and it returns identical | storyboard `shell` |
| P-166 | Leaving one criterion out is the same aggregation with n-1; renormalising is reported | `--only scenarios` |
| P-167 | Rankings are compared over the cells every scenario answered | `--only scenarios` |
| P-168 | The decomposition is exact for WLC and declared for the fuzzy operators | `--only scenarios` |
| P-169 | A scenario that cannot be computed is refused by name | `--only scenarios` |
| P-170 | A scenario overwrites nothing; the parents stay intact | `--only scenarios`, storyboard `scenarios` |
| P-171 | Every `scenarios.*` is read-only: no run committed, no artefact registered | `--only scenarios`, storyboard `scenarios` |
| P-172 | A manifest that cannot reproduce a run is refused, not written | `--only scenarios` |
| P-173 | The scenarios screen measures and decides nothing | storyboard `scenarios` |
| P-174 | Every sensitivity number carries the sample size it was measured over | `--only scenarios`, storyboard `scenarios` |
| P-175 | A potential-field operator is measured against the closed form, never another FFT | `--only potential-fields` |
| P-176 | The convention travels in every manifest and shows on screen | `--only potential-fields`, storyboard `potential_fields` |
| P-177 | Border mode, fraction, taper and sizes go into every manifest | `--only potential-fields`, storyboard |
| P-178 | A non-hermitian response is refused, never taken as `.real` | `--only potential-fields` |
| P-179 | A null in the input stays null in the output | `--only potential-fields` |
| P-180 | Downward continuation is refused by name | `--only potential-fields` |
| P-181 | A geographic CRS is refused: in degrees `|k|` is not a wavenumber | `--only potential-fields` |
| P-182 | RTP at low inclination warns before running, and says what to use instead | `--only potential-fields`, storyboard |
| P-183 | A derivative is labelled per length; the tilt in radians | `--only potential-fields`, storyboard |
| P-184 | The radial spectrum returns the curve and no depth (section 23) | `--only potential-fields` |
| P-185 | A transform that needs the vertical derivative is refused on a field declared as not potential, and the refusal names what still works | `--only potential-fields`, storyboard `potential_fields` |
| P-186 | What the data is has no default: it is declared, and it goes into the manifest | `--only potential-fields` |
| P-187 | A class layer can be a criterion, and the class table goes into the provenance | `--only other-domain`, storyboard `other_domain` |
| P-188 | A direction uses a circular membership; a negative azimuth is refused, never wrapped | `--only other-domain`, storyboard `other_domain` |
| P-189 | `.csv` and `.tif` reach one analysis only through harmonization; aggregating before it is refused by name | `--only mixed-sources` |
| P-190 | The aggregate's valid fraction equals the intersection of the criteria's masks, under either extent policy | `--only mixed-sources` |
| P-191 | The writer refuses to overwrite an existing artefact, and the refusal leaves both the file and no `.tmp` behind | `--only mixed-sources` |
| P-192 | The membership editor opens on the active layer, reading the same description the Inspector reads; without a layer it says what is missing | `--only menus` |
| P-193 | A raster's class codes are read from the file and listed with their share of the valid pixels; a continuous field is reported as having none | `--only describe` |
| P-194 | `categorical` cannot be applied while any class is unscored, and the screen says how many are missing; a score outside `[0, 1]` does not count as scored | `--only menus`, storyboard `other_domain` |
| P-195 | Both extent policies can be measured before either is chosen, by a read-only probe that registers no run and writes no artefact; an empty intersection comes back as an answer, not a failure | `--only mixed-sources`, storyboard `gridding` |
| P-196 | The scored area is the same under either policy — a score needs every criterion, so the union adds extent and no score — and the estimate states the grid it was estimated on | `--only mixed-sources`, storyboard `gridding` |
| P-197 | A class legend is read from the sidecar, the `.aux.xml` RAT or its category names, in that order; an unreadable legend is an absent one and never stops the raster being used | `--only describe` |
| P-198 | The screen states where a legend came from, and a code the legend does not name stays visibly unnamed and still scoreable | `--only menus`, storyboard `other_domain` |
| P-199 | Every file under `../data/` is a format the product reads, is readable by `describe`, and has provenance in its directory; the gate walks the tree rather than naming files | `--only data-coverage` |
| P-200 | Every data file reaches the science, not only the reader: all 19 landslide layers in one aggregation, both unused Utah surveys gridded, and the real magnetic survey through the potential-field operators | `--only data-coverage` |
| P-206 | Opening a project puts its data back on screen — the registered datasets, then the artefacts of its committed runs, in that order | `--only menus` |
| P-207 | An anchor belongs to the layer it was derived from; changing layer clears it, and a description arriving later never overwrites what was typed | `--only menus` |
| P-208 | A layer is described once: a second request while one is in flight is not a second job | `--only menus` |
| P-204 | Applying a membership produces the normalized map it promises, and re-applying to the same layer replaces its criterion instead of adding a second one | storyboard `flow` |
| P-205 | `decision.membership` and `decision.aggregate` accept the same membership vocabulary; a function usable in one is not refused by the other | `--only decision`, `--only menus` |
| P-202 | The decision screen's request is assembled in one place and the shell forwards every key the operator declares; `weights` travel with the method that uses them and with the source that produced them | `--only menus`, storyboard `flow` |
| P-203 | A run that finishes puts its result on the layer stack — a map that exists on disk and not on screen is not a result | storyboard `flow` |
| P-201 | One region carries several kinds of measurement — a raster against a scattered survey, a projected CRS against a geographic one — and they reach one analysis through gridding and harmonization; the overlap is measured, not asserted | `--only data-coverage` |

Every contract `docs/milestones/M5_5_INTERFACE.md` declared now lands:
`P-116` closed with E6, `P-117` and `P-118` with E4, `P-119` to `P-121` with
E5, `P-122` with E6 and `P-123` with E7. The rows above are ordered by when
each was added, not by number.

## What the mixed-source work did not deliver

- **The chain is not one command.** Gridding, harmonising and aggregating are
  three runs and three clicks. That is deliberate — each is a scientific
  decision — but nothing offers the sequence as a recipe.
- **The extent policy has no preview.** `intersection` scores 100 % of the
  cells here and `union` scores 27.7 %, and the person picks before seeing
  either number.
- **`overwrite=True` has no caller.** It exists so a caller that means it can
  say so; nothing in the application says so yet.

## What the cross-domain work did not deliver

- **The class table has no screen.** `categorical` works through the operator
  and is gated; the membership editor cannot edit `{class: score}`, which is a
  real screen — it needs to know which classes the raster holds, and nothing
  probes that today. Whoever uses classes builds the analysis by parameter.
- **Nothing reclassifies a continuous layer into classes.** Aspect in eight
  sectors is what much of the landslide literature does; here the alternative
  is the circular membership, which is continuous.
- **Nothing checks that a layer declared as classes is discrete.** A
  continuous layer with `categorical` would be refused for an unmapped class,
  but by accident rather than by rule.
- **The flat cell stays the operator's decision.** The refusal says what to
  do; the application offers no button that does it.
- **16 of the 20 layers were never exercised** — the forest ones and the
  curvatures take the same path and were not measured.

## What M7 did not deliver

- **Line data and XYZ ingestion with a reduction history.** MSP-14 asks; what
  exists is the grid path. Line direction, spacing and the reduction history
  are metadata QA/QC does not read yet.
- **IGRF.** MSP-15 conditions it on date, position, altitude and unit metadata
  the application does not collect. Running it without them would be inventing
  the reference field.
- **RTE.** The RTP is here; the reduction to the equator is the low-latitude
  case and needs the same stability decision, taken explicitly.
- **Lineament extraction.** MSP-15 asks for it *with human editing and human
  confirmation*. Without the last two it is automatic interpretation, which
  section 23 forbids.
- **Minimum curvature.** MSP-14 conditions it on validation.
- **A side-by-side comparison mode.** The result lands as a layer beside the
  original and the M4 split view exists; wiring them together did not happen.
- **FIS-07, Python/C++ parity.** There is no C++, by ADR-007. Not applicable,
  and recorded as such rather than claimed.
- **Nothing checks that a field *declared* as gravity actually is one.** The
  declaration is the operator's, recorded and enforced; the application does
  not audit it against the data. That is deliberate — inferring "this looks
  like gravity" from a value range is the kind of guess this project does not
  make — and it means a wrong declaration produces a wrong map with correct
  provenance.
- **The radial spectrum has no screen.** The operator exists, is read-only and
  is gated; drawing the curve is a screen that was not built.

## What M6 did not deliver

- **Resolution sensitivity (§17.7).** Re-running the analysis on another grid
  is a full run per resolution, and it depends on harmonisation choices the
  person makes on the M5.5 screen.
- **Optimisation.** Nothing here searches for the best set of weights.
- **Monte Carlo.** The sweep is deterministic, one parameter at a time, and
  that limitation travels with every result.
- **A report as a PDF.** `reporting.report` still points at M8.
- **Scenarios saved across projects.** A scenario lives in the run that made it.
- **The explanation is not on the map.** `scenarios.explain` and
  `scenarios.rank_targets` exist as operators and are gated; the screen uses
  the two sensitivity ones. Clicking a pixel to see its decomposition is next.
- **The limitation line shows in English.** It comes from the worker, which is
  English-only — the gap recorded since M5.5, now visible in one more place.

## What M5.8 did not deliver

- **`icons/jobs/` and `icons/layers/` are still empty.** The jobs panel and
  the layer panel carry their state in text and colour, not in pictures.
- **The rail is not configurable.** What is on it and in what order is in
  `ActivityBar.qml`; a person cannot reorder or prune it.
- **No new keyboard shortcut.** The rail and the Processing menu reach the
  steps; neither has an accelerator.
- **The application icon is not drawn.** `icons/app/` holds interface icons;
  the window and launcher icon M8 needs is not among them.
- **The tooltip is Qt's.** No rich formatting, no delay tuned per control, and
  a disabled control still receives none — which is why every disabled *menu*
  entry keeps its reason on the label.

## What M5.7 did not deliver

- **Kriging.** The next method a geoscientist asks for, and the only common one
  that estimates uncertainty alongside the value. Out because QGIS does not
  ship it in core, and because kriging without variogram fitting on screen is
  kriging with invented parameters.
- **Thin-plate spline.** Measured best of everything on `vp` and on
  `magtellu`, and stayed out anyway: not in QGIS core, and it **failed** with a
  singular matrix on the gravity survey, which has coincident points.
- **A radius proposed from the measurement.** The comparison scores the radius
  that is on screen; it does not search for a better one.
- **The comparison does not run on its own.** It is a button, because a
  cross-validation on every open would spend seconds nobody asked for.
- **Nothing here reaches vector data.** The triangulated methods are offered
  for tables; a polygon layer still has rasterize and distance.
- **The overshoot is not shown after the run.** It is in the manifest and the
  warning appears before running; the Inspector does not read the number back.

## What M5.6 did not deliver

- **Kriging, minimum curvature, splines.** MSP-06 names IDW; a second
  interpolator with no case demanding it is scope nobody asked for.
- **Blocks on disk and memory mapping.** `Policy.BLOCKED` processes in row
  windows, which is what §18.1 asks for first. A grid that fits in neither is
  refused, not paged.
- **Categorical rasterizing with a class table.** Burning a numeric value is
  in; mapping class to code belongs to the criterion editor.
- **`bounds` drawn on the map.** The area is typed. Using the existing AOI as
  the gridding extent is the obvious connection and was not made.
- **Automatic chaining.** Building the grid and harmonising are two steps and
  two clicks. A CSV does not become a criterion by itself, and should not: the
  method is a scientific decision.

## What M5.5 did not deliver

- **Renaming and layer properties have no screen of their own.** Renaming is a
  one-field dialog; "properties" focuses the layer panel, which **is** the
  properties. A second surface with the same controls would be two states of
  one thing.
- **Layout persistence remembers visibility, not proportions.** Which panels
  are open survives a restart; where the `SplitView` handles sit does not.
- **`system` does not tell "unknown" from "dark".** Qt reports `Unknown` on
  platforms that cannot answer, and this application's default is dark, so only
  an explicit `Light` changes what is painted.
- **A vector on the canvas is the preview's silhouette, not the data.** Capped
  at 2 000 vertices by ADR-MSP-004, with no selection, no picking and no
  attribute table bound to the map. §10.2 stays open; M6 is where it is needed.
- **The worker speaks English.** Its own messages do not go through the
  catalogue; only the application is bilingual.
- **`grid.idw` and `grid.euclidean_distance` are still planned**, and still
  marked for an M5 that has closed. MSP-06 asks for both.

## What M5 did not deliver

- **A comparison-matrix editor.** The Decision Model shows the weights and the
  consistency ratio; the judgments themselves are entered as operator
  parameters. With 10 criteria that is 45 judgments, and the screen for them
  belongs with M6's scenario work.
- **Hillshade and vector criteria on the canvas.** Carried from M4 and still
  open; both wait for a producer — a DEM operator, and a vector criterion.
- **Presets.** MSP-07 lists "presets documentados". The membership functions
  are documented and their parameters are recorded per run, but there is no
  named, saved preset to reuse across projects.

## What M4 did not deliver

- **Vectors on the canvas.** §10.2 asks for LOD simplification, spatial
  indexing, selection and picking of vector layers. The raster path is built and
  gated; the vector path is not. Carried to M5, where the criteria that need it
  arrive.
- **Hillshade and progressive preview.** §10.1 lists both. Hillshade needs a DEM
  and a stated illumination convention — M5. Progressive preview needs an
  asynchronous read; the current read is 4–9 ms on the fixture, so there is
  nothing yet to hide behind a preview.
- **`QQuickRhiItem`, `QSGRenderNode`, shaders.** §10 permits them *when
  necessary*; no measurement has established necessity.
- **A country-scale mosaic.** 4096 × 4096 proves the read is
  screen-proportional; it says nothing about a multi-gigabyte VRT.

## What M3 did not deliver

- ~~**The Project Hub's surfaces.**~~ **Delivered in M4**: create, open,
  duplicate and recent projects, with the recovery report shown on open.
  Relink remains a command without a screen.
- ~~**The Data Inspector as a screen.**~~ **Delivered in M4**: the panel is
  split into THE DATA (the worker's full-resolution statistics, with the
  histogram drawn) and THE VIEW (level of detail, pixels read, cache). The
  transformation history is not there — there are no transformations yet.
- **The grid engine itself.** M3 delivers the *planner*; reprojection,
  resampling, rasterization, distance and IDW are M5. The planner's estimate
  has not been checked against a real operator's peak RSS.
- **Vertical datum transformation.** Presence is reported as INFO; no transform
  between vertical datums exists.

## What M2 did not deliver

- **Project Hub.** The recovery *pass* and the relink/import *commands* exist
  and are gated, but the surfaces of §9.1 — create, open, recover, duplicate,
  relink, recent projects — do not. Nothing in QML calls `relinkDataset` or
  `importDataset` yet. Carried into M3.
- **Power-loss durability.** The kills are `SIGKILL` on a process. SQLite is in
  WAL mode and the writer `fsync`s before rename, but nothing tests a
  filesystem that lies about `fsync`.
- **Concurrency.** One worker, one job at a time. Queue, scheduler and
  backpressure are §18.1 and are not built.

## What M1 did not deliver

Named so the absence is a choice on record, not an oversight. `PLANO_REFATORACAO.md`
§4 assigns each to a milestone.

- ~~**Project Hub.**~~ Partly closed by M2: the recovery pass, relink and
  import exist as gated commands. The **UI** of §9.1 does not — carried to M3.
- ~~**Commands and undo.**~~ **Delivered in M2**: a command stack with
  undo/redo, an audit trail in `command_log`, and an irreversible barrier at
  every committed run.
- ~~**Recovery.**~~ **Delivered in M2**: session rows, a write-ahead job
  journal, orphan and `.tmp` reconciliation, worker restart, and the four kill
  tests.
- **Import Wizard, Data Inspector, QA/QC.** No dataset can be added through the
  interface; the slice runs on a path from the command line — M3.
- **Grid engine.** No reprojection, resampling, rasterization, IDW, distance
  transform or resource planning — M3/M5.
- **GeoCanvas at scale.** No LOD, overviews, tiles, cache, pan, zoom, vector
  layers, AOI, split view or difference map. The canvas draws one raster
  fitted to the item — M4.
- **The decision engine.** AHP, consistency ratio, Fuzzy Gamma/Product/Sum and
  weighted combination are declared in the registry as `PLANNED` and are not
  implemented — M5.
- **Scenarios, sensitivity, explainability, target ranking** — M6.
- **Gravity and magnetics** — M7.
- **Export, manifests as files, reports** — M6/M8. The manifest exists inside
  the run record; nothing writes it out.
- **Packaging.** No `.deb`, no clean-machine install, no SBOM — M8.

## Open blockers

| ID | Blocker | Required decision/evidence |
|---|---|---|
| ~~B-M01~~ | ~~Application-layer language contradicts ADR-007.~~ **RESOLVED 2026-09-01**: Python/PySide6, `docs/decisions/ADR-MSP-001`. Every other §2.2 rule preserved and gated. | Closed. |

**No blocker is open.**

## Milestone roadmap

| ID | Title | Status |
|---|---|---|
| M0 | Reality check and baseline | `PASS` |
| M1 | Skeleton Qt Quick integrado | `PARTIAL` — vertical slice `PASS`; remaining surfaces carried into M3 |
| M2 | Runtime, Project Store e recovery | `PASS` |
| M3 | Data Manager e QA/QC | `PASS` |
| M4 | GeoCanvas nativo | `PASS` |
| M5 | Geothermal Decision Engine | `PASS` |
| M5.5 | Interface profissional | `PASS` — closed `2026-09-03` |
| M5.6 | Gridding: dado esparso vira critério | `PASS` — closed `2026-09-03` |
| M5.7 | O interpolador é medido, não suposto | `PASS` — closed `2026-09-03` |
| M5.8 | Interface repaginada: ícones, trilha, Processamento | `PASS` — closed `2026-09-03` |
| M6 | Cenários e explicabilidade | `PASS` — closed `2026-09-04` |
| M7 | Potential Fields Essentials | `PASS` — closed `2026-09-04` |
| M8 | Hardening e Release Candidate | `NOT STARTED` — **active** |
| M9 | Piloto e MSP 1.0 | `NOT STARTED` |

## Completed milestones

| Milestone | Result | Validation report |
|---|---|---|
| M0 Reality check and baseline | `PASS` | `docs/validation/V-M0-M1-vertical-slice.md` |
| M1 Vertical slice | `PASS` | `docs/validation/V-M0-M1-vertical-slice.md` |
| M2 Runtime, Project Store, recovery | `PASS` | `docs/validation/V-M2-runtime-recovery.md` |
| M3 Data Manager and QA/QC | `PASS` | `docs/validation/V-M3-data-manager-qc.md` |
| M4 GeoCanvas nativo | `PASS` | `docs/validation/V-M4-geocanvas.md` |
| M5 Geothermal Decision Engine | `PASS` | `docs/validation/V-M5-decision-engine.md` |
| M5.5 Interface profissional | `PASS` | `docs/validation/V-M5_5-interface.md` |
| M5.6 Gridding | `PASS` | `docs/validation/V-M5_6-gridding.md` |
| M5.7 Interpolação medida | `PASS` | `docs/validation/V-M5_7-interpolation.md` |
| M5.8 Interface repaginada | `PASS` | `docs/validation/V-M5_8-shell.md` |
| M6 Cenários e explicabilidade | `PASS` | `docs/validation/V-M6-scenarios.md` |
| M7 Potential Fields Essentials | `PASS` | `docs/validation/V-M7-potential-fields.md` |
