"""A demonstração: o dado do Utah FORGE, do ponto ao campo interpolado.

    3 735 estações desenhadas  ->  o mapa de fundo por baixo
    ->  o colormap trocado, sem reescrever valor
    ->  a interpolação medida  ->  o campo cúbico no canvas

Existe para ser **visto**: é a sequência que vira o GIF do README. Por isso
roda sobre um levantamento só — gravimetria do Utah FORGE — em vez dos rasters
sintéticos que as outras storyboards usam. Quem assiste tem de reconhecer o
dado, não um campo inventado.

E por ser storyboard e não captura à mão, cada quadro é conferido contra
números. Um GIF bonito que mostra uma tela que o produto não produz é pior que
nenhum GIF: o `expect` de cada quadro é o que impede isso.
"""
from __future__ import annotations

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

FORGE = DATA / "utah_forge"
TABLE = FORGE / "anomaly_bouger_easting_northin_bouger.csv"

#: A grade da demonstração. Grossa de propósito: o que se mostra é o caminho,
#: e 200 m sobre este levantamento é um segundo, não um minuto.
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
    board = Storyboard("demo", "Do ponto ao campo — Utah FORGE")
    state: dict = {}

    def points(session):
        """As 3 735 estações gravimétricas, desenhadas como nuvem de pontos.

        Um CSV não é uma grade. Ele entra, é conferido e é **desenhado** — e
        é isso que se vê antes de qualquer interpolação existir.
        """
        # Em inglês: estes quadros viram o GIF de um README público, e a
        # aplicação fala os dois idiomas. A troca só re-letreia — nenhuma
        # borda de painel se move, o que o gate do M5.5 já mede.
        session.controller.tr.setLanguage("en")
        session.settle(400)

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
        session.settle(1200)

        active = session.controller.layers.activeLayer() or {}
        state["layer"] = active.get("layerId", "")
        described = session.controller.layerDescription(state["layer"]) or {}
        if not described:
            session.controller.describeLayer(state["layer"])
            session.settle(1500)
            described = session.controller.layerDescription(state["layer"]) or {}
        return {
            "layers": session.controller.layers.count,
            "kind": str(described.get("kind", "")),
            "rows": int(described.get("rows") or 0),
            "unit": str(described.get("unit") or ""),
            "colormap": str(active.get("colormap", "")),
            # Uma tabela não é harmonizável, e isso não é defeito: ela vira
            # grade antes.
            "harmonisable": len(session.controller.harmonizableDatasets()),
            "language": str(session.controller.tr.language),
        }

    def basemap(session):
        """O mapa de fundo por baixo do dado.

        Desligado por padrão (`ADR-MSP-006`) e **só exibição**: nunca é a
        camada ativa e nunca entra como insumo de operador nenhum. Ligá-lo é o
        único momento em que esta aplicação toca a rede, e a fonte é declarada
        com a licença dela.
        """
        # Pelo caminho real de um clique: o token do menu passa por
        # `dispatch`, que faz as **duas** coisas — manda o canvas buscar os
        # tiles e põe a camada no painel. Chamar só `setBasemap` registra a
        # camada e não desenha nada, que foi o primeiro erro deste quadro.
        QMetaObject.invokeMethod(
            session.window, "dispatch", Qt.DirectConnection,
            Q_ARG("QVariant", "basemap:osm"))
        session.settle(6000)

        chosen = str(session.controller.layers.layer("basemap") and "osm" or "")
        canvas = session.window.findChild(QObject, "mapCanvas")
        rows = session.controller.layers.snapshot()
        under = rows[0].get("layerId", "") if rows else ""
        return {
            "chosen": chosen,
            # O que o canvas recebeu, que é quem busca os tiles.
            "canvas_source": str(canvas.property("basemapSource") or "")
                             if canvas is not None else "",
            "layers": session.controller.layers.count,
            # Por baixo de tudo: um mapa de fundo é o chão em que o dado se
            # apoia, nunca uma camada sobre ele.
            "basemap_is_bottom": under == "basemap",
            "sources_offered": len(session.controller.basemapSources),
            # A camada ativa continua sendo o dado, não o fundo.
            "active_is_data": (session.controller.layers.activeId
                               == state.get("layer", "")),
        }

    def colormap(session):
        """A rampa trocada. Repinta e **nunca reescreve um valor** (`P-111`).

        A faixa que o Inspector mostra é a mesma antes e depois, e é assim que
        se sabe que a troca foi de exibição: se o dado tivesse sido reescrito,
        o mínimo e o máximo teriam mudado junto.
        """
        described = session.controller.layerDescription(state["layer"]) or {}
        stats = described.get("statistics") or {}
        before = (stats.get("min"), stats.get("max"))

        session.controller.layers.setColormap(state["layer"], "magma")
        session.settle(1200)

        described = session.controller.layerDescription(state["layer"]) or {}
        stats = described.get("statistics") or {}
        after = (stats.get("min"), stats.get("max"))
        active = session.controller.layers.activeLayer() or {}
        return {
            "colormap": str(active.get("colormap", "")),
            "offered": len(session.controller.layers.colormaps),
            "range_unchanged": before == after and before[0] is not None,
            "min": round(float(before[0]), 4) if before[0] is not None else None,
            "max": round(float(before[1]), 4) if before[1] is not None else None,
        }

    def measured(session):
        """Qual interpolador serve, medido neste levantamento.

        Validação cruzada k-fold sobre os próprios pontos (`ADR-MSP-007`). O
        produto não tem um interpolador preferido: ele mede os três e reporta o
        erro de cada um na unidade do dado.
        """
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

        pressed = _press(session, "griddingCompare")
        if pressed:
            session.wait_for(
                lambda: dialog.property("comparison") is not None, 180000)
        session.settle(800)
        comparison = dialog.property("comparison") or {}
        scored = comparison.get("methods") or comparison.get("scores") or []
        return {
            "opened": True,
            "pressed": pressed,
            "methods": len(scored),
            "recommended": str(comparison.get("recommended", "")),
        }

    def cubic(session):
        """O campo interpolado, Clough-Tocher.

        Cúbico por partes sobre a triangulação de Delaunay: contínuo na
        derivada primeira, que é o que dá a superfície lisa. Fora do fecho
        convexo não há valor, e o produto deixa nulo em vez de extrapolar.
        """
        dialog = state.get("dialog")
        if dialog is None:
            return {"pressed": False}
        dialog.setProperty("method", "grid.tin_cubic")
        session.settle(400)

        before = len(session.controller.store.runs())
        pressed = _press(session, "griddingRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(1500)

        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        grid = manifest.get("grid", {})
        stats = manifest.get("statistics", {})
        return {
            "pressed": pressed,
            "operator": str(manifest.get("operator", "")),
            "grid": f"{grid.get('width')}x{grid.get('height')}",
            "pixel": grid.get("pixel_size_x"),
            "valid": round(float(stats.get("valid_fraction") or 0.0) * 100, 1),
            "artifacts": len(session.controller.store.artifacts(runs[-1].id))
            if len(runs) > before else 0,
            # A grade que saiu **já** é harmonizável, que é o ponto de gerá-la.
            "harmonisable": len(session.controller.harmonizableDatasets()),
        }

    # ---- o que tem de ser verdade ----------------------------------------

    def the_points_are_drawn(frame, earlier):
        if frame.facts.get("layers", 0) < 1:
            return "o CSV não entrou no projeto"
        if frame.facts.get("kind") != "table":
            return f"entrou como {frame.facts.get('kind')!r}, não como tabela"
        if frame.facts.get("rows", 0) < 3000:
            return (f"{frame.facts.get('rows')} estações; este levantamento "
                    f"tem 3 735, e um recorte não é o dado")
        if frame.facts.get("unit") != "mGal":
            return "a unidade não chegou à camada; um número sem unidade não "\
                   "é conferível"
        if frame.facts.get("harmonisable", 0) != 0:
            return ("uma tabela foi oferecida para harmonizar; harmonização "
                    "lê raster e falharia nela")
        if frame.facts.get("language") != "en":
            return (f"a interface está em {frame.facts.get('language')!r}; "
                    f"estes quadros viram o GIF de um README público")
        return None

    def the_ground_is_under_the_data(frame, earlier):
        if frame.facts.get("chosen") != "osm":
            return f"o mapa de fundo não ligou: {frame.facts.get('chosen')!r}"
        if frame.facts.get("canvas_source") != "osm":
            return ("a camada entrou no painel e o canvas não recebeu a fonte; "
                    "quem busca os tiles é o canvas, então nada seria "
                    "desenhado")
        if not frame.facts.get("basemap_is_bottom"):
            return ("o mapa de fundo não ficou por baixo; ele é o chão em que "
                    "o dado se apoia, não uma camada sobre ele")
        if not frame.facts.get("active_is_data"):
            return ("o mapa de fundo virou a camada ativa; ele é só exibição "
                    "e nunca entra como insumo (ADR-MSP-006)")
        if frame.facts.get("sources_offered", 0) < 1:
            return "nenhuma fonte de mapa de fundo declarada"
        if frame.facts.get("layers", 0) < 2:
            return "o fundo entrou e o dado sumiu"
        return None

    def the_ramp_repaints_and_nothing_else(frame, earlier):
        if frame.facts.get("colormap") != "magma":
            return f"a rampa não trocou: {frame.facts.get('colormap')!r}"
        if frame.facts.get("offered", 0) < 6:
            return "o painel oferece menos rampas do que o módulo define"
        if not frame.facts.get("range_unchanged"):
            return ("a faixa do dado mudou junto com a rampa — então a troca "
                    "reescreveu valor, e ela é só exibição (P-111)")
        return None

    def the_choice_is_measured(frame, earlier):
        if not frame.facts.get("opened"):
            return "a tela de gerar grade não está no shell"
        if not frame.facts.get("pressed"):
            return "o botão de comparar não estava alcançável"
        if frame.facts.get("methods", 0) < 3:
            return (f"{frame.facts.get('methods')} métodos medidos; são três, "
                    f"e comparar menos não é comparar")
        return None

    def a_smooth_field_came_out(frame, earlier):
        if not frame.facts.get("pressed"):
            return "o botão de gerar não estava alcançável"
        if frame.facts.get("operator") != "grid.tin_cubic":
            return (f"rodou {frame.facts.get('operator')!r}; o quadro é sobre "
                    f"a interpolação cúbica")
        if frame.facts.get("artifacts", 0) < 1:
            return "a run não produziu raster"
        if float(frame.facts.get("valid") or 0) <= 0:
            return "o campo saiu vazio; toda célula é nula"
        if frame.facts.get("harmonisable", 0) < 1:
            return ("a grade que saiu não é harmonizável, então o CSV chegou "
                    "a um raster e parou ali")
        return None

    board.step("points",
               "As 3 735 estações gravimétricas do Utah FORGE, desenhadas. "
               "Um CSV entra, é conferido e é desenhado — antes de qualquer "
               "interpolação existir.",
               points, probes=PROBES, expect=the_points_are_drawn)
    board.step("basemap",
               "O mapa de fundo por baixo do dado: desligado por padrão, só "
               "exibição, nunca insumo, e é o único momento em que esta "
               "aplicação toca a rede.",
               basemap, probes=PROBES, expect=the_ground_is_under_the_data)
    board.step("colormap",
               "A rampa trocada para magma. Repinta a vista e não reescreve "
               "valor nenhum — a faixa no Inspector é a mesma.",
               colormap, probes=PROBES,
               expect=the_ramp_repaints_and_nothing_else)
    board.step("measured",
               "Qual interpolador serve, medido neste levantamento por "
               "validação cruzada. O produto não tem preferido: ele mede os "
               "três e reporta o erro na unidade do dado.",
               measured, probes=PROBES, expect=the_choice_is_measured)
    board.step("cubic",
               "O campo Clough-Tocher no canvas: cúbico por partes sobre a "
               "triangulação, liso na derivada primeira, e nulo fora do fecho "
               "convexo em vez de extrapolado.",
               cubic, probes=PROBES, expect=a_smooth_field_came_out)
    return board
