"""The shell, loaded for real and interrogated.

P-105 — every enabled menu entry has an action; every disabled one says why.
P-103 — the workflow the panel binds to is the one the store implies.

This builds the actual QML engine offscreen and reads the actual objects. A
test that inspected the `.qml` source as text would pass on a file that never
loads, which is the failure mode this suite exists to catch: the first run of
E1 loaded no shell at all because a role was named `state`.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

try:
    from PySide6.QtCore import QEvent, QEventLoop, QObject
    from PySide6.QtGui import QGuiApplication
    HAVE_QT = True
except ImportError:                                  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:
    from geopotential_app.app import _build_engine, _register_qml_types
    from geopotential_app.controllers.app_controller import AppController

# The tokens Main.qml's `dispatch` knows. A menu entry naming anything else is
# an entry that does nothing, which is exactly what P-105 forbids.
def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    root = Path(__file__).resolve().parents[2]
    inside = root / "data"
    return inside if inside.is_dir() else (root.parent / "data").resolve()


MAIN_QML = (
    Path(__file__).resolve().parents[2]
    / "app" / "geopotential_app" / "qml" / "Main.qml"
)


#: One shell for the whole module, built on first use and never torn down.
#:
#: Four test classes read the loaded interface, and each used to build its own
#: QML engine and destroy it. Several engines in one process share the type
#: registry and the singletons, and about one run in five a Dialog was simply
#: absent from a later class's window — `findChild` returned None with no error
#: anywhere to say why. The class docstring already promised one engine; this
#: is that promise kept. The process exits and takes it down.
_SHARED: dict = {}


def shared_shell() -> dict:
    if not _SHARED:
        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        _register_qml_types()
        workdir = Path(tempfile.mkdtemp(prefix="geopotential-shell-"))
        # The suite switches language; it must not write the developer's own.
        os.environ["GEOPOTENTIAL_PREFERENCES"] = str(workdir / "prefs.ini")
        os.environ["XDG_STATE_HOME"] = str(workdir / "state")
        controller = AppController()
        controller.createProject(str(workdir / "Shell.gpot"), "Shell")
        engine = _build_engine(controller)
        _SHARED.update(
            app=app, workdir=workdir, controller=controller, engine=engine,
            window=engine.rootObjects()[0],
        )
    return _SHARED


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class Shell(unittest.TestCase):
    """One engine for the whole suite: building it is the expensive part."""

    @classmethod
    def setUpClass(cls) -> None:
        shell = shared_shell()
        cls.app = shell["app"]
        cls.workdir = shell["workdir"]
        cls.controller = shell["controller"]
        cls.engine = shell["engine"]
        cls.window = shell["window"]
        cls.dispatch_source = MAIN_QML.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        """Deliberately nothing.

        The shell is shared, so tearing it down here would take it away from
        the classes that run after this one. Destroying and rebuilding a QML
        engine per class is what this suite used to do, and it is what made a
        Dialog vanish one run in five.
        """

    def menu_items(self) -> list[dict]:
        bar = self.window.findChild(QObject, "appMenuBar")
        self.assertIsNotNone(bar, "the menu bar did not load")
        table = bar.property("auditTable")
        # A JavaScript array arrives as a QJSValue; only `toVariant` gives the
        # plain list of dictionaries.
        if hasattr(table, "toVariant"):
            table = table.toVariant()
        self.assertTrue(table, "the menu bar produced no audit table")
        return list(table)

    # ---- P-105 ----------------------------------------------------------

    def test_the_five_menus_are_there_in_the_chosen_language(self) -> None:
        """File, Edit, View, Processing, Help.

        Processing arrived with the interface rework: the eight steps of the
        flow are the application's spine, and a person who navigates by menu
        had no way to reach them.
        """
        from geopotential_app.i18n import table

        entries = table(self.controller.tr.language)
        expected = {entries[key] for key in
                    ("menu.file", "menu.edit", "menu.view", "menu.processing",
                     "menu.help")}
        menus = {str(item["menu"]).split(" › ")[0] for item in self.menu_items()}
        self.assertEqual(menus, expected)

    def test_every_enabled_entry_has_a_token(self) -> None:
        for item in self.menu_items():
            if item["enabled"]:
                self.assertTrue(
                    str(item["token"]).strip(),
                    f"{item['menu']} › {item['label']} is enabled and does nothing",
                )

    def test_every_enabled_token_is_routed(self) -> None:
        """The token has to appear in `dispatch`, or the click is a no-op."""
        for item in self.menu_items():
            token = str(item["token"])
            if not item["enabled"] or not token:
                continue
            # Tokens that carry a value are routed by a prefix branch, so the
            # prefix is what `dispatch` has to name.
            for prefix in ("project.openRecent:", "basemap:", "step:",
                           "colormap:"):
                if token.startswith(prefix):
                    token = prefix
                    break
            self.assertIn(
                f'"{token}"', self.dispatch_source,
                f"{item['menu']} › {item['label']} sends {token}, which "
                f"Main.qml does not route",
            )

    def test_every_disabled_entry_says_why(self) -> None:
        for item in self.menu_items():
            if not item["enabled"]:
                self.assertTrue(
                    str(item["reason"]).strip(),
                    f"{item['menu']} › {item['label']} is disabled and does not "
                    f"say why",
                )

    def test_a_disabled_entry_carries_its_reason_on_the_label(self) -> None:
        """A tooltip on a disabled control is unreachable — hover does not fire.
        The reason has to be in the text the person can read."""
        for item in self.menu_items():
            if not item["enabled"]:
                self.assertIn(
                    str(item["reason"]).strip(), str(item["label"]),
                    f"{item['label']} hides its reason",
                )

    def test_the_shortcuts_of_the_help_list_are_bound(self) -> None:
        for sequence in ("Ctrl+N", "Ctrl+O", "Ctrl+I", "Ctrl+Z",
                         "Ctrl+Shift+Z", "F11", "F1"):
            self.assertIn(
                f'sequence: "{sequence}"', self.dispatch_source,
                f"{sequence} is listed in Help › Atalhos and bound nowhere",
            )

    # ---- P-103 ----------------------------------------------------------

    def test_every_map_in_the_shell_is_named(self) -> None:
        """More than one MapItem lives in the shell since the Import Wizard
        gained a preview map. Anything that finds "the canvas" by class gets
        whichever the object tree reaches first — which pointed every
        storyboard and the interaction check at an empty preview canvas, and
        every one of them still passed while proving nothing.

        So: exactly one map is `mapCanvas`, and none is anonymous.
        """
        maps = [child for child in self.window.findChildren(QObject)
                if child.metaObject().className() == "MapItem"]
        self.assertGreaterEqual(len(maps), 1, "the shell loaded no map")
        names = [m.objectName() for m in maps]
        self.assertNotIn("", names, f"an unnamed MapItem in the shell: {names}")
        self.assertEqual(names.count("mapCanvas"), 1,
                         f"expected exactly one 'mapCanvas', got {names}")

    def test_the_menu_still_holds_up_with_a_layer_active(self) -> None:
        """P-105 again, in the state the audit never saw.

        The audit was taken once, on an empty project, so every entry that is
        only reachable with a layer went unchecked — and four of them sat
        disabled naming a milestone that had already shipped, for a whole
        milestone, with the gate green the entire time.
        """
        raster = _data_dir() / "utah_forge" / "Distance_to_fault.tif"
        if not raster.exists():
            self.skipTest("the smoke raster is missing")
        layer_id = self.controller.addLayer(str(raster), "audit", "original", "m")
        self.addCleanup(self.controller.layers.remove, layer_id)
        # No event loop needed: the model's `changed` signal reaches the menu
        # bar's handler directly, and the audit is rebuilt before this returns.
        items = self.menu_items()
        layer_tokens = {"layer.properties", "layer.rename", "layer.remove"}
        seen = {str(item["token"]) for item in items}
        self.assertTrue(layer_tokens <= seen,
                        f"the layer entries are missing from the audit: "
                        f"{sorted(layer_tokens - seen)}")
        for item in items:
            token = str(item["token"])
            if item["enabled"]:
                self.assertTrue(token.strip(),
                                f"{item['label']} is enabled and does nothing")
            else:
                self.assertTrue(str(item["reason"]).strip(),
                                f"{item['label']} is disabled and silent")
        # The ramps became reachable, so they have to be routed.
        ramps = [i for i in items if str(i["token"]).startswith("colormap:")]
        self.assertTrue(ramps, "the colormap submenu stayed unreachable")
        for ramp in ramps:
            self.assertTrue(ramp["enabled"],
                            f"{ramp['label']} is in an open submenu and dead")

    # ---- P-122, E6 ------------------------------------------------------

    def test_no_interface_path_depends_on_an_injected_input(self) -> None:
        """A33 — the shell offered exactly one action, and it ran an operator
        against a path supplied on the command line. No user of the
        application ever took that path; the self-test and the storyboards
        did, which is how it survived five milestones looking exercised.

        Checked as absence, in the app tree, so it cannot come back quietly.
        """
        app_root = Path(__file__).resolve().parents[2] / "app"
        offenders = []
        for source in list(app_root.rglob("*.qml")) + list(app_root.rglob("*.py")):
            if "__pycache__" in source.parts:
                continue
            text = source.read_text(encoding="utf-8")
            for banned in ("smokeInput", "runSmokeOperator"):
                if banned in text:
                    offenders.append(f"{source.name}: {banned}")
        self.assertEqual(offenders, [], f"an injected input is back: {offenders}")

    def test_the_engine_is_built_from_the_controller_alone(self) -> None:
        """The other half of the same rule: nothing else is handed to QML."""
        import inspect

        from geopotential_app.app import _build_engine

        parameters = list(inspect.signature(_build_engine).parameters)
        self.assertEqual(parameters, ["controller"])

    def test_run_acts_on_the_step_the_workflow_is_on(self) -> None:
        """The Run button routes through `runCurrentStep`, which reads the
        step from the model — not through an operator named in the shell."""
        self.assertIn("onRunRequested: appWindow.runCurrentStep()",
                      self.dispatch_source)
        self.assertIn("function runCurrentStep()", self.dispatch_source)

    def test_a_blocked_step_run_explains_instead_of_submitting(self) -> None:
        """An empty project's current step is `data`, which is available; the
        steps after it are blocked and each carries a reason key that
        resolves. A Run that raised an empty reason would say nothing."""
        from geopotential_app.i18n import table

        entries = table(self.controller.tr.language)
        model = self.controller.workflow
        blocked = [
            model.step(model.data(model.index(i, 0), model.KeyRole))
            for i in range(model.rowCount())
            if model.data(model.index(i, 0), model.StateRole) == "blocked"
        ]
        self.assertTrue(blocked, "nothing was blocked in an empty project")
        for step in blocked:
            key = step["reasonKey"]
            self.assertTrue(key, f"step {step['key']} is blocked and silent")
            self.assertIn(key, entries,
                          f"step {step['key']} names {key}, which the "
                          f"catalogue does not carry")

    def test_every_step_action_is_routed(self) -> None:
        """Every action a step can ask for has a branch in `openStep`.

        Two of them used to fall through to "arrives in M5.5 E2" — for work
        that had already landed.
        """
        model = self.controller.workflow
        actions = {
            model.data(model.index(i, 0), model.ActionRole)
            for i in range(model.rowCount())
        }
        body = self.dispatch_source.split("function openStep", 1)[1]
        body = body.split("function ", 1)[0]
        for action in sorted(actions):
            self.assertIn(f'case "{action}":', body,
                          f"the step action {action!r} opens nothing")
        self.assertNotIn("M5.5 E2", body,
                         "openStep still defers work that has landed")

    def test_the_workflow_panel_is_bound_to_the_model(self) -> None:
        panel = self.window.findChild(QObject, "workflowPanel")
        self.assertIsNotNone(panel, "the workflow panel did not load")
        self.assertIs(panel.property("controller"), self.controller)

    def test_the_workflow_matches_the_open_project(self) -> None:
        """An open, empty project: step 1 done, step 2 open, the rest blocked."""
        model = self.controller.workflow
        rows = model.rowCount()
        self.assertEqual(rows, 8)
        states = [
            model.data(model.index(i, 0), model.StateRole) for i in range(rows)
        ]
        self.assertEqual(states[0], "done")
        self.assertEqual(states[1], "available")
        self.assertEqual(states[2:], ["blocked"] * 6)

    def test_the_workflow_is_reread_from_the_store_not_remembered(self) -> None:
        """P-103. Wipe the model's rows, recompute from the store, and get the
        same answer — the panel's state has no independent existence."""
        model = self.controller.workflow
        before = [
            model.data(model.index(i, 0), model.StateRole)
            for i in range(model.rowCount())
        ]
        model._steps = []                       # nothing remembered survives
        self.controller._refresh_workflow()
        after = [
            model.data(model.index(i, 0), model.StateRole)
            for i in range(model.rowCount())
        ]
        self.assertEqual(before, after)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TheMembershipEditorGetsItsLayer(Shell):
    """O editor de pertinência recebe a camada — e não a recebia.

    Ele era instanciado com o controller e o manipulador do sinal, e
    `criterion` ficava `{}`. Na tela isso aparece como "sem distribuição",
    âncoras vazias e nenhuma curva, **com o Inspector ao lado mostrando a
    faixa e o histograma da mesma camada** — que é como o defeito foi
    encontrado, por alguém usando o produto.

    Nenhum gate pegava porque nenhum gate abria o editor: as storyboards
    atribuíam `functionName` direto e nunca liam `ready`.
    """

    def _open_membership(self, layer_id: str) -> object:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        self.controller.layers.setActive(layer_id)
        QMetaObject.invokeMethod(self.window, "openMembership",
                                 Qt.DirectConnection)
        return self.window.findChild(QObject, "membershipEditor")

    def test_the_editor_receives_the_active_layer(self) -> None:
        raster = _data_dir() / "utah_forge" / "Distance_to_fault.tif"
        if not raster.is_file():
            self.skipTest(f"{raster} não está no repositório")
        layer_id = self.controller.addLayer(str(raster), "campo",
                                            "original", "m")
        editor = self._open_membership(layer_id)
        self.assertIsNotNone(editor, "o editor não está no shell")
        criterion = editor.property("criterion")
        if hasattr(criterion, "toVariant"):
            criterion = criterion.toVariant()
        self.assertTrue(criterion,
                        "o editor abriu com `criterion` vazio: é o defeito, "
                        "e é o que produz 'sem distribuição' na tela")
        self.assertEqual(criterion.get("name"), "campo")
        self.assertTrue(criterion.get("path"),
                        "sem o caminho, aplicar a pertinência não sabe sobre "
                        "que arquivo ela é")
        self.assertEqual(criterion.get("unit"), "m")

    def test_opening_without_a_layer_says_what_is_missing(self) -> None:
        """Um diálogo vazio não explica nada; a recusa explica."""
        from PySide6.QtCore import QMetaObject, Qt

        raised = []
        self.controller.errorRaised.connect(
            lambda message, ref: raised.append(message))
        QMetaObject.invokeMethod(self.window, "openMembership",
                                 Qt.DirectConnection)
        self.assertTrue(raised, "abrir sem camada não disse nada")
        self.assertIn("camada", raised[0].lower())

    def test_the_editor_reads_the_same_source_as_the_inspector(self) -> None:
        """`layerDescription`, e não a última coisa que o wizard descreveu —
        que é uma camada diferente sempre que algo foi calculado."""
        source = MAIN_QML.read_text(encoding="utf-8")
        self.assertIn("layerDescription", source)
        self.assertIn("openMembership", source)
        # O editor é aberto por um caminho só, que é o que lhe dá a camada.
        self.assertEqual(source.count("membershipEditor.open()"), 1,
                         "há mais de um caminho abrindo o editor, e só um "
                         "deles lhe dá a camada")
        self.assertIn('case "data.membership":    appWindow.openMembership()',
                      source)


