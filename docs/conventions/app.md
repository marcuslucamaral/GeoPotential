# Application-layer and interface rules

The application layer is the product's boundary: it opens projects, starts and
supervises the worker, submits jobs, records outcomes, and draws. **It computes
nothing.**

## Where things may not go

- **No scientific rule in QML.** No business rule, no filesystem access, no
  SQLite, no GDAL, no NumPy, no provenance decision. QML composes, binds and
  animates; Python assembles the objects.
- **No `import geopotential_worker`.** The boundary is the protocol. The gate
  fails on it, with one named exemption for `self_test.py`.
- **QtCore only** in `viewmodels/`, `models/`, `controllers/`, `ipc/` and
  `project/`, through `utils/qtcore.py`. The moment one of them can name a
  `QColor` it is making a painting decision and the separation is gone.
- **No Qt at all** in `project/`. The Project Store is exercised without an
  event loop.
- **No file reading** in `render/`. Rendering is numpy in, pixels out, so it
  can be gated without a window. The one seam in `map_item.py` is named in
  `docs/ARCHITECTURE.md` and closes at M4.

## Qt Quick

- **Expose state as a `Property` with a `NOTIFY` signal.** A `Slot` that
  returns a value is read once, and QML has no way to know the answer changed.
- **The QML import path is the directory *containing* `GeoPotential/`**, since
  a module's directory name is its module name. Point it at the module
  directory itself and you get `module "GeoPotential" is not installed`, after
  which every `Theme.*` binding is `undefined` — which presents as a theme bug
  rather than an import one. That happened; it cost a build.
- **Pass the controller with `setInitialProperties` against a `required
  property` on the root**, not as a context property: a context property leaves
  one binding pass running against `null`.
- **Do not name the root `window`.** QML has a `window` attached property that
  wins the lookup inside a `Loader`. Use `appWindow`.
- **Parent every QObject handed to QML**, or the engine's garbage collector
  deletes it and every binding that reads it raises on `null`.
- A `Label` is not a `Control` and has no `hovered`. Use a `HoverHandler`.
- Slots the interface calls twice — `startWorker` on `Component.onCompleted`
  and again from a headless driver — are **idempotent**. Refusing belongs in
  the supervisor, not in the boundary the UI touches.

## Tokens

Every colour, spacing, radius, control height and font size resolves through
`qml/GeoPotential/Theme.qml`. Nothing outside it names a colour.

**A theme change may only repaint. It must never move anything.** No metric
token depends on `dark`. Verify by comparing captures, not by eye.

## Units, CRS and labels

- **Say the unit next to the value, and make the unit follow the CRS.** A pixel
  size suffixed `m` beside a geographic CRS states a falsehood on screen. The
  inspector shows `CRS unit` and `Value unit` as separate rows because they are
  separate things.
- **Show the CRS wherever a coordinate is shown.** A coordinate without its CRS
  is a pair of numbers.
- **A dimensionless quantity says so.** `membership [0-1]` on the colour bar,
  not a bare number.
- Keep precision appropriate. Six decimals of a UTM metre is noise.
- **Label every AI/ML feature as AI or ML.** IDW, fuzzy membership, AHP and WLC
  are deterministic numerical methods and never carry an AI badge.
- **State the scientific boundary** where a result is shown: spatial
  favourability is not a resource, a reserve, thermal or electrical power, or
  economic viability.
- State destructive versus non-destructive semantics. A colormap change is
  display-only and says so; recomputing with a new gamma writes a file and says
  that too.

## The paint path

`QQuickPaintedItem.paint` runs on the **render thread** in the real
application, and on the GUI thread under `offscreen`. Two segmentation faults
lived in that gap, and no gate could see them.

- **No pyproj, no GDAL handle shared with the GUI thread, no network, no signal
  emitted** from inside `paint`. Resolve it before the frame; defer a signal
  with `QTimer.singleShot(0, …)`.
- **`QSG_RENDER_LOOP=basic`** is set in `run_gui`, so the canvas paints on the
  GUI thread. It is the configuration, not an accident: the canvas reads a
  GeoTIFF while it paints and the readout reads the same handle.
- **A worker thread has no event loop.** `QTimer.singleShot` there never fires;
  come back with a `Signal`, which Qt queues to the receiver's thread.
- `tools/interaction_check.py` is where this is proved. It runs in the gate and
  reports `BLOCKED` without a display.

## Display fields go through one list

Anything the display stack publishes for a layer reaches the canvas through
`STYLE_KEYS`, passed as a whole. Rebuilding that dictionary by hand is how
`pointSize`, `symbol` and `outline` went missing while `colormap` worked — a
control that moves and changes nothing.

## The basemap

- **Display only**, always under everything, and **never the active layer**:
  the Inspector and the colour bar read the active layer, and a basemap has no
  unit, no range and no value under the cursor.
- **Open sources only**, each with the attribution its licence obliges, shown
  on the map. A source is verified by fetching a tile and counting its colours
  (`tools/verify_sources.py`) — a licence page does not say whether the CDN
  answers an anonymous client. One did not, and wrote `API KEY REQUIRED` across
  the map.
- The mosaic is drawn at **the extent it was warped for**, so it moves with the
  data instead of being stretched into the current frame.

## State and flow

- **One authoritative application state.** The Project Store is it;
  `AppController` publishes it. No panel keeps a shadow copy, and no view holds
  a domain object of its own.
- **A step whose inputs are missing is disabled with the reason visible**, not
  enabled into a modal warning after the click. A navigator section that has
  not landed names its milestone.
- **The GUI never blocks on computation.** Every long operation is a job, with
  real progress and working cancellation. `wait_for_ready` and `pump` exist for
  headless gates and say so in their docstrings; the interactive application
  reacts to signals.
- **An error reaches the user as a safe message with the failing stage and the
  affected dataset.** The traceback goes to the worker log, and the dialog
  shows the reference that finds it.
- **Nothing partial is ever recorded.** Artefacts are held until the run
  commits; a cancelled or failed job registers nothing.

## Maps and colour

- Sequential for non-negative magnitude, distance and membership; diverging
  **centred exactly on zero** for a signed field; categorical for classes and
  masks. `RdBu` under a `[0, 1]` suitability map implies a midpoint that does
  not exist.
- A diverging table has an **odd** number of entries, so zero gets an entry of
  its own and equal departures either side get equal colours.
- Every map has a colour bar with its unit.
- **Nodata renders as nodata** — transparent, or a declared colour — never as
  the low end of the ramp.
- The map is the largest region at normal desktop sizes.

## Evidence

Capture the real running application, never a mockup, and drive the run to
completion first: a screenshot of an empty canvas proves the shell loaded and
nothing else. Sample pixels when the claim is about colour; measure in pixels
when the claim is about alignment.
