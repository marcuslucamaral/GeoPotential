# Architecture — GeoPotential Professional (MSP)

Status: `IMPLEMENTED` through M5.5; `DECLARED` for M6 onwards
Last verified against source: `2026-09-03`
Enforced by: `tools/architecture_check.py`, 84 modules, negative-tested 11/11

Nothing here is a wish list. Every claim names the gate that supports it, and
anything declared but not implemented says so.

---

## 1. The shape

```
QML — presentation only
   │   Property + NOTIFY · Theme.qml · required property on the root
   ▼
Python / PySide6 — application layer          [ GUI process ]
   controllers/   WorkerSupervisor · JobController · AppController
   viewmodels/    small, one per domain
   models/        QAbstractListModel / QAbstractTableModel
   commands/      the audit trail; nothing changes the domain around it
   project/       Project Store — SQLite, runs, lineage, hash, provenance
   raster/        windowed reads, level of detail, tile cache
   render/        GeoCanvas: viewport arithmetic, colormaps, raster/points/
                  geometry to RGBA — numpy in, pixels out, never a file read
   geo/           display-only coordinate transforms (ADR-MSP-003)
   basemap/       XYZ tiles from declared open sources (ADR-MSP-006)
   i18n/          the string catalogue, two languages
   preferences.py the person's settings, outside every project
   ipc/           the protocol client
   │
   │   QProcess · JSON Lines · stdin/stdout
   │   no HTTP · no localhost · no WebView · no browser
   ▼
Python — scientific worker                    [ separate process, no Qt ]
   domain/            CrsInfo · TargetGrid · Criterion · Stage
   io/                readers · atomic writers · hashing · bounded preview
   decision/          membership · AHP with a blocking CR · fuzzy · WLC
   operators/         the registry; one operator is one versioned contract
   qc/                14 spatial rules, each with its severity and correction
   grid/              harmonization onto one target grid, and the planner
   potential_fields/ scenarios/ reporting/   declared; M6-M8
```

Large arrays never cross the QML boundary and never enter JSON. The worker
writes a GeoTIFF and returns a path, a type and a hash.

