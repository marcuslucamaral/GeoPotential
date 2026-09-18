"""M7 — a bancada de campos potenciais. §9.4, MSP-14, MSP-15.

    um grid do campo  ->  a bancada, com as convenções à vista
    ->  o tilt rodado, e o resultado ao lado do original
    ->  a RTP em baixa inclinação, com o alerta antes de executar

Os sete requisitos do §9.4 são o que os quadros checam, e cada um por um
número do estado da aplicação e não por uma descrição do que deveria estar
lá:

  selecionar operador     o seletor tem os sete e a troca muda os parâmetros
  definir parâmetros      trocar de operador esconde o que ele não aceita
  comparar orig./proc.    o resultado entra como camada, com o original ainda lá
  registrar convenções    o bloco está visível sempre, em todos os operadores
  visualizar warnings     a RTP em I = 5° acende o alerta **antes** de rodar
  executar                a run acontece e produz um artefato
  reproduzir              o manifesto traz convenção, borda e parâmetros
"""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

#: Um grid numa grade métrica: é o que um filtro espectral aceita.
FIELD = DATA / "synthetic" / "msp" / "canvas" / "large_field.tif"

PROBES = {
    "rail": (22, 300),
    "workflow": (140, 200),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "topbar": (700, 45),
}


def _length(value) -> int:                                 # noqa: ANN001
    """Quantos itens uma lista declarada em QML tem.

    Uma lista literal de QML chega ao Python como `QJSValue`, que não tem
    `len`. `toVariant()` a converte; um `property var` que já veio como lista
    passa direto.
    """
    if value is None:
        return 0
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    try:
        return len(value)
    except TypeError:
        return 0


def _press(session, name: str) -> bool:
    button = session.window.findChild(QObject, name)
    if button is None:
        return False
    QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
    return True


