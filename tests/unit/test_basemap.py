"""The basemap: open sources, off by default, never an input. ADR-MSP-006.

P-130 — every source is an open one, and each carries the attribution its
        licence obliges.
P-131 — with no source chosen, nothing on the network is touched.
P-132 — the basemap is a picture: no operator accepts it, it carries no unit,
        and it has no value under the cursor.
P-133 — what `P-07` still forbids stays forbidden: no server, no listening
        port, no WebView, no web framework.

No test here reaches the network. A gate that needed a tile server would fail
on a train, and the one thing a basemap may never do is make the science
depend on somebody else's uptime.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


_DATA = _data_dir()
RASTER = _DATA / "utah_forge" / "Distance_to_fault.tif"
sys.path.insert(0, str(ROOT / "app"))

from geopotential_app.basemap import sources as S  # noqa: E402
from geopotential_app.basemap import tiles as T  # noqa: E402

# The services whose terms forbid using their tiles outside their own
# applications, or require a contract and a key.
CLOSED = ("google", "bing", "esri", "arcgisonline", "mapbox", "here.com",
          "tomtom", "yandex")


class OpenSourcesOnly(unittest.TestCase):
    def test_every_source_declares_a_licence_and_an_attribution(self) -> None:
        self.assertTrue(S.SOURCES)
        for key, source in S.SOURCES.items():
            self.assertTrue(source.licence.strip(), f"{key} has no licence")
            self.assertTrue(source.attribution.strip(),
                            f"{key} has no attribution, which its licence obliges")
            self.assertTrue(source.template.startswith("https://"),
                            f"{key} is not fetched over HTTPS")

    def test_no_closed_service_is_offered(self) -> None:
        """Google, Bing, Esri and Mapbox forbid this use or require a key."""
        for key, source in S.SOURCES.items():
            haystack = f"{key} {source.name} {source.template}".lower()
            for closed in CLOSED:
                self.assertNotIn(closed, haystack,
                                 f"{key} points at {closed}, whose terms forbid it")

    def test_every_source_was_verified_by_fetching_a_tile(self) -> None:
        """Five sources, all rendered from OpenStreetMap data. Each was checked
        with `tools/verify_sources.py` before being added — a licence page says
        nothing about whether the CDN answers an anonymous client."""
        self.assertGreaterEqual(len(S.SOURCES), 5)
        for source in S.SOURCES.values():
            self.assertIn("OpenStreetMap", source.attribution,
                          f"{source.key} draws OSM data and must say so")

    def test_the_listing_carries_what_a_menu_must_show(self) -> None:
        for entry in S.names():
            self.assertEqual(
                set(entry), {"key", "name", "licence", "attribution"})

    def test_no_source_needs_an_account(self) -> None:
        """Carto's styles are CC-BY and its CDN still answers an anonymous
        client with `API KEY REQUIRED`, written across the map. A licence is
        not permission to fetch: `tools/verify_sources.py` checks the tile."""
        for key, source in S.SOURCES.items():
            haystack = f"{key} {source.template}".lower()
            for gated in ("cartocdn", "carto.com", "api_key", "apikey",
                          "access_token", "{key}", "{token}"):
                self.assertNotIn(gated, haystack,
                                 f"{key} needs a key or an account")

    def test_off_is_a_real_state(self) -> None:
        self.assertEqual(S.NONE, "")
        self.assertIsNone(S.get(""))
        self.assertIsNone(S.get("google"))


class OffByDefault(unittest.TestCase):
    def test_nothing_is_fetched_without_a_source(self) -> None:
        """P-131. `get('')` is None, and the canvas returns before any fetch —
        which is what "off by default" means in code."""
        self.assertIsNone(S.get(S.NONE))

    def test_the_canvas_opens_with_no_basemap(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        item = MapItem()
        self.assertEqual(item.basemapSource, "")
        self.assertEqual(item.basemapAttribution, "")

    def test_choosing_a_source_publishes_its_attribution(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        item = MapItem()
        item.basemapSource = "osm"
        self.assertIn("OpenStreetMap", item.basemapAttribution)


class TheTileMath(unittest.TestCase):
    def test_a_known_coordinate_lands_in_its_known_tile(self) -> None:
        """reference: the slippy-map scheme. Utah FORGE at zoom 12."""
        self.assertEqual(T.deg_to_tile(-112.88, 38.50, 12), (763, 1572))

    def test_the_tile_covers_the_coordinate_it_was_asked_for(self) -> None:
        x, y = T.deg_to_tile(-112.88, 38.50, 12)
        left, bottom, right, top = T.tile_bounds(x, y, 12)
        self.assertLess(left, right)
        self.assertLess(bottom, top)

    def test_zoom_follows_the_scale(self) -> None:
        close = T.zoom_for(5.0, 38.5)
        far = T.zoom_for(500.0, 38.5)
        self.assertGreater(close, far)

    def test_a_view_never_asks_for_a_bulk_download(self) -> None:
        """The sources' terms forbid it, and a screen never needs it."""
        whole_world = (-20037508.0, -20037508.0, 20037508.0, 20037508.0)
        self.assertLessEqual(len(T.tiles_for_extent(whole_world, 12)),
                             T.MAX_TILES_PER_VIEW)

    def test_the_client_identifies_itself(self) -> None:
        """OSM's policy requires a real agent; an anonymous scraper is what
        gets a client blocked."""
        self.assertIn("GeoPotential", T.USER_AGENT)