class TheClassTable(Shell):
    """Uma nota por classe, sobre os códigos que o arquivo realmente tem.

    `membership.categorical` recusa qualquer código sem nota, e a recusa está
    certa: pontuar zero uma classe desconhecida transforma uma lacuna de dado
    em afirmação científica. Mas o editor não sabia listar os códigos, então
    satisfazer a recusa exigia já saber quais eram — geologia, uso do solo e
    solo ficavam inalcançáveis pela interface. Foi onde quem usou o produto
    parou.

    Os números vêm de `describe` sobre os arquivos reais do dataset de
    deslizamento. Inventar um histograma aqui testaria a tabela contra o que
    eu imaginei que um raster de classes é.
    """

    FACTORS = _data_dir() / "conditioning_factors"

    def _editor(self, raster: Path, unit: str = "classe") -> object:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        if not (self.FACTORS / "geology.tif").is_file():
            self.skipTest(f"{self.FACTORS} não está no repositório")
        # As estatísticas vêm da função do worker, não de um histograma que eu
        # inventei: a tabela precisa ser testada contra o que um raster de
        # classes realmente é.
        worker = str(Path(__file__).resolve().parents[2] / "worker")
        if worker not in sys.path:
            sys.path.insert(0, worker)
        from geopotential_worker.io.describe import describe

        editor = self.window.findChild(QObject, "membershipEditor")
        self.assertIsNotNone(editor, "o editor não está no shell")
        # **Aberto**, porque o que se afirma aqui é o que a pessoa vê: um item
        # dentro de um Dialog fechado lê `visible` como falso, e um aviso que
        # existe mas não aparece não avisa ninguém.
        QMetaObject.invokeMethod(editor, "open", Qt.DirectConnection)
        # O shell é compartilhado e o editor é o mesmo objeto em todos os
        # testes. Passar por uma camada vazia é a troca de camada de verdade,
        # e é o que zera as notas — sem isso a ordem alfabética dos testes
        # decide o resultado.
        editor.setProperty("criterion", {})
        editor.setProperty("criterion", {
            "path": str(raster),
            "name": raster.stem,
            "unit": unit,
            "statistics": describe(raster).statistics,
        })
        editor.setProperty("functionName", "categorical")
        self._open = editor
        return editor

    def tearDown(self) -> None:
        from PySide6.QtCore import QMetaObject, Qt

        editor = getattr(self, "_open", None)
        if editor is not None:
            QMetaObject.invokeMethod(editor, "close", Qt.DirectConnection)
            self._open = None

    def _score(self, editor: object, code: float, text: str) -> None:
        from PySide6.QtCore import Q_ARG, QMetaObject, Qt

        QMetaObject.invokeMethod(editor, "setClassScore", Qt.DirectConnection,
                                 Q_ARG("QVariant", code),
                                 Q_ARG("QVariant", text))

    def test_the_table_lists_the_codes_the_file_has(self) -> None:
        editor = self._editor(self.FACTORS / "geology.tif")
        codes = editor.property("classCodes")
        if hasattr(codes, "toVariant"):
            codes = codes.toVariant()
        self.assertEqual([float(c) for c in codes], [1.0, 2.0, 3.0, 4.0],
                         "a tabela não lista os códigos que geology.tif tem")

    def test_applying_waits_until_every_class_is_scored(self) -> None:
        """O worker recusaria o código sem nota de qualquer forma. Recusar
        aqui diz **onde** está a lacuna, em vez de devolver um job vermelho."""
        from PySide6.QtCore import QObject

        editor = self._editor(self.FACTORS / "geology.tif")
        apply = editor.findChild(QObject, "membershipApply")
        self.assertIsNotNone(apply, "o botão Aplicar não está no editor")

        self.assertEqual(editor.property("classesMissing"), 4)
        self.assertFalse(apply.property("enabled"),
                         "aplicar com a tabela vazia manda o worker recusar")

        for code, score in ((1.0, "0.2"), (2.0, "0.5"), (3.0, "0.9")):
            self._score(editor, code, score)
        self.assertEqual(editor.property("classesMissing"), 1)
        self.assertFalse(apply.property("enabled"),
                         "falta uma classe e o botão já liberou")

        self._score(editor, 4.0, "1.0")
        self.assertEqual(editor.property("classesMissing"), 0)
        self.assertTrue(apply.property("enabled"))

    def test_a_score_outside_zero_to_one_does_not_count_as_scored(self) -> None:
        """Pertinência é adimensional em [0,1]. 1.4 não é uma nota."""
        editor = self._editor(self.FACTORS / "geology.tif")
        for code in (1.0, 2.0, 3.0, 4.0):
            self._score(editor, code, "0.5")
        self.assertEqual(editor.property("classesMissing"), 0)
        self._score(editor, 3.0, "1.4")
        self.assertEqual(editor.property("classesMissing"), 1)
        self._score(editor, 3.0, "abc")
        self.assertEqual(editor.property("classesMissing"), 1)

    def test_the_spec_leaving_the_editor_is_what_the_operator_takes(self) -> None:
        """O que sai daqui atravessa o IPC e chega em `mf.categorical`: um
        `mapping` de {código: nota}, numérico, sem âncoras de curva junto —
        mandar as duas coisas faria o worker escolher, e quem escolhe é a
        tela. É o `spec()` real, não uma leitura das propriedades."""
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        editor = self._editor(self.FACTORS / "geology.tif")
        for code, score in ((1.0, "0.2"), (2.0, "0.5"),
                            (3.0, "0.9"), (4.0, "1.0")):
            self._score(editor, code, score)

        value, undefined = QQmlExpression(
            qmlContext(editor), editor, "JSON.stringify(spec())").evaluate()
        self.assertFalse(undefined)
        spec = json.loads(value)

        self.assertEqual(spec["function"], "categorical")
        self.assertEqual({float(k): v for k, v in spec["mapping"].items()},
                         {1.0: 0.2, 2.0: 0.5, 3.0: 0.9, 4.0: 1.0})
        for score in spec["mapping"].values():
            self.assertIsInstance(score, (int, float))
        for anchor in ("x_min", "x_max", "midpoint", "center", "spread"):
            self.assertNotIn(anchor, spec,
                             f"{anchor} não significa nada para classes e foi "
                             f"junto assim mesmo")

    def test_a_continuous_layer_says_it_has_no_classes(self) -> None:
        """Um botão cinza sem motivo é a mesma parede que um erro sem texto."""
        from PySide6.QtCore import QObject

        editor = self._editor(self.FACTORS / "slope.tif", unit="degree")
        self.assertIsNone(editor.property("classInfo"),
                          "slope.tif é contínua e foi lida como classes")
        notice = editor.findChild(QObject, "membershipClassNotice")
        self.assertIsNotNone(notice)
        self.assertTrue(notice.property("visible"))
        self.assertIn("contínuo", str(notice.property("text")).lower())
        apply = editor.findChild(QObject, "membershipApply")
        self.assertFalse(apply.property("enabled"))

    def test_too_many_codes_says_how_many_and_the_limit(self) -> None:
        """O MDE inteiro é integral e não é uma camada de classes. Dizer
        quantas são é o que permite agir — reclassificar — em vez de só
        recusar."""
        from PySide6.QtCore import QObject

        editor = self._editor(self.FACTORS / "dem.tif", unit="m")
        info = editor.property("classInfo")
        if hasattr(info, "toVariant"):
            info = info.toVariant()
        self.assertGreater(info["distinct"], info["limit"])
        notice = editor.findChild(QObject, "membershipClassNotice")
        self.assertTrue(notice.property("visible"))
        self.assertIn(str(info["distinct"]), str(notice.property("text")))
        apply = editor.findChild(QObject, "membershipApply")
        self.assertFalse(apply.property("enabled"),
                         "885 classes não se pontuam à mão, e o botão liberou")

    def test_changing_layer_clears_the_scores(self) -> None:
        """Notas de geologia aplicadas a uso do solo seriam notas inventadas."""
        editor = self._editor(self.FACTORS / "geology.tif")
        for code in (1.0, 2.0, 3.0, 4.0):
            self._score(editor, code, "0.5")
        self.assertEqual(editor.property("classesMissing"), 0)

        self._editor(self.FACTORS / "landcover.tif")
        self.assertEqual(editor.property("classesMissing"), 9,
                         "as notas da camada anterior sobreviveram à troca")


