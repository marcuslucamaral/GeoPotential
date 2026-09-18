"""Where the application's own resources are.

The only module that knows. It branches on `sys.frozen` once, so nothing else
has to. Never locate a resource by counting parents: `Path(__file__).parents[4]`
is meaningless in a bundle and breaks the moment a module moves.
"""
from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Directory the QML shell and other data files sit under."""
    if is_frozen():
        return Path(sys._MEIPASS) / "geopotential_app"  # type: ignore[attr-defined]
    return PACKAGE_ROOT


def qml_dir() -> Path:
    return resource_root() / "qml"


def worker_package_root() -> Path:
    """Directory to put on the worker child's PYTHONPATH.

    In a checkout the worker lives beside the app, in `worker/`. In a bundle it
    is collected next to the app package.
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return PACKAGE_ROOT.parent.parent / "worker"


def repository_root() -> Path:
    """Where `data/` is: the workspace in a checkout, the bundle when frozen.

    Only test, self-test and the default-input path use this. Application code
    never reaches for a directory outside the project it has open.

    Frozen, the fixtures are collected at the bundle root, so the shipped
    binary can run its own gate on a machine with no checkout — which is the
    only thing that makes `--self-test` evidence rather than decoration.
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return PACKAGE_ROOT.parent.parent.parent
