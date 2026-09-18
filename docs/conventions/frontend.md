# Frontend rules

The product frontend is **Qt Quick** (`src/geopotencial/gui/quick/`). A Qt
Widgets frontend (`src/geopotencial/gui/`) is retained as a parity oracle and
is gated on every run; it does not grow (ADR-003). Both draw through
`gui/map_renderer.py`.

The legacy tree has its own two frontends — Widgets panels and a Qt Quick shell
over a Leaflet `QWebEngineView` — with the duplicated-state defect this file
describes. They are unmodified; retiring them is M3's job.

The full checklist is
`docs/conventions/visual-evidence.md`, which is how that checklist is
enforced here: with storyboards that assert, not with a list to remember.
What follows must hold on every edit.

## Qt Quick

The product frontend is Qt Quick (ADR-003). `gui/quick/qml/` is the shell;
`viewmodel/` publishes state to it; `gui/map_renderer.py` does the drawing for
both frontends.

- **Expose state as a `Property` with a `NOTIFY` signal.** A `Slot` that
  returns a value is read once and never re-evaluated - QML has no way to know
  the answer changed.
- **Register a QML singleton from an absolute `QUrl`.** A plain path string is
  rejected, the module never registers, and every `Theme.*` binding silently
  becomes `undefined`. It presents as a theme bug.
- **Parent every QObject handed to QML.** A parentless one gets JavaScript
  ownership and the engine's garbage collector deletes it, after which every
  binding that reads it raises on `null`.
- **Pass the controller with `setInitialProperties` and a `required property`
  on the root**, not as a context property: a context property leaves one
  binding pass running against `null`.
- **Load a panel through `Loader.setSource(url, properties)`** when it takes a
  required property, so the property exists before the panel's own bindings run.
- **Do not name the root `window`.** QML has a `window` attached property that
  wins the lookup inside a `Loader`. Use `appWindow`.
- QML declares the interface; it does not assemble the application. Object
  wiring happens in Python.
- Every colour, spacing and size resolves through `Theme.qml`, whose values
  match `gui/theme.py`. Two frontends reading two palettes is how they drift.

## Ownership

- The UI configures and presents domain operations; it never owns an algorithm.
  A panel that computes a statistic, reprojects a coordinate or decides a
  membership is holding domain logic.
- **One authoritative application state.** `Project` is it; `AppController`
  publishes it. No panel keeps a shadow copy it syncs by hand, and no frontend
  keeps a private run configuration. In the legacy tree `ui/main_window.py` and
  `core/qml_backend.py` each own a private `_config` with different CRS and
  pixel-size defaults for the same run — the defect this rule exists for.
- **A view holds no domain object of its own.** `MapItem` constructing its own
  empty `Project` — while every panel showed the real one — is the same defect
  in miniature, and it happened. `bind()` joins the renderer to the
  controller's project.
- The Qt adapter layer belongs in `viewmodel/` or `gui/`, never in `core/`. A
  `Signal` under `core/` means the science needs Qt to run.
- Panels receive the state they need. `self.main` reaching back into the window
  for `config`, `pipeline_data` and `map_widget` couples every panel to the
  whole application.

## Units and labels

- **Say the unit next to the value, and make the unit follow the CRS.**
  A pixel-size control with the suffix `m` while the target CRS is geographic
  is stating a falsehood on screen; the suffix is derived from the CRS or the
  control refuses the CRS.
- A label names its control. Explanations go in a tooltip, never on screen as
  body text competing with the map.
- Show the CRS wherever a coordinate is shown. The status bar prints
  `Lat/Lng` from the Leaflet bridge — those are WGS 84 degrees regardless of
  the target CRS, and the two must not be presented as interchangeable.
- Keep precision appropriate to the measurement. Six decimals of a UTM metre
  is noise; five decimals of a degree is not.
- **Label every AI/ML feature explicitly as AI or ML.** IDW, fuzzy membership,
  AHP and WLC are deterministic numerical methods and must never carry an AI
  badge. GeoAI exports are ML and must say so, and a pseudo-label must be
  presented as weak supervision derived from the score, never as ground truth.
- State destructive versus non-destructive semantics. A display colormap change
  is display-only and says so; recomputing a map with a new gamma overwrites a
  GeoTIFF and says that too.

## State and flow

- The six-step flow — load, rasterize, normalize, AOI, aggregate, export — is
  a dependency chain. A step whose inputs are missing is **disabled with the
  reason visible**, not enabled into a modal warning after the click.
- Completion is derived from the pipeline state, not from a set of indices the
  window mutates on its own.
- A long operation runs off the GUI thread, reports progress, and can be
  cancelled. A cancelled run leaves no half-written GeoTIFF presented as a
  result.
- An error reaches the user with the failing stage and the layer name. The
  traceback goes to the log; the first line goes to the dialog.

## Maps and color

- Diverging colormaps for signed fields (Bouguer anomaly, residuals);
  sequential for non-negative magnitude, distance and membership; categorical
  only for classes and masks. `RdBu` as the default for a `[0, 1]` suitability
  map implies a midpoint that does not exist.
- Every map has a color bar with its unit, or `membership [0-1]` when
  dimensionless.
- Nodata renders as nodata — transparent or a declared color — never as the
  low end of the ramp.
- An overlay on the Leaflet map is reprojected to WGS 84 for display. Placing a
  UTM-bounds image on a lat/lng map by passing metres as degrees puts the layer
  in the Gulf of Guinea.
- The map is the largest region at normal desktop sizes.

## Tokens

- Every color, spacing, radius, control height and font size resolves through
  one theme source: `gui/theme.py` for Widgets, `gui/quick/qml/Theme.qml` for
  Quick, with matching values. In the legacy tree the QSS files, `main.qml`'s
  window properties and inline `setStyleSheet("color: #34d399")` calls make
  three palettes for one application.
- **A theme change may only repaint. It must never move anything.** No metric
  token depends on the mode. Verified by comparing edge maps between the two
  captures, not by eye: 99.68% agreement is "nothing moved".

## Evidence

- Capture the real running application, never a mockup, and never only the
  Plotly HTML the pipeline wrote.
- Compare before and after at the same window size, on the same data.
- Measure alignment in pixels when the claim is alignment.
- Verify every theme, and verify that nothing moved between them.
- A preview widget that loaded a file is not proof the science is right; it is
  proof a file exists.

## Comments

Same contract as `python.md`: what goes in, what comes out, units, reference.
Not the derivation, not the history, not a measurement. Panel constructors
described widget by widget in comments are describing what the next line
already says.