class TheClassLegend(Shell):
    """O nome de cada código, quando o arquivo diz um.

    A tabela pontuava `1`, `2`, `3` e não sabia dizer qual era granito. O
    editor agora mostra o nome ao lado do código, diz de onde a legenda veio, e
    deixa visivelmente sem nome o código que a legenda não menciona — inventar
    "classe 3" faria uma legenda ausente parecer presente.

    A camada é uma cópia da geologia real com um `.meta.json` ao lado: os
    códigos e as contagens são do arquivo de verdade, e só a legenda é
    montada aqui.
    """

    FACTORS = _data_dir() / "conditioning_factors"

    def setUp(self) -> None:
        import json
        import shutil

        if not (self.FACTORS / "geology.tif").is_file():
            self.skipTest(f"{self.FACTORS} não está no repositório")
        worker = str(Path(__file__).resolve().parents[2] / "worker")
        if worker not in sys.path:
            sys.path.insert(0, worker)
        self.tmp = tempfile.mkdtemp(prefix="geopotential-legend-")
        self.raster = Path(self.tmp) / "geologia.tif"
        shutil.copy(self.FACTORS / "geology.tif", self.raster)
        self.raster.with_suffix(".meta.json").write_text(
            json.dumps({"classes": {"1": "granito", "2": "xisto",
                                    "4": "aluvião"}}), encoding="utf-8")

    def tearDown(self) -> None:
        import shutil

        from PySide6.QtCore import QMetaObject, Qt

        editor = getattr(self, "_open", None)
        if editor is not None:
            QMetaObject.invokeMethod(editor, "close", Qt.DirectConnection)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _editor(self, raster: Path) -> object:
        from PySide6.QtCore import QMetaObject, QObject, Qt

        from geopotential_worker.io.describe import describe

        editor = self.window.findChild(QObject, "membershipEditor")
        self.assertIsNotNone(editor, "o editor não está no shell")
        QMetaObject.invokeMethod(editor, "open", Qt.DirectConnection)
        editor.setProperty("criterion", {})
        editor.setProperty("criterion", {
            "path": str(raster), "name": raster.stem, "unit": "classe",
            "statistics": describe(raster).statistics,
        })
        editor.setProperty("functionName", "categorical")
        self._open = editor
        return editor

    def test_the_name_sits_beside_the_code(self) -> None:
        editor = self._editor(self.raster)
        names = editor.property("classNames")
        if hasattr(names, "toVariant"):
            names = names.toVariant()
        self.assertEqual(list(names), ["granito", "xisto", "", "aluvião"],
                         "a legenda não chegou emparelhada com os códigos")
        self.assertTrue(editor.property("hasLegend"))

    def test_the_screen_says_where_the_legend_came_from(self) -> None:
        """Um rótulo afirma o que um código significa, e uma afirmação sem
        origem não é conferível."""
        from PySide6.QtCore import QObject

        editor = self._editor(self.raster)
        self.assertEqual(str(editor.property("legendSource")), "sidecar")
        shown = editor.findChild(QObject, "membershipLegendSource")
        self.assertIsNotNone(shown)
        self.assertTrue(shown.property("visible"))
        self.assertIn("sidecar", str(shown.property("text")))

    def test_a_code_the_legend_skips_is_visibly_unnamed(self) -> None:
        from PySide6.QtCore import QObject

        editor = self._editor(self.raster)
        self.assertEqual(editor.property("classesUnnamed"), 1)
        partial = editor.findChild(QObject, "membershipLegendPartial")
        self.assertIsNotNone(partial)
        self.assertTrue(partial.property("visible"),
                        "uma legenda parcial é um estado real e a tela calou")

        # O valor a que a célula se liga, e não a célula: sob `offscreen` a
        # ListView não recebe altura e não instancia delegate nenhum, então
        # `findChild` sobre uma linha acharia None mesmo com a tabela certa.
        # Que a linha **desenha** é o que o quadro de storyboard prova.
        from PySide6.QtQml import QQmlExpression, qmlContext

        for index, expected in enumerate(["granito", "xisto", "", "aluvião"]):
            with self.subTest(code=index + 1):
                value, undefined = QQmlExpression(
                    qmlContext(editor), editor,
                    f"classLabel({index})").evaluate()
                self.assertFalse(undefined)
                self.assertEqual(str(value), expected)

    def test_the_legend_does_not_gate_the_scoring(self) -> None:
        """Um código sem nome continua pontuável: quem decide se sabe o
        bastante é quem pontua, não o arquivo."""
        from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt

        editor = self._editor(self.raster)
        apply_button = editor.findChild(QObject, "membershipApply")
        for code in (1.0, 2.0, 3.0, 4.0):
            QMetaObject.invokeMethod(editor, "setClassScore",
                                     Qt.DirectConnection,
                                     Q_ARG("QVariant", code),
                                     Q_ARG("QVariant", "0.5"))
        self.assertEqual(editor.property("classesMissing"), 0)
        self.assertTrue(apply_button.property("enabled"))

    def test_without_a_legend_the_column_is_not_promised(self) -> None:
        """Uma coluna vazia em toda linha seria a tela prometendo uma legenda
        que não tem."""
        from PySide6.QtCore import QObject

        editor = self._editor(self.FACTORS / "geology.tif")
        self.assertFalse(editor.property("hasLegend"))
        self.assertEqual(str(editor.property("legendSource")), "")
        shown = editor.findChild(QObject, "membershipLegendSource")
        self.assertFalse(shown.property("visible"))
        # E a tabela continua inteira: 4 códigos, pontuáveis.
        codes = editor.property("classCodes")
        if hasattr(codes, "toVariant"):
            codes = codes.toVariant()
        self.assertEqual(len(codes), 4)


