"""E6 — the whole flow, driven through the interface, with no arguments.

    an empty project  ->  a file imported through the wizard
    ->  one analysis grid, chosen in the harmonize dialog
    ->  a prospectivity map

This is the storyboard A32 asks for, and it is deliberately different from
`m5`. That one submits operators directly: it proves the *science* runs. This
one presses the buttons — the wizard's Import, the dialog's Harmonise, the
Decision Model's Run — so it proves the **application** runs, which until E6 it
could not: the only action the shell offered was a Run wired to a dataset
handed in on the command line, and no test noticed because every test handed
one in.

Nothing here supplies an input the interface would not have. The session opens
a project and stops; every path after that is a control being used.
"""
from __future__ import annotations

from PySide6.QtCore import QObject  # noqa: E402

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

CANVAS = DATA / "synthetic" / "msp" / "canvas"
FIELD_A = CANVAS / "large_field.tif"
FIELD_B = CANVAS / "large_field_b.tif"

#: The grid the operator chooses in the dialog. Both fixtures are in this CRS,
#: so nothing is reprojected out of shape; the point is that it is *chosen*.
TARGET_CRS = "EPSG:26912"
PIXEL = 40.0

PROBES = {
    "workflow": (100, 200),
    "layers": (100, 700),
    "canvas": (700, 400),
    "inspector": (1300, 300),
    "statusbar": (700, 869),
}


def _press(session, name: str) -> bool:
    """Click a named control, the way a person does. False if it is absent."""
    from PySide6.QtCore import QMetaObject, Qt

    button = session.window.findChild(QObject, name)
    if button is None:
        return False
    QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
    return True


def _import_through_the_wizard(session, path, declared: dict) -> bool:
    """Open the wizard on a file, answer it, and press Import."""
    from PySide6.QtCore import QMetaObject, Qt

    wizard = session.wizard
    QMetaObject.invokeMethod(wizard, "clearWizard", Qt.DirectConnection)
    wizard.setProperty("path", str(path))
    for key, value in declared.items():
        wizard.setProperty(key, value)
    QMetaObject.invokeMethod(wizard, "inspect", Qt.DirectConnection)
    QMetaObject.invokeMethod(wizard, "open", Qt.DirectConnection)

    # Wait on the **store**, not on the wizard's `validated` binding.
    #
    # A QML binding is re-evaluated lazily, so on the second file the first
    # poll still reads the previous file's verdict, the wait returns at once,
    # and Import is pressed while the checks are still running — the store
    # then refuses with "has not been validated", the frame shows one dataset
    # where two were imported, and nothing says why.
    #
    # The store is what `importDataset` actually consults, so it is what a
    # driver has to wait for.
    resolved = str(path.resolve())
    session.wait_for(
        lambda: session.controller.store.latest_validation(resolved) is not None,
        30000)
    session.settle(300)
    verdict = session.controller.store.latest_validation(resolved)
    if verdict is None or not verdict["usable"]:
        return False
    return _press(session, "importButton")


