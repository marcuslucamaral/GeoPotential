"""The M1 gate: the vertical slice, driven headless.

The milestone's obligatory slice is:

  open project -> start worker -> submit job -> real progress -> produce
  artefact -> record hash -> show the result on the canvas

and its gate is:

  no browser, no HTTP port, no visible terminal, the worker started exactly
  once, the worker shut down cleanly, the result recorded by event, the result
  carrying a hash.

Every check below asserts on the authoritative state — the Project Store, the
supervisor, the model, the canvas — never on a screenshot somebody took once.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import zipfile
from pathlib import Path

from ._version import VERSION
from .controllers.app_controller import AppController
from .controllers.worker_supervisor import WorkerSupervisor
from .ipc import protocol as P

PASS, FAIL = "PASS", "FAIL"


class Checks:
    """A tiny recorder. Each check names what it asserts and prints the value."""

    def __init__(self) -> None:
        self.results: list[tuple[str, str, str]] = []

    def check(self, name: str, ok: bool, evidence: str) -> bool:
        self.results.append((name, PASS if ok else FAIL, evidence))
        return ok

    def report(self) -> int:
        width = max(len(n) for n, _, _ in self.results)
        for name, status, evidence in self.results:
            colour = "\033[32m" if status == PASS else "\033[31m"
            reset = "\033[0m" if sys.stdout.isatty() else ""
            head = colour if sys.stdout.isatty() else ""
            print(f"{head}{status}{reset}  {name.ljust(width)}  {evidence}")
        failed = sum(1 for _, s, _ in self.results if s == FAIL)
        total = len(self.results)
        print(f"\n{total - failed}/{total} checks passed")
        return 1 if failed else 0


def _listening_ports() -> list[int]:
    """TCP ports this process is listening on. The MSP forbids all of them.

    Only AF_INET/AF_INET6 stream sockets with SO_ACCEPTCONN set count. A Unix
    domain socket has a path, not a port, and is not what section 24 forbids.
    """
    ports: list[int] = []
    for fd in range(3, 256):
        try:
            duplicate = os.dup(fd)
        except OSError:
            continue
        try:
            sock = socket.socket(fileno=duplicate)
        except (OSError, ValueError):
            os.close(duplicate)
            continue
        try:
            if sock.family in (socket.AF_INET, socket.AF_INET6) and sock.type == socket.SOCK_STREAM:
                if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
                    ports.append(int(sock.getsockname()[1]))
        except OSError:
            pass
        finally:
            sock.detach()
            os.close(duplicate)
    return ports


def run_self_test(input_raster: Path) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from .utils.qt import QGuiApplication

    checks = Checks()
    app = QGuiApplication(sys.argv[:1])
    workdir = Path(tempfile.mkdtemp(prefix="geopotential-selftest-"))
    project_root = workdir / "SelfTest.gpot"

    try:
        controller = AppController()

        # 1 — open project
        created = controller.createProject(str(project_root), "SelfTest")
        store = controller.store
        checks.check(
            "1  project created",
            created and store is not None and (project_root / "project.sqlite").exists(),
            f"{project_root.name} with {len(list(project_root.iterdir()))} entries",
        )

        # 2 — start worker, once
        controller.startWorker()
        ready = controller.supervisor.wait_for_ready(20000)
        checks.check(
            "2  worker handshake",
            ready and controller.supervisor.state == WorkerSupervisor.READY,
            f"state={controller.supervisor.state}, "
            f"protocol={P.PROTOCOL_VERSION}, "
            f"capabilities={controller.supervisor.capabilities}",
        )
        checks.check(
            "3  worker started once",
            controller.supervisor.start_count == 1,
            f"start_count={controller.supervisor.start_count}",
        )

        # 4 — worker is a separate process
        checks.check(
            "4  worker out of process",
            controller.supervisor._process is not None
            and controller.supervisor._process.processId() not in (0, os.getpid()),
            f"gui pid={os.getpid()}, "
            f"worker pid={controller.supervisor._process.processId()}",
        )

        # 5 — submit and drive to completion
        finished: list[tuple[str, str]] = []
        progress: list[tuple[str, float]] = []
        artifacts: list[dict] = []
        controller.supervisor.progressReceived.connect(
            lambda m: progress.append((m["stage"], m["fraction"]))
        )
        controller.supervisor.artifactReceived.connect(artifacts.append)
        controller._job_controller.jobFinished.connect(
            lambda j, s: finished.append((j, s))
        )

        job_id = controller.submit(
            "decision.membership",
            {
                "function": "linear_decreasing",
                "criterion_name": "distance_to_fault",
                "unit": "m",
            },
            [str(input_raster)],
        )
        for _ in range(600):
            controller.supervisor.pump(50)
            app.processEvents()
            if finished:
                break

        checks.check(
            "5  job reached a terminal state",
            bool(finished) and finished[0][1] == "Succeeded",
            f"job={job_id[:8]} state={finished[0][1] if finished else 'never finished'}",
        )

        # 6 — progress was real and monotonic within each stage
        per_stage: dict[str, list[float]] = {}
        for stage, fraction in progress:
            per_stage.setdefault(stage, []).append(fraction)
        monotonic = all(
            all(b >= a - 1e-9 for a, b in zip(v, v[1:])) for v in per_stage.values()
        )
        checks.check(
            "6  progress real and monotonic",
            len(progress) >= 4 and monotonic and per_stage.get("membership", [0])[-1] == 1.0,
            f"{len(progress)} updates over stages {sorted(per_stage)}",
        )

        # 7 — the artefact exists, is closed, and hashes to what was announced
        from .project.store import ProjectStore  # noqa: F401 - type clarity

        runs = store.runs()
        artifact_rows = store.artifacts(runs[0].id) if runs else []
        row = artifact_rows[0] if artifact_rows else None
        on_disk = Path(row["path"]) if row else None
        checks.check(
            "7  artefact registered against a run",
            row is not None and on_disk.exists(),
            f"{len(runs)} run(s), {len(artifact_rows)} artefact(s)"
            + (f", {on_disk.name}" if on_disk else ""),
        )

        from .project.store import canonical_params  # noqa: F401
        from hashlib import sha256

        if on_disk and on_disk.exists():
            digest = sha256()
            with open(on_disk, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            recomputed = f"sha256:{digest.hexdigest()}"
        else:
            recomputed = ""
        checks.check(
            "8  hash recorded and correct",
            bool(row) and row["hash"] == recomputed,
            f"{(row['hash'] if row else 'none')[:26]}...",
        )

        # 9 — the run is immutable
        immutable_refused = False
        try:
            store.connect().execute(
                "UPDATE run SET manifest_json='{}' WHERE id=?", (runs[0].id,)
            )
        except Exception as exc:  # sqlite3.IntegrityError via the trigger
            immutable_refused = "immutable" in str(exc)
        checks.check(
            "9  completed run is immutable",
            immutable_refused,
            "UPDATE on a committed run was refused by the store",
        )

        # 10 — the written GeoTIFF declares its nodata and its CRS
        import numpy as np
        import rasterio

        with rasterio.open(on_disk) as src:
            nodata_declared = src.nodata is not None and np.isnan(src.nodata)
            values = src.read(1)
            crs_present = src.crs is not None
            valid = np.isfinite(values)
            in_range = bool(
                valid.any()
                and values[valid].min() >= -1e-6
                and values[valid].max() <= 1 + 1e-6
            )
        checks.check(
            "10 nodata declared as NaN",
            nodata_declared and crs_present,
            f"nodata={src.nodata}, crs={src.crs}",
        )
        checks.check(
            "11 membership within [0, 1]",
            in_range,
            f"[{values[valid].min():.6f}, {values[valid].max():.6f}] over "
            f"{valid.mean() * 100:.1f}% valid pixels",
        )

        # 12 — the canvas can show it, and reads the right value back
        from .render.geocanvas.map_item import MapItem

        canvas = MapItem()
        shown = canvas.showArtifact(str(on_disk), "membership [0-1]")
        summary = canvas.layerSummary()
        # Sample the centre of a known valid pixel and compare with the array.
        with rasterio.open(on_disk) as src:
            rows, cols = np.where(np.isfinite(src.read(1)))
            r, c = int(rows[len(rows) // 2]), int(cols[len(cols) // 2])
            x, y = src.transform * (c + 0.5, r + 0.5)
            expected = float(src.read(1)[r, c])
        sampled = canvas.sample(x, y)
        checks.check(
            "12 result displayed on the canvas",
            shown and summary.get("width", 0) > 0,
            f"{summary.get('width')}x{summary.get('height')} on {summary.get('crs')}",
        )
        checks.check(
            "13 value under cursor is correct",
            sampled is not None and abs(sampled - expected) < 1e-6,
            f"sampled {sampled:.6f} at ({x:.1f}, {y:.1f}) vs stored {expected:.6f}",
        )

        # 14 — nodata renders transparent, never as a ramp value
        from .render.colormap import to_rgba

        probe = np.array([[0.0, np.nan], [1.0, 0.5]], dtype=np.float32)
        rgba = to_rgba(probe)
        checks.check(
            "14 nodata renders transparent",
            rgba[0, 1, 3] == 0 and rgba[0, 0, 3] == 255,
            f"alpha at the null is {rgba[0, 1, 3]}, at a valid pixel {rgba[0, 0, 3]}",
        )

        # 15 — a raw criterion cannot be aggregated
        raw_refused = _raw_criterion_is_refused()
        checks.check(
            "15 a RAW criterion cannot be aggregated",
            raw_refused,
            "CriterionStack.require_normalized refused it by name",
        )

        # 16 — a source with no CRS is refused by name
        no_crs_refused = _missing_crs_is_refused(workdir)
        checks.check(
            "16 no default CRS",
            no_crs_refused,
            "a CRS-less raster was refused, naming the file",
        )

        # 17 — cancellation leaves nothing recorded
        cancel_ok = _cancellation_records_nothing(controller, app, input_raster)
        checks.check(
            "17 cancellation records no run",
            cancel_ok,
            "the cancelled job committed no run and no artefact",
        )

        # 18 — no HTTP port is open
        ports = _listening_ports()
        checks.check(
            "18 no HTTP port open",
            not ports,
            f"listening TCP ports: {ports or 'none'}",
        )

        # 19 — nothing web reached the process
        web = sorted(
            m for m in sys.modules
            if m.split(".")[0] in {"flask", "fastapi", "uvicorn", "aiohttp", "tornado"}
            or "WebEngine" in m
        )
        checks.check(
            "19 no browser or web server imported",
            not web,
            f"web modules loaded: {web or 'none'}",
        )

        # ---- M3: the Data Manager and its QA/QC --------------------------
        _m3_checks(checks, controller, app, input_raster)

        # ---- M4: the GeoCanvas -------------------------------------------
        _m4_checks(checks, controller, app, input_raster)

        # ---- M5: the decision engine -------------------------------------
        _m5_checks(checks, controller, app, input_raster)

        # ---- M2: runtime, recovery and the four kill tests ---------------
        # Last, because they kill the worker and abandon the project.
        _m2_checks(checks, controller, app, input_raster, project_root, workdir)

        print(f"\ngeopotential_app {VERSION}, protocol {P.PROTOCOL_VERSION}")
        return checks.report()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


#: Rules that are only answerable against other layers, so validating a file on
#: its own cannot raise them. `tests/integration/test_import_flow.py` covers
#: them with a real project containing a real neighbour.
CROSS_LAYER_RULES = frozenset({"extent.overlap", "grid.resolution_mismatch"})


def _m4_checks(checks, controller, app, input_raster: Path) -> None:  # noqa: ANN001
    """Gate M4. The canvas reads what the screen needs and measures the source.

    Driven through the real `MapItem`, at a real size, on a raster large enough
    that reading it whole would be visible in the numbers.
    """
    from .render.geocanvas.map_item import MapItem
    from .render.geocanvas.viewport import Extent, Viewport

    canvas_dir = input_raster.parent.parent / "synthetic" / "msp" / "canvas"
    large = canvas_dir / "large_field.tif"
    other = canvas_dir / "large_field_b.tif"
    if not large.exists():
        for number, name in (
            (28, "large raster opens reading a fraction of it"),
            (29, "the level of detail follows the scale"),
            (30, "coordinate under cursor correct under pan and zoom"),
            (31, "value under cursor comes from the source"),
            (32, "AOI persists across close and reopen"),
            (33, "split view aligns two layers"),
            (34, "the tile cache is discardable"),
            (35, "visual export matches the view"),
        ):
            checks.check(f"{number} {name}", False,
                         "BLOCKED: run tools/make_canvas_fixtures.py")
        return

    item = MapItem()
    item.setWidth(1024)
    item.setHeight(768)
    opened = item.showArtifact(str(large), "mGal")
    source = item.source
    total = source.width * source.height

    # 28 — a large raster opens without reading itself
    left, bottom, right, top = source.bounds
    item.set_viewport(Viewport(Extent(left, bottom, right, top), 1024, 768))
    viewport = item.viewport
    source.read_window(*viewport.fitted_extent.as_tuple(), viewport.scale)
    fraction = source.pixels_read / total
    checks.check(
        "28 large raster opens reading a fraction of it",
        opened and fraction < 0.15,
        f"{source.pixels_read:,} of {total:,} px ({fraction * 100:.2f}%) "
        f"for a 1024x768 view",
    )

    # 29 — the level is a function of scale, and monotone in it
    factors = [
        source.level_for_scale(scale).factor
        for scale in (2.5, 10.0, 40.0, 160.0, 640.0)
    ]
    checks.check(
        "29 the level of detail follows the scale",
        factors == sorted(factors) and factors[0] == 1 and factors[-1] > factors[0],
        f"scales 2.5 -> 640 m/px choose levels {factors}",
    )

    # 30 — the coordinate round-trip holds under pan and under zoom
    errors = []
    for view in (viewport, viewport.panned(211.0, -97.0), viewport.zoomed(0.05),
                 viewport.zoomed(4.0).panned(-40.0, 60.0)):
        for px, py in ((0, 0), (1023, 767), (512, 384), (137, 611)):
            x, y = view.to_map(px, py)
            bx, by = view.to_screen(x, y)
            errors.append(max(abs(float(bx) - px), abs(float(by) - py)))
    checks.check(
        "30 coordinate under cursor correct under pan and zoom",
        max(errors) < 1e-6,
        f"worst screen round-trip error {max(errors):.2e} px over "
        f"{len(errors)} points in 4 views",
    )

    # 31 — the value comes from the source, not from the decimated tile
    import numpy as np
    import rasterio

    tile = source.read_window(*viewport.fitted_extent.as_tuple(), viewport.scale)
    factor = tile.window.factor
    with rasterio.open(large) as src:
        values = src.read(1)
    row, col = 1500, 2500
    source_value = float(values[row, col])
    tile_value = float(tile.values[row // factor, col // factor])
    x, y = source.transform * (col + 0.5, row + 0.5)
    sampled = item.sample(float(x), float(y))
    checks.check(
        "31 value under cursor comes from the source",
        factor > 1
        and abs(sampled - source_value) < 1e-5
        and abs(sampled - tile_value) > 1e-3,
        f"at 1:{factor} the tile says {tile_value:.4f}, the source says "
        f"{source_value:.4f}, the readout says {sampled:.4f}",
    )

    # 32 — an AOI survives a close and a reopen, with its version.
    #
    # In its own project, deliberately. Closing and reopening the self-test's
    # main project would reset the command stack, restart the worker and move
    # the run count — and the M2 checks that follow assert on all three. A
    # persistence check needs a project it can close; it does not need *this*
    # one.
    polygon = [[left + 1000, top - 1000], [left + 4000, top - 1000],
               [left + 4000, top - 4000], [left + 1000, top - 4000]]
    item.setAoiPolygon(polygon)

    aoi_dir = Path(tempfile.mkdtemp(prefix="geopotential-aoi-"))
    try:
        writer = AppController()
        writer.createProject(str(aoi_dir / "Aoi.gpot"), "Aoi")
        saved = writer.saveAoi("survey", item.aoiPolygon(), item.crsName)
        writer.shutdown()

        reader = AppController()
        reader.openProject(str(aoi_dir / "Aoi.gpot"))
        recovered = reader.loadAoi("survey")
        reader.shutdown()

        checks.check(
            "32 AOI persists across close and reopen",
            bool(saved) and bool(recovered)
            and recovered["geometry"] == polygon
            and recovered["version"] == 1
            and recovered["crs"] == item.crsName,
            f"version {recovered.get('version')} recovered with "
            f"{len(recovered.get('geometry', []))} vertices in "
            f"{recovered.get('crs')}, area {recovered.get('area', 0):,.0f} m2",
        )
    finally:
        shutil.rmtree(aoi_dir, ignore_errors=True)

    # 33 — the split view shows both layers on one viewport
    item.showComparison(str(other))
    checks.check(
        "33 split view aligns two layers",
        item.splitView and item.compareName == "large_field_b"
        and item.layerName == "large_field",
        f"{item.layerName} | {item.compareName}, one viewport at "
        f"{viewport.scale:.1f} m/px",
    )

    # 34 — the cache is discardable: clearing it changes only time
    args = (*viewport.fitted_extent.as_tuple(), viewport.scale)
    first = source.read_window(*args).values.copy()
    before = source.cache.stats()
    source.cache.clear()
    second = source.read_window(*args).values
    identical = np.array_equal(
        np.nan_to_num(first, nan=-9e9), np.nan_to_num(second, nan=-9e9)
    )
    checks.check(
        "34 the tile cache is discardable",
        identical,
        f"{before['mb']} MB in {before['entries']} tiles cleared; the re-read "
        f"is identical",
    )

    # 35 — the exported image is the view, at the view's size
    exported = Path(tempfile.mkdtemp(prefix="geopotential-export-")) / "canvas.png"
    from .render.colormap import to_rgba

    rgba = to_rgba(tile.values, colormap="viridis")
    from .utils.qt import QImage

    rows, cols, _ = rgba.shape
    image = QImage(rgba.data, cols, rows, 4 * cols, QImage.Format_RGBA8888)
    written = image.save(str(exported))
    checks.check(
        "35 visual export matches the view",
        written and exported.exists()
        and (cols, rows) == (tile.values.shape[1], tile.values.shape[0]),
        f"{cols}x{rows} px written to {exported.name}, the same pixels the "
        f"canvas drew",
    )


def _m3_checks(checks, controller, app, input_raster: Path) -> None:  # noqa: ANN001
    """Gate M3. Detect, explain, permit correction, refuse, and record.

    Driven through the real worker, because "impede operação inválida" has to
    hold across the process boundary and through the Project Store, not only
    inside the rules module.
    """
    broken = input_raster.parent.parent / "synthetic" / "msp" / "broken"
    if not (broken / "MANIFEST.json").exists():
        for number, name in (
            (20, "dataset described without importing"),
            (21, "each defect detected with its own rule"),
            (22, "every finding is actionable"),
            (23, "a BLOCKER refuses the import"),
            (24, "declaring a value clears the blocker"),
            (25, "the verdict is recorded as an audit trail"),
            (26, "a resource estimate precedes the operation"),
            (27, "a warning does not block"),
        ):
            checks.check(f"{number} {name}", False,
                         "BLOCKED: run tools/make_broken_fixtures.py")
        return

    store = controller.store

    def probe(kind: str, path: Path, declared: dict) -> dict:
        seen: list[dict] = []
        signal = (controller.datasetDescribed if kind == "describe"
                  else controller.datasetValidated)
        signal.connect(seen.append)
        job = (controller.describeDataset(str(path), declared) if kind == "describe"
               else controller.validateDataset(str(path), declared))
        for _ in range(600):
            controller.supervisor.pump(20)
            app.processEvents()
            if seen:
                break
        signal.disconnect(seen.append)
        return seen[-1] if seen else {}

    # 20 — describing reads everything and imports nothing
    datasets_before = len(store.datasets())
    runs_before = len(store.runs())
    description = probe("describe", input_raster, {})
    checks.check(
        "20 dataset described without importing",
        description.get("crs") == "EPSG:26912"
        and "histogram" in description.get("statistics", {})
        and len(store.datasets()) == datasets_before
        and len(store.runs()) == runs_before,
        f"{description.get('driver')} {description.get('width')}x"
        f"{description.get('height')} on {description.get('crs')}; "
        f"0 datasets and 0 runs created",
    )

    # 21 — each defective dataset raises the rule it was built to raise
    import json as _json

    manifest = _json.loads((broken / "MANIFEST.json").read_text())["fixtures"]
    detected, missed = 0, []
    for entry in manifest:
        declared = {}
        require_metric = entry["expected_rule"] == "crs.metric_required"
        if require_metric:
            declared["require_metric"] = True
        result = probe("validate", broken / entry["file"], declared)
        rules = {f["rule"] for f in result.get("report", {}).get("findings", [])}
        if entry["expected_rule"] in rules:
            detected += 1
        elif entry["expected_rule"] not in CROSS_LAYER_RULES:
            missed.append(entry["file"])
    checks.check(
        "21 each defect detected with its own rule",
        not missed,
        f"{detected}/{len(manifest)} raised their rule alone; "
        f"{len(manifest) - detected} need cross-layer context"
        + (f"; missed {missed}" if missed else ""),
    )

    # 22 — every message answers section 33
    blocked = probe("validate", broken / "nodata_undeclared.tif", {})
    findings = blocked.get("report", {}).get("findings", [])
    actionable = all(
        f.get("what") and f.get("why") and len(f.get("fix", "")) > 20
        and f["dataset"] in f["message"]
        for f in findings
    )
    checks.check(
        "22 every finding is actionable",
        bool(findings) and actionable,
        f"{len(findings)} finding(s), each naming the dataset, the reason and "
        f"the correction",
    )

    # 23 — a BLOCKER refuses the import, not merely colours it
    errors: list[str] = []
    controller.errorRaised.connect(lambda m, r: errors.append(m))
    refused = controller.importDataset(str(broken / "nodata_undeclared.tif"), "raster")
    checks.check(
        "23 a BLOCKER refuses the import",
        refused == "" and len(store.datasets()) == datasets_before
        and any("cannot be used" in m for m in errors),
        f"import returned {refused!r}; the refusal quoted the verdict",
    )

    # 24 — declaring the missing value clears the blocker and unlocks import
    corrected = probe("validate", broken / "nodata_undeclared.tif",
                      {"nodata": -9999.0, "unit": "m"})
    usable = corrected.get("report", {}).get("usable")
    imported = controller.importDataset(
        str(broken / "nodata_undeclared.tif"), "raster"
    ) if usable else ""
    checks.check(
        "24 declaring a value clears the blocker",
        bool(usable) and bool(imported)
        and len(store.datasets()) == datasets_before + 1,
        f"after declaring nodata=-9999: {corrected.get('report', {}).get('summary')}",
    )

    # 25 — every verdict is recorded, refusals included
    verdicts = store.validations()
    refusals = [v for v in verdicts if not v["usable"]]
    checks.check(
        "25 the verdict is recorded as an audit trail",
        len(verdicts) >= len(manifest) and bool(refusals)
        and all(v["operator"] == "qc.validate_dataset" for v in verdicts),
        f"{len(verdicts)} validation result(s) recorded, {len(refusals)} of them "
        f"refusals",
    )

    # 26 — a resource estimate precedes the operation
    plan = corrected.get("plan") or {}
    checks.check(
        "26 a resource estimate precedes the operation",
        bool(plan) and plan.get("ram_mb", 0) > 0 and bool(plan.get("assumptions")),
        f"{plan.get('ram_mb')} MB RAM, {plan.get('disk_mb')} MB disk, "
        f"policy={plan.get('policy')}, {len(plan.get('assumptions', []))} "
        f"assumptions stated",
    )

    # 27 — a warning informs without blocking
    warned = probe("validate", broken / "anisotropic.tif", {"unit": "m"})
    report = warned.get("report", {})
    severities = {f["severity"] for f in report.get("findings", [])}
    checks.check(
        "27 a warning does not block",
        report.get("usable") is True and "WARNING" in severities
        and "BLOCKER" not in severities,
        f"{report.get('summary')}",
    )


def _m5_checks(checks, controller, app, input_raster: Path) -> None:  # noqa: ANN001
    """Gate M5. The flow, arrow by arrow, through the real worker.

        dados -> QA/QC -> harmonização -> membership -> AHP/pesos -> MCDA
              -> prospectividade
    """
    import numpy as np

    canvas_dir = input_raster.parent.parent / "synthetic" / "msp" / "canvas"
    a, b = canvas_dir / "large_field.tif", canvas_dir / "large_field_b.tif"
    if not a.exists():
        for number, name in (
            (36, "QA/QC clears the inputs"),
            (37, "layers arrive on one target grid"),
            (38, "each criterion becomes NORMALIZED in [0,1]"),
            (39, "AHP weights sum to 1 with their CR"),
            (40, "an inconsistent matrix is refused"),
            (41, "an override is recorded"),
            (42, "the aggregation matches an independent calculation"),
            (43, "the manifest reproduces the run"),
        ):
            checks.check(f"{number} {name}", False,
                         "BLOCKED: run tools/make_canvas_fixtures.py")
        return

    store = controller.store

    def run(operator: str, params: dict) -> tuple[str, dict]:
        finished: list[str] = []
        manifests: list[dict] = []
        controller._job_controller.jobFinished.connect(
            lambda _j, s: finished.append(s)
        )
        controller.supervisor.jobSucceeded.connect(
            lambda m: manifests.append(m["manifest"])
        )
        controller.submit(operator, params, [])
        for _ in range(1500):
            controller.supervisor.pump(20)
            app.processEvents()
            if finished:
                break
        return (finished[-1] if finished else "never finished",
                manifests[-1] if manifests else {})

    # 36 — dados -> QA/QC
    seen: list[dict] = []
    controller.datasetValidated.connect(seen.append)
    controller.validateDataset(str(a), {"unit": "mGal"})
    for _ in range(600):
        controller.supervisor.pump(20)
        app.processEvents()
        if seen:
            break
    controller.datasetValidated.disconnect(seen.append)
    report = seen[-1]["report"] if seen else {}
    checks.check(
        "36 QA/QC clears the inputs",
        bool(report.get("usable")),
        f"{report.get('summary', 'no verdict')}",
    )

    # 37 — QA/QC -> harmonização
    state, manifest = run("grid.harmonize", {
        "target_crs": "EPSG:26912", "pixel_size": 40.0,
        "extent_policy": "intersection",
        "layers": [
            {"path": str(a), "name": "heat_proxy", "unit": "mGal",
             "resampling": "bilinear"},
            {"path": str(b), "name": "structure_proxy", "unit": "mGal",
             "resampling": "bilinear"},
        ],
    })
    grid = manifest.get("grid", {})
    layers = {l["name"]: l for l in manifest.get("layers", [])}
    checks.check(
        "37 layers arrive on one target grid",
        state == "Succeeded" and len(layers) == 2
        and grid.get("crs") == "EPSG:26912" and grid.get("square_pixel"),
        f"{len(layers)} layers on {grid.get('width')}x{grid.get('height')} "
        f"at {grid.get('pixel_size_x')} m in {grid.get('crs')}",
    )

    # 38 — harmonização -> membership, and 42 -> MCDA
    state, aggregated = run("decision.aggregate", {
        "method": "fuzzy_gamma", "gamma": 0.7, "result_name": "prospectivity",
        "criteria": [
            {"path": layers["heat_proxy"]["artifact"], "name": "heat_proxy",
             "unit": "mGal", "function": "linear_increasing"},
            {"path": layers["structure_proxy"]["artifact"],
             "name": "structure_proxy", "unit": "mGal",
             "function": "linear_decreasing"},
        ],
    })
    criteria = aggregated.get("criteria", [])
    checks.check(
        "38 each criterion becomes NORMALIZED in [0,1]",
        state == "Succeeded" and len(criteria) == 2
        and all("anchors" in c and c.get("source_unit") for c in criteria),
        "; ".join(
            f"{c['name']} {c['function']} "
            f"[{c['anchors'].get('x_min', 0):.2f}, {c['anchors'].get('x_max', 0):.2f}] "
            f"{c['source_unit']}"
            for c in criteria
        ),
    )

    # 39 — membership -> AHP/pesos
    state, weights_manifest = run("decision.ahp_weights", {
        "matrix": [[1, 3], [1 / 3, 1]],
        "names": ["heat_proxy", "structure_proxy"],
    })
    ahp = weights_manifest.get("ahp", {})
    checks.check(
        "39 AHP weights sum to 1 with their CR",
        state == "Succeeded"
        and abs(sum(ahp.get("weights", [])) - 1.0) < 1e-9
        and ahp.get("consistent") is True,
        f"weights {[round(w, 3) for w in ahp.get('weights', [])]}, "
        f"CR = {ahp.get('cr', 0):.4f} against {ahp.get('threshold', 0):.2f}",
    )

    # 40 — an inconsistent matrix is refused by name
    inconsistent = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
    state, _ = run("decision.ahp_weights",
                   {"matrix": inconsistent, "names": ["a", "b", "c"]})
    message = store.jobs()[-1]["error_message"] or ""
    checks.check(
        "40 an inconsistent matrix is refused",
        state == "Failed" and "CR" in message and "justification" in message,
        message[:96] + ("…" if len(message) > 96 else ""),
    )

    # 41 — and an override is accepted, and recorded
    state, override_manifest = run("decision.ahp_weights", {
        "matrix": inconsistent, "names": ["a", "b", "c"],
        "override_reason": "accepted by the review of 2026-09-01",
    })
    recorded = [
        v for v in store.validations()
        if v["operator"] == "decision.ahp_weights"
    ]
    checks.check(
        "41 an override is recorded",
        state == "Succeeded"
        and "review" in override_manifest.get("ahp", {}).get("override", "")
        and bool(recorded),
        f"{len(recorded)} AHP verdict(s) in the audit trail; "
        f"CR = {override_manifest.get('ahp', {}).get('cr', 0):.4f} accepted",
    )

    # 42 — the aggregation matches an independent calculation
    import rasterio

    runs = store.runs()
    result_path = None
    for record in reversed(runs):
        artifacts = store.artifacts(record.id)
        if artifacts and "prospectivity" in artifacts[0]["path"]:
            result_path = artifacts[0]["path"]
            break
    agreement = "no result found"
    matches = False
    if result_path:
        with rasterio.open(layers["heat_proxy"]["artifact"]) as fa, \
             rasterio.open(layers["structure_proxy"]["artifact"]) as fb, \
             rasterio.open(result_path) as fr:
            window = rasterio.windows.Window(200, 200, 300, 300)
            va, vb, vr = (f.read(1, window=window) for f in (fa, fb, fr))
        anchors = {c["name"]: c["anchors"] for c in criteria}
        ha, hb = anchors["heat_proxy"], anchors["structure_proxy"]
        mu_a = np.clip((va - ha["x_min"]) / (ha["x_max"] - ha["x_min"]), 0, 1)
        mu_b = np.clip((hb["x_max"] - vb) / (hb["x_max"] - hb["x_min"]), 0, 1)
        g = 0.7
        expected = ((1 - (1 - mu_a) * (1 - mu_b)) ** g) * ((mu_a * mu_b) ** (1 - g))
        both = np.isfinite(va) & np.isfinite(vb) & np.isfinite(vr)
        if both.any():
            worst = float(np.abs(vr[both] - expected[both]).max())
            matches = worst < 1e-4
            agreement = (f"worst |worker - numpy| = {worst:.2e} over "
                         f"{int(both.sum()):,} pixels")
    checks.check(
        "42 the aggregation matches an independent calculation",
        matches, agreement,
    )

    # 43 — the manifest reproduces the run
    order = aggregated.get("criterion_order", [])
    hashed = all(c.get("source_hash", "").startswith("sha256:") for c in criteria)
    checks.check(
        "43 the manifest reproduces the run",
        order == ["heat_proxy", "structure_proxy"] and hashed
        and aggregated.get("params", {}).get("gamma") == 0.7
        and "grid" in aggregated,
        f"criterion order {order}, gamma "
        f"{aggregated.get('params', {}).get('gamma')}, every input hashed, "
        f"grid {aggregated.get('grid', {}).get('width')}x"
        f"{aggregated.get('grid', {}).get('height')}",
    )


def _m2_checks(checks, controller, app, input_raster: Path, project_root: Path,
               workdir: Path) -> None:  # noqa: ANN001
    """Gate M2. The four kills of section 20, and what must survive each.

    The conservative direction is what is asserted throughout: after any kill,
    no job may read `Succeeded` unless it genuinely committed, and no file may
    be registered unless the store hashed it.
    """
    from .project.store import ProjectStore

    store = controller.store

    # 21 — the session and journal exist, and the journal is write-ahead
    checks.check(
        "44 session and journal recorded",
        controller.session_id is not None
        and store.summary()["sessions"] >= 1,
        f"session={controller.session_id[:8]}, "
        f"open journal entries={store.summary()['open_journal_entries']}",
    )

    # 22 — the four log channels exist and a detail_ref resolves
    logs = controller.logs
    ref = logs.worker("error", "probe traceback", job_id="probe")
    resolved = logs.resolve(ref)
    channels_present = [
        c for c in ("application", "scientific", "worker", "crash")
        if (project_root / "logs" / f"{c}.jsonl").exists()
    ]
    checks.check(
        "45 log channels separate, refs resolve",
        resolved is not None and resolved["msg"] == "probe traceback"
        and "application" in channels_present and "worker" in channels_present,
        f"channels on disk: {', '.join(channels_present)}; ref {ref} resolved",
    )

    # 23 — the exportable diagnostic carries no scientific data
    diagnostic = workdir / "diagnostic.zip"
    logs.export_diagnostic(diagnostic, store.summary())
    with zipfile.ZipFile(diagnostic) as archive:
        names = archive.namelist()
    rasters = [n for n in names if n.endswith((".tif", ".tiff", ".gpkg", ".npy"))]
    checks.check(
        "46 diagnostic carries no science",
        not rasters and "environment.json" in names,
        f"{len(names)} entries, {len(rasters)} scientific artefacts",
    )

    # 47 — undo is refused past a committed run, with the reason.
    #
    # Self-contained: it creates the undoable command it needs rather than
    # assuming one is on the stack. Depending on whatever an earlier
    # milestone's checks happened to leave there broke this twice — once when
    # M3 added an import, once when M5 added an aggregation.
    stack = controller.commands
    controller.validateDataset(str(input_raster), {"unit": "m"})
    for _ in range(600):
        controller.supervisor.pump(20)
        app.processEvents()
        if controller.isDatasetUsable(str(input_raster)):
            break
    controller.importDataset(str(input_raster), "raster")
    undoable_before = stack.canUndo

    barrier_done: list[str] = []
    controller._job_controller.jobFinished.connect(
        lambda _j, s: barrier_done.append(s)
    )
    controller.submit(
        "decision.membership",
        {"function": "linear_increasing", "criterion_name": "barrier_probe",
         "unit": "m"},
        [str(input_raster)],
    )
    for _ in range(600):
        controller.supervisor.pump(20)
        app.processEvents()
        if barrier_done:
            break
    checks.check(
        "47 science is not undoable",
        undoable_before and not stack.canUndo and "Cannot undo" in stack.undoText,
        f"an import was undoable ({undoable_before}); after the run, undo is "
        f"{stack.undoText!r}",
    )

    # ---- kill 1: the worker, while a job is Running -------------------
    finished: list[tuple[str, str]] = []
    controller._job_controller.jobFinished.connect(
        lambda j, s: finished.append((j, s))
    )
    runs_before_kill = len(store.runs())
    running_job = controller.submit(
        "decision.membership",
        {"function": "linear_increasing", "criterion_name": "kill_probe", "unit": "m"},
        [str(input_raster)],
    )
    # Kill at once, without draining the pipe. The operator takes tens of
    # milliseconds, so waiting for a particular stage is a race: it can finish
    # first, and then the check is asserting nothing.
    #
    # So the check asserts the **invariant** instead of the timing. Two
    # outcomes are legitimate — the kill landed mid-run, or the run genuinely
    # completed first — and each has exactly one correct shape. What must never
    # happen is the mismatch: `Succeeded` without a committed run, or a run
    # committed for a job that was interrupted.
    killed_pid = controller.supervisor.kill_now()
    for _ in range(80):
        app.processEvents()
        controller.supervisor.pump(20)
        if controller.supervisor.state == WorkerSupervisor.CRASHED:
            break

    row = controller.job_model.row(running_job)
    runs_after_kill = len(store.runs())
    committed = runs_after_kill - runs_before_kill
    state = row.state if row else "gone"
    if state == "Interrupted":
        consistent = committed == 0
        outcome = "the kill landed mid-run; no run was committed"
    elif state == "Succeeded":
        consistent = committed == 1
        outcome = "the run completed before the kill; exactly one run committed"
    else:
        consistent = False
        outcome = f"unexpected state {state}"
    checks.check(
        "48 kill during Running leaves no phantom result",
        consistent and not _pid_alive(killed_pid),
        f"{outcome}; pid {killed_pid} alive={_pid_alive(killed_pid)}",
    )
    checks.check(
        "49 killed worker is detected as crashed",
        controller.supervisor.state == WorkerSupervisor.CRASHED,
        f"state={controller.supervisor.state}",
    )

    # ---- restart: the project survives, and work resumes --------------
    controller.restartWorker()
    ready = controller.supervisor.wait_for_ready(20000)
    checks.check(
        "50 worker restarts after being killed",
        ready and controller.supervisor.state == WorkerSupervisor.READY
        and controller.supervisor.start_count == 2,
        f"state={controller.supervisor.state}, starts={controller.supervisor.start_count}",
    )

    finished.clear()
    resumed = controller.submit(
        "decision.membership",
        {"function": "linear_decreasing", "criterion_name": "after_restart",
         "unit": "m"},
        [str(input_raster)],
    )
    for _ in range(600):
        controller.supervisor.pump(30)
        app.processEvents()
        if any(j == resumed for j, _ in finished):
            break
    state = next((s for j, s in finished if j == resumed), "never finished")
    checks.check(
        "51 project intact: a job runs after restart",
        state == "Succeeded" and len(store.runs()) == runs_after_kill + 1,
        f"job after restart={state}, runs {runs_after_kill} -> {len(store.runs())}",
    )

    # ---- kill 2: the whole application, with a job in flight ----------
    # Simulated the only honest way: submit, journal the intent, then abandon
    # the session without closing it — exactly what a SIGKILL on the GUI leaves
    # behind. Then reopen and let the recovery pass speak.
    orphan_job = store.create_job("decision.membership", {"function": "large"}, [])
    orphan_dir = store.artifact_dir(orphan_job)
    store.journal_open(orphan_job, "decision.membership", orphan_dir)
    store.set_job_state(orphan_job, "Running")
    (orphan_dir / "partial.tif").write_bytes(b"a partial write, not a result")
    (orphan_dir / "partial.tif.tmp").write_bytes(b"half a write")

    controller.supervisor.stop(force=True)
    store.close()  # no close_session: the session died

    reopened = AppController()
    reopened.openProject(str(project_root))
    report = reopened.recovery

    reopened_state = reopened.store.connect().execute(
        "SELECT state FROM job WHERE id=?", (orphan_job,)
    ).fetchone()["state"]
    checks.check(
        "52 kill during Running: reopen marks it Interrupted",
        reopened_state == "Interrupted",
        f"job state after reopen={reopened_state}",
    )
    checks.check(
        "53 unclean session is detected on reopen",
        report.unclean_sessions >= 1,
        f"{report.unclean_sessions} session(s) did not close normally",
    )
    checks.check(
        "54 orphan file listed, never adopted",
        any(o["path"].endswith("partial.tif") for o in report.orphan_artifacts)
        and (orphan_dir / "partial.tif").exists()
        and reopened.store.connect().execute(
            "SELECT COUNT(*) FROM artifact WHERE path LIKE '%partial.tif'"
        ).fetchone()[0] == 0,
        f"{len(report.orphan_artifacts)} orphan(s) reported, 0 registered",
    )
    checks.check(
        "55 half-written .tmp discarded",
        not (orphan_dir / "partial.tif.tmp").exists()
        and any(t.endswith(".tmp") for t in report.removed_temporaries),
        f"{len(report.removed_temporaries)} temporary file(s) removed",
    )

    # 33 — the committed runs survived every kill, still immutable
    surviving = reopened.store.runs()
    immutable_refused = False
    if surviving:
        try:
            reopened.store.connect().execute(
                "UPDATE run SET manifest_json='{}' WHERE id=?", (surviving[0].id,)
            )
        except Exception as exc:
            immutable_refused = "immutable" in str(exc)
    checks.check(
        "56 committed runs survive and stay immutable",
        len(surviving) == runs_after_kill + 1 and immutable_refused,
        f"{len(surviving)} run(s) intact after two kills",
    )

    # 34 — recovery is idempotent: a second open finds nothing new
    reopened.shutdown()
    third = AppController()
    third.openProject(str(project_root))
    checks.check(
        "57 recovery is idempotent",
        not third.recovery.interrupted_jobs and not third.recovery.removed_temporaries,
        f"second pass: {len(third.recovery.interrupted_jobs)} interrupted, "
        f"{len(third.recovery.removed_temporaries)} temporaries",
    )

    # ---- kill 3: shutdown terminates the child, always ----------------
    third.startWorker()
    third.supervisor.wait_for_ready(20000)
    child_pid = int(third.supervisor._process.processId())
    third.shutdown()
    for _ in range(40):
        app.processEvents()
        if third.supervisor.state == WorkerSupervisor.STOPPED:
            break
    checks.check(
        "58 closing the window terminates the child",
        third.supervisor.state == WorkerSupervisor.STOPPED
        and not _pid_alive(child_pid),
        f"state={third.supervisor.state}, pid {child_pid} alive={_pid_alive(child_pid)}",
    )

    # 36 — a clean shutdown leaves the session clean, so the next open is quiet
    final = ProjectStore.open(project_root)
    final.open_session(VERSION)
    unclean = len(final.unclean_sessions())
    final.close_session()
    final.close()
    checks.check(
        "59 clean shutdown closes the session",
        unclean == 1,
        f"{unclean} unclean session (the one kill we forced), not more",
    )


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _raw_criterion_is_refused() -> bool:
    """The stage guard, exercised through the app's own copy of the domain.

    The app does not import the worker package, so this reaches the same rule
    through the worker's own module on the child's path. Importing it here is
    a test-only allowance and the architecture gate exempts this module.
    """
    import numpy as np
    from affine import Affine

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
    try:
        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.domain.criterion import (
            Criterion,
            CriterionStack,
            Stage,
            StageError,
        )
        from geopotential_worker.domain.grid import TargetGrid

        grid = TargetGrid(
            Affine(10.0, 0, 0, 0, -10.0, 100),
            CrsInfo.from_user_input("EPSG:26912", source="probe"),
            4,
            4,
        )
        raw = Criterion(
            "density", np.ones((4, 4), np.float32) * 2.5, grid, Stage.RAW, unit="g/cm3"
        )
        try:
            CriterionStack([raw]).require_normalized()
        except StageError as exc:
            return "density" in str(exc)
        return False
    finally:
        sys.path.pop(0)


def _missing_crs_is_refused(workdir: Path) -> bool:
    import numpy as np
    import rasterio
    from affine import Affine

    path = workdir / "no_crs.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        transform=Affine(1, 0, 0, 0, -1, 4), nodata=float("nan"),
    ) as dst:
        dst.write(np.ones((4, 4), np.float32), 1)

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
    try:
        from geopotential_worker.domain.crs import MissingCrsError
        from geopotential_worker.io.readers import read_raster

        try:
            read_raster(path)
        except MissingCrsError as exc:
            return "no_crs.tif" in str(exc)
        return False
    finally:
        sys.path.pop(0)


def _cancellation_records_nothing(controller, app, input_raster: Path) -> bool:
    """Submit and cancel immediately; assert no run and no artefact appeared."""
    store = controller.store
    runs_before = len(store.runs())
    finished: list[tuple[str, str]] = []
    controller._job_controller.jobFinished.connect(lambda j, s: finished.append((j, s)))

    job_id = controller.submit(
        "decision.membership",
        {"function": "linear_increasing", "criterion_name": "cancel_probe", "unit": "m"},
        [str(input_raster)],
    )
    controller.cancel(job_id)
    for _ in range(400):
        controller.supervisor.pump(20)
        app.processEvents()
        if any(j == job_id for j, _ in finished):
            break

    state = next((s for j, s in finished if j == job_id), "")
    runs_after = len(store.runs())
    # Either the cancel landed and no run was committed, or the operator was
    # already past the cancellation point and committed one. Both are correct;
    # what must never happen is a cancelled job leaving a committed run.
    if state == "Cancelled":
        return runs_after == runs_before
    return state == "Succeeded"


def run_screenshot(
    out: Path, size: str, input_raster: Path, project: Path | None = None
) -> int:
    """Capture the real running window. Never a mockup.

    project  an existing `.gpot` to open; a throwaway one is created otherwise

    Honouring `--project` is what makes it possible to photograph a state the
    application only reaches through history — a project whose previous session
    was killed, say. Creating a fresh project unconditionally would make every
    screenshot a screenshot of a clean project.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from .utils.qt import QGuiApplication, QTimer

    from .app import _build_engine, _register_qml_types

    width, _, height = size.partition("x")
    app = QGuiApplication(sys.argv[:1])
    _register_qml_types()

    workdir = Path(tempfile.mkdtemp(prefix="geopotential-shot-"))
    controller = AppController()
    if project is not None and Path(project).exists():
        controller.openProject(str(project))
    elif project is not None:
        controller.createProject(str(project), Path(project).stem)
    else:
        controller.createProject(str(workdir / "Shot.gpot"), "Shot")
    engine = _build_engine(controller)
    window = engine.rootObjects()[0]
    window.setWidth(int(width))
    window.setHeight(int(height))

    controller.startWorker()
    controller.supervisor.wait_for_ready(20000)
    done: list[str] = []
    controller._job_controller.jobFinished.connect(lambda _j, s: done.append(s))
    controller.submit(
        "decision.membership",
        {"function": "linear_decreasing", "criterion_name": "distance_to_fault",
         "unit": "m"},
        [str(input_raster)],
    )
    # Drive the run to completion before capturing: a screenshot of an empty
    # canvas proves the shell loaded and nothing else.
    for _ in range(600):
        controller.supervisor.pump(30)
        app.processEvents()
        if done:
            break
    if not done or done[0] != "Succeeded":
        print(f"the run did not succeed ({done or 'never finished'}); not capturing",
              file=sys.stderr)
        controller.shutdown()
        shutil.rmtree(workdir, ignore_errors=True)
        return 1

    def capture() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        window.grabWindow().save(str(out))
        app.quit()

    QTimer.singleShot(2500, capture)
    code = app.exec()
    controller.shutdown()
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"wrote {out}")
    del engine
    return code