class TheDecisionRunCarriesItsWeights(Shell):
    """A combinação linear ponderada não podia produzir mapa nenhum.

    Encontrado por quem usou o produto: normalizar, pedir o MCDA, e nenhum
    mapa aparecer. A causa são três coisas que se somam:

    1. `runDecision` montava o pedido com método, gamma, nome e critérios — e
       **sem pesos**. `decision.aggregate` recusa a combinação ponderada sem
       eles: "sem pesos não há combinação, só uma média que ninguém escolheu".
    2. `lastAhp` era declarado `({})` e **nunca atribuído**. A coluna de peso
       mostrava "—" para todo critério.
    3. A aplicação **nunca chamava** `decision.ahp_weights`.

    Nenhum gate pegava porque a storyboard `flow` dirige `runDecision` com
    `fuzzy_gamma`, que não usa peso. O caminho ponderado nunca tinha sido
    percorrido pela interface.
    """

    def _model(self):
        from PySide6.QtCore import QMetaObject, QObject, Qt

        QMetaObject.invokeMethod(self.window, "dispatch", Qt.DirectConnection,
                                 __import__("PySide6.QtCore", fromlist=["Q_ARG"])
                                 .Q_ARG("QVariant", "decisionModel"))
        dialog = self.window.findChild(QObject, "decisionModel")
        self.assertIsNotNone(dialog, "a tela de decisão não está no shell")
        return dialog

    CRITERIA = [
        {"name": "a", "path": "/tmp/a.tif", "unit": "mGal",
         "function": "linear_increasing"},
        {"name": "b", "path": "/tmp/b.tif", "unit": "m",
         "function": "linear_decreasing"},
    ]

    def test_the_request_carries_weights_when_the_method_needs_them(self) -> None:
        """O que sai da tela tem de ser o que o operador aceita. Sem pesos, a
        combinação ponderada é recusada e quem opera vê um job vermelho no
        lugar do mapa."""
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        dialog = self._model()
        dialog.setProperty("criteria", self.CRITERIA)
        dialog.setProperty("method", "weighted_linear_combination")

        value, undefined = QQmlExpression(
            qmlContext(dialog), dialog, "JSON.stringify(request())").evaluate()
        self.assertFalse(undefined, "a tela não expõe o pedido que envia")
        request = json.loads(value)

        self.assertEqual(request["method"], "weighted_linear_combination")
        self.assertIn("weights", request,
                      "o pedido sai sem pesos e o operador recusa")
        names = [w["name"] for w in request["weights"]]
        self.assertEqual(sorted(names), ["a", "b"],
                         "os pesos têm de nomear os critérios a que se ligam")
        total = sum(w["weight"] for w in request["weights"])
        self.assertAlmostEqual(total, 1.0, places=6,
                               msg="pesos que não somam 1 não são pesos")

    def test_gamma_carries_no_weights_because_it_uses_none(self) -> None:
        """Mandar peso para um operador que não os usa seria registrar na
        procedência uma escolha que não afetou o resultado."""
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        dialog = self._model()
        dialog.setProperty("criteria", self.CRITERIA)
        dialog.setProperty("method", "fuzzy_gamma")
        value, _ = QQmlExpression(
            qmlContext(dialog), dialog, "JSON.stringify(request())").evaluate()
        request = json.loads(value)
        self.assertEqual(request["method"], "fuzzy_gamma")
        self.assertNotIn("weights", request)
        self.assertIn("gamma", request)

    def test_equal_weights_are_the_declared_starting_point(self) -> None:
        """Dois critérios começam em 50 % cada. Um default silencioso seria
        uma escolha científica que ninguém fez; declarado e visível, é um
        ponto de partida que se corrige."""
        dialog = self._model()
        dialog.setProperty("criteria", self.CRITERIA)
        weights = dialog.property("weightByName")
        if hasattr(weights, "toVariant"):
            weights = weights.toVariant()
        self.assertEqual(sorted(weights), ["a", "b"])
        for name, value in weights.items():
            with self.subTest(criterion=name):
                self.assertAlmostEqual(float(value), 0.5, places=6)

    def test_run_is_refused_on_screen_rather_than_by_a_red_job(self) -> None:
        """Sem critério nenhum não há o que combinar, e o botão diz isso em
        vez de deixar o worker recusar depois do clique."""
        from PySide6.QtCore import QObject

        dialog = self._model()
        dialog.setProperty("criteria", [])
        button = dialog.findChild(QObject, "decisionRun")
        self.assertIsNotNone(button, "o botão de rodar não está nomeado")
        self.assertFalse(button.property("enabled"))

        dialog.setProperty("criteria", self.CRITERIA)
        self.assertTrue(button.property("enabled"))

    def test_the_shell_forwards_every_key_the_operator_declares(self) -> None:
        """`runDecision` é o funil entre a tela e o operador. Uma chave que a
        tela monta e ele deixa cair é uma decisão perdida em silêncio."""
        # A função inteira, não uma janela de tamanho fixo: a primeira
        # versão deste teste fatiava 700 caracteres e passou a falhar quando
        # um comentário empurrou `weights` para fora da fatia. Um teste que
        # depende de quanto se escreveu acima da linha não testa a linha.
        source = MAIN_QML.read_text(encoding="utf-8")
        start = source.index("function runDecision")
        body = source[start:source.index("\n    }", start)]
        for key in ("method", "gamma", "criteria", "weights"):
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', body,
                              f"runDecision não repassa {key!r}")


