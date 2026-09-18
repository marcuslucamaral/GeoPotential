# Python rules

GeoPotencial is a Python application end to end. There is no C++ in this
project; a rule that mentions one is stale.

## Layers

The dependency rule is executable, not advisory: `tools/architecture_check.py`
scans imports and fails. Adding an import that breaks it is a red gate, so
check the direction before writing it.

| Layer | May import | Must not import |
|---|---|---|
| `core/crs/` | `pyproj`, `numpy`, stdlib | Qt, plotting, `rasterio`, `geopandas` |
| `core/layers/` | `numpy`, `affine`, `core/crs`, `geospatial` | Qt, plotting, `geopandas`, `pandas` |
| `core/project/` | `core/*` | Qt, plotting |
| `core/io/` | `rasterio`, `geopandas`, `pandas`, `core/*` | Qt, plotting |
| `geospatial/` | `rasterio.warp`, `pyproj`, `numpy` | Qt, plotting |
| `mcda/` | `numpy`, `shapely`, `core/crs`, `geospatial` | Qt, plotting, I/O libraries |
| `visualization/` | `numpy`, `shapely` | Qt, plotting, I/O libraries |
| `viewmodel/` | `core/*`, **QtCore only** via `utils/qtcore.py` | QtGui, QtWidgets, QtQuick, QtQml, `utils/qt.py`, I/O libraries |
| `gui/` | anything, including Qt | — |

`viewmodel/` refusing QtGui is deliberate: the moment it can name a `QColor` it
is making painting decisions and the separation is gone. That is why there are
two shims — `utils/qtcore.py` for view models, `utils/qt.py` for `gui/`.

`core/` refusing Qt is the point. The moment a `QThread` or a `Signal` lives
under `core/`, the arithmetic can no longer be exercised from a plain
`python3 -c` and every numerical gate needs a display.

`core/` refusing `matplotlib` and `plotly` is the same rule applied to output.
A function that computes a raster and also writes an HTML preview cannot be
tested for what it computes.

## Qt binding

- **One binding shim, imported by everything.** The project targets PySide6,
  with the PyQt5 fallback isolated in one module. Thirteen copies of
  `try: from PyQt5 ... except ImportError: from PySide6 ...` is thirteen places
  that drift, and the one that drifted is a bare `from PyQt5.QtWidgets import
  QMessageBox` inside a function body, which raises on a PySide6-only machine.
- No `from ... import *`. It defeats the shim's purpose and hides which symbols
  a module actually needs.
- An import inside a function body is for breaking a cycle or for an optional
  dependency, and it carries a comment saying which. Never for a Qt class.

## Scientific hygiene

- Make array axis order, dtype, units and coordinate conventions explicit — in
  names, in dataclass fields, in docstrings, or in an assertion. `(rows, cols)`
  and `(x, y)` both look right in a debugger and disagree about which is first.
- Rasters are `float32`, row-major, north-up, origin at the top-left of the
  target grid. State it where an array crosses an API boundary.
- Record package and runtime versions for every experiment that lands in
  `experiments/REGISTER.md`.
- Seed every stochastic library a reproducible run touches, and record the seed.
- Do not silently copy large arrays. A full-grid copy per stage per layer is
  the difference between a 200 MB and a 2 GB run on a real survey; when a copy
  is deliberate, say why.
- Keep notebooks and exploratory scripts out of the authoritative package.
- Experiment parameters live in immutable configuration files under
  `experiments/configs/`, never as literals in source.

## Vectorization is a correctness-of-performance rule, not a preference

Python is fast in this project **because** the code dispatches to compiled
kernels. Code that stops doing that loses two orders of magnitude silently.
Measured on this machine (`docs/validation/PERF-backend.md`):

| Operation | vectorized | Python loop | factor |
|---|---|---|---|
| per-pixel scaling, 490k px | 0.25 ms | 22.6 ms | **90×** |
| coordinate transform, 1M pts | 4.1 ms | 692 ms | **169×** |
| geometry walk, 200k polygons | 424 ms (shapely bulk) | 3327 ms | **7.8×** |

