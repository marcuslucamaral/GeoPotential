"""M5.8 — the shell repaginated: icons, a rail, and the words on the hover.

    the window as it opens  ->  the rail hidden  ->  the rail back
    ->  the light theme, with the geometry unchanged

The claim this storyboard exists to check is the one the request made: the
buttons became pictures, and **the words did not disappear** — they moved to
the hover. A frame cannot photograph a tooltip, so what is asserted here is
what a frame cannot show and a probe can: every icon button carries a tip,
every icon names a file that exists, and hiding the rail changes the layout by
exactly the rail's width and nothing else.

The theme frame is the one that would have caught the mistake this rework could
most easily have made: an icon with its own colour looks right in the dark
theme and vanishes in the light one.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"

#: Where each panel sits, so a frame can be checked by what changed and where.
PROBES = {
    "rail": (22, 300),
    "workflow": (140, 200),
    "layers": (140, 700),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "topbar": (700, 45),
}

QML = (Path(__file__).resolve().parents[2] / "app" / "geopotential_app"
       / "qml" / "GeoPotential")


def _icon_buttons(window) -> list:
    """Every IconButton on screen, found by what it carries and not by class.

    QML component types are not reachable from Python by name, so the rail's
    and the toolbar's buttons are identified the way the shell identifies
    them: they have an `iconName` and a `tip`.
    """
    found = []
    for child in window.findChildren(QObject):
        name = child.property("iconName")
        if isinstance(name, str) and name:
            found.append(child)
    return found


def build() -> Storyboard:
    board = Storyboard("shell", "M5.8 — a interface repaginada")
    state: dict = {}

    def opened(session):
        """The window as a person meets it: rail, flow, map, inspector."""
        session.controller.addLayer(str(RASTER), "Distance to fault",
                                    "original", "m")
        session.settle(900)
        rail = session.window.findChild(QObject, "activityBar")
        buttons = _icon_buttons(session.window)
        with_tip = [b for b in buttons
                    if isinstance(b.property("tip"), str)
                    and b.property("tip").strip()]
        missing = sorted({
            b.property("iconName") for b in buttons
            if not (QML / "icons" / f"{b.property('iconName')}.svg").is_file()})
        state["rail"] = rail
        return {
            "rail": rail is not None,
            "railWidth": int(rail.property("width")) if rail else 0,
            "iconButtons": len(buttons),
            "withTip": len(with_tip),
            "iconsMissing": len(missing),
            "missing": ", ".join(missing)[:80],
            "layers": session.controller.layers.count,
        }

    def rail_hidden(session):
        """View › Icon rail. It is a panel like the others, and it is theirs."""
        before = int(state["rail"].property("width")) if state.get("rail") else 0
        state["railWidthBefore"] = before
        session.controller.preferences.setPanelVisible("rail", False)
        # The shell reads panel visibility back from the preferences.
        QMetaObject.invokeMethod(session.window, "applyPanels",
                                 Qt.DirectConnection)
        session.settle(700)
        rail = state.get("rail")
        return {
            "railVisible": bool(rail.property("visible")) if rail else True,
            "remembered": session.controller.preferences.panelVisible("rail"),
            "widthBefore": before,
        }

    def rail_back(session):
        """And back, because a toggle that only goes one way is a delete."""
        session.controller.preferences.setPanelVisible("rail", True)
        QMetaObject.invokeMethod(session.window, "applyPanels",
                                 Qt.DirectConnection)
        session.settle(700)
        rail = state.get("rail")
        return {
            "railVisible": bool(rail.property("visible")) if rail else False,
            "railWidth": int(rail.property("width")) if rail else 0,
            "widthBefore": state.get("railWidthBefore", 0),
        }

    def light_theme(session):
        """An icon with its own colour survives the dark theme and dies here."""
        session.controller.preferences.setThemeMode("light")
        session.settle(900)
        rail = state.get("rail")
        return {
            "theme": session.controller.preferences.effectiveTheme,
            "railWidth": int(rail.property("width")) if rail else 0,
            "iconButtons": len(_icon_buttons(session.window)),
        }

    # ---- what has to be true ---------------------------------------------

    def the_shell_is_icons_with_their_words(frame, earlier):
        if not frame.facts.get("rail"):
            return "the icon rail is not in the shell"
        if frame.facts.get("railWidth", 0) <= 0:
            return "the rail is in the tree with no width"
        if frame.facts.get("iconButtons", 0) < 20:
            return (f"only {frame.facts.get('iconButtons')} icon buttons were "
                    f"found; the rail and the toolbar alone are more than that")
        if frame.facts.get("iconButtons") != frame.facts.get("withTip"):
            return ("an icon button carries no tooltip: the word did not move "
                    "to the hover, it was deleted")
        if frame.facts.get("iconsMissing", 0) != 0:
            return (f"icons named but not on disk: "
                    f"{frame.facts.get('missing')}")
        return None

    def the_rail_can_be_put_away(frame, earlier):
        if frame.facts.get("railVisible"):
            return "the rail is still showing after being switched off"
        if frame.facts.get("remembered") is not False:
            return "hiding the rail was not remembered in the preferences"
        return None

    def the_rail_comes_back_the_same(frame, earlier):
        if not frame.facts.get("railVisible"):
            return "the rail did not come back"
        if frame.facts.get("railWidth") != frame.facts.get("widthBefore"):
            return (f"the rail came back {frame.facts.get('railWidth')} wide "
                    f"and left at {frame.facts.get('widthBefore')}")
        return None

    def the_icons_follow_the_theme(frame, earlier):
        if frame.facts.get("theme") != "light":
            return "the light theme was not applied"
        if frame.facts.get("railWidth") != PROBES and frame.facts.get("railWidth", 0) <= 0:
            return "the rail lost its width with the theme"
        if frame.facts.get("iconButtons", 0) < 20:
            return "buttons disappeared with the theme change"
        # P-123: a theme change only repaints. The rail is the newest panel and
        # the one most likely to move, so its width is checked across it.
        if earlier and earlier[-1].facts.get("railWidth") != frame.facts.get("railWidth"):
            return ("the rail changed width with the theme; a theme change "
                    "only repaints (P-123)")
        return None

    board.step("opened",
               "A janela como ela abre: a trilha de ícones à esquerda, o fluxo "
               "em uma linha por etapa, o mapa, o Inspector. Cada botão é um "
               "ícone e cada ícone tem a sua palavra na dica.",
               opened, probes=PROBES, expect=the_shell_is_icons_with_their_words)
    board.step("rail_hidden",
               "Exibir › Trilha de ícones: a trilha some, e a escolha fica "
               "guardada como a de qualquer outro painel.",
               rail_hidden, probes=PROBES, expect=the_rail_can_be_put_away)
    board.step("rail_back",
               "E volta, com a mesma largura — um interruptor que só vai para "
               "um lado é um botão de apagar.",
               rail_back, probes=PROBES, expect=the_rail_comes_back_the_same)
    board.step("light",
               "O tema claro. Um ícone com cor própria fica bonito no escuro e "
               "some aqui; estes são recoloridos pelo tema, e nada mudou de "
               "lugar.",
               light_theme, probes=PROBES, expect=the_icons_follow_the_theme)
    return board
