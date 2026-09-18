"""A aplicação num domínio que não é o geotérmico. A lacuna de evidência.

    três camadas de deslizamento na tela  ->  o editor de pertinência com a
    curva circular  ->  a agregação misturando contínuo e categórico
    ->  a sensibilidade sobre essa análise

`../data/conditioning_factors/` são 20 camadas de suscetibilidade a
deslizamento — MDE, declividade, TWI, uso do solo, geologia, solo, floresta —
de uma bacia na Coreia, em `EPSG:5186`. **Nada de geofísica.**

A aplicação sempre foi agnóstica de domínio por desenho. Até esta storyboard
isso nunca tinha sido **mostrado**: todo quadro de toda storyboard anterior
rodava sobre o dataset geotérmico de Utah, e a única menção a este arquivo em
toda a árvore era uma linha do M0 dizendo que nada o usava.

Os quadros existem para provar três coisas que só este dado expõe:

  1. um CRS que não é o EPSG:26912 de Utah atravessa o caminho inteiro;
  2. o editor de pertinência sabe desenhar uma curva **circular**, que é a
     única correta para azimute — e o dado de Utah não tem camada direcional;
  3. uma análise mistura contínuo e categórico, que é o caso comum fora da
     geofísica e que o dado de Utah não conseguia montar.
"""
from __future__ import annotations

import json  # noqa: E402
import shutil  # noqa: E402

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

LAND = DATA / "conditioning_factors"

PROBES = {
    "rail": (22, 300),
    "workflow": (140, 200),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "topbar": (700, 45),
}


