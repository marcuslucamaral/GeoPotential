"""M5.7 — choosing the interpolator by measurement, not by default.

    a lattice CSV imported  ->  the screen measures which method errs least
    ->  the recommended method runs  ->  IDW runs on the same data, for contrast

The claim this storyboard exists to check is the one the user found by using
the application: on `vp_500_m.csv` — 1 626 samples on a regular 125 m lattice —
IDW came out mottled and pulled toward the mean, and the screen offered no
other method. So the frames have to show three things happening on the real
window, not three controls existing:

  1. the comparison **runs in the worker** and comes back with a ranking;
  2. the method the person picks is the one that runs;
  3. the two runs differ in the way the measurement predicted — the
     triangulated field spans more of the data's range than IDW's.

Every number here comes from the runs' own manifests and from the worker's
cross-validation result, never from a description of what they should say.
"""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

#: A regular lattice, which is the case IDW handles worst and the one the
#: report was about. The Bouguer survey in the `gridding` storyboard is the
#: opposite case and is deliberately left there.
TABLE = DATA / "utah_forge" / "vp_500_m.csv"

TARGET_CRS = "EPSG:26912"
#: Coarse on purpose: this is about the path and the ranking, and a 125 m
#: pixel over this survey is a second rather than a minute.
PIXEL = "125"
RADIUS = "375"

PROBES = {
    "workflow": (100, 200),
    "layers": (100, 700),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "statusbar": (700, 869),
}


def _press(session, name: str) -> bool:
    button = session.window.findChild(QObject, name)
    if button is None:
        return False
    QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
    return True


def _span(manifest: dict) -> float:
    """How much of the field's range the run actually produced."""
    stats = manifest.get("statistics") or {}
    low, high = stats.get("min"), stats.get("max")
    if low is None or high is None:
        return 0.0
    return float(high) - float(low)


