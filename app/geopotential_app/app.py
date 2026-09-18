"""Entry point.

    python -m geopotential_app FILE.tif        the workspace, Qt Quick
    python -m geopotential_app --self-test     the M1 gate, headless
    python -m geopotential_app --screenshot P  capture the running window
    python -m geopotential_app --version

The application is the only place that assembles objects. QML declares the
interface; it does not wire anything.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from ._version import VERSION
from .controllers.app_controller import AppController
from .utils.paths import qml_dir, repository_root

# The dataset the slice runs on when none is given. It is real: EPSG:26912,
# 10 m, a distance-to-fault field over the Utah FORGE geothermal site.
DEFAULT_INPUT = repository_root() / "data" / "utah_forge" / "Distance_to_fault.tif"


def _register_qml_types() -> None:
    from PySide6.QtQml import qmlRegisterType

    from .render.geocanvas.map_item import MapItem

    qmlRegisterType(MapItem, "GeoPotential.Canvas", 1, 0, "MapItem")


def _follow_system_theme(app, controller: AppController) -> None:  # noqa: ANN001
    """Keep `preferences.systemDark` in step with the desktop.

    Qt reports `Unknown` on platforms and plugins that cannot say — offscreen
    is one — and unknown is not light: this application's default is dark, so
    only an explicit `Light` turns it off.
    """
    from PySide6.QtCore import Qt

    hints = app.styleHints()

    def apply() -> None:
        controller.preferences.setSystemDark(
            hints.colorScheme() != Qt.ColorScheme.Light)

    apply()
    # The desktop can change while the application is open, and a theme that
    # only follows at startup is a theme that stops following.
    hints.colorSchemeChanged.connect(lambda _scheme: apply())


def _build_engine(controller: AppController):
    from .utils.qt import QQmlApplicationEngine, QUrl

    engine = QQmlApplicationEngine()
    # The import path is the directory *containing* `GeoPotential/`, because a
    # QML module's directory name is its module name. Pointing at the module
    # directory itself leaves `module "GeoPotential" is not installed`, and
    # every `Theme.*` binding then becomes undefined — which presents as a
    # theme bug rather than an import one.
    engine.addImportPath(str(qml_dir()))

    # Icons are SVG files tinted by the theme. The tint is done on the CPU
    # rather than by a shader effect, because the shader effects draw nothing
    # under the offscreen platform every storyboard is captured with —
    # `icons.py` records the measurement.
    from . import icons

    icons.install(engine, qml_dir())

    # The controller reaches QML through setInitialProperties against a
    # `required property` on the root, not as a context property: a context
    # property leaves one binding pass running against null.
    #
    # The controller, and nothing else: no dataset, no operator, no parameter.
    # Every action the shell offers comes from the workflow, whose state is
    # derived from the Project Store, so no interface path can depend on
    # something only a gate supplies (P-122).
    engine.setInitialProperties({"controller": controller})
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("the QML shell did not load; see the Qt warnings above")
    return engine


def run_gui(argv: argparse.Namespace) -> int:
    from .utils.qt import QGuiApplication

    # **The scene graph renders on this thread, not on its own.**
    #
    # `QQuickPaintedItem.paint` is called on the render thread under Qt's
    # default threaded loop. Our canvas reads a GeoTIFF through GDAL while it
    # paints, and the same dataset is read from the GUI thread for the value
    # under the cursor: two threads, one GDAL handle, and a segmentation fault
    # that shows up when panning and never in a headless test — because the
    # offscreen platform already uses this basic loop.
    #
    # The canvas is CPU-painted (ADR: no QQuickRhiItem until a measurement asks
    # for one), so a threaded render loop buys nothing here and costs
    # correctness.
    os.environ.setdefault("QSG_RENDER_LOOP", "basic")

    app = QGuiApplication(sys.argv)
    _register_qml_types()

    controller = AppController()
    # The desktop's own light/dark setting, pushed in from here because reading
    # it needs QtGui and `preferences.py` is on the QtCore-only side. It only
    # decides anything while the chosen theme is `system`.
    _follow_system_theme(app, controller)
    if argv.project:
        project_root = Path(argv.project)
        if project_root.exists():
            controller.openProject(str(project_root))
        else:
            controller.createProject(str(project_root), project_root.stem)

    engine = _build_engine(controller)
    # A file named on the command line enters through the same door as any
    # other file: the Import Wizard, with its QA/QC. It is a convenience, not
    # a second way in.
    if argv.input:
        from .utils.qt import Q_ARG, QMetaObject, Qt

        window = engine.rootObjects()[0]
        QMetaObject.invokeMethod(
            window, "openImport", Qt.QueuedConnection,
            Q_ARG("QVariant", str(Path(argv.input).resolve())))
    app.aboutToQuit.connect(controller.shutdown)
    code = app.exec()
    del engine
    return code


def _default_project() -> Path:
    """The project a `--project` run reuses when it names one that is absent.

    Launching with no project no longer creates one: the application opens with
    the Project Hub and step 1 of the workflow waiting, because a project
    nobody asked for is a project nobody knows they have — and twelve of them
    ended up in someone's recents.
    """
    return Path(tempfile.gettempdir()) / "geopotential-session.gpot"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="geopotential_app",
        description="GeoPotential Professional — spatial MCDA for geothermal "
                    "and potential-field data.",
    )
    parser.add_argument(
        "input", nargs="?",
        help="a dataset to open the Import Wizard on")
    parser.add_argument("--project", help="path to a .gpot project directory")
    parser.add_argument("--version", action="store_true", help="print the version")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the M1 vertical-slice gate headless and exit",
    )
    parser.add_argument(
        "--screenshot", metavar="PATH", help="capture the running window and exit"
    )
    parser.add_argument("--size", default="1440x880", help="screenshot size, WxH")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        print(VERSION)
        return 0
    if args.self_test:
        from .self_test import run_self_test

        return run_self_test(Path(args.input) if args.input else DEFAULT_INPUT)
    if args.screenshot:
        from .self_test import run_screenshot

        return run_screenshot(
            Path(args.screenshot),
            args.size,
            Path(args.input or DEFAULT_INPUT),
            Path(args.project) if args.project else None,
        )
    return run_gui(args)