def build() -> Storyboard:
    board = Storyboard("flow", "E6 — o fluxo real, pela interface")
    state: dict = {}

    def empty(session):
        """The application as it opens: a project, and step 2 waiting.

        No dataset, because none was given — and that used to mean the one
        action on the top bar could do nothing at all.
        """
        return {
            "datasets": len(session.controller.store.datasets()),
            "layers": session.controller.layers.count,
            "current": session.controller.currentStep,
        }

    def imported(session):
        """Two rasters in, each through the wizard's own Import button."""
        first = _import_through_the_wizard(
            session, FIELD_A, {"declaredUnit": "mGal"})
        session.settle(400)
        second = _import_through_the_wizard(
            session, FIELD_B, {"declaredUnit": "mGal"})
        session.settle(600)
        state["imported"] = bool(first and second)
        return {
            "pressed": state["imported"],
            "datasets": len(session.controller.store.datasets()),
            "layers": session.controller.layers.count,
            "current": session.controller.currentStep,
        }

    def harmonized(session):
        """One analysis grid, with the CRS and the pixel chosen in the dialog.

        There is no default CRS (ADR-004) and the extent policy is two
        different maps (P-82), so the dialog asks for all three and the run's
        manifest records what was answered.
        """
        dialog = session.window.findChild(QObject, "harmonizeDialog")
        if dialog is None:
            return {"opened": False}
        finished: list[str] = []
        session.controller._job_controller.jobFinished.connect(
            lambda _job, outcome: finished.append(outcome))

        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
        session.settle(300)
        offered = dialog.property("datasets") or []
        dialog.setProperty("targetCrs", TARGET_CRS)
        dialog.setProperty("pixelSize", str(PIXEL))
        dialog.setProperty("extentPolicy", "intersection")
        session.settle(100)
        before = len(session.controller.store.runs())
        pressed = _press(session, "harmonizeRun")
        # Wait for the **run**, not for the job's outcome: `jobFinished`
        # announces the outcome and the commit follows it, so a driver that
        # stops at the signal reads the store one step too early and finds no
        # manifest at all.
        session.wait_for(
            lambda: len(session.controller.store.runs()) > before, 60000)
        session.settle(400)
        state["harmonized"] = finished[:1] == ["Succeeded"]
        # The manifest from the committed run, not from the signal that
        # announced it: the run is the record, and reading it here is the same
        # thing a person reads afterwards.
        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if runs else {}
        state["layers"] = {
            layer["name"]: layer["artifact"]
            for layer in manifest.get("layers", [])
        }
        # Nothing is painted by hand here: the shell put each artefact on the
        # stack itself when `artifactReady` arrived. `showArtifact` is the M4
        # single-layer entry the gates use, and calling it here would clear a
        # stack the layer panel still lists — two opinions about one screen.
        session.settle(400)
        return {
            "opened": True,
            "offered": len(offered),
            "pressed": pressed,
            "outcome": finished[0] if finished else "none",
            "crs": TARGET_CRS,
            "pixel": PIXEL,
            "onGrid": len(state["layers"]),
        }

    def membership(session):
        """Every harmonized layer becomes a criterion, through the editor.

        The Apply button is pressed for each: the spec the editor builds is
        the one that reaches the Decision Model, so nothing here invents a
        membership the screen would not have produced.
        """
        from PySide6.QtCore import QMetaObject, Qt

        editor = session.window.findChild(QObject, "membershipEditor")
        if editor is None:
            return {"applied": 0}
        applied = 0
        for name, path in sorted(state.get("layers", {}).items()):
            described = session.describe(path, {"unit": "mGal"})
            editor.setProperty("criterion", {
                "name": name, "path": path, "unit": "mGal",
                "statistics": described.get("statistics", {}),
            })
            editor.setProperty("functionName", "linear_increasing")
            QMetaObject.invokeMethod(editor, "open", Qt.DirectConnection)
            session.settle(300)
            if _press(session, "membershipApply"):
                applied += 1
            session.settle(200)
        # Aplicar duas vezes na **mesma** camada corrige a curva; não cria
        # um segundo critério. A lista mostrava a mesma camada duas vezes e a
        # agregação a contava duas vezes.
        again = sorted(state.get("layers", {}).items())[0]
        described = session.describe(again[1], {"unit": "mGal"})
        editor.setProperty("criterion", {
            "name": again[0], "path": again[1], "unit": "mGal",
            "statistics": described.get("statistics", {}),
        })
        editor.setProperty("functionName", "linear_decreasing")
        QMetaObject.invokeMethod(editor, "open", Qt.DirectConnection)
        session.settle(300)
        _press(session, "membershipApply")
        # A pertinência produz raster: o job é read-write e leva um tempo.
        session.settle(3500)

        criteria = session.window.property("criteria") or []
        if hasattr(criteria, "toVariant"):
            criteria = criteria.toVariant()
        state["criteria"] = list(criteria)
        names = [c.get("name", "") for c in state["criteria"]]
        return {
            "applied": applied,
            "criteria": len(state["criteria"]),
            # Reaplicar não pode inflar a lista.
            "unique_paths": len({c.get("path", "") for c in state["criteria"]}),
            "reapplied_function": next(
                (c.get("function", "") for c in state["criteria"]
                 if c.get("path") == again[1]), ""),
            # E a etapa 5 passa a **produzir mapa**: um critério que só existe
            # como linha numa lista não pode ser conferido antes de combinado.
            # Uma pertinência por camada de origem. Três tentativas de
            # curva deixavam três rasters na pilha, quase com o mesmo nome.
            "membership_layers": sum(
                1 for row in session.controller.layers.snapshot()
                if row.get("role") == "membership"),
            "membership_names": len({
                row.get("name") for row in session.controller.layers.snapshot()
                if row.get("role") == "membership"}),
            "named": ", ".join(sorted(names))[:60],
        }

    def prospectivity(session):
        """The map, by **pressing the screen's own Run button**.

        Not by calling `runDecision` with a request built here. Building the
        request in the driver is what let the weighted path stay broken for
        eleven versions: the screen assembled one thing, the shell forwarded
        another, and no frame ever compared them because no frame ever asked
        the screen for its own request.

        The method is the **weighted** one on purpose. Gamma takes no weights,
        so a frame that runs gamma cannot notice weights going missing.
        """
        from PySide6.QtCore import QMetaObject, Qt

        model = session.window.findChild(QObject, "decisionModel")
        if model is None:
            return {"screen": False}
        QMetaObject.invokeMethod(model, "open", Qt.DirectConnection)
        session.settle(300)
        model.setProperty("criteria", state.get("criteria", []))
        model.setProperty("method", "weighted_linear_combination")
        session.settle(400)

        finished: list[str] = []
        session.controller._job_controller.jobFinished.connect(
            lambda _job, outcome: finished.append(outcome))

        before_layers = session.controller.layers.count
        button = session.window.findChild(QObject, "decisionRun")
        pressed = button is not None and bool(button.property("enabled"))
        if pressed:
            QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
        session.wait_for(lambda: bool(finished), 120000)
        session.settle(1200)

        runs = session.controller.store.runs()
        manifest = runs[-1].manifest if runs else {}
        artifacts = (session.controller.store.artifacts(runs[-1].id)
                     if runs else [])
        weights = manifest.get("weights") or {}
        session.settle(600)
        return {
            "screen": True,
            "pressed": pressed,
            "outcome": finished[0] if finished else "none",
            # O método fica em `params`, junto com o resto do que foi
            # pedido: o manifesto separa o que se pediu do que saiu.
            "method": str((manifest.get("params") or {}).get("method", "")),
            # Os pesos têm de chegar ao manifesto: são a prioridade declarada,
            # e sem eles a run não se reproduz.
            "weighted": len(weights),
            "runs": len(runs),
            "artifacts": len(artifacts),
            # **O mapa apareceu?** É a pergunta que quem usou o produto fez.
            "layers_before": before_layers,
            "layers_after": session.controller.layers.count,
        }

    # ---- what each frame has to be true for --------------------------------

    def nothing_was_injected(frame, earlier):
        """The application opened with no data at all. If it had any, the
        session handed it something and the rest proves nothing."""
        if frame.facts.get("datasets", 0) != 0:
            return "the project already held a dataset before anything ran"
        if frame.facts.get("layers", 0) != 0:
            return "the view already held a layer before anything ran"
        return None

    def the_wizard_imported(frame, earlier):
        if not frame.facts.get("pressed"):
            return "the wizard's Import button was not reachable or refused"
        if frame.facts.get("datasets", 0) < 2:
            return (f"{frame.facts.get('datasets')} datasets in the catalogue "
                    f"after two imports")
        if frame.facts.get("layers", 0) < 2:
            return "the imported data did not reach the view"
        return None

    def the_grid_was_chosen(frame, earlier):
        if not frame.facts.get("opened"):
            return "the harmonize dialog is not in the shell"
        if frame.facts.get("offered", 0) < 2:
            return (f"the dialog offered {frame.facts.get('offered')} layers; "
                    f"it reads the catalogue, which holds two")
        if not frame.facts.get("pressed"):
            return "the dialog's Harmonise button was not reachable"
        if frame.facts.get("outcome") != "Succeeded":
            return f"harmonization ended {frame.facts.get('outcome')!r}"
        if frame.facts.get("onGrid", 0) < 2:
            return (f"{frame.facts.get('onGrid')} layers came back on the "
                    f"grid; two went in")
        return None

    def every_layer_became_a_criterion(frame, earlier):
        if frame.facts.get("applied", 0) < 2:
            return (f"the editor's Apply was pressed {frame.facts.get('applied')} "
                    f"times for two layers")
        if frame.facts.get("criteria", 0) < 2:
            return "the specs the editor built did not reach the shell"
        if frame.facts.get("criteria", 0) != frame.facts.get("unique_paths", 0):
            return (f"{frame.facts.get('criteria')} critérios sobre "
                    f"{frame.facts.get('unique_paths')} caminhos: reaplicar a "
                    f"pertinência duplicou o critério em vez de corrigi-lo")
        if frame.facts.get("reapplied_function") != "linear_decreasing":
            return ("reaplicar não substituiu a curva; a lista guardou a "
                    "primeira e a agregação usaria a errada")
        if frame.facts.get("membership_layers", 0) < 1:
            return ("a etapa 5 não produziu mapa nenhum: o critério existe "
                    "como linha numa lista e ninguém confere a pertinência "
                    "antes de combiná-la")
        if frame.facts.get("membership_layers") != frame.facts.get(
                "membership_names"):
            return ("duas camadas de pertinência com o mesmo nome; reaplicar "
                    "empilhou em vez de substituir")
        if frame.facts.get("membership_layers", 0) > frame.facts.get(
                "unique_paths", 0):
            return (f"{frame.facts.get('membership_layers')} pertinências "
                    f"para {frame.facts.get('unique_paths')} camadas: cada "
                    f"tentativa de curva deixou um raster para trás")
        return None

    def a_map_came_out(frame, earlier):
        if not frame.facts.get("screen"):
            return "a tela de decisão não está no shell"
        if not frame.facts.get("pressed"):
            return ("o botão Rodar não estava habilitado; a recusa tem de "
                    "estar na tela, mas aqui há critérios e ele devia acender")
        if frame.facts.get("outcome") != "Succeeded":
            return (f"a agregação terminou {frame.facts.get('outcome')!r} — "
                    f"que é exatamente o que quem usou o produto viu quando "
                    f"escolheu o método ponderado")
        if frame.facts.get("method") != "weighted_linear_combination":
            return f"o manifesto registra {frame.facts.get('method')!r}"
        if frame.facts.get("weighted", 0) < 2:
            return ("os pesos não chegaram ao manifesto; sem eles a run não "
                    "se reproduz, e o operador teria recusado")
        if frame.facts.get("artifacts", 0) < 1:
            return "a run não registrou artefato; não há mapa"
        # A pergunta de quem usou o produto: **o mapa apareceu?**
        if frame.facts.get("layers_after", 0) <= frame.facts.get(
                "layers_before", 0):
            return ("a run terminou e nenhuma camada entrou na pilha; o mapa "
                    "existe em disco e não aparece na tela, que é o defeito "
                    "relatado")
        return None

    board.step("empty", "A aplicação recém-aberta, sem nenhum argumento de "
               "linha de comando: um projeto, e a etapa 2 esperando.",
               empty, probes=PROBES, must_change=False,
               expect=nothing_was_injected)
    board.step("imported", "Dois rasters importados pelo botão Importar do "
               "próprio assistente, cada um com o seu veredito de QA/QC.",
               imported, probes=PROBES, expect=the_wizard_imported)
    board.step("harmonized", "Uma grade de análise, com CRS, pixel e política "
               "de extensão escolhidos no diálogo — nenhum deles assumido.",
               harmonized, probes=PROBES, expect=the_grid_was_chosen)
    # `must_change` is off here, and the reason is not that the step is weak:
    # it is that its `expect` is stronger. The editor opens and closes inside
    # the step, so what it leaves behind is two criteria in the shell and not
    # a different screen — and since the Inspector began following the active
    # layer, even the incidental difference is gone. The pixel guard catches a
    # step that did nothing; this one asserts what it did.
    board.step("membership", "Cada camada harmonizada vira um critério pelo "
               "botão Aplicar do editor, com a curva sobre o histograma.",
               membership, probes=PROBES, must_change=False,
               expect=every_layer_became_a_criterion)
    board.step("prospectivity", "O mapa de prospectividade, ao fim de um fluxo "
               "que começou numa janela vazia.",
               prospectivity, probes=PROBES, expect=a_map_came_out)
    return board