def build() -> Storyboard:
    board = Storyboard("interpolation", "M5.7 — o método é medido, não suposto")
    state: dict = {}

    def imported(session):
        """The lattice in the project, and the methods it is offered."""
        wizard = session.wizard
        QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
        wizard.setProperty("path", str(TABLE))
        wizard.setProperty("declaredCrs", TARGET_CRS)
        wizard.setProperty("declaredUnit", "km/s")
        QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
        session.wait_for(
            lambda: session.controller.store.latest_validation(
                str(TABLE.resolve())) is not None, 30000)
        session.settle(300)
        session.controller.importDataset(str(TABLE), "table")
        session.settle(800)
        offered = session.controller.griddableDatasets()
        methods = offered[0]["methods"] if offered else []
        return {
            "datasets": len(session.controller.store.datasets()),
            "layers": session.controller.layers.count,
            "methods": len(methods),
            "has_tin": "grid.tin_cubic" in methods,
            "spacing": round(float(offered[0]["spacing"] or 0), 1)
            if offered else 0,
        }

    def measured(session):
        """The comparison, run by the worker on the samples themselves."""
        dialog = session.window.findChild(QObject, "griddingDialog")
        if dialog is None:
            return {"opened": False}
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(400)
        dialog.setProperty("targetCrs", TARGET_CRS)
        dialog.setProperty("pixelSize", PIXEL)
        dialog.setProperty("radius", RADIUS)
        session.settle(200)
        state["dialog"] = dialog

        pressed = _press(session, "griddingCompare")
        session.wait_for(lambda: dialog.property("comparison") is not None,
                         120000)
        session.settle(600)
        comparison = dialog.property("comparison") or {}
        rows = comparison.get("methods") or []
        by_name = {r["method"]: r for r in rows}
        return {
            "opened": True,
            "pressed": pressed,
            "scored": len(rows),
            "recommended": comparison.get("recommended", ""),
            "idw_rmse": round(float(by_name.get("grid.idw", {}).get("rmse")
                                    or 0.0), 5),
            "cubic_rmse": round(float(by_name.get("grid.tin_cubic", {}).get("rmse")
                                      or 0.0), 5),
            # The comparison must not have committed anything: it is a probe.
            "runs": len(session.controller.store.runs()),
        }

    def controls_swapped(session):
        """Choosing a triangulated method swaps the controls, not just a label.

        IDW has a search radius and a power; a triangulation has neither, and
        it has an optional maximum distance instead. Leaving a radius box on
        screen under a method that ignores it is a control that does nothing,
        which is worse than a missing one.
        """
        dialog = state["dialog"]
        dialog.setProperty("method", "grid.tin_cubic")
        session.settle(500)
        radius = session.window.findChild(QObject, "griddingRadius")
        max_distance = session.window.findChild(QObject, "griddingMaxDistance")
        return {
            "method": str(dialog.property("method")),
            "interpolates": bool(dialog.property("interpolates")),
            "usesRadius": bool(dialog.property("usesRadius")),
            "triangulated": bool(dialog.property("triangulated")),
            # Visible, not merely present: both exist in the tree either way.
            "radius_visible": bool(radius.property("visible")) if radius else None,
            "maxdist_visible": (bool(max_distance.property("visible"))
                                if max_distance else None),
            "ready": bool(dialog.property("ready")),
        }

    def recommended_ran(session):
        """The method the comparison recommended, run and on the canvas."""
        dialog = state.get("dialog")
        comparison = dialog.property("comparison") or {}
        chosen = comparison.get("recommended") or "grid.tin_cubic"
        dialog.setProperty("method", chosen)
        session.settle(300)
        before = len(session.controller.store.runs())
        pressed = _press(session, "griddingRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(1200)
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        state["recommended_manifest"] = manifest
        gridding = manifest.get("gridding") or {}
        stats = manifest.get("statistics") or {}
        return {
            "pressed": pressed,
            "chose": chosen,
            "operator": manifest.get("operator", ""),
            "method": gridding.get("method", ""),
            "bounded_by": gridding.get("bounded_by", ""),
            "span": round(_span(manifest), 4),
            "valid": round(float(stats.get("valid_fraction") or 0.0) * 100, 1),
            # The cubic's overshoot is reported, never clamped (ADR-MSP-007).
            "overshoot_reported": stats.get("overshoot") is not None,
            "artifacts": len(session.controller.store.artifacts(runs[-1].id))
            if len(runs) > before else 0,
        }

    def idw_for_contrast(session):
        """IDW on the same samples and the same grid, for the comparison."""
        dialog = state.get("dialog")
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(400)
        dialog.setProperty("method", "grid.idw")
        dialog.setProperty("targetCrs", TARGET_CRS)
        dialog.setProperty("pixelSize", PIXEL)
        dialog.setProperty("radius", RADIUS)
        session.settle(300)
        before = len(session.controller.store.runs())
        pressed = _press(session, "griddingRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(1200)
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        recommended = state.get("recommended_manifest") or {}
        return {
            "pressed": pressed,
            "operator": manifest.get("operator", ""),
            "idw_span": round(_span(manifest), 4),
            "recommended_span": round(_span(recommended), 4),
            "runs": len(runs),
            "harmonisable": len(session.controller.harmonizableDatasets()),
        }

    # ---- what has to be true ---------------------------------------------

    def the_lattice_is_offered_every_method(frame, earlier):
        if frame.facts.get("datasets", 0) < 1:
            return "the table did not enter the project"
        if frame.facts.get("layers", 0) < 1:
            return "the table entered the project and was not drawn"
        if not frame.facts.get("has_tin"):
            return ("a table was not offered the triangulated methods; before "
                    "M5.7 IDW was the only interpolator on this screen")
        if frame.facts.get("methods", 0) < 4:
            return (f"a table was offered only {frame.facts.get('methods')} "
                    f"methods")
        return None

    def the_worker_measured_and_ranked(frame, earlier):
        if not frame.facts.get("opened"):
            return "the gridding dialog is not in the shell"
        if not frame.facts.get("pressed"):
            return "the comparison button was not reachable"
        if frame.facts.get("scored", 0) < 3:
            return (f"only {frame.facts.get('scored')} methods were scored; "
                    f"three interpolators are offered")
        if not frame.facts.get("recommended"):
            return "the comparison came back with no recommendation"
        if frame.facts.get("runs", 0) != 0:
            return ("the comparison committed a run; it is a read-only probe "
                    "and must commit nothing (P-53)")
        idw, cubic = frame.facts.get("idw_rmse"), frame.facts.get("cubic_rmse")
        if not (idw and cubic):
            return "a method came back with no error at all"
        if cubic >= idw:
            return (f"on a regular lattice Clough-Tocher did not beat IDW "
                    f"({cubic} vs {idw}); that ordering is the finding this "
                    f"milestone rests on")
        return None

    def a_method_without_a_radius_shows_none(frame, earlier):
        if frame.facts.get("method") != "grid.tin_cubic":
            return "the method did not change"
        if not frame.facts.get("interpolates"):
            return "a triangulated method did not declare that it estimates"
        if not frame.facts.get("triangulated"):
            return "the screen does not know this method is triangulated"
        if frame.facts.get("usesRadius"):
            return "the screen thinks a triangulation has a search radius"
        if frame.facts.get("radius_visible") is not False:
            return ("the search radius is still on screen under a method that "
                    "ignores it")
        if frame.facts.get("maxdist_visible") is not True:
            return "the maximum distance, which this method does take, is hidden"
        if not frame.facts.get("ready"):
            return ("the screen is not ready without a radius, although a "
                    "triangulation does not need one")
        return None

    def the_chosen_method_is_the_one_that_ran(frame, earlier):
        if not frame.facts.get("pressed"):
            return "the Build button was not reachable"
        if frame.facts.get("operator") != frame.facts.get("chose"):
            return (f"the screen chose {frame.facts.get('chose')!r} and "
                    f"{frame.facts.get('operator')!r} ran")
        if frame.facts.get("artifacts", 0) < 1:
            return "the run committed no raster"
        if float(frame.facts.get("valid") or 0) <= 0:
            return "the field came out empty; every cell is null"
        if frame.facts.get("bounded_by") != "convex hull of the samples":
            return ("the manifest does not record what bounded the "
                    "triangulation")
        if not frame.facts.get("overshoot_reported"):
            return ("the manifest carries no overshoot; ADR-MSP-007 requires "
                    "it measured and recorded rather than clamped")
        return None

    def the_two_runs_differ_as_measured(frame, earlier):
        if not frame.facts.get("pressed"):
            return "the second run did not start"
        if frame.facts.get("operator") != "grid.idw":
            return f"the contrast run was {frame.facts.get('operator')!r}"
        idw = float(frame.facts.get("idw_span") or 0)
        best = float(frame.facts.get("recommended_span") or 0)
        if idw <= 0 or best <= 0:
            return "one of the two runs produced no range at all"
        if best <= idw:
            return (f"the recommended method spanned {best} and IDW spanned "
                    f"{idw}; a weighted mean cannot reach further than a "
                    f"method that reproduces the samples, so this ordering "
                    f"failing means the two runs are not what they say")
        if frame.facts.get("harmonisable", 0) < 2:
            return "the two rasters did not both reach harmonisation"
        return None

    board.step("imported",
               "O CSV numa malha regular de 125 m entra no projeto, e a tela "
               "passa a oferecer os três interpoladores do QGIS, não só o IDW.",
               imported, probes=PROBES,
               expect=the_lattice_is_offered_every_method)
    board.step("measured",
               "O worker separa um quinto das amostras e mede o erro de cada "
               "método. Nada é gravado: é uma sondagem, e a escolha continua "
               "sendo de quem opera.",
               measured, probes=PROBES,
               expect=the_worker_measured_and_ranked)
    board.step("controls",
               "Escolher um método triangulado troca os controles: some o "
               "raio de busca, que ele não tem, e aparece a distância máxima, "
               "que ele aceita. Aparece também o aviso do cúbico.",
               controls_swapped, probes=PROBES,
               expect=a_method_without_a_radius_shows_none)
    board.step("recommended",
               "O método recomendado roda, e o manifesto registra o que "
               "limitou a superfície e quanto ela passou do intervalo das "
               "amostras.",
               recommended_ran, probes=PROBES,
               expect=the_chosen_method_is_the_one_that_ran)
    board.step("idw_contrast",
               "O IDW na mesma grade, para contraste: a média ponderada "
               "alcança menos da faixa do dado do que o método recomendado.",
               idw_for_contrast, probes=PROBES,
               expect=the_two_runs_differ_as_measured)
    return board
