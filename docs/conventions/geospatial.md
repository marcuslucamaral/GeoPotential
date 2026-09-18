# Geospatial and MCDA domain rules

These are the conventions the science depends on. Breaking one produces a map
that looks correct and is wrong, which is the failure mode this file exists to
stop.

## Coordinate reference systems

- **There is no default CRS.** A layer with no CRS, or a CSV with no
  `source_crs`, stops the run with a message naming the layer. Assuming the
  target CRS "because it is probably already in it" silently reprojects nothing
  and shifts everything.
- The target CRS is chosen once, carried by `TargetGrid`, and every layer is
  reprojected to it before it reaches the grid. No stage re-reads it from the
  config dictionary.
- **A projected CRS is required for any metric operation.** Euclidean distance,
  pixel size in metres, and IDW search radii are meaningless in degrees.
  Refuse the operation on a geographic CRS rather than producing degrees
  labelled as metres.
- State the CRS beside every coordinate shown to a user, and beside every
  coordinate written to a file.

## Grid and pixel size

- One `TargetGrid` per run owns `transform`, `crs`, `width`, `height` and
  `(pixel_size_x, pixel_size_y)`. Every raster in a run is on that grid. A
  second transform living in a per-layer dictionary is a second representation.
- Pixel size carries the unit of the target CRS. A control labelled `m` while
  the CRS is geographic is a defect, not a rounding issue.
- Anisotropic pixels are legal. Any code that collapses `px` and `py` into one
  scalar — averaging them, taking the first, assuming a square pixel — must
  either be corrected or refuse anisotropic input explicitly. Averaging is
  silently wrong everywhere except `px == py`.
- Grid extent is derived from the union of input bounds unless the config gives
  explicit bounds. Record which of the two produced the grid.

## Null values

- **NaN is the single in-memory null.** `float32` arrays, NaN for absent data,
  everywhere, at every stage.
- **Every GeoTIFF written declares its nodata.** Writing NaN into a file whose
  profile says `nodata=None` means every downstream reader treats NaN as data.
- A null must survive every stage. Interpolation fills nulls only where the
  method is defined to do so, and that filling is recorded in provenance.
- Aggregation is defined only where every contributing layer is valid. State
  which rule applies — all-valid, or valid-with-weight-renormalization — and
  apply the same rule in every aggregation operator. Two operators in one
  program disagreeing about nulls is the defect.

## Units and stages

- A `CriterionLayer` is `RAW` or `NORMALIZED`, never both, never unlabelled.
  - `RAW` carries a physical unit: `mGal`, `g/cm3`, `m`, `°C`, `mW/m2`.
  - `NORMALIZED` is a dimensionless fuzzy membership in `[0, 1]`.
- Aggregation accepts `NORMALIZED` only. Passing a raw layer to a Gamma Fuzzy or
  WLC operator is a programming error and must raise, not clamp.
- Normalization is not reversible and must not overwrite the raw values under
  the same name. Keep both, or keep the raw file path in provenance.
- Say the unit in the name, the dataclass field or the docstring. `density` is
  ambiguous; `density_g_cm3` and `units="g/cm3"` are not.

## Fuzzy membership

- Every membership function returns values in `[0, 1]` on valid pixels and NaN
  on invalid pixels. Test both properties, on every function.
- A degenerate range (`hi - lo < eps`) is a real condition, not an edge case to
  paper over. The current behaviour returns `0.5` everywhere; that choice is a
  scientific decision and belongs in an ADR, with the alternative — refusing —
  stated.
- Percentile clamping changes the result. Record the percentiles used in
  provenance; a map made with `[2, 98]` is not the map made with the full range.
- Direction (`higher_is_better`) is part of the scientific claim, not a display
  preference. It belongs in the layer definition and in the manifest.

## AHP

- Follow Saaty. The comparison matrix is square, strictly positive and
  reciprocal; weights come from the normalized principal eigenvector; report
  `lambda_max`, `CI`, `RI` and `CR`.
- **`CR >= 0.10` is a refusal, not a warning.** Do not compute a suitability
  map from an inconsistent judgment matrix without an explicit, recorded
  operator override. Reporting the number and proceeding anyway defeats the
  test.
- The Random Index table is Saaty's, valid to `n = 10`. Beyond that, refuse
  rather than reusing `1.49`.
- **Matrix row `i` binds to criterion `i` of `CriterionStack.names`, and that
  binding must be explicit.** Deriving criterion order from
  `list(some_dict.keys())` at two different call sites is how weights end up on
  the wrong layers with no error anywhere.

## Aggregation

- Gamma Fuzzy: `mu = (1 - prod(1 - mu_i))^gamma * (prod mu_i)^(1 - gamma)`,
  `gamma` in `[0, 1]`. `gamma = 0` is the algebraic product (AND-like),
  `gamma = 1` the algebraic sum (OR-like). Zimmermann and Zysno (1980).
- WLC: `S = (sum w_i v_i) * prod c_j`, weights summing to 1, constraints
  strictly boolean. Renormalizing weights silently changes the result — record
  that it happened.
- **Layer selection is part of the result.** A group filter that matches fewer
  layers than expected must fail loudly. Silently falling back to "aggregate
  everything" produces a different scientific product under the same filename.
- Constraints and factors are different things. A constraint is boolean and
  multiplies; a factor is continuous and is weighted. Do not let one become the
  other through a config field.

## GeoAI

- This is the only part of the project that is ML, and it must be labelled ML
  wherever it is exposed.
- Pseudo-labels are weak supervision derived from the MCDA score by threshold.
  They are not observations. Export them with the thresholds that produced them
  and with the count of uncertain pixels.
- Record the channel order with the tensor. A `(C, H, W)` array with no channel
  names is unusable six months later.
- Filling NaN with `0.0` before export is a decision that biases any model
  trained on it. Keep it explicit, keep the valid mask, and export the mask.

## Reproducibility

- Every completed run writes a manifest: input paths and checksums, CRS, grid,
  per-layer method and parameters, aggregation method and parameters, package
  versions, timestamp.
- Experiment parameters live in `experiments/configs/`, never as literals in
  source.
- Seed every stochastic step and record the seed. Nothing in the current
  pipeline is stochastic; the day something is, this rule already applies.
- Record completed runs in `experiments/REGISTER.md`.
