"""M5.5 — the shell: workflow, layers, tools, language, import preview.

Six frames, each one a claim the milestone makes, and each one checked
numerically before anyone looks:

    the flow says where you are  ->  the layers say what is drawn
    ->  the AOI is a mode        ->  leaving the mode leaves nothing
    ->  the interface speaks the language that was chosen
    ->  the wizard draws the file before the file is a dataset

The fourth frame is the one that matters most. The defect it replaces drew an
AOI on the map for the rest of the session, with nothing on screen saying what
the yellow lines were. `expect` compares it against the frame before it, which
is the only way to assert "and then it was gone".
"""
from __future__ import annotations

from PySide6.QtCore import QObject  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

CANVAS = DATA / "synthetic" / "msp" / "canvas"
FIELD_A = CANVAS / "large_field.tif"
FIELD_B = CANVAS / "large_field_b.tif"
#: A shapefile, for the frame that proves a vector reaches the screen.
VECTOR = DATA / "synthetic" / "blocks.shp"

PROBES = {
    "menubar": (60, 12),
    "workflow": (100, 200),
    "layers": (100, 700),
    "toolbar": (255, 120),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "statusbar": (700, 869),
}

# Theme.warn, the AOI's colour. Sampled, not eyeballed.
AOI_COLOUR = (224, 179, 65)

# `render/geometry.py` takes a silhouette's stroke from three quarters up the
# layer's ramp. Viridis at 0.75. Read from the module rather than typed here
# would be better; it is a tool, and importing the app into it would put the
# whole GUI package on the storyboard's path for one triple.
STROKE_COLOUR = (94, 201, 98)


def _colour_pixels(path, colour, box=None, tolerance=(30, 30, 40)) -> int:
    """How many pixels of a given colour the frame carries, inside `box`."""
    from PIL import Image

    image = Image.open(path).convert("RGB")
    crop = image.crop(box) if box else image
    dr, dg, db = tolerance
    return sum(
        1 for r, g, b in crop.getdata()
        if abs(r - colour[0]) < dr and abs(g - colour[1]) < dg
        and abs(b - colour[2]) < db
    )


def _aoi_pixels(path, box=(300, 60, 1160, 780)) -> int:
    """How many pixels of the AOI's own colour are inside the map area."""
    return _colour_pixels(path, AOI_COLOUR, box)


