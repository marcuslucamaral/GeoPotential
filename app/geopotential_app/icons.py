"""The icon provider: an SVG on disk, painted in the colour the theme asks for.

    image://icon/tools/identify?color=e6e9ef

QML asks for a path under `qml/GeoPotential/icons/` and a colour; this renders
the file and tints it. It reads files and it draws — which is why it lives here
and not in `render/`, whose contract is that it reads nothing (P-06, P-80).

**Why not a shader.** The obvious answer is `ColorOverlay` or `MultiEffect`, and
the icons' own README suggested the first. Both were tried and both draw
**nothing under `QT_QPA_PLATFORM=offscreen`**: measured, on this machine, with
the plain `Image` beside them rendering correctly. Every storyboard in this
project is captured offscreen, so a shader-tinted icon would be a blank square
in every piece of visual evidence the gate collects, and the gate would still
pass because a blank square is a valid frame. The tint is therefore done on the
CPU, with `QPainter`, where the answer does not depend on which render loop is
running.

The cost is one render per (icon, colour, size), cached. A theme change asks for
a colour that is not in the cache yet; everything after it is a dictionary hit.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

#: The URL scheme QML uses. `image://icon/...` throughout the shell.
SCHEME = "icon"

#: What a request gets when it names an icon that is not there. A magenta
#: square is deliberate: it is visible in every theme and in every screenshot,
#: so a typo in a source path is found by looking rather than by reading logs.
MISSING = QColor("#ff00ff")

#: Requests are capped so a bad binding cannot ask for a 4 000 px icon and
#: fill the cache with one entry.
MAX_SIZE = 256


class IconProvider(QQuickImageProvider):
    """Renders `icons/<folder>/<name>.svg` in a requested colour."""

    def __init__(self, root: Path) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._root = Path(root)
        self._cache: dict[tuple[str, str, int, int], QImage] = {}

    def requestImage(self, request_id: str, size, requested):  # noqa: N802, ANN001
        """QML's entry point.

        request_id  "<folder>/<name>?color=rrggbb" — the colour arrives
                    **without** its `#`, so nothing has to be percent-encoded
                    on the way in or decoded here. `urllib` is not importable
                    anywhere in the app but the tile client (P-07), and
                    decoding a colour is not a reason to bend that
        size        out-parameter Qt fills with what was actually produced
        requested   the size QML asked for; (-1, -1) when it asked for none
        """
        path_part, _, query = request_id.partition("?")
        colour = MISSING
        for pair in query.split("&"):
            key, _, value = pair.partition("=")
            if key != "color" or not value:
                continue
            # `#rrggbb` is accepted too, so a caller that sends one is not
            # silently painted magenta.
            if not value.startswith("#") and len(value) in (6, 8):
                value = "#" + value
            candidate = QColor(value)
            if candidate.isValid():
                colour = candidate

        width = requested.width() if requested and requested.width() > 0 else 24
        height = requested.height() if requested and requested.height() > 0 else width
        width = max(1, min(int(width), MAX_SIZE))
        height = max(1, min(int(height), MAX_SIZE))

        key = (path_part, colour.name(QColor.HexArgb), width, height)
        cached = self._cache.get(key)
        if cached is not None:
            if size is not None:
                size.setWidth(cached.width())
                size.setHeight(cached.height())
            return cached

        image = self._render(path_part, colour, width, height)
        self._cache[key] = image
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image

    def _render(self, path_part: str, colour: QColor, width: int,
                height: int) -> QImage:
        image = QImage(QSize(width, height), QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)

        source = self._resolve(path_part)
        if source is None:
            image.fill(MISSING)
            return image

        renderer = QSvgRenderer(str(source))
        if not renderer.isValid():
            image.fill(MISSING)
            return image

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, width, height))
        # Keep the alpha the drawing produced and replace every colour with
        # the theme's. This is what `ColorOverlay` does, minus the shader.
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), colour)
        painter.end()
        return image

    def _resolve(self, path_part: str) -> Path | None:
        """The file for `<folder>/<name>`, or None.

        Refuses anything that climbs out of the icons directory: the request
        arrives as a string from QML, and a provider that resolves `..` is a
        file-read primitive with a URL in front of it.
        """
        candidate = (self._root / f"{path_part}.svg").resolve()
        try:
            candidate.relative_to(self._root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None


def install(engine, qml_root: Path) -> IconProvider:
    """Register the provider on a QML engine. Called once, from `app.py`."""
    provider = IconProvider(Path(qml_root) / "GeoPotential" / "icons")
    engine.addImageProvider(SCHEME, provider)
    return provider
