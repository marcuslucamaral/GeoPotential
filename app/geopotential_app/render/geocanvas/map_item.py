"""The GeoCanvas item.

Section 10, in the form M4 delivers it: a painted item over the viewport
arithmetic in `viewport.py`, reading through `raster/` at the level of detail
the current scale needs, and never reading more than the screen can show.

Two separations hold this together, and both are enforced by the architecture
gate:

  - **this file draws; it does not read.** `RasterSource` owns the file.
  - **the tile on screen is not the data.** Every readout, and everything that
    will later become a statistic, goes to `RasterSource.sample`, which reads
    the source at full resolution. A decimated tile's pixel is an average of
    up to thousands of source pixels and is not a measurement of anything.

`QQuickPaintedItem` rather than `QQuickRhiItem`: section 10 permits the scene
graph "quando necessário", and necessity is a measurement nobody has taken.
When one exists it goes in `docs/validation/` and the item changes then.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import threading

import numpy as np

from ...raster import RasterSource, reproject_tile, source_window
from ...utils.qt import (
    QColor,
    QImage,
    QPainter,
    QPointF,
    QQuickPaintedItem,
    QRectF,
    Qt,
    Property,
    QTimer,
    Signal,
    Slot,
)
from .. import geometry as geometry_render
from .. import points as point_render
from ... import basemap
from ...geo import coordinates
from ..colormap import stretch_limits, to_rgba
from . import tools
from .viewport import Extent, Viewport


#: Every display field a layer can carry. Named once: `applyStack` used to
#: rebuild this dict by hand and forgot `pointSize`, `symbol` and `outline`,
#: so choosing a marker shape changed the model and never the picture.
STYLE_KEYS = ("colormap", "invert", "vmin", "vmax", "opacity", "visible",
              "pointSize", "symbol", "outline")


class _Painted:
    """One layer as the canvas holds it: an open source and a display style.

    The style is a copy of what `models/layer_model.py` decided; it is display
    only, and nothing here writes it back. The stretch limits are taken once,
    when the layer opens, for the reason `_layer_limits` explains.
    """

    __slots__ = ("layer_id", "source", "unit", "name", "limits", "style",
                 "points", "parts", "extent", "crs", "crs_unit")

    def __init__(self, layer_id: str, source: RasterSource | None, name: str,
                 unit: str, limits: tuple[float, float], *,
                 points: np.ndarray | None = None,
                 parts: list | None = None,
                 extent: "Extent | None" = None,
                 crs: str = "", crs_unit: str = "") -> None:
        self.layer_id = layer_id
        self.source = source
        # A table's points, (n, 3): x, y, value. Display data, bounded by
        # ADR-MSP-004 before it ever left the worker.
        self.points = points
        # A vector's silhouette: one array of (n, 2) coordinates per ring or
        # line, in this layer's CRS. Also display data, also bounded before it
        # crossed the IPC, and never an input to anything.
        self.parts = parts
        self.extent = extent
        self.crs = crs
        self.crs_unit = crs_unit
        self.name = name
        self.unit = unit
        self.limits = limits
        self.style: dict[str, Any] = {
            "colormap": "viridis", "invert": False,
            "vmin": None, "vmax": None, "opacity": 1.0, "visible": True,
            # Only points read these. A marker too small to see on a busy
            # ground is a layer that looks absent.
            "pointSize": 2, "symbol": "circle", "outline": False,
        }


class MapItem(QQuickPaintedItem):
    """One or two raster layers on a native canvas, with pan, zoom and readout."""

    cursorMoved = Signal(float, float, str)     # x, y, formatted value
    layerChanged = Signal()
    viewportChanged = Signal()
    aoiChanged = Signal()
    toolChanged = Signal()
    measured = Signal(str)                      # a formatted length or area
    identified = Signal(float, float, str)      # x, y, formatted value
    refused = Signal(str)                       # why an operation was refused
    # A fetched mosaic, handed back from the fetching thread. A Signal, not a
    # `QTimer.singleShot`: a single-shot created on a thread with no event loop
    # is a timer that never fires, and the tiles arrived nowhere.
    basemapArrived = Signal(object, object, int, int, object)

    # How much wider than the screen a basemap frame is fetched. A quarter
    # covers an ordinary pan without a new request, and costs a ring of tiles.
    BASEMAP_MARGIN = 0.25

    # Zoom per wheel notch. 1.25 keeps a double-click-equivalent at about three
    # notches, which is what a hand expects from a map.
    ZOOM_STEP = 1.25

    def __init__(self, parent=None) -> None:  # noqa: ANN001 - Qt parent
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.MiddleButton)
        self.setAcceptHoverEvents(True)

        self._source: RasterSource | None = None
        self._compare: RasterSource | None = None
        self._viewport: Viewport | None = None
        self._full_extent: Extent | None = None
        self._layer_name = ""
        self._compare_name = ""
        self._unit = ""
        self._crs_name = ""
        self._crs_unit = ""
        self._colormap = "viridis"
        self._split = False
        self._split_fraction = 0.5

        # Kept alive alongside the QImage: QImage does not own its buffer.
        self._rgba: dict[str, np.ndarray] = {}
        self._images: dict[str, QImage] = {}
        self._placements: dict[str, tuple[float, float, float, float]] = {}
        self._limits: tuple[float, float] = (0.0, 1.0)
        self._compare_limits: tuple[float, float] = (0.0, 1.0)

        # Every layer the canvas draws, bottom of the list drawn first. The
        # order is the display stack's order and means nothing else (P-106).
        self._stack: list[_Painted] = []
        self._active_id = ""

        self._panning = False
        self._pan_from: QPointF | None = None
        self._tool = tools.NAVIGATE
        self._aoi = tools.Sketch()
        self._measure = tools.Sketch()
        self._measurement = ""
        # The map's ground. Black hides dark points and dark ramps, so it is
        # the shell's choice and not a constant here.
        self._ground = "#000000"
        # The CRS the view is in. Empty means "whatever the first layer was",
        # which is what a single-layer project wants. Setting it is what lets
        # two layers in two CRSs share a screen (ADR-006: the sources are
        # untouched; only the picture is warped).
        self._view_crs = ""
        # The view's CRS, already resolved. See `_get_view_crs`.
        self._view_crs_resolved = ""
        # Point clouds already transformed into a view CRS, per layer.
        self._projected: dict[str, tuple[str, np.ndarray]] = {}
        # How a coordinate is written: native, UTM, decimal degrees or DMS.
        self._coordinate_style = coordinates.NATIVE
        # The basemap. Empty means off, which is what it is until someone
        # turns it on (ADR-MSP-006): with no source chosen, no connection is
        # ever opened.
        self._basemap = ""
        self._basemap_cache = None
        self._basemap_visible = True
        self._basemap_opacity = 1.0
        self._basemap_image = None
        self._basemap_rgba = None
        self._basemap_key = ()
        self._basemap_pending = None
        self._basemap_extent = None
        self._basemap_crs = ""
        # Queued by Qt because the emitter lives on another thread: the slot
        # runs here, on the GUI thread, which is the only place a QImage may
        # be built from this buffer.
        self.basemapArrived.connect(self._basemap_ready)
        self._reported_pixels = 0

    # ---- properties QML binds to ---------------------------------------

    def _get_layer_name(self) -> str:
        return self._layer_name

    def _get_crs_name(self) -> str:
        return self._crs_name

    def _get_unit(self) -> str:
        return self._unit

    def _get_has_layer(self) -> bool:
        return bool(self._stack)

    def _get_split(self) -> bool:
        return self._split and self._compare is not None

    def _set_split(self, value: bool) -> None:
        if value != self._split:
            self._split = bool(value)
            self.layerChanged.emit()
            self.update()

    def _get_compare_name(self) -> str:
        return self._compare_name

    def _get_scale_text(self) -> str:
        """The scale bar's label: a round distance and its unit."""
        if self._viewport is None:
            return ""
        target = self._viewport.scale * 120.0  # about 120 px of bar
        nice = _nice_number(target)
        unit = self._crs_unit or "units"
        if unit == "metre" and nice >= 1000:
            return f"{nice / 1000:g} km"
        return f"{nice:g} {'m' if unit == 'metre' else unit}"

    def _get_scale_pixels(self) -> float:
        if self._viewport is None:
            return 0.0
        target = self._viewport.scale * 120.0
        return float(_nice_number(target) / self._viewport.scale)

    def _get_lod(self) -> int:
        if self._source is None or self._viewport is None:
            return 1
        return self._source.level_for_scale(self._viewport.scale).factor

    def _get_aoi_points(self) -> int:
        return len(self._aoi)

    def _get_aoi_drawing(self) -> bool:
        return self._aoi.drawing

    def _get_tool(self) -> str:
        return self._tool

    def _set_tool(self, mode: str) -> None:
        """Exactly one mode at a time, and leaving a mode leaves nothing behind.

        The AOI defect this replaces was a sketch that outlived its mode. So
        switching away cancels whatever was being drawn: a half-drawn shape
        belongs to the tool that was drawing it.
        """
        if mode not in tools.MODES or mode == self._tool:
            return
        self._aoi.cancel()
        self._measure.cancel()
        self._measurement = ""
        self._tool = mode
        self.toolChanged.emit()
        self.aoiChanged.emit()
        self.update()

    def _get_measurement(self) -> str:
        return self._measurement

    def _get_view_crs(self) -> str:
        """What the view is in: the chosen CRS, else the first layer's.

        With neither — a basemap on an empty project — it is the tiles' own
        Web Mercator, because that is the only thing on screen.

        Answered from a remembered string, never by asking pyproj. `paint` can
        run on the render thread while the cursor readout uses pyproj on the
        GUI thread, and a PROJ context shared between the two segfaults — which
        it did, on a real window, while panning. The resolution happens once,
        when the stack or the choice changes.
        """
        if self._view_crs:
            return self._view_crs
        if self._view_crs_resolved:
            return self._view_crs_resolved
        return basemap.TILE_CRS if self._basemap else ""

    def _default_extent(self) -> "Extent | None":
        """Somewhere to look when nothing has been loaded yet.

        The whole world in Web Mercator, brought into the view's CRS. It is a
        starting frame, not a claim about any data: the moment a layer arrives,
        `_reveal` takes the view to it.
        """
        world = (-20037508.34, -20037508.34, 20037508.34, 20037508.34)
        view_crs = self._get_view_crs() or basemap.TILE_CRS
        if view_crs == basemap.TILE_CRS:
            return Extent(*world)
        try:
            return Extent(*coordinates.transform_extent(
                world, basemap.TILE_CRS, view_crs))
        except Exception:                            # noqa: BLE001
            return None

    def _resolve_view_crs(self) -> None:
        """Work out the view's CRS once, off the drawing path."""
        resolved = ""
        for painted in self._stack:
            crs = self._crs_of(painted)
            if not crs:
                continue
            try:
                resolved = coordinates.canonical(crs)
            except coordinates.CrsUnknown:
                continue
            break
        self._view_crs_resolved = resolved

    def _set_view_crs(self, crs: str) -> None:
        try:
            crs = coordinates.canonical(crs) if crs else ""
        except coordinates.CrsUnknown:
            return
        if crs == self._view_crs:
            return
        self._view_crs = crs
        # The extent the view is fitted to was in the old CRS.
        self._projected.clear()
        self._full_extent = self._stack_extent()
        self._viewport = None
        self._invalidate()
        self.layerChanged.emit()
        self.viewportChanged.emit()
        self.update()

    @staticmethod
    def _crs_of(painted: "_Painted") -> str:
        if painted.source is not None and painted.source.crs:
            return str(painted.source.crs)
        return painted.crs

    def _extent_of(self, painted: "_Painted") -> "Extent | None":
        """A layer's extent, expressed in the view's CRS."""
        if painted.source is not None:
            left, bottom, right, top = painted.source.bounds
            box = (left, bottom, right, top)
        elif painted.extent is not None:
            box = painted.extent.as_tuple()
        else:
            return None
        view_crs = self._get_view_crs()
        layer_crs = self._crs_of(painted)
        if view_crs and layer_crs and view_crs != layer_crs:
            try:
                box = coordinates.transform_extent(box, layer_crs, view_crs)
            except Exception:                        # noqa: BLE001
                return None
        return Extent(*box)

    def _stack_extent(self) -> "Extent | None":
        """Everything the stack covers, in the view's CRS."""
        boxes = [self._extent_of(p) for p in self._stack]
        boxes = [b for b in boxes if b is not None]
        if not boxes:
            return None
        return Extent(min(b.left for b in boxes), min(b.bottom for b in boxes),
                      max(b.right for b in boxes), max(b.top for b in boxes))

    def _get_coordinate_style(self) -> str:
        return self._coordinate_style

    def _set_coordinate_style(self, style: str) -> None:
        if style in coordinates.FORMATS and style != self._coordinate_style:
            self._coordinate_style = style
            self.viewportChanged.emit()

    def _get_basemap(self) -> str:
        return self._basemap

    def _set_basemap(self, key: str) -> None:
        if key == self._basemap:
            return
        self._basemap = key or ""
        self._basemap_key = ()
        self._basemap_pending = None
        self._basemap_rgba = None
        self._basemap_image = None
        self.layerChanged.emit()
        self.update()

    def _get_basemap_visible(self) -> bool:
        return self._basemap_visible

    def _set_basemap_visible(self, visible: bool) -> None:
        if bool(visible) != self._basemap_visible:
            self._basemap_visible = bool(visible)
            self.layerChanged.emit()
            self.update()

    def _get_basemap_opacity(self) -> float:
        return self._basemap_opacity

    def _set_basemap_opacity(self, opacity: float) -> None:
        value = max(0.0, min(1.0, float(opacity)))
        if abs(value - self._basemap_opacity) > 1e-6:
            self._basemap_opacity = value
            self.update()

    def _get_attribution(self) -> str:
        """What the licence obliges the map to show. Empty when off."""
        source = basemap.get(self._basemap)
        return source.attribution if source else ""

    @Slot(str)
    def setBasemapCache(self, directory: str) -> None:  # noqa: N802
        """Where fetched tiles are kept — inside the project, so the map that
        supported a decision reopens with it, and without a network."""
        from pathlib import Path

        self._basemap_cache = (basemap.TileCache(Path(directory))
                               if directory else None)

    def _get_ground(self) -> str:
        return self._ground

    def _set_ground(self, colour: str) -> None:
        if colour and colour != self._ground:
            self._ground = colour
            self.update()

    def _get_layer_count(self) -> int:
        return len(self._stack)

    def _get_colormap(self) -> str:
        painted = self._find(self._active_id)
        return painted.style.get("colormap", "viridis") if painted else "viridis"

    def _get_limits(self) -> list:
        """The active layer's colour limits, as the legend must label them."""
        painted = self._find(self._active_id)
        if painted is None:
            return []
        style = painted.style
        low = style.get("vmin")
        high = style.get("vmax")
        low = painted.limits[0] if low is None else float(low)
        high = painted.limits[1] if high is None else float(high)
        return [low, high]

    colormapName = Property(str, _get_colormap, notify=layerChanged)
    displayLimits = Property(list, _get_limits, notify=layerChanged)
    layerName = Property(str, _get_layer_name, notify=layerChanged)
    compareName = Property(str, _get_compare_name, notify=layerChanged)
    crsName = Property(str, _get_crs_name, notify=layerChanged)
    unit = Property(str, _get_unit, notify=layerChanged)
    hasLayer = Property(bool, _get_has_layer, notify=layerChanged)
    splitView = Property(bool, _get_split, _set_split, notify=layerChanged)
    scaleText = Property(str, _get_scale_text, notify=viewportChanged)
    scalePixels = Property(float, _get_scale_pixels, notify=viewportChanged)
    lodFactor = Property(int, _get_lod, notify=viewportChanged)
    aoiPointCount = Property(int, _get_aoi_points, notify=aoiChanged)
    aoiDrawing = Property(bool, _get_aoi_drawing, notify=aoiChanged)
    toolMode = Property(str, _get_tool, _set_tool, notify=toolChanged)
    measurement = Property(str, _get_measurement, notify=aoiChanged)
    ground = Property(str, _get_ground, _set_ground, notify=layerChanged)
    viewCrs = Property(str, _get_view_crs, _set_view_crs, notify=layerChanged)
    coordinateStyle = Property(str, _get_coordinate_style, _set_coordinate_style,
                               notify=viewportChanged)
    basemapSource = Property(str, _get_basemap, _set_basemap, notify=layerChanged)
    basemapAttribution = Property(str, _get_attribution, notify=layerChanged)
    basemapVisible = Property(bool, _get_basemap_visible, _set_basemap_visible,
                              notify=layerChanged)
    basemapOpacity = Property(float, _get_basemap_opacity, _set_basemap_opacity,
                              notify=layerChanged)
    layerCount = Property(int, _get_layer_count, notify=layerChanged)

    # `displayState` is a Property, not a Slot. A Slot that returns a value is
    # read once by QML and never re-evaluated, so the inspector would show the
    # level of detail and the pixel count from the first paint for the rest of
    # the session — which is exactly what it did until this line existed.
    displayState = Property("QVariant", lambda self: self.layerSummary(),
                            notify=viewportChanged)

    # ---- loading --------------------------------------------------------

    @Slot(str, str, result=bool)
    def showArtifact(self, path: str, unit: str = "membership [0-1]") -> bool:  # noqa: N802
        """Open a raster **as the only layer** and fit it to the item.

        path  a closed, hashed artefact, or any raster the project vouched for
        unit  what the values mean, shown beside the readout

        This is the single-layer entry the vertical slice and the gates use.
        `addLayer` is the one that builds a stack.
        """
        self.clearLayers()
        return bool(self.addLayer("main", str(path), Path(path).stem, unit))

    @Slot(str, str, str, str, result=bool)
    def addLayer(self, layer_id: str, path: str, name: str = "",  # noqa: N802
                 unit: str = "") -> bool:
        """Put a raster on top of the display stack.

        layer_id  the display layer's id, so style and order can find it again
        path      the file to read; `raster/` owns the reading
        name      what the panel calls it
        unit      what the values mean

        The stack is a display order and nothing else: the layer that draws
        last does not win an argument about a number (ADR-MSP-002).
        """
        target = Path(path)
        if not target.exists():
            return False
        source = RasterSource(target)
        # The caller may not know the unit — an artefact reaches the stack
        # named only by the operator that made it — but the file does.
        unit = unit or getattr(source, "unit", "") or ""
        left, bottom, right, top = source.bounds
        extent = Extent(left, bottom, right, top)
        painted = _Painted(
            layer_id, source, name or target.stem, unit,
            self._layer_limits(source, extent),
        )
        self._stack.append(painted)
        self._full_extent = extent if self._full_extent is None else self._full_extent
        self._resolve_view_crs()
        self.setActiveLayer(layer_id)
        self._reveal(painted)
        self._viewport = None  # rebuilt at the next paint, fitted to the item
        self._invalidate()
        self.layerChanged.emit()
        self.update()
        return True

    @Slot(str, "QVariant", str, str, str, str, result=bool)
    def addPointLayer(self, layer_id: str, points, name: str = "",  # noqa: N802, ANN001
                      unit: str = "", crs: str = "", crs_unit: str = "") -> bool:
        """Put a point cloud on top of the stack.

        layer_id  the display layer's id
        points    [[x, y, value], …] in the CRS named by `crs`; the bounded,
                  decimated preview the worker produced (ADR-MSP-004)
        unit      what the values mean

        A table becomes visible here. Before this, importing a CSV added a row
        to the project and nothing to the screen, which reads as "nothing
        happened".
        """
        array = np.asarray(
            [[float(p[0]), float(p[1]),
              float(p[2]) if len(p) > 2 and p[2] is not None else np.nan]
             for p in (points or [])],
            dtype=np.float64,
        )
        if array.size == 0:
            return False
        box = point_render.bounds(array[:, 0], array[:, 1])
        if box is None:
            return False
        extent = Extent(*box)
        finite = array[np.isfinite(array[:, 2]), 2]
        limits = ((float(finite.min()), float(finite.max()))
                  if finite.size else (0.0, 1.0))
        try:
            # `26912` is a CRS to pyproj and not to rasterio. Normalising here
            # means every consumer downstream reads the same string.
            crs = coordinates.canonical(crs)
        except coordinates.CrsUnknown:
            crs = ""
        painted = _Painted(layer_id, None, name or layer_id, unit, limits,
                           points=array, extent=extent, crs=crs,
                           crs_unit=crs_unit or coordinates.linear_unit(crs))
        self._stack.append(painted)
        if self._full_extent is None:
            self._full_extent = extent
        self._resolve_view_crs()
        self.setActiveLayer(layer_id)
        self._reveal(painted)
        self._viewport = None
        self._invalidate()
        self.layerChanged.emit()
        self.update()
        return True

    @Slot(str, "QVariant", str, str, str, result=bool)
    def addGeometryLayer(self, layer_id: str, parts, name: str = "",  # noqa: N802, ANN001
                         crs: str = "", crs_unit: str = "") -> bool:
        """Put a vector silhouette on top of the stack.

        layer_id  the display layer's id
        parts     [[[x, y], …], …] in the CRS named by `crs` — one list per
                  ring or line, the bounded and decimated preview the worker
                  produced (ADR-MSP-004)

        A vector becomes visible here. Before this, a shapefile added a row to
        the project and nothing to the screen — the gap M4 carried forward and
        named, because the raster path was built and the vector path was not.

        The silhouette answers "is this the right file" and nothing else: it
        carries no attribute values, so there is no readout under the cursor
        and no colour ramp over it, only a stroke taken from the layer's own.
        """
        cleaned = [
            np.asarray(part, dtype=np.float64)
            for part in (parts or [])
            if part is not None and len(part) >= 2
        ]
        box = geometry_render.bounds(cleaned)
        if box is None:
            return False
        extent = Extent(*box)
        try:
            # `26912` is a CRS to pyproj and not to rasterio, exactly as in
            # `addPointLayer`; normalising here keeps every consumer reading
            # the same string.
            crs = coordinates.canonical(crs)
        except coordinates.CrsUnknown:
            crs = ""
        painted = _Painted(layer_id, None, name or layer_id, "", (0.0, 1.0),
                           parts=cleaned, extent=extent, crs=crs,
                           crs_unit=crs_unit or coordinates.linear_unit(crs))
        self._stack.append(painted)
        if self._full_extent is None:
            self._full_extent = extent
        self._resolve_view_crs()
        self.setActiveLayer(layer_id)
        self._reveal(painted)
        self._viewport = None
        self._invalidate()
        self.layerChanged.emit()
        self.update()
        return True

    @Slot(str, result=bool)
    def removeLayer(self, layer_id: str) -> bool:  # noqa: N802
        """Take a layer out of the **view**. Nothing on disk is touched."""
        for position, painted in enumerate(self._stack):
            if painted.layer_id == layer_id:
                if painted.source is not None:
                    painted.source.close()
                del self._stack[position]
                self._resolve_view_crs()
                if self._active_id == layer_id:
                    self.setActiveLayer(
                        self._stack[-1].layer_id if self._stack else "")
                self._invalidate()
                self.layerChanged.emit()
                self.update()
                return True
        return False

    @Slot()
    def clearLayers(self) -> None:  # noqa: N802
        for painted in self._stack:
            if painted.source is not None:
                painted.source.close()
        self._stack = []
        self._active_id = ""
        self._view_crs_resolved = ""
        self._source = None
        self._full_extent = None
        self._layer_name = self._unit = self._crs_name = self._crs_unit = ""
        self._invalidate()
        self.layerChanged.emit()

    @Slot(str)
    def setActiveLayer(self, layer_id: str) -> None:  # noqa: N802
        """The layer the readout, the identify tool and the inspector read."""
        painted = self._find(layer_id)
        self._active_id = painted.layer_id if painted else ""
        self._source = painted.source if painted else None
        self._layer_name = painted.name if painted else ""
        self._unit = painted.unit if painted else ""
        self._limits = painted.limits if painted else (0.0, 1.0)
        self._colormap = painted.style["colormap"] if painted else "viridis"
        if painted is not None and painted.source is not None:
            crs = painted.source.crs
            self._crs_name = str(crs) if crs else ""
            self._crs_unit = crs.linear_units if crs else ""
        elif painted is not None:
            self._crs_name = painted.crs
            self._crs_unit = painted.crs_unit
        else:
            self._crs_name = self._crs_unit = ""
        self.layerChanged.emit()
        self.update()

    @Slot(str, "QVariant")
    def setLayerStyle(self, layer_id: str, style) -> None:  # noqa: N802, ANN001
        """Apply a display style. It repaints; it never rewrites a value.

        P-111: the artefact's bytes and its hash are the same before and after.
        """
        painted = self._find(layer_id)
        if painted is None:
            return
        for key in STYLE_KEYS:
            if style is not None and key in style:
                painted.style[key] = style[key]
        if layer_id == self._active_id:
            self._colormap = painted.style["colormap"]
        self._invalidate()
        self.layerChanged.emit()
        self.update()

    @Slot("QVariant")
    def setLayerOrder(self, order) -> None:  # noqa: N802, ANN001
        """Reorder the stack. Display only; no manifest ever sees this."""
        wanted = [str(one) for one in (order or [])]
        by_id = {painted.layer_id: painted for painted in self._stack}
        reordered = [by_id[one] for one in wanted if one in by_id]
        reordered += [p for p in self._stack if p.layer_id not in wanted]
        self._stack = reordered
        self._invalidate()
        self.layerChanged.emit()
        self.update()

    @Slot("QVariant")
    def applyStack(self, layers) -> None:  # noqa: N802, ANN001
        """Make the canvas show exactly this stack.

        layers  the display stack's own snapshot, bottom to top

        One call, idempotent: layers that arrived are opened, layers that left
        are closed, styles are applied and the order is set. The display stack
        is the authority and the canvas never keeps a second opinion about what
        is drawn.
        """
        wanted = list(layers or [])
        wanted_ids = [str(one["layerId"]) for one in wanted]

        for painted in list(self._stack):
            if painted.layer_id not in wanted_ids:
                self.removeLayer(painted.layer_id)

        for one in wanted:
            layer_id = str(one["layerId"])
            if self._find(layer_id) is None:
                if one.get("kind") == "basemap":
                    # It is drawn from `basemapSource`, not from a file: what
                    # the stack carries for it is visibility and opacity.
                    self.basemapVisible = bool(one.get("visible", True))
                    self.basemapOpacity = float(one.get("opacity", 1.0))
                    continue
                if one.get("kind") == "points":
                    # Its points arrive separately, through `addPointLayer`:
                    # the display stack carries no coordinates (ADR-MSP-002).
                    continue
                path = str(one.get("path") or "")
                if not path:
                    continue          # a layer with no file to read: not ours
                self.addLayer(layer_id, path, str(one.get("name") or ""),
                              str(one.get("unit") or ""))
            if self._find(layer_id) is None:
                if one.get("kind") == "basemap":
                    self.basemapVisible = bool(one.get("visible", True))
                    self.basemapOpacity = float(one.get("opacity", 1.0))
                continue
            # Passed through, not retyped: a field the snapshot carries and
            # this list forgot is a control that moves and changes nothing.
            self.setLayerStyle(
                layer_id, {key: one[key] for key in STYLE_KEYS if key in one}
            )
        self.setLayerOrder(wanted_ids)

    def _reveal(self, painted: "_Painted") -> None:
        """Bring a newly added layer into view when the view is elsewhere.

        Adding a layer and seeing nothing is indistinguishable from adding
        nothing. The view only moves when the new layer does **not** intersect
        it: otherwise the person's current framing is theirs to keep.
        """
        box = None
        if painted.source is not None:
            left, bottom, right, top = painted.source.bounds
            box = Extent(left, bottom, right, top)
        elif painted.extent is not None:
            box = painted.extent
        if box is None:
            return
        if self._viewport is None:
            self._full_extent = box
            return
        view = self._viewport.fitted_extent
        intersects = (box.left < view.right and box.right > view.left
                      and box.bottom < view.top and box.top > view.bottom)
        if not intersects:
            self._full_extent = box
            self._viewport = None      # refitted to the new layer at next paint

    def _find(self, layer_id: str) -> "_Painted | None":
        for painted in self._stack:
            if painted.layer_id == layer_id:
                return painted
        return None

    @staticmethod
    def _layer_limits(source: RasterSource, extent: Extent) -> tuple[float, float]:
        """The display stretch for a layer, taken once from a coarse overview.

        Held for the life of the layer. Recomputing it per view — which is what
        happens if it is derived from whatever tile is on screen — makes the
        same colour mean a different value at every zoom, so panning across a
        boundary appears to change the data. It did, until this existed: a
        storyboard frame after `zoomToFit` came back saturated because the
        limits were still those of the zoomed-in tile.

        A coarse level is enough: the stretch is percentile-based, and the
        percentiles of a decimated field track the full one closely enough for
        a display decision.
        """
        span = max(extent.width, extent.height)
        coarse = source.read_window(
            extent.left, extent.bottom, extent.right, extent.top, span / 512.0
        )
        return stretch_limits(coarse.values) if coarse is not None else (0.0, 1.0)

    @Slot(str, result=bool)
    def showComparison(self, path: str) -> bool:  # noqa: N802
        """Open a second raster for the split view. Same viewport, same scale."""
        target = Path(path)
        if not target.exists():
            return False
        if self._compare is not None:
            self._compare.close()
        self._compare = RasterSource(target)
        self._compare_name = target.stem
        left, bottom, right, top = self._compare.bounds
        self._compare_limits = self._layer_limits(
            self._compare, Extent(left, bottom, right, top)
        )
        self._split = True
        self._invalidate()
        self.layerChanged.emit()
        self.update()
        return True

    @Slot()
    def clearComparison(self) -> None:  # noqa: N802
        if self._compare is not None:
            self._compare.close()
        self._compare = None
        self._compare_name = ""
        self._split = False
        self._invalidate()
        self.layerChanged.emit()
        self.update()

    def _invalidate(self) -> None:
        self._rgba.clear()
        self._images.clear()
        self._placements.clear()

    # ---- navigation -----------------------------------------------------

    @Slot()
    def zoomToFit(self) -> None:  # noqa: N802
        self._viewport = None
        self._invalidate()
        self.update()
        self.viewportChanged.emit()

    @Slot(str, result=bool)
    def zoomToLayer(self, layer_id: str) -> bool:  # noqa: N802
        """Fit one layer's own extent. Display only; nothing is reprojected."""
        painted = self._find(layer_id)
        if painted is None:
            return False
        if painted.source is not None:
            left, bottom, right, top = painted.source.bounds
            self._full_extent = Extent(left, bottom, right, top)
        elif painted.extent is not None:
            self._full_extent = painted.extent
        else:
            return False
        self._viewport = None      # rebuilt at the next paint, fitted
        self._invalidate()
        self.update()
        self.viewportChanged.emit()
        return True

    @Slot(float)
    def zoomBy(self, factor: float) -> None:  # noqa: N802
        if self._viewport is None:
            return
        self._viewport = self._viewport.zoomed(factor)
        self._invalidate()
        self.update()
        self.viewportChanged.emit()

    def wheelEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._viewport is None:
            return
        notches = event.angleDelta().y() / 120.0
        factor = self.ZOOM_STEP ** (-notches)
        position = event.position()
        anchor = self._viewport.to_map(position.x(), position.y())
        self._viewport = self._viewport.zoomed(
            factor, at=(float(anchor[0]), float(anchor[1]))
        )
        self._invalidate()
        self.update()
        self.viewportChanged.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        """What a click means depends on the mode, and on nothing else.

        Exactly one mode is active, the toolbar shows which, and the status bar
        names it. A click that does two things depending on hidden state is the
        defect the mode replaces.
        """
        if event.button() != Qt.LeftButton or self._viewport is None:
            self._panning = True
            self._pan_from = event.position()
            return

        x, y = self._viewport.to_map(event.position().x(), event.position().y())
        if self._tool == tools.AOI:
            if not self._aoi.drawing:
                self._aoi.begin()
            self._aoi.add(x, y)
            self.aoiChanged.emit()
            self.update()
            return
        if self._tool in (tools.MEASURE_DISTANCE, tools.MEASURE_AREA):
            if not self._measure.drawing:
                self._measure.begin()
            self._measure.add(x, y)
            self._recompute_measurement()
            self.update()
            return
        if self._tool == tools.IDENTIFY:
            value = self.sample(float(x), float(y))
            text = "no data" if value is None else f"{value:.4g} {self._unit}"
            self.identified.emit(float(x), float(y), text)
            return

        self._panning = True
        self._pan_from = event.position()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        if not self._panning or self._pan_from is None or self._viewport is None:
            return
        position = event.position()
        self._viewport = self._viewport.panned(
            position.x() - self._pan_from.x(), position.y() - self._pan_from.y()
        )
        self._pan_from = position
        self._invalidate()
        self.update()
        self.viewportChanged.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802, ANN001
        self._panning = False
        self._pan_from = None

    def hoverMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._report(event.position())

    # ---- painting -------------------------------------------------------

    def paint(self, painter: QPainter) -> None:
        painter.fillRect(self.boundingRect(), QColor(self._ground))
        # Not `self._source`: a stack of point layers has no raster, and the
        # guard that asked for one made a table-only project paint nothing at
        # all. It was invisible in testing because a raster was always present.
        has_basemap = basemap.get(self._basemap) is not None and self._basemap_visible
        if not self._stack and not has_basemap:
            return
        if self._full_extent is None:
            if not has_basemap:
                return
            # A basemap with no data still has to draw. Without an extent of
            # its own there is no viewport, and without a viewport nothing
            # paints — which is why choosing a basemap on an empty project
            # looked like choosing nothing at all.
            self._full_extent = self._default_extent()
            if self._full_extent is None:
                return

        width = max(1, int(self.width()))
        height = max(1, int(self.height()))
        if self._viewport is None:
            self._viewport = Viewport(self._full_extent, width, height)
            QTimer.singleShot(0, self.viewportChanged.emit)
        elif (self._viewport.pixel_width, self._viewport.pixel_height) != (width, height):
            self._viewport = self._viewport.resized(width, height)
            self._invalidate()

        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        # Under everything, always. A basemap is a picture the data sits on.
        self._paint_basemap(painter, QRectF(0, 0, width, height))
        if self._get_split():
            split_x = int(width * self._split_fraction)
            self._paint_source(painter, self._source, "main",
                               QRectF(0, 0, split_x, height),
                               limits=self._limits)
            self._paint_source(painter, self._compare, "compare",
                               QRectF(split_x, 0, width - split_x, height),
                               limits=self._compare_limits)
            painter.setPen(Qt.white)
            painter.drawLine(split_x, 0, split_x, height)
        else:
            # Bottom of the stack first. The order is the display order and
            # carries no other meaning (ADR-MSP-002).
            full = QRectF(0, 0, width, height)
            for painted in self._stack:
                if not painted.style.get("visible", True):
                    continue
                if painted.points is not None:
                    self._paint_points(painter, painted, full)
                elif painted.parts is not None:
                    self._paint_geometry(painter, painted, full)
                else:
                    self._paint_source(
                        painter, painted.source, painted.layer_id, full,
                        limits=painted.limits, style=painted.style,
                    )

        # The sketches sit above every layer, once, not once per layer.
        self._paint_sketches(painter)

        # Announce after the reads, not before them — and **after** the paint,
        # never during it. `viewportChanged` fires when the viewport is built,
        # which is before any tile has been fetched, so an inspector bound to
        # it would show a pixel count of zero for the rest of the session (it
        # did). Emitting from inside `paint` is the other half: a binding that
        # runs there re-enters the item while it is drawing itself.
        if (self._source is not None
                and self._source.pixels_read != self._reported_pixels):
            self._reported_pixels = self._source.pixels_read
            QTimer.singleShot(0, self.viewportChanged.emit)

    def _paint_source(self, painter: QPainter, source: RasterSource | None,
                      slot: str, clip: QRectF, *,
                      limits: tuple[float, float] | None = None,
                      style: dict[str, Any] | None = None) -> None:
        """Draw one raster into a screen rectangle, at the current level."""
        if source is None or self._viewport is None:
            return
        painter.save()
        painter.setClipRect(clip)

        extent = self._viewport.fitted_extent
        view_crs = self._get_view_crs()
        layer_crs = str(source.crs) if source.crs else ""
        warping = bool(view_crs and layer_crs and view_crs != layer_crs)

        if warping:
            # Read the part of the source the view covers — a rectangle in the
            # view's CRS is not a rectangle in the source's, so the box that
            # contains it is what gets read. ADR-006: the file is untouched.
            try:
                window = source_window(
                    (extent.left, extent.bottom, extent.right, extent.top),
                    view_crs, layer_crs,
                )
            except Exception:                        # noqa: BLE001
                painter.restore()
                return
            span = max(window[2] - window[0], window[3] - window[1])
            scale = span / max(1.0, clip.width())
            tile = source.read_window(*window, scale)
        else:
            tile = source.read_window(
                extent.left, extent.bottom, extent.right, extent.top,
                self._viewport.scale,
            )
        if tile is not None:
            values = tile.values
            if warping:
                values = reproject_tile(
                    tile.values, tile.transform, source.crs,
                    target_crs=view_crs,
                    extent=(extent.left, extent.bottom, extent.right, extent.top),
                    width=max(1, int(clip.width())),
                    height=max(1, int(clip.height())),
                )
            # The layer's own stretch, fixed when it was opened. Every tile of
            # a layer is coloured by the same mapping, at every zoom, so a
            # colour means one value. A style limit the person set wins over
            # it — that is what setting one is for — and `None` means the
            # automatic one, which is why it is not simply `or`.
            low, high = limits if limits is not None else self._limits
            style = style or {}
            if style.get("vmin") is not None:
                low = float(style["vmin"])
            if style.get("vmax") is not None:
                high = float(style["vmax"])

            rgba = to_rgba(
                values,
                colormap=style.get("colormap", self._colormap),
                vmin=low, vmax=high,
                invert=bool(style.get("invert", False)),
                opacity=float(style.get("opacity", 1.0)),
            )
            self._rgba[slot] = rgba
            rows, cols, _ = rgba.shape
            image = QImage(rgba.data, cols, rows, 4 * cols, QImage.Format_RGBA8888)
            self._images[slot] = image

            if warping:
                # The warped tile already covers exactly the view's extent.
                painter.drawImage(clip, image)
                self._placements[slot] = (clip.left(), clip.top(),
                                          clip.right(), clip.bottom())
            else:
                t = tile.transform
                tile_left, tile_top = t * (0, 0)
                tile_right, tile_bottom = t * (cols, rows)
                left, top = self._viewport.to_screen(tile_left, tile_top)
                right, bottom = self._viewport.to_screen(tile_right, tile_bottom)
                painter.drawImage(
                    QRectF(float(left), float(top),
                           float(right) - float(left), float(bottom) - float(top)),
                    image,
                )
                self._placements[slot] = (float(left), float(top),
                                          float(right), float(bottom))

        painter.restore()

    def _paint_basemap(self, painter: QPainter, clip: QRectF) -> None:
        """Draw the chosen basemap under the layers, warped into the view.

        Nothing happens when no source is chosen — that is what "off by
        default" means in code, not in prose. A fetch that fails leaves the
        map without a background and the work untouched.
        """
        source = basemap.get(self._basemap)
        if source is None or self._viewport is None or not self._basemap_visible:
            return
        view_crs = self._get_view_crs()
        if not view_crs:
            return
        extent = self._viewport.fitted_extent
        width = max(1, int(clip.width()))
        height = max(1, int(clip.height()))

        try:
            mercator = coordinates.transform_extent(
                (extent.left, extent.bottom, extent.right, extent.top),
                view_crs, basemap.TILE_CRS,
            )
            centre = coordinates.transform(
                (extent.left + extent.right) / 2.0,
                (extent.bottom + extent.top) / 2.0, view_crs,
                coordinates.GEOGRAPHIC,
            )
        except Exception:                            # noqa: BLE001
            return

        metres_per_pixel = (mercator[2] - mercator[0]) / max(1, width)
        zoom = min(source.max_zoom, basemap.zoom_for(metres_per_pixel, centre[1]))

        # Fetch a frame wider than the screen, so a small pan is already
        # covered, and key the request coarsely so nudging the map does not
        # start a new fetch. Rounded to the pixel, every mouse move was a new
        # request and the background never settled.
        pad_x = (mercator[2] - mercator[0]) * self.BASEMAP_MARGIN
        pad_y = (mercator[3] - mercator[1]) * self.BASEMAP_MARGIN
        mercator = (mercator[0] - pad_x, mercator[1] - pad_y,
                    mercator[2] + pad_x, mercator[3] + pad_y)
        step = max(1.0, (mercator[2] - mercator[0]) / 8.0)
        key = (source.key, zoom,
               tuple(round(v / step) for v in mercator), width, height)
        if key != self._basemap_key:
            # **Never fetch from inside paint.** A tile server is a network
            # away, and blocking the thread that draws freezes the application
            # — or, on the threaded render loop, corrupts it. The fetch is
            # asked for here and the picture arrives at a later frame.
            self._request_basemap(source, mercator, zoom, key, width, height)
            self._draw_basemap(painter, clip)
            return
        self._draw_basemap(painter, clip)

    def _request_basemap(self, source, mercator, zoom, key,  # noqa: ANN001
                         width: int, height: int) -> None:
        """Fetch a mosaic in the background, once per view.

        The thread does network and numpy only; everything that touches Qt
        happens back on the GUI thread, through a queued single-shot.
        """
        if self._basemap_pending == key:
            return
        self._basemap_pending = key
        extent = self._viewport.fitted_extent if self._viewport else None
        view_crs = self._get_view_crs()
        if extent is None or not view_crs:
            return
        box = (extent.left, extent.bottom, extent.right, extent.top)

        def work() -> None:
            stitched = basemap.mosaic(source, mercator, zoom, self._basemap_cache)
            if stitched is None:
                self._basemap_pending = None
                return
            canvas, tile_extent = stitched
            try:
                rgba = self._warp_basemap(canvas, tile_extent, view_crs, box,
                                          width, height)
            except Exception:                        # noqa: BLE001
                self._basemap_pending = None
                return
            self.basemapArrived.emit(key, rgba, width, height, box)

        threading.Thread(target=work, name="basemap-fetch", daemon=True).start()

    @staticmethod
    def _warp_basemap(canvas, tile_extent, view_crs, box,  # noqa: ANN001
                      width: int, height: int) -> np.ndarray:
        """Web Mercator tiles into the view's CRS. Pure numpy and rasterio."""
        rgb = np.stack([
            reproject_tile(
                canvas[..., channel].astype(np.float32),
                _affine_for(tile_extent, canvas.shape[1], canvas.shape[0]),
                basemap.TILE_CRS, target_crs=view_crs, extent=box,
                width=width, height=height,
            )
            for channel in range(3)
        ], axis=-1)
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        finite = np.isfinite(rgb).all(axis=-1)
        rgba[..., :3] = np.nan_to_num(rgb).clip(0, 255).astype(np.uint8)
        rgba[..., 3] = np.where(finite, 255, 0)
        return np.ascontiguousarray(rgba)

    @Slot(object, object, int, int, object)
    def _basemap_ready(self, key, rgba,  # noqa: ANN001
                       width: int, height: int, extent) -> None:  # noqa: ANN001
        """The fetched mosaic, taken up on the GUI thread.

        The extent it was warped for is kept with it. Drawing it into whatever
        rectangle the view happens to be now is what made the background slide
        against the data while zooming: the picture was stretched to the new
        frame instead of staying where its own coordinates put it.
        """
        self._basemap_pending = None
        self._basemap_rgba = rgba
        self._basemap_image = QImage(self._basemap_rgba.data, width, height,
                                     4 * width, QImage.Format_RGBA8888)
        self._basemap_key = key
        self._basemap_extent = extent
        self._basemap_crs = self._get_view_crs()
        self.update()

    def _draw_basemap(self, painter: QPainter, clip: QRectF) -> None:
        """Put the mosaic where its own coordinates say, not where the view is.

        While new tiles are on their way the previous picture stays, correctly
        placed: it slides and scales with everything else, and is replaced when
        the fetch lands. That is the difference between a background that lags
        and one that is simply a little coarse for a moment.
        """
        if (self._basemap_image is None or self._viewport is None
                or self._basemap_extent is None):
            return
        if self._basemap_crs and self._basemap_crs != self._get_view_crs():
            return                    # it belongs to a view that no longer is
        left, bottom, right, top = self._basemap_extent
        x0, y0 = self._viewport.to_screen(left, top)
        x1, y1 = self._viewport.to_screen(right, bottom)
        painter.setOpacity(self._basemap_opacity)
        painter.drawImage(
            QRectF(float(x0), float(y0), float(x1) - float(x0),
                   float(y1) - float(y0)),
            self._basemap_image,
        )
        painter.setOpacity(1.0)

    def _paint_points(self, painter: QPainter, painted: "_Painted",
                      clip: QRectF) -> None:
        """Draw a point cloud into the current view.

        The whole cloud is rasterised in numpy — screen positions, colours and
        marker footprints are array operations — and the result is drawn as one
        image. A Python loop over the points would be a loop in a draw path.
        """
        if self._viewport is None or painted.points is None:
            return
        points = self._points_in_view(painted)
        if points is None:
            return
        width = max(1, int(clip.width()))
        height = max(1, int(clip.height()))
        extent = self._viewport.fitted_extent
        style = painted.style

        rgba = point_render.to_rgba(
            points[:, 0], points[:, 1], points[:, 2],
            width=width, height=height,
            extent=(extent.left, extent.bottom, extent.right, extent.top),
            colormap=style.get("colormap", "viridis"),
            invert=bool(style.get("invert", False)),
            vmin=style.get("vmin", painted.limits[0]),
            vmax=style.get("vmax", painted.limits[1]),
            opacity=float(style.get("opacity", 1.0)),
            radius=int(style.get("pointSize", 2)),
            symbol=str(style.get("symbol", "circle")),
            outline=bool(style.get("outline", False)),
        )
        self._rgba[painted.layer_id] = rgba          # QImage does not own it
        image = QImage(rgba.data, width, height, 4 * width,
                       QImage.Format_RGBA8888)
        self._images[painted.layer_id] = image
        painter.drawImage(clip, image)

    def _paint_geometry(self, painter: QPainter, painted: "_Painted",
                        clip: QRectF) -> None:
        """Draw a vector silhouette into the current view.

        The whole outline is rasterised in numpy and drawn as one image, the
        same way a point cloud is: a Python loop over 2 000 vertices would be a
        loop in a draw path.
        """
        if self._viewport is None or painted.parts is None:
            return
        parts = self._geometry_in_view(painted)
        if parts is None:
            return
        width = max(1, int(clip.width()))
        height = max(1, int(clip.height()))
        extent = self._viewport.fitted_extent
        style = painted.style

        rgba = geometry_render.to_rgba(
            parts,
            width=width, height=height,
            extent=(extent.left, extent.bottom, extent.right, extent.top),
            colormap=style.get("colormap", "viridis"),
            invert=bool(style.get("invert", False)),
            opacity=float(style.get("opacity", 1.0)),
            # A vector reuses the marker size as its stroke half-width: it is
            # the same question — how big is the mark — and adding a second
            # size control would add a style key for one layer kind.
            thickness=max(0, int(style.get("pointSize", 2)) - 1),
            outline=bool(style.get("outline", False)),
        )
        self._rgba[painted.layer_id] = rgba          # QImage does not own it
        image = QImage(rgba.data, width, height, 4 * width,
                       QImage.Format_RGBA8888)
        self._images[painted.layer_id] = image
        painter.drawImage(clip, image)

    def _geometry_in_view(self, painted: "_Painted") -> "list | None":
        """A silhouette in the view's CRS, transformed once and remembered.

        The parts are transformed as one array and split back, so pyproj is
        called once per view change rather than once per ring.
        """
        if painted.parts is None:
            return None
        view_crs = self._get_view_crs()
        layer_crs = painted.crs
        if not view_crs or not layer_crs or view_crs == layer_crs:
            return painted.parts
        cached = self._projected.get(painted.layer_id)
        if cached is not None and cached[0] == view_crs:
            return cached[1]
        counts = [part.shape[0] for part in painted.parts]
        if not counts:
            return painted.parts
        flat = np.concatenate(painted.parts, axis=0)
        try:
            x, y = coordinates.transform_arrays(
                flat[:, 0], flat[:, 1], layer_crs, view_crs
            )
        except Exception:                            # noqa: BLE001
            return None
        moved = np.column_stack([x, y])
        edges = np.cumsum(counts)[:-1]
        parts = [np.ascontiguousarray(p) for p in np.split(moved, edges)]
        self._projected[painted.layer_id] = (view_crs, parts)
        return parts

    def _points_in_view(self, painted: "_Painted") -> "np.ndarray | None":
        """A point cloud in the view's CRS, transformed once and remembered.

        Transforming 5 000 points per repaint would be work per frame; pyproj
        does the whole array in one call, and the answer only changes when the
        view's CRS does.
        """
        if painted.points is None:
            return None
        view_crs = self._get_view_crs()
        layer_crs = painted.crs
        if not view_crs or not layer_crs or view_crs == layer_crs:
            return painted.points
        cached = self._projected.get(painted.layer_id)
        if cached is not None and cached[0] == view_crs:
            return cached[1]
        try:
            x, y = coordinates.transform_arrays(
                painted.points[:, 0], painted.points[:, 1], layer_crs, view_crs
            )
        except Exception:                            # noqa: BLE001
            return None
        moved = np.column_stack([x, y, painted.points[:, 2]])
        self._projected[painted.layer_id] = (view_crs, moved)
        return moved

    def _paint_sketches(self, painter: QPainter) -> None:
        """Draw the AOI and the measurement — **only while their tool is on**.

        P-109. The defect this replaces drew an AOI forever, because ending the
        drawing lowered a flag and cleared nothing, and no label ever said what
        the yellow lines were.
        """
        if self._viewport is None:
            return
        if self._tool == tools.AOI:
            self._paint_sketch(painter, self._aoi, QColor(255, 200, 60),
                               close=True)
        elif self._tool in (tools.MEASURE_DISTANCE, tools.MEASURE_AREA):
            self._paint_sketch(painter, self._measure, QColor(120, 210, 255),
                               close=self._tool == tools.MEASURE_AREA)

    def _paint_sketch(self, painter: QPainter, sketch: "tools.Sketch",
                      colour: QColor, *, close: bool) -> None:
        """Vertices with markers, and the segments between them.

        The markers are the point: a vertex you cannot see is a vertex you
        cannot decide to undo.
        """
        if not sketch.points or self._viewport is None:
            return
        points = [self._viewport.to_screen(x, y) for x, y in sketch.points]
        painter.setPen(colour)
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
        if close and len(points) > 2:
            (x0, y0), (x1, y1) = points[-1], points[0]
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))
        painter.setBrush(colour)
        for x, y in points:
            painter.drawEllipse(QPointF(float(x), float(y)), 3.0, 3.0)
        painter.setBrush(Qt.NoBrush)

    # ---- readout --------------------------------------------------------

    def _report(self, pos: QPointF) -> None:
        if self._viewport is None or not self._stack:
            return
        x, y = self._viewport.to_map(pos.x(), pos.y())
        value = self.sample(float(x), float(y))
        text = "no data" if value is None else f"{value:.4g} {self._unit}"
        self.cursorMoved.emit(float(x), float(y), text)

    @Slot(float, float, result=str)
    def formatPosition(self, x: float, y: float) -> str:  # noqa: N802
        """A map coordinate, written in the chosen format.

        Always carries what it is in: a coordinate without its CRS, or degrees
        without a hemisphere, is a pair of numbers.
        """
        return coordinates.format_position(
            float(x), float(y), self._get_view_crs(),
            coordinates.linear_unit(self._get_view_crs()),
            self._coordinate_style,
        )

    @Slot(result=str)
    def positionLabel(self) -> str:  # noqa: N802
        """The CRS the readout is expressed in."""
        return coordinates.label_for(self._coordinate_style, self._get_view_crs())

    def sample(self, x: float, y: float) -> float | None:
        """The value at a map coordinate, **from the source, at full resolution**.

        Not from the tile on screen. At a level-of-detail factor of 32 the
        displayed pixel is the average of 1024 source pixels; reporting that as
        the value under the cursor would report a number that appears nowhere
        in the dataset. Gate M4 checks exactly this.

        The cursor is in the **view's** CRS. When the layer is in another one,
        the point is transformed before the source is read: sampling the source
        at the view's coordinates would read a place kilometres away and report
        the number found there.
        """
        if self._source is None:
            return None
        view_crs = self._get_view_crs()
        layer_crs = str(self._source.crs) if self._source.crs else ""
        if view_crs and layer_crs and view_crs != layer_crs:
            try:
                x, y = coordinates.transform(x, y, view_crs, layer_crs)
            except Exception:                        # noqa: BLE001
                return None
        return self._source.sample(x, y)

    @Slot(float, float, result="QVariant")
    def identifyAt(self, x: float, y: float) -> list:  # noqa: N802
        """Every visible layer's value at one map coordinate.

        x, y     in the **view's** CRS
        returns  [{name, value, unit, row, column, crs, onGrid}], top first

        The active layer alone is not an answer: a person clicks a point to
        compare what the layers say there, which is the whole reason the
        stack exists. Each layer is sampled **from its own source at full
        resolution** and in **its own CRS** — reading the displayed tile would
        report an average of up to a thousand source pixels as if it were a
        measurement, and reading at the view's coordinates would read a place
        kilometres away.

        A point layer reports no value: it holds samples, not a field, and the
        value "at" a coordinate it does not occupy does not exist.
        """
        view_crs = self._get_view_crs()
        readings = []
        for painted in reversed(self._stack):
            if not painted.style.get("visible", True):
                continue
            if painted.source is None:
                readings.append({
                    "name": painted.name,
                    "kind": "points" if painted.points is not None else "vector",
                    "value": None, "unit": painted.unit,
                    "row": None, "column": None,
                    "crs": painted.crs, "onGrid": False,
                })
                continue
            layer_crs = str(painted.source.crs) if painted.source.crs else ""
            lx, ly = float(x), float(y)
            if view_crs and layer_crs and view_crs != layer_crs:
                try:
                    lx, ly = coordinates.transform(lx, ly, view_crs, layer_crs)
                except Exception:                    # noqa: BLE001
                    continue
            value = painted.source.sample(lx, ly)
            row = column = None
            try:
                inverse = ~painted.source.transform
                column = int(inverse.a * lx + inverse.b * ly + inverse.c)
                row = int(inverse.d * lx + inverse.e * ly + inverse.f)
            except Exception:                        # noqa: BLE001
                pass
            inside = (
                row is not None and column is not None
                and 0 <= row < painted.source.height
                and 0 <= column < painted.source.width
            )
            readings.append({
                "name": painted.name,
                "kind": "raster",
                "value": None if value is None else float(value),
                "unit": painted.unit,
                "row": row if inside else None,
                "column": column if inside else None,
                "crs": layer_crs,
                "onGrid": inside,
            })
        return readings

    def _active_painted(self) -> "_Painted | None":
        return self._find(self._active_id)

    @Slot(float, float, result=float)
    def sampleAt(self, x: float, y: float) -> float:  # noqa: N802
        value = self.sample(x, y)
        return float("nan") if value is None else value

    # ---- AOI ------------------------------------------------------------

    @Slot()
    def beginAoi(self) -> None:  # noqa: N802
        """Enter the AOI mode with an empty sketch."""
        self._set_tool(tools.AOI)
        self._aoi.begin()
        self.aoiChanged.emit()
        self.update()

    @Slot()
    def endAoi(self) -> None:  # noqa: N802
        """Stop placing vertices, keeping them for whoever saves them."""
        self._aoi.finish()
        self.aoiChanged.emit()
        self.update()

    @Slot(float, float)
    def addAoiVertex(self, x: float, y: float) -> None:  # noqa: N802
        """Place one vertex in map coordinates, as a click would.

        The same path a click takes, so a gate driving the AOI drives the real
        thing rather than a second implementation of it.
        """
        if not self._aoi.drawing:
            self._aoi.begin()
        self._aoi.add(x, y)
        self.aoiChanged.emit()
        self.update()

    @Slot(result=bool)
    def undoAoiVertex(self) -> bool:  # noqa: N802
        """Remove the last vertex placed."""
        removed = self._aoi.undo()
        if removed:
            self.aoiChanged.emit()
            self.update()
        return removed

    @Slot()
    def cancelAoi(self) -> None:  # noqa: N802
        """Abandon the drawing. P-110: no version, no record, nothing left."""
        self._aoi.cancel()
        self.aoiChanged.emit()
        self.update()

    @Slot(result="QVariant")
    def aoiPolygon(self) -> list:  # noqa: N802
        """The AOI's vertices in map coordinates, ready to persist."""
        return [[x, y] for x, y in self._aoi.points]

    @Slot("QVariant")
    def setAoiPolygon(self, points: list) -> None:  # noqa: N802
        """Restore a saved AOI. Map coordinates, in the layer's CRS."""
        self._aoi.points = [(float(p[0]), float(p[1])) for p in points or []]
        self._aoi.drawing = False
        self.aoiChanged.emit()
        self.update()

    # ---- measurement ----------------------------------------------------

    def _recompute_measurement(self) -> None:
        """Length or area of what is being measured, refused where it has no
        meaning. The refusal names the CRS instead of returning a number."""
        source = self._source
        geographic = bool(source is not None and source.crs
                          and source.crs.is_geographic)
        try:
            tools.require_metric(geographic, self._crs_name)
        except tools.GeographicCrsRefused as refusal:
            self._measurement = ""
            self._measure.cancel()
            self.refused.emit(str(refusal))
            self.aoiChanged.emit()
            return

        unit = self._crs_unit or "units"
        points = self._measure.points
        if self._tool == tools.MEASURE_AREA:
            self._measurement = (
                tools.format_area(tools.polygon_area(points), unit)
                if len(points) >= 3 else "")
        else:
            self._measurement = (
                tools.format_distance(tools.polyline_length(points), unit)
                if len(points) >= 2 else "")
        if self._measurement:
            self.measured.emit(self._measurement)
        self.aoiChanged.emit()

    @Slot()
    def clearMeasurement(self) -> None:  # noqa: N802
        self._measure.cancel()
        self._measurement = ""
        self.aoiChanged.emit()
        self.update()

    @Slot(result=bool)
    def undoMeasureVertex(self) -> bool:  # noqa: N802
        removed = self._measure.undo()
        if removed:
            self._recompute_measurement()
            self.update()
        return removed

    # ---- reporting ------------------------------------------------------

    @Slot(result="QVariant")
    def layerSummary(self) -> dict:  # noqa: N802
        """What the inspector shows. Units and CRS stated, never implied."""
        painted = self._active_painted()
        if self._source is None:
            # A point layer has no raster to report a level of detail for; it
            # reports what it is instead of reporting nothing.
            if painted is None:
                return {}
            if painted.parts is not None:
                # A silhouette has no values, so it reports no statistics and
                # no unit — saying "0" for either would read as a measurement.
                return {
                    "name": painted.name,
                    "crs": painted.crs,
                    "crs_unit": painted.crs_unit,
                    "kind": "geometry",
                    "parts": len(painted.parts),
                    "vertices": int(sum(p.shape[0] for p in painted.parts)),
                    "colormap": painted.style.get("colormap", "viridis"),
                    "extent": (list(painted.extent.as_tuple())
                               if painted.extent else None),
                }
            if painted.points is None:
                return {}
            return {
                "name": painted.name,
                "crs": painted.crs,
                "crs_unit": painted.crs_unit,
                "unit": painted.unit,
                "kind": "points",
                "points": int(painted.points.shape[0]),
                "colormap": painted.style.get("colormap", "viridis"),
                "extent": list(painted.extent.as_tuple()) if painted.extent else None,
            }
        summary: dict[str, Any] = {
            "name": self._layer_name,
            "crs": self._crs_name,
            "crs_unit": self._crs_unit,
            "unit": self._unit,
            "width": self._source.width,
            "height": self._source.height,
            "colormap": self._colormap,
            "lod": self._get_lod(),
            "pixels_read": self._source.pixels_read,
            "cache": self._source.cache.stats(),
        }
        if self._full_extent:
            summary["extent"] = list(self._full_extent.as_tuple())
        rgba = self._rgba.get("main")
        if rgba is not None:
            summary["displayed_pixels"] = int(rgba.shape[0] * rgba.shape[1])
        return summary

    @Slot(result="QVariant")
    def viewportInfo(self) -> dict:  # noqa: N802
        if self._viewport is None:
            return {}
        extent = self._viewport.fitted_extent
        return {
            "extent": list(extent.as_tuple()),
            "scale": self._viewport.scale,
            "lod": self._get_lod(),
            "pixel_width": self._viewport.pixel_width,
            "pixel_height": self._viewport.pixel_height,
        }

    @property
    def source(self) -> RasterSource | None:
        """For the gate, which measures what was read. Not for QML."""
        return self._source

    @property
    def viewport(self) -> Viewport | None:
        return self._viewport

    def set_viewport(self, viewport: Viewport) -> None:
        """Drive the canvas from a gate without a mouse."""
        self._viewport = viewport
        self._invalidate()
        self.viewportChanged.emit()


def _affine_for(extent: tuple[float, float, float, float],
                width: int, height: int):  # noqa: ANN202 - affine.Affine
    """The transform of a north-up grid covering `extent`."""
    from affine import Affine

    left, bottom, right, top = extent
    return Affine((right - left) / width, 0.0, left,
                  0.0, -(top - bottom) / height, top)


def _nice_number(value: float) -> float:
    """Round down to 1, 2 or 5 times a power of ten.

    A scale bar reading "1 km" is read; one reading "1.37 km" is not.
    """
    if value <= 0:
        return 1.0
    exponent = np.floor(np.log10(value))
    base = 10.0 ** exponent
    for step in (5.0, 2.0, 1.0):
        if value >= step * base:
            return step * base
    return base
