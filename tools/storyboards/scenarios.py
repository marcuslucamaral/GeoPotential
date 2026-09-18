"""M6 — o que muda se a escolha tivesse sido outra. MSP-11, §17.

    uma análise com três critérios  ->  a tela de cenários
    ->  o leave-one-out medido no worker  ->  a varredura de gamma

O que esta storyboard existe para checar é a propriedade que separa uma tela de
sensibilidade útil de uma decorativa: **ela mede e não decide.** Os quadros
provam, com números vindos do estado da aplicação e não de uma descrição:

  1. a tela pega a análise do Decision Model — os mesmos critérios, o mesmo
     operador — porque um cenário medido contra outra análise não mede nada;
  2. o worker devolve uma linha por critério, ordenada pelo que mais move o
     mapa, com o tamanho da amostra ao lado de cada número;
  3. **nada foi commitado**: uma sondagem não cria run nem artefato;
  4. os pesos e o método continuam exatamente como estavam depois de medir.
"""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

#: Três critérios que discordam, para que tirar um tenha onde aparecer. São os
#: rasters de canvas do projeto, que já estão numa grade só.
CANVAS = DATA / "synthetic" / "msp" / "canvas"

PROBES = {
    "rail": (22, 300),
    "workflow": (140, 200),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "topbar": (700, 45),
}


def _press(session, name: str) -> bool:
    button = session.window.findChild(QObject, name)
    if button is None:
        return False
    QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
    return True