def build() -> Storyboard:
    board = Storyboard("other_domain", "Outro domínio — suscetibilidade a deslizamento")
    state: dict = {}

    def _geology_with_a_legend(session):
        """Uma cópia de `geology.tif` com a legenda ao lado.

        O dataset de deslizamento **não** traz legenda nenhuma — nem
        `.aux.xml`, nem `.vat.dbf`, nem nome de categoria embutido — então o
        arquivo original mostra `1`, `2`, `3` e nada mais. A cópia é o único
        jeito honesto de mostrar a coluna de nomes: os códigos e as contagens
        continuam sendo os do arquivo de verdade, e só a legenda é declarada
        aqui, pela convenção `.meta.json` que este projeto já usa.
        """
        copy = session.workdir / "geologia.tif"
        if not copy.exists():
            shutil.copy(LAND / "geology.tif", copy)
            copy.with_suffix(".meta.json").write_text(
                json.dumps({"classes": {"1": "granito", "2": "xisto",
                                        "4": "aluvião"}}), encoding="utf-8")
        return copy

    def layers(session):
        """Três camadas de outro domínio, em EPSG:5186."""
        for filename, name, unit in (
            ("slope.tif", "declividade", "grau"),
            ("twi.tif", "TWI", "adimensional"),
            (_geology_with_a_legend(session), "geologia", "classe"),
        ):
            source = filename if isinstance(filename, str) \
                else str(filename)
            if not source.startswith("/"):
                source = str(LAND / source)
            session.controller.addLayer(source, name, "original", unit)
        session.settle(900)
        active = session.controller.layers.activeLayer() or {}
        canvas = session.canvas_state if isinstance(session.canvas_state, dict) \
            else {}
        return {
            "layers": session.controller.layers.count,
            "crs": str(active.get("crs") or canvas.get("crs", "")),
        }

    def circular_curve(session):
        """O editor de pertinência, na curva que só serve para direção."""
        editor = session.window.findChild(QObject, "membershipEditor")
        if editor is None:
            return {"opened": False}
        QMetaObject.invokeMethod(editor, "open", Qt.DirectConnection)
        session.settle(500)
        state["editor"] = editor

        editor.setProperty("functionName", "circular")
        editor.setProperty("preferred", "180")
        editor.setProperty("angularSpread", "90")
        session.settle(600)
        return {
            "opened": True,
            "function": str(editor.property("functionName")),
            "preferred": str(editor.property("preferred")),
            "sense": str(editor.property("physicalSense")),
            # `spread` continua sendo o de small/large: duas grandezas
            # diferentes não podem ter um nome só.
            "value_spread": str(editor.property("spread")),
            "angular_spread": str(editor.property("angularSpread")),
        }

    def class_table(session):
        """A tabela de classes, preenchida pelo caminho de verdade.

        Nada aqui atribui `criterion`: a camada é tornada ativa, `openMembership`
        pede a descrição ao worker e o editor a recebe pelo sinal. Um quadro que
        atribuísse a propriedade não testaria quem a preenche — foi assim que o
        editor ficou sem a camada e nenhum gate pegou.
        """
        geology = None
        for row in session.controller.layers.snapshot():
            if row.get("name") == "geologia":
                geology = row.get("layerId")
        if not geology:
            return {"opened": False}
        session.controller.layers.setActive(geology)
        QMetaObject.invokeMethod(session.window, "openMembership",
                                 Qt.DirectConnection)
        # A descrição é um job read-only: sai pelo IPC e volta pelo sinal.
        session.settle(2500)

        editor = session.window.findChild(QObject, "membershipEditor")
        if editor is None:
            return {"opened": False}
        state["editor"] = editor
        editor.setProperty("functionName", "categorical")
        session.settle(300)

        codes = editor.property("classCodes")
        codes = codes.toVariant() if hasattr(codes, "toVariant") else codes
        codes = [float(c) for c in (codes or [])]
        apply_button = editor.findChild(QObject, "membershipApply")
        before = {
            "missing": int(editor.property("classesMissing") or 0),
            "apply": bool(apply_button and apply_button.property("enabled")),
        }

        # Uma nota por classe, do menos ao mais favorável.
        for i, code in enumerate(codes):
            score = round((i + 1) / max(1, len(codes)), 2)
            QMetaObject.invokeMethod(editor, "setClassScore", Qt.DirectConnection,
                                     Q_ARG("QVariant", code),
                                     Q_ARG("QVariant", str(score)))
        session.settle(500)

        return {
            "opened": True,
            "codes": len(codes),
            "described": editor.property("stats") is not None
                         and bool(codes),
            "missing_before": before["missing"],
            "apply_before": before["apply"],
            "missing_after": int(editor.property("classesMissing") or 0),
            "apply_after": bool(apply_button
                                and apply_button.property("enabled")),
            # A legenda: quantos códigos o arquivo nomeia, e de onde.
            "named": sum(1 for i in range(len(codes))
                         if editor.property("classNames")
                         and list(editor.property("classNames"))[i]),
            "unnamed": int(editor.property("classesUnnamed") or 0),
            "legend": str(editor.property("legendSource") or ""),
        }

    def mixed_analysis(session):
        """Contínuo e categórico na mesma agregação."""
        editor = state.get("editor")
        if editor is not None:
            QMetaObject.invokeMethod(editor, "close", Qt.DirectConnection)
            session.settle(300)

        before = len(session.controller.store.runs())
        session.controller.submit("decision.aggregate", {
            "method": "weighted_linear_combination",
            "result_name": "suscetibilidade",
            "criteria": [
                {"path": str(LAND / "slope.tif"), "name": "declividade",
                 "unit": "grau", "function": "linear_increasing"},
                {"path": str(LAND / "twi.tif"), "name": "TWI",
                 "unit": "adimensional", "function": "linear_increasing"},
                {"path": str(LAND / "geology.tif"), "name": "geologia",
                 "unit": "classe", "function": "categorical",
                 "mapping": {1: 0.2, 2: 0.5, 3: 0.8, 4: 1.0}},
            ],
            "weights": [{"name": "declividade", "weight": 0.5},
                        {"name": "TWI", "weight": 0.3},
                        {"name": "geologia", "weight": 0.2}],
        }, [])
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(1500)
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        criteria = manifest.get("criteria") or []
        functions = sorted({c.get("function", "") for c in criteria})
        geology = [c for c in criteria if c.get("name") == "geologia"]
        return {
            "operator": manifest.get("operator", ""),
            "criteria": len(criteria),
            "functions": ", ".join(functions),
            "valid": round(float((manifest.get("result") or {})
                                 .get("valid_fraction") or 0) * 100, 1),
            # A tabela de classes na procedência: sem ela ninguém reproduz a
            # análise, porque a nota de cada classe é a decisão inteira.
            "class_table": len((geology[0].get("anchors") or {}).get("mapping")
                               or {}) if geology else 0,
            "crs": (manifest.get("grid") or {}).get("crs", ""),
            "artifacts": len(session.controller.store.artifacts(runs[-1].id))
            if len(runs) > before else 0,
        }

    def sensitivity(session):
        """M6 sobre esta análise: os cenários são do produto, não do dataset."""
        dialog = session.window.findChild(QObject, "scenariosDialog")
        if dialog is None:
            return {"opened": False}
        dialog.setProperty("criteria", [
            {"path": str(LAND / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
            {"path": str(LAND / "twi.tif"), "name": "TWI",
             "unit": "adimensional", "function": "linear_increasing"},
            {"path": str(LAND / "geology.tif"), "name": "geologia",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 0.2, 2: 0.5, 3: 0.8, 4: 1.0}},
        ])
        dialog.setProperty("method", "fuzzy_gamma")
        dialog.setProperty("weights", [])
        QMetaObject.invokeMethod(dialog, "clearMeasurements", Qt.DirectConnection)
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(500)

        button = session.window.findChild(QObject, "scenariosRunLoo")
        pressed = button is not None
        if pressed:
            QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
            session.wait_for(
                lambda: dialog.property("leaveOneOut") is not None, 180000)
        session.settle(700)
        report = dialog.property("leaveOneOut") or {}
        rows = report.get("criteria") or []
        return {
            "opened": True,
            "pressed": pressed,
            "rows": len(rows),
            "first": rows[0]["dropped"] if rows else "",
            "cells": rows[0]["cells_compared"] if rows else 0,
        }

    # ---- o que tem de ser verdade ----------------------------------------

    def another_crs_reaches_the_canvas(frame, earlier):
        if frame.facts.get("layers", 0) < 3:
            return "as três camadas não entraram na visualização"
        if "5186" not in frame.facts.get("crs", ""):
            return (f"o CRS na tela é {frame.facts.get('crs')!r}; este dado é "
                    f"EPSG:5186, e todo gate anterior rodava em EPSG:26912")
        return None

    def a_direction_gets_a_circular_curve(frame, earlier):
        if not frame.facts.get("opened"):
            return "o editor de pertinência não está no shell"
        if frame.facts.get("function") != "circular":
            return "o editor não aceitou a função circular"
        if "direction" not in frame.facts.get("sense", ""):
            return ("o editor não diz em palavras o que a curva faz; uma "
                    "direção expressa só por um nome de função é uma direção "
                    "que ninguém confere")
        if frame.facts.get("value_spread") == frame.facts.get("angular_spread"):
            return ("o alcance angular e o de valores viraram a mesma "
                    "propriedade; são grandezas diferentes e uma passaria a "
                    "ser lida como a outra")
        return None

    def the_class_table_is_reachable_and_blocks(frame, earlier):
        if not frame.facts.get("opened"):
            return "o editor de pertinência não abriu sobre a geologia"
        if not frame.facts.get("described"):
            return ("o editor abriu sem as estatísticas da camada: a descrição "
                    "não chegou pelo sinal, que é o defeito que deixou o "
                    "editor sem a camada da primeira vez")
        if frame.facts.get("codes") != 4:
            return (f"a tabela lista {frame.facts.get('codes')} códigos; "
                    f"geology.tif tem 4, e uma tabela que não bate com o "
                    f"arquivo é uma tabela de classes inventadas")
        if frame.facts.get("missing_before") != 4:
            return ("as classes já entraram pontuadas; uma nota que o produto "
                    "escolheu sozinho é uma afirmação científica de ninguém")
        if frame.facts.get("apply_before"):
            return ("aplicar liberou com a tabela vazia: o worker recusaria o "
                    "código sem nota e a pessoa receberia um job vermelho no "
                    "lugar de saber onde está a lacuna")
        if frame.facts.get("missing_after") != 0:
            return "pontuar as quatro classes não zerou o que falta"
        if not frame.facts.get("apply_after"):
            return "a tabela inteira preenchida e aplicar continua desligado"
        if frame.facts.get("legend") != "sidecar":
            return (f"a legenda veio de {frame.facts.get('legend')!r}; a tela "
                    f"tem de dizer de onde, porque um rótulo afirma o que um "
                    f"código significa")
        if frame.facts.get("named") != 3:
            return (f"{frame.facts.get('named')} códigos nomeados; a legenda "
                    f"declara três")
        if frame.facts.get("unnamed") != 1:
            return ("o código que a legenda não menciona não ficou marcado "
                    "como sem nome; inventar um nome faria uma legenda "
                    "ausente parecer presente")
        return None

    def continuous_and_categorical_aggregate_together(frame, earlier):
        if frame.facts.get("operator") != "decision.aggregate":
            return f"rodou {frame.facts.get('operator')!r}"
        if frame.facts.get("criteria") != 3:
            return f"a análise tem {frame.facts.get('criteria')} critérios"
        if "categorical" not in frame.facts.get("functions", ""):
            return ("nenhum critério é categórico; era o defeito — a função "
                    "estava declarada no módulo e não ligada ao operador")
        if "linear_increasing" not in frame.facts.get("functions", ""):
            return "a análise não mistura contínuo com categórico"
        if frame.facts.get("class_table", 0) != 4:
            return ("a tabela de classes não entrou na procedência; sem ela a "
                    "análise não é reproduzível, porque a nota de cada classe "
                    "é a decisão inteira")
        if "5186" not in str(frame.facts.get("crs", "")):
            return "a grade do resultado não é a do dado de entrada"
        if frame.facts.get("artifacts", 0) < 1:
            return "a run não produziu artefato"
        if float(frame.facts.get("valid") or 0) < 90:
            return (f"só {frame.facts.get('valid')} % das células têm score; "
                    f"algo está anulando a análise")
        return None

    def the_scenarios_work_here_too(frame, earlier):
        if not frame.facts.get("pressed"):
            return "o botão de medir não estava alcançável"
        if frame.facts.get("rows") != 3:
            return f"vieram {frame.facts.get('rows')} linhas para três critérios"
        if frame.facts.get("cells", 0) < 100000:
            return "a medição rodou sobre poucas células para ser evidência"
        return None

    board.step("layers",
               "Três camadas de suscetibilidade a deslizamento — declividade, "
               "TWI e geologia — em EPSG:5186. Nenhum gate anterior tinha "
               "saído do EPSG:26912 de Utah.",
               layers, probes=PROBES, expect=another_crs_reaches_the_canvas)
    board.step("circular",
               "O editor de pertinência na curva circular, a única correta "
               "para azimute: 359° e 1° estão a dois graus um do outro, e "
               "toda curva linear os põe nas pontas opostas.",
               circular_curve, probes=PROBES,
               expect=a_direction_gets_a_circular_curve)
    board.step("classes",
               "A tabela de classes sobre a geologia: um código por linha, com "
               "a área que ocupa e a nota que recebe. Aplicar espera a tabela "
               "inteira — pontuar zero uma classe é uma afirmação científica.",
               class_table, probes=PROBES,
               expect=the_class_table_is_reachable_and_blocks)
    board.step("mixed",
               "Contínuo e categórico na mesma agregação, com a tabela de "
               "classes na procedência. Era o defeito: `categorical` estava "
               "no módulo e não ligada ao operador.",
               mixed_analysis, probes=PROBES,
               expect=continuous_and_categorical_aggregate_together)
    board.step("sensitivity",
               "E a sensibilidade do M6 sobre esta análise: os cenários são "
               "do produto, não do dataset geotérmico.",
               sensitivity, probes=PROBES, expect=the_scenarios_work_here_too)
    return board
