"""E7 — the four themes, and the claim that a theme only repaints.

    dark  ->  light  ->  high contrast  ->  system, following a light desktop

Two things are asserted across the frames, and neither can be seen by looking:

**Geometry is identical.** Every named panel keeps the same rectangle in all
four, compared exactly and with no tolerance — that is the promise: someone who
turns on high contrast to read the screen must not have to find it again. The
rectangles are read from the live objects, not from the pixels: an edge
detector measures how *visible* a border is, which changes with the palette by
design, and it cannot tell "the panel moved" from "the border got fainter".

**`system` follows the desktop.** The last frame chooses `system` with the
desktop reported as light, and has to come out pixel-identical to the light
frame. A `system` that quietly painted its own palette would pass a check that
only asked whether the screen changed.
"""
from __future__ import annotations

from PySide6.QtCore import QObject  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

CANVAS = DATA / "synthetic" / "msp" / "canvas"
FIELD = CANVAS / "large_field.tif"

PROBES = {
    "menubar": (60, 12),
    "workflow": (100, 200),
    "layers": (100, 700),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "statusbar": (700, 869),
}

#: The panels whose rectangle is compared between themes. Named in the shell,
#: so this reads the real objects and not a second description of the layout.
PANELS = ("appMenuBar", "workflowPanel", "layerPanel", "mapCanvas",
          "mapToolBar", "jobsPanel")


def _layout(session) -> dict:
    """Every named panel's rectangle, in window coordinates.

    Read from the live objects rather than inferred from pixels. An edge
    detector run over a screenshot measures how *visible* a border is, which
    changes with the palette by design — it cannot tell "the panel moved" from
    "the border got fainter", and it reported the first when it saw the second.
    """
    rects = {}
    for name in PANELS:
        item = session.window.findChild(QObject, name)
        if item is None:
            continue
        rects[name] = [round(float(item.property(side) or 0.0), 3)
                       for side in ("x", "y", "width", "height")]
    return rects


def build() -> Storyboard:
    board = Storyboard("themes", "E7 — os quatro temas")
    state: dict = {}

    def _paint(session, mode: str, system_dark: bool | None = None):
        prefs = session.controller.preferences
        if system_dark is not None:
            prefs.setSystemDark(system_dark)
        prefs.setThemeMode(mode)
        session.settle(500)
        state[mode] = _layout(session)
        return {
            "chosen": prefs.themeMode,
            "painted": prefs.effectiveTheme,
            "layers": session.controller.layers.count,
            "panels": len(state[mode]),
        }

    def dark(session):
        """The default, with a layer on the canvas so there is real content."""
        session.controller.addLayer(str(FIELD), "field", "original", "mGal")
        session.settle(700)
        return _paint(session, "dark")

    def light(session):
        """The same screen, repainted."""
        return _paint(session, "light")

    def high_contrast(session):
        """A third palette, not the dark one turned up. `--only theme`
        measures its ratios; this frame is what they look like."""
        return _paint(session, "highContrast")

    def system(session):
        """Following the desktop, reported here as light.

        Pushed in rather than read: a gate must not depend on the developer's
        desktop being in the right mode to prove anything.
        """
        return _paint(session, "system", system_dark=False)

    # ---- the checks ------------------------------------------------------

    def _geometry_matches(frame, earlier, mode: str, other: str):
        """Every named panel occupies the same rectangle it did. Exactly.

        No tolerance, because there is nothing to be tolerant about: not one
        metric token in `Theme.qml` reads the mode, so a rectangle that moved
        by a pixel would mean one had started to.
        """
        here, there = state.get(mode, {}), state.get(other, {})
        if not here or not there:
            return f"no layout was recorded for {mode} or {other}"
        if set(here) != set(there):
            return (f"a panel appeared or vanished between {other} and "
                    f"{mode}: {sorted(set(here) ^ set(there))}")
        moved = {name: (there[name], here[name])
                 for name in here if here[name] != there[name]}
        frame.facts["panels"] = len(here)
        if moved:
            return (f"a theme change moved {sorted(moved)}: "
                    + "; ".join(f"{n} {was} -> {now}"
                                for n, (was, now) in sorted(moved.items())))
        return None

    def light_did_not_move(frame, earlier):
        return _geometry_matches(frame, earlier, "light", "dark")

    def contrast_did_not_move(frame, earlier):
        return _geometry_matches(frame, earlier, "highContrast", "dark")

    def system_is_the_light_one(frame, earlier):
        """It must not merely be *close* to light: it has to be light.

        `system` is a choice to follow, so with a light desktop the painted
        palette is the light palette, to the pixel.
        """
        if frame.facts.get("painted") != "light":
            return (f"system painted {frame.facts.get('painted')!r} while the "
                    f"desktop was reported light")
        if frame.facts.get("chosen") != "system":
            return "the chosen mode is no longer system"
        import numpy as np
        from PIL import Image

        before = next((f for f in earlier if f.name == "light"), None)
        if before is None:
            return "the light frame is missing"
        here = np.asarray(Image.open(frame.path).convert("RGB"))
        there = np.asarray(Image.open(before.path).convert("RGB"))
        if here.shape != there.shape:
            return "the window changed size"
        differing = int((here != there).any(axis=2).sum())
        frame.facts["pixelsDifferingFromLight"] = differing
        if differing:
            return (f"{differing} pixels differ from the light frame; "
                    f"following a light desktop must paint the light palette")
        return _geometry_matches(frame, earlier, "system", "dark")

    board.step("dark", "O tema escuro, o padrão, com uma camada no canvas.",
               dark, probes=PROBES, must_change=False)
    board.step("light", "O tema claro. Só as cores mudam: as bordas dos "
               "painéis caem exatamente nas mesmas colunas.",
               light, probes=PROBES, expect=light_did_not_move)
    board.step("high_contrast", "Alto contraste — uma terceira paleta, com "
               "texto e bordas em 7:1 ou mais, medidos por `--only theme`.",
               high_contrast, probes=PROBES, expect=contrast_did_not_move)
    board.step("system", "Automático, seguindo uma área de trabalho clara: "
               "idêntico ao tema claro, pixel a pixel.",
               system, probes=PROBES, must_change=True,
               expect=system_is_the_light_one)
    return board