So:

- **A per-pixel or per-vertex `for` loop in a draw or processing path is a
  defect**, not a style question. It forfeits a factor the whole language
  decision rests on (ADR-007).
- Walk geometry with shapely's bulk API — `get_parts`, `get_type_id`,
  `get_coordinates(return_index=True)`, `get_exterior_ring` — never one
  geometry at a time.
- **Cull before you compute.** Culling 200k features to the visible 8k took
  0.6 ms and beat every optimization applied after it. Cheap rejection first.
- When a loop is genuinely unavoidable, say why in a comment and record the
  measurement that justified it.

## Configuration

- A configuration is a validated object with named fields, not a
  `Dict[str, Any]` read with `.get()` and a fallback at each use site. The
  fallback chain `config.get("target_crs", config.get("crs", "EPSG:31982"))`
  written in three modules is three chances to disagree, and it converts a
  missing required field into a silent wrong answer.
- Validate once, at the boundary, and fail with the field name.
- No user path baked into source. `~/Downloads/geopotencial_output` is a
  default that belongs in configuration, not in a window constructor.

## Errors

- Raise with the layer name and the field that is wrong. `ValueError("method
  inválido")` costs a debugging session that `ValueError("layer 'density':
  method 'idw2' inválido; use neighbors|euclidean_distance|fixed")` does not.
- Never `except: pass`, and never a bare `except:`. Catch what you can handle,
  name it, and log the rest.
- A background worker reports failure through its error channel with the
  traceback intact. Truncating a traceback to 100 characters for a status bar
  is a display decision; do it in the UI, not in the worker.

## Comments

**A function comment is: what goes in, what comes out, units, and the
reference.**

```python
def points_idw_neighbors(points, value_field, grid, k=8, power=2.0):
    """Inverse distance weighting over the k nearest samples.

    points       point layer in the target CRS; `value_field` in its own unit
    grid         target grid; result is (grid.height, grid.width) float32
    k            neighbours per cell
    power        distance exponent
    returns      interpolated field, same unit as `value_field`, NaN outside
    Shepard (1968), ACM National Conference, sec. 2.
    """
```

That is the whole contract. Someone who wants the derivation goes to Shepard;
a paraphrase above the signature is worse than the paper because it cannot be
checked.

### What does not go in a comment

- The derivation, the theory, or a summary of the paper.
- What the code used to be, what was tried first, or how a bug was found.
  That goes to `docs/decisions/` when it is a decision, `docs/validation/`
  when it is evidence.
- A timing or a measurement. Those age. `docs/validation/` with a date.
- A version banner. `"GeoPotencial v1.3"` in a module docstring while the
  window title says `v1.4` is a version number in two places, and both are
  wrong the moment one changes.

A non-obvious constraint may be stated in one or two lines when the code cannot
state it itself — a unit, an index base, an ordering requirement, a library
behaviour that surprises. One or two lines, not a paragraph.

## Versioning

Scheme and meaning: `docs/VERSIONING.md`. `MAJOR.MINOR.PATCH`, PATCH
zero-padded to two digits (`0.2.03`).

- **One source.** `src/geopotencial/_version.py`. `pyproject.toml` derives it,
  `__init__.py` re-exports it, the build script and `--version` read it. Never
  write a version literal anywhere else — it was in two places until `0.2.03`,
  which is the defect this file already names two sections above.
- **PEP 440 strips the padding.** `0.2.03` is reported by `pip` as `0.2.3`.
  `VERSION` is the project form, `PEP440_VERSION` is derived; packaging reads
  the second. A tag that disagrees with `pip show` is expected, not a bug.
- **Bump by what the user gets**, not by lines changed. A capability is a
  MINOR; a fix, a closed blocker or documentation is a PATCH.
- **Every update gets an entry in `CHANGELOG.md`**, and the entry says what the
  update does *not* deliver. A changelog that only lists gains is how a project
  loses track of its own gaps.
- Tag with a `v` prefix so a tag can never collide with a branch name.