class AnchorsBelongToTheirLayer(Shell):
    """Trocar de camada não pode manter as âncoras da anterior.

    Encontrado por quem usou o produto, e é o pior tipo: **silencioso e
    cientificamente errado**. Abrir a pertinência numa camada de 2,25 a 2,86,
    trocar para um MDE de 120 a 1005, e o `x_max` continuava 100 — todo pixel
    saturava em 1. O mapa saía com faixa "1,0000 a 1,0000", média 1,0000, e
    nada na tela dizia por quê.

    A causa: as âncoras eram preenchidas `if (xMin.length === 0)`, então uma
    vez postas por uma camada elas sobreviviam a todas as seguintes.
    """

    FACTORS = _data_dir() / "conditioning_factors"

    def _editor(self):
        from PySide6.QtCore import QObject

        editor = self.window.findChild(QObject, "membershipEditor")
        self.assertIsNotNone(editor)
        return editor

    def _put(self, editor, path, low, high):
        editor.setProperty("criterion", {
            "name": Path(path).stem, "path": str(path), "unit": "m",
            "statistics": {"min": low, "max": high, "valid": 100,
                           "valid_fraction": 1.0,
                           "histogram": {"counts": [1] * 32,
                                         "edges": list(range(33))}},
        })

    def test_a_new_layer_gets_its_own_anchors(self) -> None:
        editor = self._editor()
        self._put(editor, "/tmp/density.tif", 2.2490, 2.8611)
        self.assertAlmostEqual(float(editor.property("xMax")), 2.8611, places=3)

        self._put(editor, "/tmp/dem.tif", 120.0, 1005.0)
        self.assertAlmostEqual(
            float(editor.property("xMax")), 1005.0, places=1,
            msg="o x_max da camada anterior sobreviveu; todo pixel do MDE "
                "satura em 1 e o mapa sai constante")
        self.assertAlmostEqual(float(editor.property("xMin")), 120.0, places=1)
        self.assertAlmostEqual(float(editor.property("centre")), 562.5,
                               places=1)

    def test_the_same_layer_keeps_what_was_typed(self) -> None:
        """Corrigir a curva não pode ser desfeito por uma descrição que chega
        depois: o pedido é read-only e a resposta vem pelo sinal."""
        editor = self._editor()
        self._put(editor, "/tmp/dem.tif", 120.0, 1005.0)
        editor.setProperty("xMax", "800")
        self._put(editor, "/tmp/dem.tif", 120.0, 1005.0)
        self.assertEqual(str(editor.property("xMax")), "800")

    def test_the_layer_picker_is_filled_when_the_screen_opens(self) -> None:
        """Uma chamada de função numa ligação de propriedade é avaliada uma
        vez, na carga do shell, quando ainda não há camada nenhuma — o combo
        ficava vazio para sempre."""
        source = MAIN_QML.read_text(encoding="utf-8")
        start = source.index("function openMembership")
        body = source[start:source.index("\n    }", start)]
        self.assertIn("membershipCandidates", body,
                      "o seletor de camada não é repovoado ao abrir")

    def test_the_candidates_exclude_what_cannot_take_a_membership(self) -> None:
        """Um mapa de fundo não tem valor sob o cursor, e normalizar um
        resultado seria pertinência de pertinência."""
        offered = self.controller.membershipCandidates()
        for row in offered:
            with self.subTest(layer=row.get("name")):
                self.assertNotIn(row.get("role"),
                                 ("basemap", "result", "membership"))
                self.assertTrue(row.get("path"))


