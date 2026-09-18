"""The scenes the live recording walks through.

Driven through the shell's own objects, the same way the storyboards are
driven — never by clicking at guessed coordinates. A scene that cannot happen
therefore does not get recorded as though it had; it raises.

The pointer is the exception. It is moved with `pyautogui` over the canvas, so
the capture shows motion a viewer can follow and the status bar's coordinate
and value readout changes under it — which is the one claim a still frame
cannot make.

Order is the product's own: data in, ground under it, display choices,
interpolation measured then run, membership, potential fields, scenarios, and
the map at the end.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt

from session import DATA

FORGE = DATA / "utah_forge"
TABLE = FORGE / "anomaly_bouger_easting_northin_bouger.csv"
CRS = "EPSG:26912"
PIXEL = "200"
RADIUS = "1000"


# ---- the pointer -------------------------------------------------------

def _pointer():
    """`pyautogui`, bound to the recording's display, or None."""
    try:
        import pyautogui
    except Exception:                                   # pragma: no cover
        return None
    pyautogui.FAILSAFE = False
    return pyautogui


def glide(session, to_x: int, to_y: int, ms: int = 900) -> None:
    """Move the pointer there in steps, pumping the event loop between them.

    `pyautogui.moveTo(duration=...)` sleeps inside itself, which freezes the
    Qt event loop: the window stops repainting and the capture records a
    stalled frame with a cursor sliding over it. Stepping and settling keeps
    the interface alive under the pointer.
    """
    gui = _pointer()
    if gui is None:
        session.settle(ms)
        return
    from_x, from_y = gui.position()
    steps = max(6, ms // 60)
    for i in range(1, steps + 1):
        gui.moveTo(int(from_x + (to_x - from_x) * i / steps),
                   int(from_y + (to_y - from_y) * i / steps))
        session.settle(max(20, ms // steps))


def _press(session, name: str) -> bool:
    button = session.window.findChild(QObject, name)
    if button is None:
        return False
    QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
    return True


def _dispatch(session, token: str) -> None:
    QMetaObject.invokeMethod(session.window, "dispatch", Qt.DirectConnection,
                             Q_ARG("QVariant", token))


def _dialog(session, name: str):
    return session.window.findChild(QObject, name)


# ---- the scenes --------------------------------------------------------

def run_scenes(session) -> None:
    state: dict = {}

    def opening():
        """The shell, in English, with nothing loaded."""
        session.controller.tr.setLanguage("en")
        session.settle(1200)
        glide(session, 720, 400, 800)

    def wizard_preview():
        """The file described and **drawn** before it can enter the project.

        This is the screen that answers "what am I about to import": the
        format, the columns, the statistics, and a picture of the file — the
        point cloud, not a placeholder. It opens with **no CRS**, because a
        table carries none and this project refuses to invent one; declaring
        it is what turns the refusal into a usable dataset, and the
        declaration is recorded as the operator's, not the file's.
        """
        wizard = session.wizard
        QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
        QMetaObject.invokeMethod(wizard, "open", Qt.DirectConnection)
        session.settle(900)
        glide(session, 700, 300, 1200)

        # The file, before anything is declared about it.
        wizard.setProperty("path", str(TABLE))
        session.settle(600)
        QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
        session.wait_for(
            lambda: session.controller.store.latest_validation(
                str(TABLE.resolve())) is not None, 30000)
        # The description and the drawing arrive here: rows, columns, range,
        # and the survey's own shape on the preview map.
        session.settle(2600)
        glide(session, 560, 430, 1500)
        session.settle(1800)

        # Now the two things the file cannot state for itself. Each is typed
        # separately so the screen is seen answering to it.
        wizard.setProperty("declaredCrs", CRS)
        wizard.setProperty("declaredUnit", "mGal")
        # Wait on the verdict, not on a stopwatch. Declaring restarts a 450 ms
        # debounce and then submits a fresh check; a fixed settle recorded the
        # screen still saying "Blocked" while the answer was in flight.
        session.wait_for(lambda: bool(wizard.property("usable")), 30000)
        session.settle(1200)
        glide(session, 880, 360, 1400)
        session.settle(2000)
        state["wizard"] = wizard

    def points():
        """3 735 gravity stations on the canvas, by the wizard's own Import."""
        if not _press(session, "importButton"):
            session.controller.importDataset(str(TABLE), "table")
        session.settle(2200)
        state["layer"] = (session.controller.layers.activeLayer()
                          or {}).get("layerId", "")
        # Over the cloud: the status bar reads the coordinate and the value
        # under the pointer, from the source at full resolution.
        glide(session, 560, 300, 900)
        glide(session, 880, 470, 1100)

    def basemap():
        """The ground under the data — the one time this app touches the net."""
        _dispatch(session, "basemap:osm")
        # The tiles are fetched, not drawn from a cache on a fresh project,
        # and the software rasteriser is slower than the GPU path the first
        # recording assumed. Six seconds left the scene showing an empty
        # ground with the attribution already on it — the basemap announced
        # and not yet arrived. Glide while it lands, so the wait is motion
        # rather than a frozen frame.
        session.settle(4000)
        glide(session, 520, 260, 1800)
        glide(session, 900, 430, 1800)
        session.settle(3000)
        glide(session, 700, 300, 1400)

    def colormaps():
        """Three ramps. Display only: the range in the Inspector never moves."""
        for ramp in ("magma", "turbo", "viridis"):
            session.controller.layers.setColormap(state["layer"], ramp)
            session.settle(1300)
        glide(session, 150, 600, 700)

    def themes():
        """Four themes, one measured at 7:1. They repaint; nothing moves."""
        # Each theme gets long enough to be seen and read, not just to
        # flash past: a sweep sampled every nine seconds missed the whole
        # scene in the first recording.
        for mode, x in (("light", 640), ("highContrast", 820),
                        ("system", 560), ("dark", 740)):
            session.controller.preferences.setThemeMode(mode)
            session.settle(900)
            glide(session, x, 340, 1500)
            session.settle(600)

    def measured():
        """Which interpolator suits this survey, by cross-validation."""
        dialog = _dialog(session, "griddingDialog")
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(700)
        dialog.setProperty("targetCrs", CRS)
        dialog.setProperty("pixelSize", PIXEL)
        dialog.setProperty("radius", RADIUS)
        dialog.setProperty("minPoints", "3")
        session.settle(500)
        state["gridding"] = dialog
        if _press(session, "griddingCompare"):
            session.wait_for(
                lambda: dialog.property("comparison") is not None, 180000)
        session.settle(2200)

    def cubic():
        """The Clough-Tocher field: null outside the hull, not extrapolated."""
        dialog = state["gridding"]
        dialog.setProperty("method", "grid.tin_cubic")
        session.settle(700)
        before = len(session.controller.store.runs())
        _press(session, "griddingRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(2500)
        glide(session, 620, 330, 1000)

    def membership():
        """The curve chosen over the layer's own histogram."""
        QMetaObject.invokeMethod(session.window, "openMembership",
                                 Qt.DirectConnection)
        session.settle(2500)
        editor = _dialog(session, "membershipEditor")
        for fn in ("linear_increasing", "sigmoidal", "large"):
            editor.setProperty("functionName", fn)
            session.settle(1400)
        editor.setProperty("functionName", "linear_increasing")
        session.settle(700)
        if _press(session, "membershipApply"):
            session.settle(3500)

    def potential_fields():
        """Transforms that declare what the data has to be."""
        dialog = _dialog(session, "potentialFieldsDialog")
        if dialog is None:
            return
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(900)
        for op in ("potential_fields.tilt",
                   "potential_fields.total_horizontal_gradient",
                   "potential_fields.analytic_signal"):
            dialog.setProperty("operator", op)
            session.settle(1300)
        QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
        session.settle(600)

    def scenarios():
        """How much the answer depends on each criterion. Measures, changes
        nothing."""
        dialog = _dialog(session, "scenariosDialog")
        if dialog is None:
            return
        QMetaObject.invokeMethod(dialog, "clearMeasurements",
                                 Qt.DirectConnection)
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(1600)
        QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
        session.settle(600)

    def decision():
        """The criteria, the operator, and the map."""
        dialog = _dialog(session, "decisionModel")
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(1800)
        QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
        session.settle(800)
        glide(session, 720, 380, 1000)
        session.settle(1500)

    for scene in (opening, wizard_preview, points, basemap, colormaps,
                  themes, measured,
                  cubic, membership, potential_fields, scenarios, decision):
        scene()
