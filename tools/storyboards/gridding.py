"""M5.6 — a CSV of scattered samples becomes a raster criterion.

    a table imported  ->  the gridding screen, with the method named
    ->  the interpolated field on the canvas

The claim this storyboard exists to check is the one the user found by using
the application: before M5.6 a CSV could be imported, checked and drawn, and
then had nowhere to go — `grid.harmonize` reads rasters, and the only screen
that builds an analysis grid filtered tables out without saying why.

Every number here comes from the run's own manifest, not from a description of
what the run should have done.
"""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

TABLE = DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
#: Um segundo raster, com outra extensão. Com uma camada só as duas
#: políticas de extensão coincidem, e o quadro que as compara não provaria
#: nada.
RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"

#: The grid the operator chooses. Coarse on purpose: the storyboard is about
#: the path, and a 200 m pixel over this survey is a second, not a minute.
TARGET_CRS = "EPSG:26912"
PIXEL = "200"
RADIUS = "1000"

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


def build() -> Storyboard:
    board = Storyboard("gridding", "M5.6 — dado esparso vira critério")
    state: dict = {}

    def imported(session):
        """The CSV in the project: 3 735 samples, drawn, and not a grid."""
        wizard = session.wizard
        QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
        wizard.setProperty("path", str(TABLE))
        wizard.setProperty("declaredCrs", TARGET_CRS)
        wizard.setProperty("declaredUnit", "mGal")
        QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
        session.wait_for(
            lambda: session.controller.store.latest_validation(
                str(TABLE.resolve())) is not None, 30000)
        session.settle(300)
        session.controller.importDataset(str(TABLE), "table")
        session.settle(800)
        return {
            "datasets": len(session.controller.store.datasets()),
            "layers": session.controller.layers.count,
            # The point: a table is not harmonisable, and that is not a bug.
            "harmonisable": len(session.controller.harmonizableDatasets()),
            "griddable": len(session.controller.griddableDatasets()),
        }

    def chosen(session):
        """The gridding screen, with the method and what it does to the data."""
        dialog = session.window.findChild(QObject, "griddingDialog")
        if dialog is None:
            return {"opened": False}
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(400)
        dialog.setProperty("targetCrs", TARGET_CRS)
        dialog.setProperty("pixelSize", PIXEL)
        dialog.setProperty("radius", RADIUS)
        dialog.setProperty("minPoints", "3")
        session.settle(300)
        state["dialog"] = dialog
        return {
            "opened": True,
            "method": str(dialog.property("method")),
            "interpolates": bool(dialog.property("interpolates")),
            "ready": bool(dialog.property("ready")),
        }

    def gridded(session):
        """The run, and the field it produced."""
        before = len(session.controller.store.runs())
        pressed = _press(session, "griddingRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 120000)
        session.settle(1200)
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        grid = manifest.get("grid", {})
        stats = manifest.get("statistics", {})
        return {
            "pressed": pressed,
            "operator": manifest.get("operator", ""),
            "grid": f"{grid.get('width')}x{grid.get('height')}",
            "pixel": grid.get("pixel_size_x"),
            "valid": round(float(stats.get("valid_fraction") or 0.0) * 100, 1),
            "artifacts": len(session.controller.store.artifacts(runs[-1].id))
            if len(runs) > before else 0,
            "harmonisable": len(session.controller.harmonizableDatasets()),
        }

    def policies(session):
        """A escolha da extensão, com os dois números na tela antes dela.

        A grade que saiu do CSV e o raster de distância cobrem áreas
        diferentes, que é o caso em que interseção e união deixam de ser duas
        grafias de uma coisa só. `grid.compare_policies` é read-only: mede o
        que cada uma daria sem harmonizar nada.
        """
        # Pelo mesmo caminho do quadro 1: o dataset é validado antes de
        # entrar. Chamar `importDataset` sem isso não registra nada, e o
        # `expect` deste quadro pegou exatamente isso ao ser escrito.
        wizard = session.wizard
        QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
        wizard.setProperty("path", str(RASTER))
        wizard.setProperty("declaredCrs", TARGET_CRS)
        wizard.setProperty("declaredUnit", "m")
        QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
        session.wait_for(
            lambda: session.controller.store.latest_validation(
                str(RASTER.resolve())) is not None, 30000)
        session.settle(300)
        session.controller.importDataset(str(RASTER), "raster")
        session.settle(800)

        dialog = session.window.findChild(QObject, "harmonizeDialog")
        if dialog is None:
            return {"opened": False}
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(300)
        dialog.setProperty("targetCrs", TARGET_CRS)
        dialog.setProperty("pixelSize", PIXEL)
        session.settle(100)

        # Antes e depois, no mesmo quadro: uma sonda read-only não pode
        # acrescentar run nenhuma à linhagem do projeto (P-53).
        runs_before = len(session.controller.store.runs())
        pressed = _press(session, "harmonizeCompare")
        session.wait_for(lambda: dialog.property("comparison") is not None,
                         120000)
        session.settle(600)

        def facts(name):
            found = dialog.property("comparison").get("policies") or []
            for row in found:
                if row.get("policy") == name:
                    return row
            return {}

        a, b = facts("intersection"), facts("union")
        return {
            "opened": True,
            "pressed": pressed,
            "offered": len(dialog.property("datasets") or []),
            "intersection_cells": a.get("cells", 0),
            "intersection_scored": round(a.get("scored_fraction", 0) * 100, 1),
            "union_cells": b.get("cells", 0),
            "union_scored": round(b.get("scored_fraction", 0) * 100, 1),
            # A leitura que os dois números sozinhos não davam.
            "scored_cells_intersection": a.get("scored_cells", 0),
            "scored_cells_union": b.get("scored_cells", 0),
            "runs_before": runs_before,
            "runs_after": len(session.controller.store.runs()),
        }

    # ---- what has to be true ---------------------------------------------

    def a_table_is_not_harmonisable(frame, earlier):
        if frame.facts.get("datasets", 0) < 1:
            return "the table did not enter the project"
        if frame.facts.get("layers", 0) < 1:
            return "the table entered the project and was not drawn"
        if frame.facts.get("harmonisable", 0) != 0:
            return ("a table was offered for harmonisation; harmonize reads "
                    "rasters and would fail on it")
        if frame.facts.get("griddable", 0) < 1:
            return "the table was offered no way onto a grid at all"
        return None

    def the_method_is_named(frame, earlier):
        if not frame.facts.get("opened"):
            return "the gridding dialog is not in the shell"
        if frame.facts.get("method") != "grid.idw":
            return f"a table was offered {frame.facts.get('method')!r} first"
        if not frame.facts.get("interpolates"):
            return "IDW did not declare that it estimates"
        if not frame.facts.get("ready"):
            return "the screen was not ready with a CRS, a pixel and a radius"
        return None

    def a_criterion_came_out(frame, earlier):
        if not frame.facts.get("pressed"):
            return "the Build button was not reachable"
        if frame.facts.get("operator") != "grid.idw":
            return f"the run was {frame.facts.get('operator')!r}"
        if frame.facts.get("artifacts", 0) < 1:
            return "the run committed no raster"
        if float(frame.facts.get("valid") or 0) <= 0:
            return "the field came out empty; every cell is null"
        if frame.facts.get("harmonisable", 0) < 1:
            return ("the raster it produced is still not harmonisable, so the "
                    "table reached a grid and stopped there")
        return None

    def the_choice_stops_being_blind(frame, earlier):
        if not frame.facts.get("opened"):
            return "a tela de harmonização não está no shell"
        if not frame.facts.get("pressed"):
            return "o botão de comparar não estava alcançável"
        if frame.facts.get("offered", 0) < 2:
            return ("só uma camada foi oferecida; com uma camada as duas "
                    "políticas coincidem e o quadro não prova nada")
        if frame.facts.get("union_cells", 0) <= frame.facts.get(
                "intersection_cells", 0):
            return "a união não deu uma grade maior que a interseção"
        if frame.facts.get("union_scored", 0) >= frame.facts.get(
                "intersection_scored", 0):
            return ("a união não tem fração menor de células com score; então "
                    "as duas políticas dariam o mesmo mapa e não há escolha "
                    "a informar")
        # O ponto: a união acrescenta área, não acrescenta score. Com uma
        # tolerância, porque as duas grades têm origens diferentes e as
        # células não caem exatamente uma sobre a outra.
        with_all = frame.facts.get("scored_cells_intersection", 0)
        union_all = frame.facts.get("scored_cells_union", 0)
        if with_all <= 0:
            return "a interseção não tem célula nenhuma com score"
        if abs(union_all - with_all) / with_all > 0.02:
            return (f"a união tem {union_all} células com score contra "
                    f"{with_all} da interseção; um score precisa de todos os "
                    f"critérios, então as duas têm de ser praticamente a "
                    f"mesma área")
        if frame.facts.get("runs_after") != frame.facts.get("runs_before"):
            return ("a sonda registrou uma run; ela é read-only e não computa "
                    "resultado nenhum (P-53)")
        return None

    board.step("imported", "O CSV no projeto: amostras desenhadas, e nenhuma "
               "delas harmonizável — harmonização lê raster.",
               imported, probes=PROBES, expect=a_table_is_not_harmonisable)
    board.step("chosen", "A tela de gerar grade, com o método escolhido e o "
               "aviso de que IDW estima valor onde nada foi medido.",
               chosen, probes=PROBES, expect=the_method_is_named)
    board.step("gridded", "O campo interpolado no canvas, e o raster que "
               "saiu já entra na harmonização.",
               gridded, probes=PROBES, expect=a_criterion_came_out)
    board.step("policies", "As duas políticas de extensão medidas antes de "
               "escolher: a união dá uma grade maior e a mesma área com "
               "score. Sonda read-only, nenhuma run registrada.",
               policies, probes=PROBES,
               expect=the_choice_stops_being_blind)
    return board