def build() -> Storyboard:
    board = Storyboard("m55", "M5.5 — Interface profissional")
    state: dict = {}

    def flow(session):
        """The workflow, with a project open and nothing imported yet."""
        model = session.controller.workflow
        states = [
            model.data(model.index(i, 0), model.StateRole)
            for i in range(model.rowCount())
        ]
        return {"steps": len(states), "done": states.count("done"),
                "blocked": states.count("blocked"),
                "current": session.controller.currentStep}

    def layers(session):
        """Two layers in the stack, drawn in the stack's order."""
        first = session.controller.addLayer(str(FIELD_A), "heat_proxy",
                                            "original", "mGal")
        second = session.controller.addLayer(str(FIELD_B), "structure_proxy",
                                             "original", "mGal")
        state["first"], state["second"] = first, second
        stack = session.controller.layers
        stack.setColormap(second, "magma")
        session.settle(500)
        return {"layers": stack.count, "active": stack.activeId,
                "colormap": stack.activeLayer().get("colormap"),
                "drawn": session.canvas.layerCount}

    def aoi_mode(session):
        """The AOI, while its tool is on: vertices, count, and a way out."""
        session.canvas.toolMode = "aoi"
        session.canvas.beginAoi()
        extent = session.canvas.viewportInfo().get("extent", [0, 0, 1, 1])
        left, bottom, right, top = extent
        width, height = right - left, top - bottom
        for fx, fy in ((0.3, 0.3), (0.7, 0.35), (0.6, 0.7), (0.35, 0.65)):
            # The same slot a click reaches, so this drives the real drawing
            # rather than a second implementation of it.
            session.canvas.addAoiVertex(left + fx * width, bottom + fy * height)
        session.settle(400)
        return {"mode": session.canvas.toolMode,
                "vertices": session.canvas.aoiPointCount,
                "drawing": session.canvas.aoiDrawing}

    def aoi_gone(session):
        """Leaving the mode leaves nothing — the defect this milestone fixes."""
        session.canvas.toolMode = "navigate"
        session.settle(400)
        return {"mode": session.canvas.toolMode,
                "vertices": session.canvas.aoiPointCount,
                "drawing": session.canvas.aoiDrawing}

    def english(session):
        """The same screen, in the other language. Nothing moves; text changes."""
        session.controller.tr.setLanguage("en")
        session.settle(400)
        return {"language": session.controller.tr.language,
                "sample": session.controller.tr.t("workflow.caption")}

    def import_preview(session):
        """E4 — the wizard draws the file before the file is a dataset.

        A shapefile, because that is the kind that drew nothing at all until
        now: it went in as a raster read, failed, and left the canvas empty
        while the panel listed a layer.
        """
        from PySide6.QtCore import QMetaObject, Qt

        wizard = session.wizard
        QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
        wizard.setProperty("path", str(VECTOR))
        QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
        QMetaObject.invokeMethod(wizard, "open", Qt.DirectConnection)
        # The describe and the QA/QC both go to the worker and come back.
        session.settle(2500)

        described = wizard.property("description") or {}
        preview = session.window.findChild(QObject, "previewMap")
        return {
            "kind": described.get("kind", ""),
            "features": described.get("features", 0),
            "drawn": bool(preview and preview.property("drawn")),
            "parts": len((described.get("preview") or {}).get("parts", [])),
        }

    def the_file_was_drawn(frame, earlier):
        """The silhouette has to be **on the screen**, not merely described.

        Asserted twice, because either alone is weak: the component reports it
        drew, and the frame carries pixels of the stroke's own colour. A map
        that draws into a buffer nobody composites would pass the first.
        """
        if frame.facts.get("kind") != "vector":
            return f"the wizard described a {frame.facts.get('kind')!r}"
        if not frame.facts.get("drawn"):
            return "the preview map reports that it drew nothing"
        if frame.facts.get("parts", 0) < 1:
            return "the description carried no outline to draw"
        painted = _colour_pixels(frame.path, STROKE_COLOUR)
        frame.facts["stroke_pixels"] = painted
        if painted < 40:
            return (f"only {painted} pixels of the silhouette's colour on "
                    f"screen; the outline was computed and never composited")
        return None

    def aoi_is_visible(frame, earlier):
        """The AOI has to be **on the map**, not merely in the model."""
        drawn = _aoi_pixels(frame.path)
        frame.facts["aoi_pixels"] = drawn
        if drawn < 60:
            return (f"only {drawn} AOI-coloured pixels on the map; the AOI is "
                    f"in the model but not drawn")
        return None

    def aoi_is_gone(frame, earlier):
        """P-109, asserted across two frames: it was drawn, and now it is not.

        One frame cannot make this claim. This is exactly the sort of thing a
        person is supposed to notice on a contact sheet and does not.
        """
        before = next((f for f in earlier if f.name == "aoi_mode"), None)
        if before is None:
            return "the frame that drew the AOI is missing"
        drawn = _aoi_pixels(frame.path)
        frame.facts["aoi_pixels"] = drawn
        was = before.facts.get("aoi_pixels", 0)
        if drawn > max(20, was * 0.1):
            return (f"{drawn} AOI-coloured pixels remain after leaving the AOI "
                    f"tool (there were {was}); the sketch outlived its mode")
        return None

    def nothing_moved(frame, earlier):
        """A language change may only re-letter. Panel edges stay where they
        were: the probes are on panel backgrounds, so a layout that shifted
        would change what they sample."""
        before = next((f for f in earlier if f.name == "aoi_gone"), None)
        if before is None:
            return "the frame before the language change is missing"
        for label in ("menubar", "workflow", "layers", "inspector", "statusbar"):
            was, now = before.probes.get(label), frame.probes.get(label)
            if was and now and was != now:
                return (f"the {label} panel changed colour at {label} "
                        f"({was} -> {now}); a language change may only re-letter")
        return None

    board.step("flow", "Oito etapas, com o estado lido do projeto: a etapa 1 "
               "concluída, a 2 disponível, o resto bloqueado com o motivo.",
               flow, probes=PROBES, must_change=False)
    board.step("layers", "Duas camadas na pilha, cada uma com o seu colormap. "
               "A ordem é ordem de desenho e não entra em nenhum manifesto.",
               layers, probes=PROBES)
    board.step("aoi_mode", "O modo AOI: a faixa diz 'Desenhando AOI', os "
               "vértices têm marcadores, e desfazer, cancelar e finalizar "
               "estão à mão.",
               aoi_mode, probes=PROBES, expect=aoi_is_visible)
    board.step("aoi_gone", "Fora do modo AOI não sobra nada na tela. Era este "
               "o defeito: linhas amarelas que ficavam para sempre.",
               aoi_gone, probes=PROBES, expect=aoi_is_gone)
    board.step("english", "A mesma tela em inglês. Só o texto muda; nenhum "
               "painel se move.",
               english, probes=PROBES, expect=nothing_moved)
    board.step("import_preview", "O assistente de importação desenhando um "
               "shapefile: silhueta, fatos por tipo e histograma, antes de o "
               "arquivo entrar no projeto.",
               import_preview, probes=PROBES, expect=the_file_was_drawn)
    return board