class Language(Shell):
    """Both languages, on the real menu bar.

    The shell is shared, so this one puts the language back: leaving it in
    English would make every class that runs after it assert against labels
    it never chose.

    The catalogue being complete is a unit test; that the shell *uses* it is
    this one. A label that came from a literal in a `.qml` file does not change
    when the language does, and that is exactly what this catches.
    """

    def test_switching_relabels_the_menus(self) -> None:
        before = {item["token"]: item["label"] for item in self.menu_items()}
        self.controller.tr.setLanguage("en")
        try:
            after = {item["token"]: item["label"] for item in self.menu_items()}
            self.assertEqual(set(before), set(after),
                             "the language changed which entries exist")
            changed = [t for t in before if before[t] != after[t]]
            self.assertTrue(changed, "no label changed with the language")
        finally:
            self.controller.tr.setLanguage("pt")

    def test_no_label_is_empty_in_either_language(self) -> None:
        for language in ("pt", "en"):
            self.controller.tr.setLanguage(language)
            for item in self.menu_items():
                self.assertTrue(
                    str(item["label"]).strip(),
                    f"an entry has no label in {language}")
        self.controller.tr.setLanguage("pt")

    def test_a_reason_is_still_on_the_label_in_english(self) -> None:
        self.controller.tr.setLanguage("en")
        try:
            for item in self.menu_items():
                if not item["enabled"]:
                    self.assertIn(str(item["reason"]).strip(),
                                  str(item["label"]))
        finally:
            self.controller.tr.setLanguage("pt")


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class JobOutcomes(unittest.TestCase):
    """P-115. A failure belongs to the job that failed.

    The defect: one global status string, written by whatever happened last,
    reading `job failed` beside a job that had succeeded.
    """

    def setUp(self) -> None:
        from geopotential_app.models.job_model import JobListModel

        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        self.model = JobListModel()
        self.model.add("good", "decision.membership", inputs=["/data/a.tif"])
        self.model.add("bad", "grid.harmonize", inputs=["/data/b.tif"])
        self.model.set_state("good", "Succeeded", message="run committed")
        self.model.set_state(
            "bad", "Failed",
            message="the target CRS is geographic; a metric grid was asked for",
            error_code="CRS_GEOGRAPHIC", detail_ref="ab12cd",
        )

    def test_the_message_is_on_the_job_that_failed(self) -> None:
        self.assertIn("geographic", self.model.detail("bad")["message"])
        self.assertEqual(self.model.detail("bad")["errorCode"], "CRS_GEOGRAPHIC")

    def test_the_job_that_succeeded_carries_no_failure(self) -> None:
        good = self.model.detail("good")
        self.assertEqual(good["state"], "Succeeded")
        self.assertEqual(good["errorCode"], "")
        self.assertNotIn("failed", good["message"].lower())

    def test_a_finished_job_is_no_longer_active(self) -> None:
        self.assertFalse(self.model.detail("bad")["active"])
        self.assertFalse(self.model.detail("good")["active"])
        self.model.add("running", "decision.aggregate")
        self.model.update_progress("running", "combine", 0.4, "combining")
        self.assertTrue(self.model.detail("running")["active"])

    def test_the_controller_does_not_write_an_outcome_into_the_status(self) -> None:
        """The line the panel shows beside JOBS says what the *project* is
        doing. `_on_job_finished` must not write a job's outcome there."""
        import inspect

        from geopotential_app.controllers.app_controller import AppController

        source = inspect.getsource(AppController._on_job_finished)
        self.assertNotIn("_set_status", source,
                         "a job's outcome is being written into the global "
                         "status line again")


