#!/usr/bin/env python3
"""Executable layer contract for geopotencial_msp.

The dependency rule is not prose. This scans imports and fails, and it is
negative-tested: `--self-check` injects one violation of each class and asserts
that every one is caught. A gate that has only ever passed is not a gate.

    tools/architecture_check.py              check the tree
    tools/architecture_check.py --self-check prove the checks can fail

Exit codes:  0 PASS   1 FAIL
"""
from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "geopotential_app"
WORKER = ROOT / "worker" / "geopotential_worker"

QT_MODULES = ("PySide6", "PyQt5", "PyQt6", "PySide2", "shiboken6")
QTGUI_MODULES = ("PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtQuick", "PySide6.QtQml")
IO_MODULES = ("rasterio", "geopandas", "fiona", "osgeo", "pandas")
PLOTTING = ("matplotlib", "plotly", "seaborn", "bokeh")
# ADR-MSP-006 narrowed P-07: no server, no listening port, no WebView, no web
# framework. A basemap's tiles are fetched by one named HTTPS client, and only
# when a source is chosen. `requests` and `httpx` stay out — the client uses the
# standard library and is the only module allowed to speak network at all.
WEB = ("flask", "fastapi", "uvicorn", "aiohttp", "tornado", "requests", "httpx",
       "starlette", "django")

# Vocabulary that belongs to another project. AmoraSeismic is an engineering
# reference; its domain has no meaning here and must not leak into names.
FORBIDDEN_WORDS = (
    "TraceMatrix", "SEG-Y", "SEGY", "segy", "gather", "NMO", "nmo",
    "migration", "velocity analysis",
)

# `self_test.py` reaches into the worker package on purpose, to exercise the
# domain guards through the same modules the worker uses. It is a test driver,
# not application code, and the exemption is named rather than implied.
WORKER_IMPORT_EXEMPT = {APP / "self_test.py"}


class Violation:
    def __init__(self, path: Path, line: int, rule: str, detail: str) -> None:
        self.path, self.line, self.rule, self.detail = path, line, rule, detail

    def __str__(self) -> str:
        try:
            where = self.path.relative_to(ROOT)
        except ValueError:
            where = self.path
        return f"{where}:{self.line}  [{self.rule}]  {self.detail}"


