"""Full Qt binding shim, for `render/` and the entry point.

QtCore, QtGui, QtQml and QtQuick. Anything under `app/` that is not a view,
a renderer or the entry point uses `qtcore.py` instead.
"""
from __future__ import annotations

from PySide6.QtCore import (  # noqa: F401
    Q_ARG,
    QMetaObject,
    QObject,
    QPointF,
    QRectF,
    QSize,
    QTimer,
    QUrl,
    Qt,
    Property,
    Signal,
    Slot,
)
from PySide6.QtGui import (  # noqa: F401
    QColor,
    QGuiApplication,
    QImage,
    QPainter,
    QPixmap,
)
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonType  # noqa: F401
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem  # noqa: F401