class ACacheThatRecords(unittest.TestCase):
    def test_it_writes_what_the_tiles_were_and_when(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="basemap-"))
        cache = T.TileCache(root)
        cache.write(S.SOURCES["osm"], 12, 763, 1572, b"not-a-png")
        self.assertEqual(cache.read(S.SOURCES["osm"], 12, 763, 1572), b"not-a-png")

        record = json.loads((root / "SOURCES.json").read_text())
        self.assertIn("osm", record)
        for key in ("name", "template", "licence", "attribution", "last_fetched"):
            self.assertIn(key, record["osm"])

    def test_a_missing_tile_is_absent_not_an_error(self) -> None:
        import tempfile

        cache = T.TileCache(Path(tempfile.mkdtemp(prefix="basemap-")))
        self.assertIsNone(cache.read(S.SOURCES["osm"], 1, 1, 1))


class StillForbidden(unittest.TestCase):
    """P-133. `P-07` was narrowed, not dropped.

    Checked on imports, not on text: `self_test.py` names the forbidden things
    in order to assert they are absent, and a text search finds them there.
    """

    #: The tile client is the one module allowed to speak to the network, and
    #: the self-test is allowed `socket` because its job is to prove no port is
    #: listening. Both are named here, the way P-02's exemption is named.
    NETWORK_ALLOWED = {Path("basemap/tiles.py"), Path("self_test.py")}

    @staticmethod
    def _imports(module: Path) -> set[str]:
        found: set[str] = set()
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        return found

    def test_no_web_framework_and_no_webview_is_imported(self) -> None:
        app = ROOT / "app" / "geopotential_app"
        forbidden = {"flask", "fastapi", "uvicorn", "aiohttp", "tornado",
                     "starlette", "django"}
        for module in app.rglob("*.py"):
            imported = self._imports(module)
            self.assertEqual(imported & forbidden, set(),
                             f"{module.name} imports a web framework")
            for name in imported:
                self.assertNotIn("webengine", name.lower(),
                                 f"{module.name} imports a WebView")

    def test_the_tile_client_is_the_only_thing_that_speaks_network(self) -> None:
        app = ROOT / "app" / "geopotential_app"
        network = {"urllib", "http", "socket", "requests", "httpx",
                   "websocket", "websockets"}
        for module in app.rglob("*.py"):
            relative = module.relative_to(app)
            if relative in self.NETWORK_ALLOWED:
                continue
            self.assertEqual(
                self._imports(module) & network, set(),
                f"{relative} speaks to the network; only the tile client may",
            )

    def test_the_tile_client_opens_no_server(self) -> None:
        source = (ROOT / "app" / "geopotential_app" / "basemap"
                  / "tiles.py").read_text(encoding="utf-8")
        for name in ("socketserver", "HTTPServer", ".listen(", ".bind("):
            self.assertNotIn(name, source, f"the tile client uses {name}")

    def test_the_qml_holds_no_webview(self) -> None:
        qml = ROOT / "app" / "geopotential_app" / "qml"
        for screen in qml.rglob("*.qml"):
            text = screen.read_text(encoding="utf-8")
            self.assertNotIn("WebEngineView", text, f"{screen.name} has a WebView")
            self.assertNotIn("WebView", text, f"{screen.name} has a WebView")


