#!/usr/bin/env python3
"""Drive the running application on a real window, and survive it.

Every other gate renders offscreen, which uses Qt's **basic** render loop. The
application a person opens uses the platform's own loop, and the two are not
the same program: `paint` can run on the render thread, where a shared PROJ
context or a GDAL handle is a segmentation fault rather than a wrong pixel.

Two crashes were found exactly here and nowhere else:

  - panning a GeoTIFF, because `paint` resolved the view's CRS through pyproj
    while the cursor readout used pyproj on the GUI thread;
  - turning on the basemap, because `paint` transformed the view's extent for
    the tile request on the same shared context.

So this check opens a real window and *uses* it: loads a table and a raster,
pans with the cursor moving, reprojects the view, turns the basemap on, pans
again, zooms. It asserts nothing about pixels — the storyboards do that. It
asserts that the application is still alive at the end.

    tools/interaction_check.py            run it
    tools/interaction_check.py --loop threaded   force the dangerous loop

`BLOCKED` when there is no display: a machine without one cannot answer this
question, and a gate that reported `FAIL` there would be reporting the wrong
thing.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
TABLE = DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"

BLOCKED = 2


def has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", default="basic",
                        choices=("basic", "threaded"),
                        help="which scene-graph render loop to force")
    parser.add_argument("--steps", type=int, default=60,
                        help="how many cursor moves per pan")
    options = parser.parse_args()

    if not has_display():
        print("BLOCKED: no display; this check needs a real window")
        return BLOCKED
    for fixture in (TABLE, RASTER):
        if not fixture.exists():
            print(f"BLOCKED: {fixture.name} is missing")
            return BLOCKED

    os.environ["QSG_RENDER_LOOP"] = options.loop
    os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp(prefix="gp-inter-"))
    os.environ.setdefault("GEOPOTENTIAL_PREFERENCES",
                          str(Path(os.environ["XDG_STATE_HOME"]) / "prefs.ini"))
    sys.path.insert(0, str(ROOT / "app"))

    import faulthandler

    faulthandler.enable()

    from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt, QTimer
    from PySide6.QtGui import QMouseEvent

    from geopotential_app.app import _build_engine, _register_qml_types
    from geopotential_app.controllers.app_controller import AppController
    from geopotential_app.utils.qt import QGuiApplication

    app = QGuiApplication(sys.argv[:1])
    _register_qml_types()
    workdir = Path(tempfile.mkdtemp(prefix="gp-interaction-"))
    controller = AppController()
    controller.createProject(str(workdir / "Interaction.gpot"), "Interaction")
    engine = _build_engine(controller)
    window = engine.rootObjects()[0]
    window.setWidth(900)
    window.setHeight(650)
    controller.startWorker()
    controller.supervisor.wait_for_ready(20000)

    def settle(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def wait_for(predicate, ms: int = 20000) -> None:
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: predicate() and loop.quit())
        timer.start(50)
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
        timer.stop()

    def canvas():  # noqa: ANN202 - the shell's own map, found by name
        # By name: the Import Wizard's preview holds a MapItem too, and taking
        # the first one the tree yields drove this check against an empty
        # canvas that had nothing to still be drawing.
        found = []

        def walk(obj) -> None:  # noqa: ANN001
            for child in obj.children():
                if (child.metaObject().className() == "MapItem"
                        and child.objectName() == "mapCanvas"):
                    found.append(child)
                walk(child)

        walk(window)
        return found[0] if found else None

    def drag(item, steps: int) -> None:  # noqa: ANN001
        item.mousePressEvent(QMouseEvent(
            QEvent.MouseButtonPress, QPointF(400, 300), Qt.LeftButton,
            Qt.LeftButton, Qt.NoModifier))
        for i in range(steps):
            position = QPointF(400 + i * 5, 300 + i * 4)
            item.mouseMoveEvent(QMouseEvent(
                QEvent.MouseMove, position, Qt.NoButton, Qt.LeftButton,
                Qt.NoModifier))
            # The readout reads the source while the canvas draws: the two
            # halves of the crash that started this file.
            item.hoverMoveEvent(QMouseEvent(
                QEvent.MouseMove, position, Qt.NoButton, Qt.NoButton,
                Qt.NoModifier))
            settle(10)
        item.mouseReleaseEvent(QMouseEvent(
            QEvent.MouseButtonRelease, QPointF(500, 400), Qt.LeftButton,
            Qt.NoButton, Qt.NoModifier))

    steps: list[str] = []

    def note(what: str) -> None:
        steps.append(what)
        print(f"  ok   {what}", flush=True)

    # The basemap **before** any data: it used to draw nothing, because the
    # viewport was only built once a layer existed.
    item_early = canvas()
    if item_early is not None:
        item_early.setProperty("basemapSource", "osm")
        settle(4000)
        note("a basemap chosen before any data "
             f"(attribution: {item_early.property('basemapAttribution')})")
        item_early.setProperty("basemapSource", "")
        settle(200)

    verdicts: list[dict] = []
    controller.datasetValidated.connect(verdicts.append)
    controller.validateDataset(str(TABLE), {"crs": "26912", "unit": "mGal"})
    wait_for(lambda: bool(verdicts))
    controller.importDataset(str(TABLE), "table")
    settle(1200)
    note(f"a table imported and drawn ({controller.layers.count} layer)")

    controller.addLayer(str(RASTER), "distance", "original", "m")
    settle(1000)
    note(f"a raster added ({controller.layers.count} layers)")

    item = canvas()
    if item is None:
        print("FAIL: the canvas is not in the loaded shell")
        return 1

    drag(item, options.steps)
    note(f"panned {options.steps} steps with the cursor reading values")

    item.setProperty("viewCrs", "EPSG:4326")
    settle(800)
    note(f"the view reprojected to {item.property('viewCrs')}")

    item.setProperty("basemapSource", "osm")
    settle(5000)
    note("the basemap turned on")

    drag(item, max(20, options.steps // 3))
    note("panned again, over the basemap")

    for factor in (0.8, 1.25, 0.8, 1.25):
        item.zoomBy(factor)
        settle(250)
    note("zoomed in and out")

    alive = item.property("layerCount")
    controller.shutdown()
    settle(200)
    print(f"\n{len(steps)}/{len(steps)} interactions survived "
          f"({options.loop} render loop, {alive} layers still drawn)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
