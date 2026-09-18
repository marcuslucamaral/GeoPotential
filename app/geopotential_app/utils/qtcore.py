"""QtCore-only binding shim.

Imported by `viewmodels/`, `models/`, `controllers/` and `ipc/`. It exposes
QtCore and nothing else, deliberately: the moment a view model can name a
QColor it is making painting decisions and the separation is gone.

One shim, imported by everything. Thirteen copies of a try/except drift, and
the one that drifted is what raises on a PySide6-only machine.
"""
from __future__ import annotations

from PySide6.QtCore import (  # noqa: F401
    QAbstractListModel,
    QAbstractTableModel,
    QByteArray,
    QModelIndex,
    QObject,
    QProcess,
    QProcessEnvironment,
    QSettings,
    QTimer,
    QUrl,
    Qt,
    Property,
    Signal,
    Slot,
)

__all__ = [
    "QAbstractListModel",
    "QAbstractTableModel",
    "QByteArray",
    "QModelIndex",
    "QObject",
    "QProcess",
    "QProcessEnvironment",
    "QSettings",
    "QTimer",
    "QUrl",
    "Qt",
    "Property",
    "Signal",
    "Slot",
]