DATA = _data_dir()
RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"
VECTOR = DATA / "synthetic" / "blocks.shp"
TABLE = DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ThePreviewMap(unittest.TestCase):
    """E4 — the wizard draws the file, not just facts about it.

    Instantiated for real from the QML, because a component that parses is not
    a component that runs: `PreviewMap` bound `tool` instead of `toolMode` and
    parsed perfectly while failing to create.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtQml import QQmlComponent, QQmlEngine

        cls.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        _register_qml_types()
        qml = Path(__file__).resolve().parents[2] / "app" / "geopotential_app" / "qml"
        cls.engine = QQmlEngine()
        cls.engine.addImportPath(str(qml))
        cls.component = QQmlComponent(
            cls.engine, str(qml / "GeoPotential" / "PreviewMap.qml"))
        cls.errors = [e.toString() for e in cls.component.errors()]

    @classmethod
    def tearDownClass(cls) -> None:
        del cls.engine

    def _described(self, path: Path) -> dict:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
        from geopotential_worker.io.describe import describe
        return describe(path).as_dict()

    def _shown(self, path: Path):
        """Create the component, hand it a description, return the item."""
        self.assertEqual(self.errors, [], "PreviewMap did not parse")
        item = self.component.create()
        self.assertIsNotNone(item, "PreviewMap did not instantiate: "
                                   + "; ".join(e.toString()
                                               for e in self.component.errors()))
        item.setProperty("width", 320)
        item.setProperty("height", 240)
        item.setProperty("description", self._described(path))
        return item

    @unittest.skipUnless(RASTER.exists(), "the smoke raster is missing")
    def test_a_raster_is_drawn_from_the_file_itself(self) -> None:
        """ADR-MSP-004: a raster does not travel as a preview. The canvas
        reads the file through its own seam, at the scale the view needs."""
        item = self._shown(RASTER)
        self.assertTrue(item.property("drawn"))
        self.assertEqual(item.property("kind"), "raster")

    @unittest.skipUnless(VECTOR.exists(), "the synthetic vector is missing")
    def test_a_vector_is_drawn_as_a_silhouette(self) -> None:
        item = self._shown(VECTOR)
        self.assertTrue(item.property("drawn"),
                        "a shapefile still puts nothing on the screen")
        self.assertEqual(item.property("kind"), "vector")

    @unittest.skipUnless(TABLE.exists(), "the smoke table is missing")
    def test_a_table_is_drawn_as_points(self) -> None:
        item = self._shown(TABLE)
        self.assertTrue(item.property("drawn"))
        self.assertEqual(item.property("kind"), "table")

    def test_an_empty_description_draws_nothing_and_says_so(self) -> None:
        self.assertEqual(self.errors, [])
        item = self.component.create()
        self.assertIsNotNone(item)
        item.setProperty("description", {})
        self.assertFalse(item.property("drawn"))

    @unittest.skipUnless(VECTOR.exists(), "the synthetic vector is missing")
    def test_the_preview_map_reaches_no_operator(self) -> None:
        """The map is display. Nothing it holds may be submitted (ADR-MSP-004).

        Checked at the seam that would carry it: `PreviewMap.qml` names no
        controller, no submit and no store — in its **code**. The comments are
        stripped first, because the file says "no project, no store" in prose
        and a substring search would fail on the sentence promising the rule.
        """
        source = (Path(__file__).resolve().parents[2] / "app"
                  / "geopotential_app" / "qml" / "GeoPotential"
                  / "PreviewMap.qml").read_text(encoding="utf-8")
        code = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        for forbidden in ("controller", "submit", "importDataset", "store"):
            self.assertNotIn(forbidden, code,
                             f"the preview map reaches {forbidden}")


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TheWizardFitsOnScreen(Shell):
    """The Import button has to be reachable, whatever the file brings.

    A CSV brings a preview map, a histogram and an attribute table, and the
    column grew past the dialog: the content spilled over the background and
    Import went off the bottom of the screen — on a centred modal, which
    cannot be moved out of the way. So the decision is the dialog's **footer**
    and the content scrolls.
    """

    def _wizard(self):
        wizard = self.window.findChild(QObject, "importWizard")
        self.assertIsNotNone(wizard, "the Import Wizard did not load")
        return wizard

    def test_the_dialog_never_exceeds_the_window(self) -> None:
        wizard = self._wizard()
        self.assertLessEqual(
            float(wizard.property("height")),
            float(self.window.property("height")),
            "the dialog is taller than the window it is centred in")

    def test_the_import_button_is_in_the_footer_not_the_content(self) -> None:
        """In the content it can be scrolled away or pushed off; in the footer
        it is always at the bottom of the dialog, whatever is above it."""
        wizard = self._wizard()
        button = wizard.findChild(QObject, "importButton")
        self.assertIsNotNone(button, "the Import button is not in the wizard")

        footer = wizard.property("footer")
        self.assertIsNotNone(footer, "the wizard has no footer")
        ancestors = []
        node = button.parent()
        while node is not None:
            ancestors.append(node)
            node = node.parent()
        self.assertIn(footer, ancestors,
                      "the Import button is not inside the dialog's footer")

    def test_prefilling_a_declaration_does_not_ask_again(self) -> None:
        """The wizard copies the file's own CRS and unit into the declaration
        fields so the person corrects rather than types. Those are the same
        fields a person types into, so the prefill fired the re-check that had
        just produced it — and a raster carries a CRS, so opening the wizard on
        one read the file twice and showed every job in the panel twice.

        Checked at the guard, because the loop is between two signals and no
        single value shows it.
        """
        source = (Path(__file__).resolve().parents[2] / "app"
                  / "geopotential_app" / "qml" / "GeoPotential"
                  / "ImportWizard.qml").read_text(encoding="utf-8")
        handlers = [line for line in source.splitlines()
                    if line.strip().startswith("onDeclared")
                    and "recheck.restart()" in line]
        self.assertGreaterEqual(len(handlers), 6,
                                "the re-check handlers moved or were renamed")
        for line in handlers:
            self.assertIn("!root.prefilling", line,
                          f"this handler re-checks on a prefill: {line.strip()}")
        described = source.split("function onDatasetDescribed", 1)[1]
        described = described.split("function onDatasetValidated", 1)[0]
        self.assertIn("root.prefilling = true", described)
        self.assertIn("root.prefilling = false", described)

    def test_the_content_scrolls(self) -> None:
        """Whatever a file adds above the decision has somewhere to go."""
        wizard = self._wizard()
        content = wizard.property("contentItem")
        self.assertIsNotNone(content)
        # A QML-declared ScrollView reports a generated class name like
        # `ScrollView_QMLTYPE_97`, so the family is what identifies it.
        self.assertIn(
            "ScrollView", content.metaObject().className(),
            f"the wizard's content is a {content.metaObject().className()}, "
            f"which cannot scroll")


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class HarmonisationIsAChoice(Shell):
    """An analysis is a subset of the catalogue, not all of it.

    A project keeps its data across sessions, so by the time someone
    harmonises, the catalogue holds everything ever imported. Taking all of it
    silently is how a run ends up with layers nobody meant to include — and
    with two CRSs whose areas do not overlap, whose intersection is empty.
    """

    def _dialog(self):
        dialog = self.window.findChild(QObject, "harmonizeDialog")
        self.assertIsNotNone(dialog, "the harmonize dialog did not load")
        return dialog

    def _offer(self, dialog, rows) -> None:
        dialog.setProperty("datasets", rows)

    @staticmethod
    def _list(value):
        """A JavaScript array arrives as a QJSValue; only `toVariant` gives
        the plain list — the same shape the menu audit needed."""
        return list(value.toVariant() if hasattr(value, "toVariant") else value)

    ROWS = [
        {"id": "d1", "name": "a.tif", "path": "/tmp/a.tif", "unit": "mGal",
         "crs": "EPSG:26912", "pixelX": 10.0, "pixelY": 10.0, "missing": False},
        {"id": "d2", "name": "b.tif", "path": "/tmp/b.tif", "unit": "mGal",
         "crs": "EPSG:26912", "pixelX": 40.0, "pixelY": 40.0, "missing": False},
        {"id": "d3", "name": "gone.tif", "path": "/tmp/gone.tif", "unit": "",
         "crs": "EPSG:5186", "pixelX": 10.0, "pixelY": 10.0, "missing": True},
    ]

    def test_everything_present_is_chosen_to_begin_with(self) -> None:
        dialog = self._dialog()
        self._offer(dialog, self.ROWS)
        self.assertEqual(dialog.property("usable"), 2,
                         "a missing file must not be counted as usable")

    def test_unchecking_a_layer_takes_it_out_of_the_run(self) -> None:
        from PySide6.QtCore import Q_ARG, QMetaObject, Qt

        dialog = self._dialog()
        self._offer(dialog, self.ROWS)
        QMetaObject.invokeMethod(dialog, "choose", Qt.DirectConnection,
                                 Q_ARG("QVariant", "d2"),
                                 Q_ARG("QVariant", False))
        self.assertEqual(dialog.property("usable"), 1)

        import json

        from PySide6.QtQml import QQmlExpression, qmlContext
        value, undefined = QQmlExpression(
            qmlContext(dialog), dialog,
            "JSON.stringify(layerRequests())").evaluate()
        self.assertFalse(undefined)
        names = [layer["name"] for layer in json.loads(value)]
        self.assertEqual(names, ["a.tif"],
                         "an unchecked layer still reached the operator")

    def test_a_missing_file_never_reaches_the_operator(self) -> None:
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        dialog = self._dialog()
        self._offer(dialog, self.ROWS)
        value, _ = QQmlExpression(
            qmlContext(dialog), dialog,
            "JSON.stringify(layerRequests())").evaluate()
        paths = [layer["path"] for layer in json.loads(value)]
        self.assertNotIn("/tmp/gone.tif", paths)

    def test_mixed_crs_is_reported_before_the_run(self) -> None:
        """Two CRSs is legal and is what the step is for — and it is also how
        an intersection comes out empty. Said before the click."""
        dialog = self._dialog()
        rows = [dict(row) for row in self.ROWS]
        rows[2]["missing"] = False          # the EPSG:5186 layer is present
        self._offer(dialog, rows)
        in_use = self._list(dialog.property("crsInUse"))
        self.assertEqual(sorted(in_use), ["EPSG:26912", "EPSG:5186"])

    def test_one_crs_raises_no_warning(self) -> None:
        dialog = self._dialog()
        self._offer(dialog, self.ROWS[:2])
        self.assertEqual(self._list(dialog.property("crsInUse")),
                         ["EPSG:26912"])


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SparseDataReachesAGrid(Shell):
    """M5.6 E5 — a CSV is offered a way onto the grid, and the way is named.

    Harmonisation reprojects a raster. Before M5.6 a table could be imported,
    checked and drawn, and then had nowhere to go: it was filtered out of the
    only screen that builds an analysis grid, with nothing saying why.
    """

    TABLE = _data_dir() / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"

    def _dialog(self):
        dialog = self.window.findChild(QObject, "griddingDialog")
        self.assertIsNotNone(dialog, "the gridding dialog did not load")
        return dialog

    def test_a_table_is_offered_interpolation_and_distance(self) -> None:
        """And rasterizing is not offered: a table of samples has no geometry
        to burn, so the method would be meaningless for it."""
        dialog = self._dialog()
        dialog.setProperty("datasets", [{
            "id": "t1", "name": "survey.csv", "path": str(self.TABLE),
            "kind": "table", "crs": "EPSG:26912", "unit": "mGal",
            "fields": ["easting", "northing", "gCBGA"], "xField": "easting",
            "yField": "northing", "valueField": "gCBGA", "extent": None,
            "methods": ["grid.idw", "grid.euclidean_distance"],
            "missing": False,
        }])
        dialog.setProperty("selected", 0)
        self.assertEqual(dialog.property("method"), "grid.idw")
        self.assertTrue(dialog.property("interpolates"))

    def test_only_idw_says_it_estimates(self) -> None:
        """The line between measuring and estimating is the one thing this
        screen must not blur."""
        dialog = self._dialog()
        dialog.setProperty("method", "grid.euclidean_distance")
        self.assertFalse(dialog.property("interpolates"))
        dialog.setProperty("method", "grid.rasterize")
        self.assertFalse(dialog.property("interpolates"))
        dialog.setProperty("method", "grid.idw")
        self.assertTrue(dialog.property("interpolates"))

    def test_idw_without_a_radius_cannot_run(self) -> None:
        dialog = self._dialog()
        dialog.setProperty("datasets", [{
            "id": "t1", "name": "s.csv", "path": str(self.TABLE),
            "kind": "table", "crs": "EPSG:26912", "unit": "mGal",
            "fields": [], "xField": "easting", "yField": "northing",
            "valueField": "gCBGA", "extent": None,
            "methods": ["grid.idw"], "missing": False,
        }])
        dialog.setProperty("selected", 0)
        dialog.setProperty("method", "grid.idw")
        dialog.setProperty("targetCrs", "EPSG:26912")
        dialog.setProperty("pixelSize", "100")
        dialog.setProperty("radius", "")
        self.assertFalse(dialog.property("ready"),
                         "IDW was ready to run with no search radius")
        dialog.setProperty("radius", "500")
        self.assertTrue(dialog.property("ready"))

    def test_a_chosen_area_has_to_be_four_numbers(self) -> None:
        dialog = self._dialog()
        dialog.setProperty("wholeExtent", False)
        dialog.setProperty("boundsText", "1, 2, 3")
        self.assertFalse(dialog.property("ready"))
        dialog.setProperty("boundsText", "1, 2, 3, 4")
        dialog.setProperty("wholeExtent", True)

    def test_the_detail_levels_divide_the_sample_spacing(self) -> None:
        """A pixel equal to the spacing gives one cell per sample and a field
        with no gradient in it — which is what "it does not catch the nuances"
        looks like. The levels divide the spacing; they never multiply it."""
        dialog = self._dialog()
        details = dialog.property("details")
        details = details.toVariant() if hasattr(details, "toVariant") else details
        divisors = [int(d["divisor"]) for d in details]
        self.assertEqual(divisors, sorted(divisors),
                         "the levels are not ordered coarse to fine")
        self.assertGreaterEqual(min(divisors), 1,
                                "a level made the pixel coarser than the "
                                "spacing, which recovers nothing")
        self.assertEqual(dialog.property("detail"), "balanced",
                         "the default is not the recommended level")

    def test_every_detail_level_has_a_label_in_both_languages(self) -> None:
        from geopotential_app.i18n import table

        for language in ("pt", "en"):
            entries = table(language)
            for key in ("coarse", "balanced", "fine"):
                self.assertIn(f"gridding.detail.{key}", entries)

    def test_distance_on_a_table_is_explained_as_coverage(self) -> None:
        """The "features" of a table are its own samples, so the distance
        field measures the survey and not the ground. Choosing it is
        legitimate and is almost never what someone wants from a criterion."""
        from geopotential_app.i18n import table

        for language in ("pt", "en"):
            entries = table(language)
            self.assertIn("gridding.distance.onSamples", entries)
            self.assertIn("gridding.distance.onFeatures", entries)
        # And the method's own name says which distance it is.
        self.assertIn("uclidean",
                      table("en")["gridding.method.grid.euclidean_distance"])
        self.assertIn("uclidian" if False else "uclidiana",
                      table("pt")["gridding.method.grid.euclidean_distance"])

    def test_the_three_operators_are_routed_and_named(self) -> None:
        """Every method the dialog can choose must be one the worker has, and
        every one must have a label in both languages."""
        from geopotential_app.i18n import table

        for language in ("pt", "en"):
            entries = table(language)
            for name in ("grid.idw", "grid.euclidean_distance",
                         "grid.rasterize"):
                key = f"gridding.method.{name}"
                self.assertIn(key, entries, f"{key} missing in {language}")
                self.assertTrue(entries[key].strip())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class AContainerFileAsksWhichLayer(unittest.TestCase):
    """A26 — a GeoPackage holding several layers requires the choice.

    Reading the first layer and importing it under the file's name records a
    dataset nobody chose, and the choice would never appear in the provenance
    because nothing ever asked.
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import geopandas as gpd
            import shapely
        except ImportError:                          # pragma: no cover
            raise unittest.SkipTest("geopandas is not installed")

        from PySide6.QtQml import QQmlComponent, QQmlEngine

        cls.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        _register_qml_types()
        cls.workdir = Path(tempfile.mkdtemp(prefix="geopotential-gpkg-"))
        os.environ["GEOPOTENTIAL_PREFERENCES"] = str(cls.workdir / "prefs.ini")

        # Two layers in one file, written here rather than added to ../data:
        # the fixture exists for this assertion and nothing else.
        cls.path = cls.workdir / "two_layers.gpkg"
        for name, x in (("faults", 0.0), ("contacts", 10.0)):
            frame = gpd.GeoDataFrame(
                {"id": [1, 2]},
                geometry=[shapely.LineString([(x, 0), (x + 1, 1)]),
                          shapely.LineString([(x, 1), (x + 1, 2)])],
                crs="EPSG:31982",
            )
            frame.to_file(cls.path, layer=name, driver="GPKG")

        cls.controller = AppController()
        cls.controller.createProject(str(cls.workdir / "P.gpot"), "P")
        qml = Path(__file__).resolve().parents[2] / "app" / "geopotential_app" / "qml"
        cls.engine = QQmlEngine()
        cls.engine.addImportPath(str(qml))
        cls.component = QQmlComponent(
            cls.engine, str(qml / "GeoPotential" / "ImportWizard.qml"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.controller.shutdown()
        del cls.engine

    def _wizard(self):
        self.assertEqual([e.toString() for e in self.component.errors()], [])
        wizard = self.component.createWithInitialProperties(
            {"controller": self.controller})
        self.assertIsNotNone(wizard, "the Import Wizard did not instantiate")
        return wizard

    def _described(self) -> dict:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
        from geopotential_worker.io.describe import describe
        return describe(self.path).as_dict()

    def test_the_file_reports_both_of_its_layers(self) -> None:
        self.assertEqual(sorted(self._described()["layers"]),
                         ["contacts", "faults"])

    def test_no_layer_is_chosen_by_default(self) -> None:
        wizard = self._wizard()
        wizard.setProperty("description", self._described())
        self.assertEqual(wizard.property("declaredLayer"), "")
        self.assertTrue(wizard.property("layerUndecided"),
                        "a two-layer file was ready to import with no choice")

    def test_choosing_a_layer_unblocks_it(self) -> None:
        wizard = self._wizard()
        wizard.setProperty("description", self._described())
        wizard.setProperty("declaredLayer", "contacts")
        self.assertFalse(wizard.property("layerUndecided"))

    def test_the_choice_travels_as_a_declaration(self) -> None:
        """It has to reach the worker, or the control is decoration: the
        declaration is what `describe` and `validate` are re-run with, and
        what the import records as the operator's assertion."""
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        wizard = self._wizard()
        wizard.setProperty("description", self._described())
        wizard.setProperty("declaredLayer", "faults")
        # `evaluate()` answers (value, isUndefined); the declarations are read
        # as the wizard itself builds them, not as a second implementation.
        value, undefined = QQmlExpression(
            qmlContext(wizard), wizard,
            "JSON.stringify(declarations())").evaluate()
        self.assertFalse(undefined, "declarations() returned nothing")
        self.assertEqual(json.loads(value).get("layer"), "faults")

    def test_a_single_layer_file_asks_nothing(self) -> None:
        """The question is only worth asking when there is a choice."""
        wizard = self._wizard()
        wizard.setProperty("description", {"kind": "vector", "layers": ["one"]})
        self.assertFalse(wizard.property("layerUndecided"))


if __name__ == "__main__":
    unittest.main()
