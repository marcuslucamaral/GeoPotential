"""The display stack: what is drawn, in what order, and how it is painted.

ADR-MSP-002. A `DisplayLayer` is **a decision about display**, derived one way
from something already registered — an imported dataset or a committed run's
artefact. It carries visibility, draw order, opacity, colormap, style limits, a
name and a role, and it carries nothing else:

- no pixels and no geometry — it references the source;
- no unit, no CRS, no nodata, no statistics — those belong to the registry;
- nothing that enters a computation.

Three consequences the gate enforces:

1. the display order is **not** a scientific order — `CriterionStack.names`
   stays the only one weights bind to (P-106);
2. no aggregation accepts a `DisplayLayer` (P-106);
3. removing a layer from the view removes nothing from the project (P-108).

QtCore only: a model that can name a QColor is choosing a style. A colormap is
named here, never resolved to colours — `render/colormap.py` does that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.qtcore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Qt,
    Property,
    Signal,
    Slot,
)

# What a layer is, in the flow. It is a label for the person, never a rule:
# nothing branches on the role, and the panel only shows it.
ROLES = ("original", "harmonized", "membership", "result", "aoi", "basemap")


@dataclass
class DisplayLayer:
    """One entry in the display stack."""

    layer_id: str
    name: str
    path: str = ""                 # the file the canvas reads, when there is one
    role: str = "original"
    kind: str = "raster"           # raster | vector | aoi
    source_ref: str = ""           # dataset id or artefact id it derives from
    unit: str = ""                 # read from the registry, shown, never decided here
    crs: str = ""
    visible: bool = True
    opacity: float = 1.0
    colormap: str = "viridis"
    invert: bool = False
    # Style limits. `None` means "whatever the source's own range is" — the
    # automatic limits the person can always come back to.
    vmin: float | None = None
    vmax: float | None = None
    # Points only. A marker too small to see on the chosen ground is a layer
    # that reads as absent, so both are the person's to set.
    point_size: int = 2
    symbol: str = "circle"
    outline: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def style(self) -> dict[str, Any]:
        """What the canvas needs to paint it. Display only, every time."""
        return {
            "colormap": self.colormap,
            "invert": self.invert,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "opacity": self.opacity,
            "pointSize": self.point_size,
            "symbol": self.symbol,
            "outline": self.outline,
        }


class LayerStackModel(QAbstractListModel):
    """The display stack, top of the list drawn last.

    The list order **is** the draw order, and it is the only thing order means
    here. Reordering repaints; it never changes a number.
    """

    IdRole = Qt.UserRole + 1
    NameRole = Qt.UserRole + 2
    RoleRole = Qt.UserRole + 3
    KindRole = Qt.UserRole + 4
    VisibleRole = Qt.UserRole + 5
    OpacityRole = Qt.UserRole + 6
    ColormapRole = Qt.UserRole + 7
    ActiveRole = Qt.UserRole + 8
    UnitRole = Qt.UserRole + 9
    CrsRole = Qt.UserRole + 10
    PathRole = Qt.UserRole + 11
    InvertRole = Qt.UserRole + 12

    changed = Signal()
    activeChanged = Signal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001 - Qt parent
        super().__init__(parent)
        self._layers: list[DisplayLayer] = []
        self._active: str = ""
        # Bumped on every change. QML needs something *notifiable* to depend
        # on: a binding that calls `activeLayer()` and nothing else is read
        # once and never re-read, which is the same trap a value-returning
        # Slot always is.
        self._revision = 0

    # ---- Qt model interface ---------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, ANN001
        return 0 if parent.isValid() else len(self._layers)

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {
            self.IdRole: QByteArray(b"layerId"),
            self.NameRole: QByteArray(b"name"),
            self.RoleRole: QByteArray(b"layerRole"),
            self.KindRole: QByteArray(b"kind"),
            self.VisibleRole: QByteArray(b"layerVisible"),
            self.OpacityRole: QByteArray(b"layerOpacity"),
            self.ColormapRole: QByteArray(b"colormap"),
            self.ActiveRole: QByteArray(b"isActive"),
            self.UnitRole: QByteArray(b"unit"),
            self.CrsRole: QByteArray(b"crs"),
            self.PathRole: QByteArray(b"path"),
            self.InvertRole: QByteArray(b"invert"),
        }

    def data(self, index, role=Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or not 0 <= index.row() < len(self._layers):
            return None
        layer = self._layers[index.row()]
        return {
            self.IdRole: layer.layer_id,
            self.NameRole: layer.name,
            self.RoleRole: layer.role,
            self.KindRole: layer.kind,
            self.VisibleRole: layer.visible,
            self.OpacityRole: layer.opacity,
            self.ColormapRole: layer.colormap,
            self.ActiveRole: layer.layer_id == self._active,
            self.UnitRole: layer.unit,
            self.CrsRole: layer.crs,
            self.PathRole: layer.path,
            self.InvertRole: layer.invert,
            Qt.DisplayRole: layer.name,
        }.get(role)

    # ---- the stack -------------------------------------------------------

    def add(self, layer: DisplayLayer, *, make_active: bool = True) -> str:
        """Put a layer on top of the stack.

        A second layer over the same source is legal and sometimes wanted — the
        same field with two stretches, side by side — so nothing is deduplicated
        here.
        """
        position = len(self._layers)
        self.beginInsertRows(QModelIndex(), position, position)
        self._layers.append(layer)
        self.endInsertRows()
        # A basemap is never made active, however empty the stack was.
        if layer.role != "basemap" and (make_active or not self._active):
            self.setActive(layer.layer_id)
        self._bump()
        return layer.layer_id

    @Slot(str, result=bool)
    def remove(self, layer_id: str) -> bool:
        """Take a layer out of the **view**.

        P-108: nothing else happens. The dataset stays registered, the runs stay
        committed, the artefacts stay on disk with their hashes.
        """
        position = self._index_of(layer_id)
        if position < 0:
            return False
        self.beginRemoveRows(QModelIndex(), position, position)
        del self._layers[position]
        self.endRemoveRows()
        if self._active == layer_id:
            remaining = [one for one in self._layers if one.role != "basemap"]
            self._active = remaining[-1].layer_id if remaining else ""
            self.activeChanged.emit()
        self._bump()
        return True

    @Slot(str, bool)
    def setVisible(self, layer_id: str, visible: bool) -> None:  # noqa: N802
        layer = self.layer(layer_id)
        if layer is None or layer.visible == visible:
            return
        layer.visible = visible
        self._touch(layer_id, [self.VisibleRole])

    @Slot(str, float)
    def setOpacity(self, layer_id: str, opacity: float) -> None:  # noqa: N802
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.opacity = min(1.0, max(0.0, float(opacity)))
        self._touch(layer_id, [self.OpacityRole])

    @Slot(str, str)
    def setColormap(self, layer_id: str, name: str) -> None:  # noqa: N802
        """Display only. It repaints and never rewrites a value (P-111)."""
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.colormap = name
        self._touch(layer_id, [self.ColormapRole])

    @Slot(str, str, result=bool)
    def setName(self, layer_id: str, name: str) -> bool:  # noqa: N802
        """What this layer is called **in the view**.

        Display only, like everything else here: the dataset in the catalogue
        keeps the name it was registered under, and no manifest changes. Two
        layers may read the same file with different names, which is the point
        — "distance, raw" and "distance, membership" are the same file twice.

        An empty name is refused: a nameless row in the panel is a row nobody
        can talk about.
        """
        layer = self.layer(layer_id)
        cleaned = name.strip()
        if layer is None or not cleaned:
            return False
        layer.name = cleaned
        self._touch(layer_id, [self.NameRole])
        return True

    @Slot(str, bool)
    def setInvert(self, layer_id: str, invert: bool) -> None:  # noqa: N802
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.invert = bool(invert)
        self._touch(layer_id, [self.InvertRole])

    @Slot(str, "QVariant", "QVariant")
    def setLimits(self, layer_id: str, vmin, vmax) -> None:  # noqa: N802, ANN001
        """Style limits. `null` on either side restores the automatic one."""
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.vmin = None if vmin is None or vmin == "" else float(vmin)
        layer.vmax = None if vmax is None or vmax == "" else float(vmax)
        self._touch(layer_id, [])

    @Slot(str, int)
    def setPointSize(self, layer_id: str, size: int) -> None:  # noqa: N802
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.point_size = max(0, min(8, int(size)))
        self._touch(layer_id, [])

    @Slot(str, str)
    def setSymbol(self, layer_id: str, symbol: str) -> None:  # noqa: N802
        """The marker's shape. Shape is read before colour on a busy map."""
        from ..render.points import SYMBOLS

        layer = self.layer(layer_id)
        if layer is None or symbol not in SYMBOLS:
            return
        layer.symbol = symbol
        self._touch(layer_id, [])

    @Slot(str, bool)
    def setOutline(self, layer_id: str, outline: bool) -> None:  # noqa: N802
        layer = self.layer(layer_id)
        if layer is None:
            return
        layer.outline = bool(outline)
        self._touch(layer_id, [])

    @Slot(str)
    def resetLimits(self, layer_id: str) -> None:  # noqa: N802
        self.setLimits(layer_id, None, None)

    @Slot(str)
    def setActive(self, layer_id: str) -> None:  # noqa: N802
        """The active layer is the one the Inspector and identify read.

        **A basemap can never be it.** It has no unit, no values and no colour
        limits, so an Inspector pointed at one shows blanks and the colour bar
        loses its numbers — which is exactly what happened when the basemap was
        the first layer in an empty project, or when its row was clicked.
        """
        layer = self.layer(layer_id)
        if layer is None or layer_id == self._active or layer.role == "basemap":
            return
        previous = self._active
        self._active = layer_id
        for one in (previous, layer_id):
            if one:
                self._touch(one, [self.ActiveRole], quiet=True)
        self.activeChanged.emit()
        self._bump()

    @Slot(str, int, result=bool)
    def move(self, layer_id: str, delta: int) -> bool:
        """Move a layer in the draw order. Display only (P-106)."""
        position = self._index_of(layer_id)
        target = position + delta
        if position < 0 or not 0 <= target < len(self._layers):
            return False
        self.beginResetModel()
        self._layers.insert(target, self._layers.pop(position))
        self.endResetModel()
        self._bump()
        return True

    @Slot()
    def clear(self) -> None:
        self.beginResetModel()
        self._layers = []
        self._active = ""
        self.endResetModel()
        self.activeChanged.emit()
        self._bump()

    # ---- reading ---------------------------------------------------------

    def layer(self, layer_id: str) -> DisplayLayer | None:
        for one in self._layers:
            if one.layer_id == layer_id:
                return one
        return None

    @property
    def layers(self) -> list[DisplayLayer]:
        """Bottom to top, which is also the order they are painted in."""
        return list(self._layers)

    def visible_layers(self) -> list[DisplayLayer]:
        return [one for one in self._layers if one.visible]

    def _get_active(self) -> str:
        return self._active

    def _get_count(self) -> int:
        return len(self._layers)

    def _get_revision(self) -> int:
        return self._revision

    def _get_colormaps(self) -> list:
        """The ramps the panel offers, from the one place that defines them.

        Names, not colours: resolving a name to RGB stays in `render/`, which
        is what keeps this model free of painting decisions.
        """
        from ..render.colormap import names

        return list(names())

    def _get_symbols(self) -> list:
        """The marker shapes on offer, from the one place that draws them."""
        from ..render.points import SYMBOLS

        return list(SYMBOLS)

    colormaps = Property(list, _get_colormaps, constant=True)
    symbols = Property(list, _get_symbols, constant=True)
    activeId = Property(str, _get_active, notify=activeChanged)
    count = Property(int, _get_count, notify=changed)
    revision = Property(int, _get_revision, notify=changed)

    @Slot(result="QVariant")
    def snapshot(self) -> list[dict[str, Any]]:
        """The whole stack, bottom to top, as plain dictionaries.

        The canvas is handed this and reconciles against it in one call. Two
        halves each doing their own incremental bookkeeping is how a panel and
        a map end up disagreeing about what is drawn.
        """
        return [
            {
                "layerId": one.layer_id, "path": one.path, "name": one.name,
                "unit": one.unit, "kind": one.kind, "role": one.role,
                "visible": one.visible, "opacity": one.opacity,
                "colormap": one.colormap, "invert": one.invert,
                "vmin": one.vmin, "vmax": one.vmax,
                "pointSize": one.point_size, "symbol": one.symbol,
                "outline": one.outline,
            }
            for one in self._layers
        ]

    @Slot(result="QVariant")
    def activeLayer(self) -> dict[str, Any]:  # noqa: N802
        layer = self.layer(self._active)
        if layer is None:
            return {}
        return {
            "layerId": layer.layer_id, "name": layer.name, "role": layer.role,
            "kind": layer.kind, "path": layer.path, "unit": layer.unit,
            "crs": layer.crs, "colormap": layer.colormap, "invert": layer.invert,
            "opacity": layer.opacity, "vmin": layer.vmin, "vmax": layer.vmax,
            "pointSize": layer.point_size, "symbol": layer.symbol,
            "outline": layer.outline,
        }

    # ---- internals -------------------------------------------------------

    def _bump(self) -> None:
        self._revision += 1
        self.changed.emit()

    def _index_of(self, layer_id: str) -> int:
        for position, one in enumerate(self._layers):
            if one.layer_id == layer_id:
                return position
        return -1

    def _touch(self, layer_id: str, roles: list[int], *, quiet: bool = False) -> None:
        position = self._index_of(layer_id)
        if position < 0:
            return
        index = self.index(position, 0)
        self.dataChanged.emit(index, index, roles)
        if not quiet:
            self._bump()
