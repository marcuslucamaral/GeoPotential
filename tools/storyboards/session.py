"""One running application, driven by a storyboard.

Everything a step needs to reach the real shell: the controller, the canvas,
the wizard, the worker, and helpers that wait for work to finish rather than
sleeping and hoping.

Nothing here is a stub. A storyboard that photographed a mock would prove that
the mock renders.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMetaObject, QObject, Qt

from geopotential_app.app import _build_engine, _register_qml_types
from geopotential_app.controllers.app_controller import AppController
from geopotential_app.utils.qt import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
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
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
class Session:
    """The running application, plus the handles a storyboard step needs."""

    def __init__(self, size: tuple[int, int] = (1440, 880)) -> None:
        self.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        _register_qml_types()

        self.workdir = Path(tempfile.mkdtemp(prefix="gp-storyboard-"))
        # Preferences go to a throwaway file. A storyboard that wrote the
        # developer's own language would make the next run start somewhere
        # else — which it did, and the sequence stopped being reproducible.
        os.environ["GEOPOTENTIAL_PREFERENCES"] = str(self.workdir / "prefs.ini")
        # And the recents. A storyboard that wrote into the real list would
        # fill a person's Project Hub with throwaway projects in /tmp — which
        # it did, twelve of them.
        os.environ["XDG_STATE_HOME"] = str(self.workdir / "state")
        self.controller = AppController()
        self.controller.createProject(str(self.workdir / "Utah FORGE.gpot"),
                                      "Utah FORGE")

        self.engine = _build_engine(self.controller)
        self.window = self.engine.rootObjects()[0]
        self.window.setWidth(size[0])
        self.window.setHeight(size[1])

        self.controller.startWorker()
        self.controller.supervisor.wait_for_ready(20000)

        # By name, not by type. There is more than one MapItem in the shell
        # since the Import Wizard gained a preview map, and a search by class
        # returns whichever the object tree reaches first — which silently
        # pointed every storyboard at an empty canvas.
        self.canvas = self.window.findChild(QObject, "mapCanvas")
        if self.canvas is None:                      # pragma: no cover
            raise RuntimeError(
                "the shell has no MapItem named 'mapCanvas'; a storyboard "
                "driving an unnamed canvas proves nothing about the map")
        self.wizard = self.window.findChild(QObject, "importWizard")
        self.hub = self.window.findChild(QObject, "projectHub")

    # ---- finding things -------------------------------------------------

    def _find(self, class_prefix: str) -> QObject | None:
        for child in self.window.findChildren(QObject):
            if child.metaObject().className().startswith(class_prefix):
                return child
        return None

    def invoke(self, target: QObject, method: str) -> None:
        """Call a QML-declared function, the way a click would."""
        QMetaObject.invokeMethod(target, method, Qt.DirectConnection)

    # ---- waiting --------------------------------------------------------

    def settle(self, ms: int = 600) -> None:
        """Let the event loop repaint. Not a sleep: it pumps the worker too."""
        steps = max(1, ms // 20)
        for _ in range(steps):
            self.controller.supervisor.pump(20)
            self.app.processEvents()

    def wait_for(self, predicate, timeout_ms: int = 20000) -> bool:  # noqa: ANN001
        for _ in range(max(1, timeout_ms // 20)):
            self.controller.supervisor.pump(20)
            self.app.processEvents()
            if predicate():
                return True
        return False

    def run_job(self, operator: str, params: dict, inputs: list[str]) -> str:
        """Submit and wait. Returns the final state."""
        done: list[str] = []
        self.controller._job_controller.jobFinished.connect(
            lambda _j, s: done.append(s)
        )
        job = self.controller.submit(operator, params, inputs)
        if not job:
            return "refused"
        self.wait_for(lambda: bool(done))
        return done[-1] if done else "never finished"

    def describe(self, path: Path, declared: dict | None = None) -> dict:
        seen: list[dict] = []
        self.controller.datasetDescribed.connect(seen.append)
        self.controller.describeDataset(str(path), declared or {})
        self.wait_for(lambda: bool(seen))
        self.controller.datasetDescribed.disconnect(seen.append)
        return seen[-1] if seen else {}

    def validate(self, path: Path, declared: dict | None = None) -> dict:
        seen: list[dict] = []
        self.controller.datasetValidated.connect(seen.append)
        self.controller.validateDataset(str(path), declared or {})
        self.wait_for(lambda: bool(seen))
        self.controller.datasetValidated.disconnect(seen.append)
        return seen[-1] if seen else {}

    # ---- capturing ------------------------------------------------------

    def grab(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.window.grabWindow().save(str(path))
        return path

    def close(self) -> None:
        self.controller.shutdown()
        del self.engine
        shutil.rmtree(self.workdir, ignore_errors=True)

    # ---- convenience ----------------------------------------------------

    @property
    def canvas_state(self) -> dict[str, Any]:
        return self.canvas.property("displayState") or {}