def build() -> Storyboard:
    board = Storyboard("potential_fields", "M7 — bancada de campos potenciais")
    state: dict = {}

    def field_loaded(session):
        """O campo na visualização, antes de qualquer filtro."""
        session.controller.addLayer(str(FIELD), "campo total", "original", "nT")
        session.settle(700)
        return {
            "layers": session.controller.layers.count,
            "runs": len(session.controller.store.runs()),
        }

    def workbench(session):
        """A bancada aberta, com as convenções à vista."""
        dialog = session.window.findChild(QObject, "potentialFieldsDialog")
        if dialog is None:
            return {"opened": False}
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(600)
        state["dialog"] = dialog

        conventions = session.window.findChild(QObject, "pfConventions")
        return {
            "opened": True,
            "operators": _length(dialog.property("operators")),
            "fields": _length(dialog.property("layers")),
            "operator": str(dialog.property("operator")),
            "ready": bool(dialog.property("ready")),
            # FIS-02 na tela, e não só no manifesto.
            "conventions_visible": bool(conventions.property("visible"))
                                   if conventions else False,
            "conventions_len": len(str(conventions.property("text")))
                               if conventions else 0,
            # O tilt não pede altura nem inclinação: os campos somem.
            "needs_height": bool(dialog.property("needsHeight")),
            "needs_magnetic": bool(dialog.property("needsMagnetic")),
            "unstable": bool(dialog.property("unstable")),
        }

    def tilt_ran(session):
        """O tilt executado, e o resultado ao lado do original."""
        dialog = state["dialog"]
        before = len(session.controller.store.runs())
        layers_before = session.controller.layers.count
        pressed = _press(session, "pfRun")
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 180000)
        session.settle(1500)
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if len(runs) > before else {}
        return {
            "pressed": pressed,
            "operator": manifest.get("operator", ""),
            "unit": manifest.get("unit", ""),
            "has_conventions": bool(manifest.get("conventions")),
            "pad_mode": (manifest.get("filter", {}).get("border", {})
                         .get("mode", "")),
            "artifacts": len(session.controller.store.artifacts(runs[-1].id))
            if len(runs) > before else 0,
            # O original continua lá: comparar é ter os dois.
            "layers_before": layers_before,
            "layers_after": session.controller.layers.count,
        }

    def not_a_potential_field(session):
        """Declarar "outro" desabilita o que depende de Laplace.

        Era a lacuna: os operadores aceitavam qualquer raster métrico e
        rodavam uma continuação para cima num MDE sem dizer nada.
        """
        dialog = state["dialog"]
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(400)
        dialog.setProperty("operator", "potential_fields.tilt")
        dialog.setProperty("fieldKind", "other")
        session.settle(500)
        warning = session.window.findChild(QObject, "pfKindWarning")
        reason = str(dialog.property("operatorReason"))
        blocked = bool(dialog.property("ready"))
        # Lido **agora**, com o tilt ainda escolhido. Ler depois de trocar de
        # operador seria ler o aviso de outro estado — foi o que este quadro
        # pegou na primeira execução.
        warning_visible = bool(warning.property("visible")) if warning else False

        # E o gradiente horizontal total continua disponível: ele é
        # matemática de grade, não física de campo potencial.
        dialog.setProperty("operator",
                           "potential_fields.total_horizontal_gradient")
        session.settle(300)
        thg_ok = len(str(dialog.property("operatorReason"))) == 0
        return {
            "kind": str(dialog.property("fieldKind")),
            "tilt_reason": reason[:60],
            "tilt_blocked": not blocked,
            "warning_visible": warning_visible,
            "thg_still_available": thg_ok,
        }

    def rtp_warning(session):
        """A RTP em baixa inclinação, com o alerta antes de executar."""
        dialog = state["dialog"]
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(400)
        dialog.setProperty("fieldKind", "magnetic")
        dialog.setProperty("operator", "potential_fields.rtp")
        dialog.setProperty("inclination", "5")
        session.settle(500)
        warning = session.window.findChild(QObject, "pfWarning")
        return {
            "operator": str(dialog.property("operator")),
            "needs_magnetic": bool(dialog.property("needsMagnetic")),
            "needs_height": bool(dialog.property("needsHeight")),
            "unstable": bool(dialog.property("unstable")),
            "warning_visible": bool(warning.property("visible"))
                               if warning else False,
            "warning_mentions_equator": "equador" in str(
                warning.property("text")).lower() if warning else False,
        }

    # ---- o que tem de ser verdade ----------------------------------------

    def the_field_is_there(frame, earlier):
        if frame.facts.get("layers", 0) < 1:
            return "o grid do campo não entrou na visualização"
        return None

    def the_workbench_shows_its_conventions(frame, earlier):
        if not frame.facts.get("opened"):
            return "a bancada não está no shell"
        if frame.facts.get("operators", 0) != 7:
            return (f"a bancada oferece {frame.facts.get('operators')} "
                    f"operadores; MSP-14/15 pedem os sete")
        if frame.facts.get("fields", 0) < 1:
            return "a bancada não achou nenhum campo para filtrar"
        if not frame.facts.get("conventions_visible"):
            return ("as convenções não estão à vista; o §9.4 pede registrá-las "
                    "e o FIS-02 pede declará-las")
        if frame.facts.get("conventions_len", 0) < 120:
            return "o bloco de convenções está vazio ou quase"
        if frame.facts.get("needs_height") or frame.facts.get("needs_magnetic"):
            return ("o tilt não pede altura nem inclinação, e a tela está "
                    "mostrando campos que aquele operador ignora")
        if frame.facts.get("unstable"):
            return "o alerta de RTP acendeu num operador que não é RTP"
        return None

    def the_result_sits_beside_the_original(frame, earlier):
        if not frame.facts.get("pressed"):
            return "o botão de executar não estava alcançável"
        if frame.facts.get("operator") != "potential_fields.tilt":
            return f"rodou {frame.facts.get('operator')!r}"
        if frame.facts.get("unit") != "rad":
            return (f"o tilt saiu rotulado {frame.facts.get('unit')!r}; ele é "
                    f"um ângulo, e um mapa rotulado errado é lido errado")
        if not frame.facts.get("has_conventions"):
            return "o manifesto não traz as convenções (FIS-02)"
        if frame.facts.get("pad_mode") != "reflect":
            return "o manifesto não traz a borda (FIS-03)"
        if frame.facts.get("artifacts", 0) < 1:
            return "a run não produziu artefato"
        if frame.facts.get("layers_after", 0) <= frame.facts.get("layers_before", 0):
            return ("o resultado não entrou como camada; comparar original e "
                    "processado é ter os dois")
        return None

    def laplace_is_enforced_not_assumed(frame, earlier):
        if frame.facts.get("kind") != "other":
            return "o tipo de campo não mudou"
        if not frame.facts.get("tilt_blocked"):
            return ("o tilt continua executável num dado que não é campo "
                    "potencial; ele usa a derivada vertical, que é inferida "
                    "do dado horizontal pela equação de Laplace")
        if not frame.facts.get("warning_visible"):
            return "a razão não está na tela"
        if "potencial" not in frame.facts.get("tilt_reason", ""):
            return "a razão não diz por que a transformação não vale ali"
        if not frame.facts.get("thg_still_available"):
            return ("o gradiente horizontal total foi bloqueado junto; ele usa "
                    "só dx e dy, é matemática de grade, e vale num MDE")
        return None

    def the_warning_comes_before_the_run(frame, earlier):
        if frame.facts.get("operator") != "potential_fields.rtp":
            return "o operador não mudou para RTP"
        if not frame.facts.get("needs_magnetic"):
            return "a RTP não está pedindo inclinação e declinação"
        if frame.facts.get("needs_height"):
            return "a tela está pedindo altura para um operador que não a usa"
        if not frame.facts.get("unstable"):
            return "I = 5° não acendeu a instabilidade; MSP-15 manda avisar"
        if not frame.facts.get("warning_visible"):
            return ("o alerta existe no estado e não está na tela; um alerta "
                    "que não aparece não é um alerta")
        if not frame.facts.get("warning_mentions_equator"):
            return "o alerta não diz por que a RTP é instável ali"
        return None

    board.step("field",
               "O grid do campo na visualização, numa grade métrica — que é o "
               "que um filtro espectral aceita.",
               field_loaded, probes=PROBES, expect=the_field_is_there)
    board.step("workbench",
               "A bancada: sete operadores, os parâmetros que o escolhido "
               "aceita, a borda como parâmetro, e as convenções à vista.",
               workbench, probes=PROBES,
               expect=the_workbench_shows_its_conventions)
    board.step("tilt",
               "O tilt rodado. Sai rotulado em radianos, o manifesto traz a "
               "convenção e a borda, e o original continua na pilha ao lado.",
               tilt_ran, probes=PROBES,
               expect=the_result_sits_beside_the_original)
    board.step("not_potential",
               "Declarar o dado como \"outro\" desabilita as cinco "
               "transformações que dependem de Laplace, com a razão no "
               "rótulo. O gradiente horizontal total continua: ele é "
               "matemática de grade.",
               not_a_potential_field, probes=PROBES,
               expect=laplace_is_enforced_not_assumed)
    board.step("rtp_warning",
               "RTP com inclinação de 5°: o alerta de instabilidade acende "
               "**antes** de executar, e diz o que fazer no lugar.",
               rtp_warning, probes=PROBES,
               expect=the_warning_comes_before_the_run)
    return board