The application layer is Python by decision, recorded with its evidence in
`decisions/ADR-MSP-001-camada-de-aplicacao.md`. Every other rule of
`IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §2.2 holds unchanged, and the IPC boundary
is language-agnostic, so the migration question stays open behind the M8 gate.

---

## 2. Layer contracts — enforced

`tools/architecture_check.py` walks the import graph and fails. It is
negative-tested: `--self-check` injects one violation of each class into a copy
of the tree and asserts every one is caught.

| Layer | May import | Must not import | Rule id |
|---|---|---|---|
| `worker/**` | numpy, scipy, rasterio, geopandas, pyproj, shapely, affine | **Qt in any form**, matplotlib, plotly, any web module | `worker-no-qt`, `worker-no-plotting`, `no-web` |
| `worker/domain`, `worker/decision` | numpy, pyproj, affine, stdlib | rasterio, geopandas, fiona, pandas, osgeo | `domain-no-io` |
| `app/**` | Qt, stdlib | `geopotential_worker`, any web module, matplotlib, plotly | `app-no-worker-import`, `no-web`, `app-no-plotting` |
| `app/viewmodels`, `app/models`, `app/controllers`, `app/ipc`, `app/project` | **QtCore only**, via `utils/qtcore.py` | QtGui, QtWidgets, QtQuick, QtQml, `utils/qt.py` | `*-qtcore-only` |
| `app/project` | sqlite3, stdlib | **Qt in any form** | `store-no-qt` |
| `app/render` | Qt, numpy, shapely | rasterio, geopandas, pandas | `render-no-io` |

Two rules subsume most of the table:

1. **Qt does not exist in the worker.** A `Signal` or a `QThread` under
   `worker/` means the arithmetic can no longer be exercised from a plain
   `python3 -c`, and every numerical gate needs a display.
2. **The app does not import the worker package.** The only thing crossing the
   boundary is the protocol. An import here reintroduces the coupling that
   process separation exists to remove, and "kill the worker, restart it" stops
   meaning anything.

### Two named exemptions

Named, because an unnamed exemption is a hole.

- **`app/geopotential_app/self_test.py`** imports the worker package on
  purpose, to exercise the domain guards through the same modules the worker
  runs. It is a test driver, not application code. The exemption is a literal
  set in the checker.
- **`app/geopotential_app/render/geocanvas/map_item.py`** imports `rasterio`
  inside the one function that reads an artefact the store already vouched for.
  It is a seam, and it closes at M4 when overviews and tiles move behind the
  store.

### The protocol is one file in two places

`app/geopotential_app/ipc/protocol.py` and
`worker/geopotential_worker/protocol.py` are **byte-identical**, checked by the
architecture gate (`protocol-mirrors`) and again by the contract suite. The app
cannot import the worker's copy without breaking rule 2, and a hand-maintained
second copy would drift. So: edit the worker's, copy it over, run the gate.

---

## 3. Central representations

**`Criterion` on a `TargetGrid`** is the domain object of one analysis. There
is no second one.

```
CrsInfo      a CRS with the unit it measures in; no default, ever
TargetGrid   transform, crs, width, height; pixel_size is TWO numbers
Criterion    name, values float32 (NaN is the null), grid, stage, unit,
             higher_is_better, provenance
Stage        RAW (carries a physical unit) | NORMALIZED (dimensionless [0,1])
CriterionStack   ordered; `names` is the ONLY criterion order weights bind to
```

The stage split is what makes the legacy tree's primary defect impossible
before a single method is written. In `geopotencial_legacy`,
`core/normalization.py:93` wrote the membership over the raw physical values
under the key `array`, so a raw layer could be aggregated as if normalized and
nothing anywhere would notice. Here:

- `NORMALIZED` may not carry a unit — refused at construction;
- `NORMALIZED` is range-checked in `[0, 1]` at construction;
- `RAW` must declare its unit — refused at construction;
- `require_normalized()` refuses a stack containing a raw criterion **and names
  it**.

### The Project Store

A project is a directory, not a file. SQLite holds the catalogue; **no
scientific grid is ever a blob**. Rasters live in `artifacts/` and the database
holds the path and the hash.

Section 14.4's integrity rules are constraints and code, not prose:

| Rule | How |
|---|---|
| a completed run is immutable | `BEFORE UPDATE`/`BEFORE DELETE` triggers on `run` |
| an output is never silently overwritten | `artifact.path` is `UNIQUE`; a second claim raises |
| an artefact cannot exist without a run | foreign key `artifact.run_id -> run.id` |
| parameters enter the hash | `content_key()` over operator, version, sorted inputs, canonical params |
| serialization is canonical | `canonical_params()` — sorted keys, no insignificant whitespace |
| an external input records size, mtime and hash | `dataset` columns, written by `add_dataset` |
| deleting the cache never destroys a run | `cache/` is referenced by nothing |

---

## 4. The job lifecycle

```
Queued -> Validating -> Running -> Committing -> Succeeded
              ↓            ↓
          Cancelled    Cancelled           (and Failed from any of the four)
```

`Succeeded` is reachable **only** from `Committing`, and `Committing` cannot be
cancelled. Together those two facts are why a partial output can never be
published as a result. Asserted in `tests/contract/test_protocol.py`.

Where each step happens:

1. the operator writes to `.tmp`, flushes, closes, `fsync`s;
2. the writer **reopens and validates** shape, nodata, CRS and transform;
3. the writer hashes the closed file and renames it atomically;
4. the worker emits `job_artifact` — never before step 3;
5. `JobController` **holds** artefacts rather than writing them, because the
   run does not exist yet and the foreign key forbids the orphan;
6. `job_succeeded` arrives, the run commits sealed as immutable, and only then
   are the artefacts registered against it.

A crash between 4 and 6 leaves files on disk that belong to no run — visible to
the recovery pass, and never mistaken for a result.

---

## 5. What is implemented, and what is declared

**Implemented and gated** (see `validation/V-M0-M1-vertical-slice.md`):
`CrsInfo`, `TargetGrid`, `Criterion`, `CriterionStack`, the membership family
(linear increasing/decreasing, sigmoidal, gaussian, small, large, categorical),
raster reading with null normalization, atomic GeoTIFF writing with declared
nodata and hashing, the protocol, the worker server with cooperative
cancellation, the WorkerSupervisor, the JobController, the job model, the
Project Store, colormaps and raster-to-RGBA, viewport arithmetic, the Qt Quick
shell, and the `decision.membership` operator.

**Declared and not implemented**: everything in `registry.PLANNED`, each with
the milestone that owns it. The interface shows them disabled and names the
milestone, rather than offering an operation that fails after the click. The
full list is in `PROJECT_STATE.md` under "What M1 did not deliver".

---

## 6. Relationship to the other trees

- **`../src/geopotencial/`** — the Etapa 0 GIS foundation. The principal source
  of design, and of ported code for CRS, layers, I/O, rendering and the
  criterion contract. It is **not modified** and **not imported**.
- **`../geopotencial_legacy/`** — the behavioural reference for the science.
  `fuzzy.py`, `ahp.py`, `gamma_fuzzy_combine` and `points_idw_neighbors` carry
  the maths this project ports. Its 18 defects are catalogued in
  `../docs/ARCHITECTURE.md` and each port names the defect it forecloses. It is
  **not modified** and **not imported**.
- **`../data/`** — read, never written. The only dataset directory.
- **The reference tree** — engineering practice only. No code, no domain objects, no
  vocabulary. The `no-seismic-vocabulary` rule fails the build on `TraceMatrix`,
  SEG-Y, gathers, NMO, migration and velocity analysis, and that check is
  exercised.

---

## 7. Unverified questions

- Whether the canvas holds up on a country-scale mosaic. One 0.8 Mpx raster has
  been drawn, fitted to the item. M4.
- Whether the worker survives a forced kill during `Running` and during
  `Committing`, and whether the project reopens intact afterwards. M2.
- Whether the membership and aggregation operators agree with an independent
  calculation to a stated tolerance. The range and null contracts are gated;
  numerical agreement is M5.
- Whether the bundle starts on a machine with no development environment. M8.