def build() -> Storyboard:
    board = Storyboard("scenarios", "M6 — cenários e sensibilidade")
    state: dict = {}

    def analysis(session):
        """Uma análise de três critérios, na tela que a produz."""
        raster = CANVAS / "large_field.tif"
        other = CANVAS / "large_field_b.tif"
        session.controller.addLayer(str(raster), "campo A", "original", "mGal")
        session.controller.addLayer(str(other), "campo B", "original", "mGal")
        session.settle(600)

        decision = session.window.findChild(QObject, "decisionModel")
        criteria = [
            {"path": str(raster), "name": "campo A", "unit": "mGal",
             "function": "linear_increasing"},
            {"path": str(other), "name": "campo B", "unit": "mGal",
             "function": "linear_decreasing"},
            {"path": str(raster), "name": "campo A invertido", "unit": "mGal",
             "function": "linear_decreasing"},
        ]
        decision.setProperty("criteria", criteria)
        decision.setProperty("method", "fuzzy_gamma")
        decision.setProperty("gamma", 0.7)
        session.settle(300)
        state["decision"] = decision
        return {
            "criteria": len(decision.property("criteria") or []),
            "method": str(decision.property("method")),
            "layers": session.controller.layers.count,
        }

    def opened(session):
        """A tela de cenários, com a análise que ela vai questionar."""
        QMetaObject.invokeMethod(session.window, "openScenarios",
                                 Qt.DirectConnection)
        session.settle(600)
        dialog = session.window.findChild(QObject, "scenariosDialog")
        state["dialog"] = dialog
        if dialog is None:
            return {"opened": False}
        return {
            "opened": True,
            "criteria": len(dialog.property("criteria") or []),
            "method": str(dialog.property("method")),
            "ready": bool(dialog.property("ready")),
            # Nada medido ainda: a tela abre sem inventar resultado.
            "measured": dialog.property("leaveOneOut") is not None,
            "runs": len(session.controller.store.runs()),
        }

    def leave_one_out(session):
        """O worker tira um critério por vez e mede o que o mapa perde."""
        dialog = state["dialog"]
        runs_before = len(session.controller.store.runs())
        pressed = _press(session, "scenariosRunLoo")
        session.wait_for(lambda: dialog.property("leaveOneOut") is not None,
                         180000)
        session.settle(700)
        report = dialog.property("leaveOneOut") or {}
        rows = report.get("criteria") or []
        return {
            "pressed": pressed,
            "rows": len(rows),
            "first": rows[0]["dropped"] if rows else "",
            "ordered": all(
                (rows[i]["mean_abs_change"] or 0) >= (rows[i + 1]["mean_abs_change"] or 0)
                for i in range(len(rows) - 1)),
            "cells": rows[0]["cells_compared"] if rows else 0,
            "has_limitation": "interactions" in (report.get("limitation") or ""),
            # Uma sondagem não commita run e não registra artefato.
            "runs_before": runs_before,
            "runs_after": len(session.controller.store.runs()),
            # E não mexeu na análise.
            "method_after": str(dialog.property("method")),
        }

    def gamma_sweep(session):
        """A varredura de gamma, na mesma tela e na mesma análise."""
        dialog = state["dialog"]
        pressed = _press(session, "scenariosRunSweep")
        session.wait_for(lambda: dialog.property("sweep") is not None, 180000)
        session.settle(700)
        report = dialog.property("sweep") or {}
        rows = report.get("rows") or []
        return {
            "pressed": pressed,
            "parameter": report.get("parameter", ""),
            "values": len(rows),
            "worst_change": round(float(report.get("worst_mean_abs_change") or 0), 5),
            "worst_agreement": round(float(report.get("worst_top_agreement") or 0), 4),
            "runs": len(session.controller.store.runs()),
            "loo_still_there": dialog.property("leaveOneOut") is not None,
        }

    # ---- o que tem de ser verdade ----------------------------------------

    def the_analysis_exists(frame, earlier):
        if frame.facts.get("criteria", 0) < 3:
            return "a análise não tem três critérios para tirar um"
        if frame.facts.get("layers", 0) < 2:
            return "as camadas não entraram na visualização"
        return None

    def the_screen_takes_the_analysis(frame, earlier):
        if not frame.facts.get("opened"):
            return "a tela de cenários não está no shell"
        if frame.facts.get("criteria") != 3:
            return (f"a tela pegou {frame.facts.get('criteria')} critérios; a "
                    f"análise tem três, e um cenário medido contra outra "
                    f"análise não mede nada")
        if frame.facts.get("method") != "fuzzy_gamma":
            return "a tela não pegou o operador que a análise usa"
        if not frame.facts.get("ready"):
            return "a tela não se considera pronta com três critérios"
        if frame.facts.get("measured"):
            return "a tela abriu já com um resultado; ela não mediu nada ainda"
        return None

    def the_worker_measured_and_ordered(frame, earlier):
        if not frame.facts.get("pressed"):
            return "o botão de medir não estava alcançável"
        if frame.facts.get("rows") != 3:
            return f"vieram {frame.facts.get('rows')} linhas para três critérios"
        if not frame.facts.get("ordered"):
            return ("a tabela não está ordenada pelo que mais move o mapa; a "
                    "primeira linha é a resposta e ela tem de estar em cima")
        if not frame.facts.get("cells"):
            return ("um número de sensibilidade sem o tamanho da amostra não é "
                    "evidência (P-174)")
        if not frame.facts.get("has_limitation"):
            return ("a limitação do desenho um-de-cada-vez não veio com o "
                    "resultado; quem não a conhece vai supor o contrário")
        if frame.facts.get("runs_after") != frame.facts.get("runs_before"):
            return ("medir um cenário commitou uma run; é uma sondagem e não "
                    "pode criar linhagem (P-53)")
        if frame.facts.get("method_after") != "fuzzy_gamma":
            return "medir mudou o operador da análise; a tela mede e não decide"
        return None

    def the_sweep_measured_without_undoing_the_first(frame, earlier):
        if not frame.facts.get("pressed"):
            return "o botão da varredura não estava alcançável"
        if frame.facts.get("parameter") != "gamma":
            return f"varreu {frame.facts.get('parameter')!r} em vez de gamma"
        if frame.facts.get("values", 0) < 5:
            return f"a varredura tem {frame.facts.get('values')} valores"
        if frame.facts.get("worst_change", 0) <= 0:
            return ("gamma não mudou nada em nenhum valor: ou a varredura não "
                    "rodou, ou está medindo a mesma agregação seis vezes")
        if not frame.facts.get("loo_still_there"):
            return "a segunda medição apagou a primeira"
        if frame.facts.get("runs", 0) != 0:
            return "a varredura commitou uma run"
        return None

    board.step("analysis",
               "Uma análise de três critérios que discordam, para que tirar um "
               "tenha onde aparecer.",
               analysis, probes=PROBES, expect=the_analysis_exists)
    board.step("opened",
               "A tela de cenários pega a análise do Decision Model — os "
               "mesmos critérios, o mesmo operador — e abre sem inventar "
               "resultado nenhum.",
               opened, probes=PROBES, expect=the_screen_takes_the_analysis)
    board.step("leave_one_out",
               "O worker tira um critério por vez e reagrega. A primeira linha "
               "é aquela cuja remoção mais move o mapa, e cada número vem com "
               "quantas células foram comparadas.",
               leave_one_out, probes=PROBES,
               expect=the_worker_measured_and_ordered)
    board.step("gamma_sweep",
               "A varredura de gamma na mesma análise. Nada foi commitado, "
               "nenhum peso foi reescrito, e a primeira medição continua lá.",
               gamma_sweep, probes=PROBES,
               expect=the_sweep_measured_without_undoing_the_first)
    return board