def imports_of(path: Path) -> list[tuple[int, str]]:
    """Every module name imported by a file, with its line number."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise SystemExit(f"{path}: cannot parse: {exc}")
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
    return found


def matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def check_tree(app: Path, worker: Path) -> list[Violation]:
    violations: list[Violation] = []

    # ---- the worker is Qt-free ------------------------------------------
    # The moment a Signal or a QThread lives under worker/, the arithmetic can
    # no longer be exercised from a plain `python3 -c` and every numerical gate
    # needs a display.
    for path in python_files(worker):
        for line, module in imports_of(path):
            if matches(module, QT_MODULES):
                violations.append(Violation(
                    path, line, "worker-no-qt",
                    f"the scientific worker imports {module}; it runs in its own "
                    f"process and must never need a display"))
            if matches(module, PLOTTING):
                violations.append(Violation(
                    path, line, "worker-no-plotting",
                    f"{module} in the worker: a function that computes a raster "
                    f"and also renders it cannot be tested for what it computes"))
            if matches(module, WEB):
                violations.append(Violation(
                    path, line, "no-web",
                    f"{module}: the MSP forbids HTTP, localhost and any web "
                    f"server in the product"))

    # ---- the worker's domain layer is I/O-free --------------------------
    for path in python_files(worker / "domain") + python_files(worker / "decision"):
        for line, module in imports_of(path):
            if matches(module, IO_MODULES):
                violations.append(Violation(
                    path, line, "domain-no-io",
                    f"{module} under domain/ or decision/: these layers are "
                    f"numpy and pyproj only, so a numerical gate needs no files"))

    # ---- the app does not import the worker package ---------------------
    # The only thing crossing the boundary is the protocol. An import here
    # reintroduces the coupling that process separation exists to remove, and
    # "kill the worker and restart it" stops meaning anything.
    for path in python_files(app):
        if path in WORKER_IMPORT_EXEMPT:
            continue
        for line, module in imports_of(path):
            if matches(module, ("geopotential_worker",)):
                violations.append(Violation(
                    path, line, "app-no-worker-import",
                    "the application imports the worker package; the boundary "
                    "is the protocol, and nothing else"))
            if matches(module, WEB):
                violations.append(Violation(
                    path, line, "no-web",
                    f"{module}: the MSP forbids HTTP, localhost and any web "
                    f"server in the product"))
            if matches(module, PLOTTING):
                violations.append(Violation(
                    path, line, "app-no-plotting",
                    f"{module}: the canvas is native; plotting libraries have no "
                    f"place in the application layer"))

    # ---- QtCore-only layers ---------------------------------------------
    # viewmodels, models, controllers, ipc and project publish state; they do
    # not paint. The moment one can name a QColor it is making a painting
    # decision and the separation is gone.
    for layer in ("viewmodels", "models", "controllers", "ipc", "project"):
        for path in python_files(app / layer):
            for line, module in imports_of(path):
                if matches(module, QTGUI_MODULES):
                    violations.append(Violation(
                        path, line, f"{layer}-qtcore-only",
                        f"{module} under {layer}/: use utils/qtcore.py; a layer "
                        f"that can name a QColor is choosing a style"))
                if module.endswith("utils.qt") or module.endswith("utils import qt"):
                    violations.append(Violation(
                        path, line, f"{layer}-qtcore-only",
                        f"{layer}/ must import utils/qtcore.py, not utils/qt.py"))

    # ---- the display-only geodesy seam ----------------------------------
    # ADR-MSP-003. `geo/coordinates.py` transforms coordinates for the screen.
    # The layers that record things may not reach it: a transform on the way
    # to a manifest would be a reprojection nobody asked for and nobody
    # recorded.
    for layer in ("project", "commands"):
        for path in python_files(app / layer):
            for line, module in imports_of(path):
                if "geo.coordinates" in module or module.endswith("geo"):
                    violations.append(Violation(
                        path, line, "geo-display-only",
                        f"{module} under {layer}/: the display transform is "
                        f"display only (ADR-MSP-003). Reprojecting data is a "
                        f"run in the worker, with a manifest."))

    # `geo/` itself reads and writes nothing.
    for path in python_files(app / "geo"):
        for line, module in imports_of(path):
            if matches(module, IO_MODULES):
                violations.append(Violation(
                    path, line, "geo-no-io",
                    f"{module} under geo/: the display transform reads no "
                    f"file and writes none."))

    # ---- the Project Store is Qt-free -----------------------------------
    for path in python_files(app / "project"):
        for line, module in imports_of(path):
            if matches(module, QT_MODULES):
                violations.append(Violation(
                    path, line, "store-no-qt",
                    f"{module} in the Project Store; persistence is exercised "
                    f"without a Qt event loop"))

    # ---- the render layer does not read files ---------------------------
    # No exception any more. M1 left one named seam in `map_item.py` so the
    # slice could end at a picture; M4 replaced it with `raster/`, which is
    # allowed to read and whose job is exactly that.
    for path in python_files(app / "render"):
        for line, module in imports_of(path):
            if matches(module, IO_MODULES):
                violations.append(Violation(
                    path, line, "render-no-io",
                    f"{module} under render/: rendering is numpy in, pixels out, "
                    f"so it can be gated without a window. Reading belongs in "
                    f"raster/."))

    # ---- the raster layer reads, and does not paint ---------------------
    # It may open files; it may not know what a colour is. Keeping the split
    # is what lets a LOD decision be tested without a window and a colormap be
    # tested without a file.
    for path in python_files(app / "raster"):
        for line, module in imports_of(path):
            if matches(module, QTGUI_MODULES):
                violations.append(Violation(
                    path, line, "raster-no-painting",
                    f"{module} under raster/: this layer reads pixels, it does "
                    f"not draw them"))
            if matches(module, PLOTTING):
                violations.append(Violation(
                    path, line, "raster-no-painting",
                    f"{module} under raster/: rendering lives in render/"))

    # ---- the protocol is one contract, mirrored byte for byte -----------
    app_protocol = app / "ipc" / "protocol.py"
    worker_protocol = worker / "protocol.py"
    if app_protocol.exists() and worker_protocol.exists():
        if app_protocol.read_bytes() != worker_protocol.read_bytes():
            violations.append(Violation(
                app_protocol, 1, "protocol-mirrors",
                "app/ipc/protocol.py and worker/protocol.py have drifted. They "
                "are one contract; copy the worker's over the app's and run the "
                "contract suite"))

    # ---- no seismic vocabulary ------------------------------------------
    for path in python_files(app) + python_files(worker) + sorted(
        (app / "qml").rglob("*.qml")
    ):
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN_WORDS:
            for match in re.finditer(rf"\b{re.escape(word)}\b", text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(Violation(
                    path, line, "no-seismic-vocabulary",
                    f"{word!r} belongs to AmoraSeismic, which is an engineering "
                    f"reference and never a source of domain vocabulary"))

    # ---- one version per package ----------------------------------------
    # The *software* version, and only that. `PROTOCOL_VERSION` and
    # `SCHEMA_VERSION` are contract versions: they belong to the contract they
    # version, they change on a different schedule, and section 29 governs
    # them. The pattern anchors on a bare `VERSION`/`PEP440_VERSION` at the
    # start of a line, which is how `_version.py` declares it.
    software_version = re.compile(r'^(?:PEP440_)?VERSION\s*=\s*["\']\d+\.\d+', re.M)
    for package, version_file in ((app, app / "_version.py"),
                                  (worker, worker / "_version.py")):
        for path in python_files(package):
            if path == version_file:
                continue
            text = path.read_text(encoding="utf-8")
            for match in software_version.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(Violation(
                    path, line, "one-version-source",
                    "a version literal outside _version.py; the software "
                    "version lives in one place"))

    return violations


def self_check() -> int:
    """Inject one violation of each class and assert every one is caught."""
    import shutil

    classes = {
        "worker-no-qt": (
            "worker/geopotential_worker/qc/probe.py",
            "from PySide6.QtCore import QObject\n",
        ),
        "domain-no-io": (
            "worker/geopotential_worker/domain/probe.py",
            "import rasterio\n",
        ),
        "app-no-worker-import": (
            "app/geopotential_app/controllers/probe.py",
            "import geopotential_worker\n",
        ),
        "viewmodels-qtcore-only": (
            "app/geopotential_app/viewmodels/probe.py",
            "from PySide6.QtGui import QColor\n",
        ),
        "store-no-qt": (
            "app/geopotential_app/project/probe.py",
            "import PySide6\n",
        ),
        "render-no-io": (
            "app/geopotential_app/render/probe.py",
            "import geopandas\n",
        ),
        "raster-no-painting": (
            "app/geopotential_app/raster/probe.py",
            "from PySide6.QtGui import QImage\n",
        ),
        "no-web": (
            "app/geopotential_app/ipc/probe.py",
            "import fastapi\n",
        ),
        "no-seismic-vocabulary": (
            "worker/geopotential_worker/grid/probe.py",
            "# a TraceMatrix would go here\n",
        ),
        "one-version-source": (
            "app/geopotential_app/models/probe.py",
            'VERSION = "9.9.99"\n',
        ),
        "protocol-mirrors": ("app/geopotential_app/ipc/protocol.py", None),
    }

    failures: list[str] = []
    for rule, (relative, content) in classes.items():
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "tree"
            shutil.copytree(
                ROOT, sandbox,
                ignore=shutil.ignore_patterns("__pycache__", ".git", "logs", "*.gpot"),
            )
            target = sandbox / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                target.write_text(
                    target.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8"
                )
            else:
                target.write_text(content, encoding="utf-8")
            caught = check_tree(
                sandbox / "app" / "geopotential_app",
                sandbox / "worker" / "geopotential_worker",
            )
            if not any(v.rule == rule for v in caught):
                failures.append(rule)

    for rule in classes:
        status = "FAIL" if rule in failures else "PASS"
        print(f"{status}  negative test: {rule}")
    if failures:
        print(f"\n{len(failures)} check(s) cannot fail and are therefore not gates")
        return 1
    print(f"\n{len(classes)}/{len(classes)} checks proved able to fail")
    return 0


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    violations = check_tree(APP, WORKER)
    if violations:
        print(f"architecture: FAIL — {len(violations)} violation(s)\n")
        for v in violations:
            print(f"  {v}")
        return 1
    files = len(python_files(APP)) + len(python_files(WORKER))
    print(f"architecture: PASS — {files} modules, every layer contract held")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