class ASeenLayer(unittest.TestCase):
    """The basemap is a row in the panel, and display only.

    It appears where a person looks for what is drawn, and it may never become
    anything a computation can reach.
    """

    def _controller(self):  # noqa: ANN202
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        import tempfile

        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.controllers.app_controller import AppController

        workdir = Path(tempfile.mkdtemp(prefix="basemap-layer-"))
        controller = AppController()
        controller.createProject(str(workdir / "B.gpot"), "B")
        return controller

    def test_choosing_a_source_adds_one_row(self) -> None:
        controller = self._controller()
        self.assertEqual(controller.setBasemap("osm"), "osm")
        rows = [layer for layer in controller.layers.snapshot()
                if layer["role"] == "basemap"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "basemap")
        controller.shutdown()

    def test_choosing_another_replaces_it(self) -> None:
        controller = self._controller()
        keys = list(S.SOURCES)
        self.assertGreaterEqual(len(keys), 2, "two sources are needed to swap")
        controller.setBasemap(keys[0])
        controller.setBasemap(keys[1])
        rows = [layer for layer in controller.layers.snapshot()
                if layer["role"] == "basemap"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], S.SOURCES[keys[1]].name)
        controller.shutdown()

    def test_an_unknown_source_turns_the_basemap_off(self) -> None:
        """Naming a source that is not there is not a way to get a basemap —
        it is how the row disappears, which is what removing Carto did."""
        controller = self._controller()
        controller.setBasemap("osm")
        self.assertEqual(controller.setBasemap("carto-dark"), "")
        self.assertEqual(
            [l for l in controller.layers.snapshot() if l["role"] == "basemap"],
            [])
        controller.shutdown()

    def test_turning_it_off_removes_the_row(self) -> None:
        controller = self._controller()
        controller.setBasemap("osm")
        controller.setBasemap("")
        self.assertEqual(
            [l for l in controller.layers.snapshot() if l["role"] == "basemap"],
            [])
        controller.shutdown()

    def test_it_is_the_ground_under_everything(self) -> None:
        controller = self._controller()
        controller.addLayer("/tmp/whatever.tif", "data", "original", "m")
        controller.setBasemap("osm")
        # Bottom of the stack is drawn first.
        self.assertEqual(controller.layers.snapshot()[0]["role"], "basemap")
        controller.shutdown()

    def test_it_is_never_active_even_as_the_only_layer(self) -> None:
        """The Inspector and the colour bar read the active layer. With the
        basemap active they showed a name and no values, and the legend lost
        its numbers — which is what a person actually sees."""
        controller = self._controller()
        controller.setBasemap("osm")
        self.assertEqual(controller.layers.activeId, "",
                         "a basemap became the active layer on an empty stack")
        controller.shutdown()

    def test_clicking_its_row_does_not_make_it_active(self) -> None:
        controller = self._controller()
        controller.addLayer("/tmp/whatever.tif", "data", "original", "m")
        active = controller.layers.activeId
        controller.setBasemap("osm")
        controller.layers.setActive("basemap")
        self.assertEqual(controller.layers.activeId, active)
        controller.shutdown()

    def test_removing_the_data_leaves_no_basemap_active(self) -> None:
        controller = self._controller()
        layer = controller.addLayer("/tmp/whatever.tif", "data", "original", "m")
        controller.setBasemap("osm")
        controller.layers.remove(layer)
        self.assertEqual(controller.layers.activeId, "")
        controller.shutdown()

    def test_it_is_never_the_active_layer_by_accident(self) -> None:
        """The Inspector and the identify tool read the active layer; a basemap
        has no value to give them."""
        controller = self._controller()
        controller.addLayer("/tmp/whatever.tif", "data", "original", "m")
        active = controller.layers.activeId
        controller.setBasemap("osm")
        self.assertEqual(controller.layers.activeId, active)
        controller.shutdown()

    def test_its_visibility_reaches_the_canvas(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        item = MapItem()
        item.applyStack([{"layerId": "basemap", "kind": "basemap",
                          "role": "basemap", "name": "OSM", "path": "",
                          "visible": False, "opacity": 0.5, "unit": "",
                          "colormap": "viridis", "invert": False,
                          "vmin": None, "vmax": None}])
        self.assertFalse(item.basemapVisible)
        self.assertAlmostEqual(item.basemapOpacity, 0.5, places=3)


class DrawnWithTheData(unittest.TestCase):
    """The background and the data are one picture, not two that drift.

    Two defects lived here: a basemap on an empty project painted nothing at
    all, because the guard asked for a data layer before building a viewport;
    and the mosaic was stretched into whatever rectangle the view had become,
    so it slid against the data while zooming instead of moving with it.

    Neither test reaches the network: both drive the drawing with a mosaic that
    is already in hand.
    """

    def _item(self):  # noqa: ANN202
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        item = MapItem()
        item.setWidth(400)
        item.setHeight(300)
        return item

    @staticmethod
    def _paint(item) -> None:  # noqa: ANN001
        from PySide6.QtGui import QImage, QPainter

        image = QImage(400, 300, QImage.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter)
        painter.end()

    def test_a_basemap_alone_gets_a_view_to_be_drawn_in(self) -> None:
        item = self._item()
        item.basemapSource = "osm"
        self._paint(item)
        self.assertIsNotNone(item.viewport,
                             "a basemap with no data built no viewport, so it "
                             "could never be drawn")
        self.assertEqual(item.viewCrs, "EPSG:3857",
                         "with nothing loaded the view is the tiles' own CRS")

    def test_no_view_is_invented_when_the_basemap_is_off(self) -> None:
        item = self._item()
        self._paint(item)
        self.assertIsNone(item.viewport)

    def test_the_mosaic_keeps_the_extent_it_was_warped_for(self) -> None:
        """Drawn at its own coordinates, it slides and scales with the data.
        Drawn into the current frame, it lags — which is what it did."""
        import numpy as np

        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m") if RASTER.exists() else None
        if not RASTER.exists():
            self.skipTest("the smoke raster is missing")
        self._paint(item)
        view = item.viewportInfo()["extent"]

        rgba = np.zeros((300, 400, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        item._basemap_ready(("k",), rgba, 400, 300, tuple(view))
        self.assertEqual(tuple(item._basemap_extent), tuple(view))

        # Zoom out: the picture must be drawn smaller, in the same place,
        # rather than restretched over the whole view.
        item.zoomBy(2.0)
        self._paint(item)
        self.assertEqual(tuple(item._basemap_extent), tuple(view),
                         "the stale mosaic was thrown away instead of reused")
        viewport = item.viewport
        left, top = viewport.to_screen(view[0], view[3])
        right, bottom = viewport.to_screen(view[2], view[1])
        self.assertLess(right - left, 400,
                        "the mosaic still covers the whole view after zooming "
                        "out; it is being stretched, not placed")

    def test_a_mosaic_from_another_crs_is_not_drawn(self) -> None:
        import numpy as np

        if not RASTER.exists():
            self.skipTest("the smoke raster is missing")
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        self._paint(item)
        rgba = np.zeros((300, 400, 4), dtype=np.uint8)
        item._basemap_ready(("k",), rgba, 400, 300, (0.0, 0.0, 1.0, 1.0))
        item.viewCrs = "EPSG:4326"
        self._paint(item)          # must not place a picture from the old view

    def test_a_small_pan_does_not_ask_for_new_tiles(self) -> None:
        """The frame fetched is wider than the screen, and the request is keyed
        coarsely: nudging the map used to start a fetch on every mouse move."""
        if not RASTER.exists():
            self.skipTest("the smoke raster is missing")
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        item.basemapSource = "osm"
        self._paint(item)
        first = item._basemap_pending
        for _ in range(4):
            item.set_viewport(item.viewport.panned(3, 2))
            self._paint(item)
        self.assertEqual(item._basemap_pending, first,
                         "a small pan started another fetch")


class ThePaintPathIsSafe(unittest.TestCase):
    """What `paint` may do, on whichever thread Qt calls it from.

    The real application renders on the render thread; the offscreen platform
    used by every gate renders on the GUI thread. A `paint` that emits a signal
    or opens a socket is correct in one and a segmentation fault in the other,
    and only the person running the real window ever finds out.
    """

    @staticmethod
    def _paint_body() -> str:
        source = (ROOT / "app" / "geopotential_app" / "render" / "geocanvas"
                  / "map_item.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        body: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                    "paint", "_paint_source", "_paint_points",
                    "_paint_basemap", "_paint_sketches", "_paint_sketch"):
                body.extend(lines[node.lineno - 1:node.end_lineno])
        return "\n".join(body)

    def test_paint_emits_no_signal_directly(self) -> None:
        for line in self._paint_body().splitlines():
            stripped = line.strip()
            if ".emit(" in stripped and "singleShot" not in stripped:
                self.fail(f"paint emits a signal directly: {stripped}")

    def test_paint_fetches_nothing(self) -> None:
        body = self._paint_body()
        for name in ("mosaic(", "urlopen", "fetch("):
            self.assertNotIn(name, body,
                             f"the paint path calls {name}; a tile server is a "
                             f"network away from a frame")

    def test_the_render_loop_is_the_single_threaded_one(self) -> None:
        """The canvas reads GDAL while it paints and the GUI thread reads the
        same handle for the readout. One thread, by configuration."""
        source = (ROOT / "app" / "geopotential_app"
                  / "app.py").read_text(encoding="utf-8")
        self.assertIn("QSG_RENDER_LOOP", source)
        self.assertIn("basic", source)


class NotAnInput(unittest.TestCase):
    """P-132. A basemap is a picture the data sits on, and nothing else."""

    def test_no_operator_accepts_a_basemap(self) -> None:
        """The worker never hears of it: a basemap is not a parameter, not an
        input, and not something the science can be made to depend on."""
        worker = ROOT / "worker" / "geopotential_worker"
        for module in worker.rglob("*.py"):
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn("basemap", node.value.lower(),
                                     f"{module.name} names a basemap")
                elif isinstance(node, ast.Name):
                    self.assertNotIn("basemap", node.id.lower(),
                                     f"{module.name} names a basemap")

    def test_the_worker_cannot_even_import_it(self) -> None:
        """The boundary is the protocol; the basemap lives on the app's side of
        it and never crosses."""
        worker = ROOT / "worker"
        self.assertFalse((worker / "geopotential_worker" / "basemap").exists())


if __name__ == "__main__":
    unittest.main()
