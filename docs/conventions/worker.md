# Scientific worker rules

This tree is the science. It runs in its own process, it never sees a display,
and everything it writes has to be reproducible from what it records.

## The two rules the gate enforces

- **No Qt, in any form.** A `Signal` or a `QThread` here means the arithmetic
  can no longer be exercised from a plain `python3 -c` and every numerical gate
  needs a window.
- **No plotting, and no web.** A function that computes a raster and also
  renders an HTML preview cannot be tested for what it computes. `matplotlib`,
  `plotly`, `flask`, `fastapi` and their kind fail the build.

`domain/` and `decision/` additionally refuse `rasterio`, `geopandas`, `fiona`
and `pandas`: those two layers are numpy and pyproj, so a numerical gate needs
no files at all.

## stdout belongs to the protocol

**Never `print()`.** One stray line desynchronizes the stream and the
application sees a protocol error instead of a result. stdout is JSON Lines,
one message per line; stderr is the structured worker log; that is the whole
convention.

## Operators

- An operator declares its parameters — **type, unit, documented default,
  range** — and `validate()` returns the *resolved* set, defaults filled in.
  That resolved set, not what the caller sent, is what enters the manifest and
  the content key, so a run made on a default is reproducible from its record.
- **No silent default.** Section 16: every default is documented, editable,
  visible and versioned.
- **Progress is derived from work done.** `ctx.progress(stage, fraction, msg)`
  is called with the fraction actually completed, and is monotonic within a
  stage. A bar advanced on a timer is a defect, not a UX choice.
- **Cancellation is cooperative.** Call `ctx.check_cancel()` between stages and
  inside long loops. A cancelled job registers nothing.
- An operator that changes what it computes gets a new `version`. The version
  is in the content key, so an old run stays findable and a new one is a
  different run.

## Numerical hygiene

- **Rasters are float32, row-major, north-up, origin at the top-left of the
  target grid.** State it where an array crosses an API boundary; `(rows, cols)`
  and `(x, y)` both look right in a debugger and disagree about which is first.
- **NaN is the single in-memory null.** Convert a file's sentinel at read, once,
  and never let a `-9999` travel further.
- **Resolve a transform's parameters over the whole valid population, then
  apply them chunk by chunk.** Resolving per chunk makes each chunk a different
  scientific transform — the bug is invisible and the map looks plausible.
- **A per-pixel Python loop is a defect.** Vectorize, or record the measurement
  that justified not doing so. The factor is 90-169x
  (`../../docs/validation/PERF-backend.md`).
- Seed every stochastic step and record the seed.

## Refusals

Refusing is usually the correct answer, and it is always better than a
plausible number.

- A source with no CRS: refuse, and **name the source**.
- A metric operation on a geographic CRS: refuse. Degrees labelled as metres
  is the failure this rule exists to stop.
- A degenerate value range: refuse. The legacy tree returned `0.5` everywhere,
  which turns an absent gradient into a stated middling suitability.
- A categorical class present in the data but absent from the mapping: refuse.
  Scoring it zero turns a data gap into a scientific claim.
- A RAW criterion reaching an aggregation: raise, and name it. Never clamp.
- `CR >= 0.10`: refuse. Reporting the number and proceeding anyway defeats the
  test.
- A group filter matching fewer layers than expected: fail loudly. Silently
  falling back to "aggregate everything" produces a different scientific
  product under the same filename.

Every refusal names the layer, the field and what would fix it.
`ValueError("method inválido")` costs a debugging session that
`ValueError("layer 'density': method 'idw2' invalid; use neighbors|euclidean_distance|fixed")`
does not.

## Writing

Use `io/writers.py`. It writes `.tmp`, flushes, `fsync`s, **reopens and
validates**, hashes, renames, and only then returns an `Artifact`. Do not write
a GeoTIFF any other way, and never announce a file the writer has not returned.

Every GeoTIFF declares `nodata=NaN`. A raster with `nodata=None` whose array
carries NaN is a contract violation — it was true at all four `save_geotiff`
call sites of the legacy tree, and every downstream reader treated NaN as data.

## Comments

**Inputs, output, units, reference.** Cite the paper or book section and stop.
Saaty (1980) for AHP, Zadeh / Zimmermann for the fuzzy operators, Shepard
(1968) for IDW.

```python
def points_idw_neighbors(points, value_field, grid, k=8, power=2.0):
    """Inverse distance weighting over the k nearest samples.

    points   point layer in the target CRS; `value_field` in its own unit
    grid     target grid; result is (grid.height, grid.width) float32
    k        neighbours per cell
    power    distance exponent
    returns  interpolated field, same unit as `value_field`, NaN outside
    Shepard (1968), ACM National Conference, sec. 2.
    """
```

Not the derivation, not what the code used to be, not a timing. Those go to
`docs/decisions/` and `docs/validation/`.
