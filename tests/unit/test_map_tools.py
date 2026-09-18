"""The map's tools: one mode at a time, and a measurement that refuses.

P-109 — the AOI is drawn only while its tool is on.
P-110 — cancelling a drawing records nothing.
P-113 — exactly one mode is active, and the canvas is the one that knows.
P-114 — a measurement is refused on a geographic CRS, and matches an
        independent calculation on a projected one.
"""
from __future__ import annotations

import math
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from geopotential_app.render.geocanvas import tools  # noqa: E402

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


RASTER = _data_dir() / "utah_forge" / "Distance_to_fault.tif"

try:
    from PySide6.QtGui import QGuiApplication
    HAVE_QT = True
except ImportError:                                      # pragma: no cover
    HAVE_QT = False


def _app():
    return QGuiApplication.instance() or QGuiApplication(sys.argv[:1])


class TheSketch(unittest.TestCase):
    def test_a_vertex_lands_only_while_drawing(self) -> None:
        sketch = tools.Sketch()
        sketch.add(1.0, 2.0)
        self.assertEqual(len(sketch), 0)
        sketch.begin()
        sketch.add(1.0, 2.0)
        self.assertEqual(len(sketch), 1)

    def test_undo_removes_the_last_vertex(self) -> None:
        sketch = tools.Sketch()
        sketch.begin()
        sketch.add(0.0, 0.0)
        sketch.add(1.0, 1.0)
        self.assertTrue(sketch.undo())
        self.assertEqual(sketch.points, [(0.0, 0.0)])
        self.assertTrue(sketch.undo())
        self.assertFalse(sketch.undo())

    def test_cancelling_leaves_nothing(self) -> None:
        """P-110. Not "stops drawing" — leaves nothing."""
        sketch = tools.Sketch()
        sketch.begin()
        for x in range(4):
            sketch.add(float(x), 0.0)
        sketch.cancel()
        self.assertEqual(sketch.points, [])
        self.assertFalse(sketch.drawing)

    def test_finishing_keeps_the_vertices_and_stops_drawing(self) -> None:
        sketch = tools.Sketch()
        sketch.begin()
        sketch.add(0.0, 0.0)
        sketch.add(1.0, 0.0)
        sketch.add(1.0, 1.0)
        kept = sketch.finish()
        self.assertEqual(len(kept), 3)
        self.assertFalse(sketch.drawing)


class Measuring(unittest.TestCase):
    def test_a_geographic_crs_is_refused_by_name(self) -> None:
        """P-114. Refused, never approximated, and the refusal names the CRS."""
        with self.assertRaises(tools.GeographicCrsRefused) as refusal:
            tools.require_metric(True, "EPSG:4326")
        self.assertIn("EPSG:4326", str(refusal.exception))
        self.assertIn("degrees", str(refusal.exception))

    def test_a_projected_crs_is_allowed(self) -> None:
        tools.require_metric(False, "EPSG:26912")     # raises nothing

    def test_a_length_matches_an_independent_calculation(self) -> None:
        """Tolerance declared before the test: exact to 1e-9 of a metre, since
        both sides are the same plane arithmetic in float64."""
        points = [(0.0, 0.0), (300.0, 400.0), (300.0, 1000.0)]
        expected = math.hypot(300.0, 400.0) + 600.0
        self.assertAlmostEqual(tools.polyline_length(points), expected, delta=1e-9)

    def test_an_area_matches_an_independent_calculation(self) -> None:
        square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        self.assertAlmostEqual(tools.polygon_area(square), 10_000.0, delta=1e-9)
        triangle = [(0.0, 0.0), (300.0, 0.0), (0.0, 400.0)]
        self.assertAlmostEqual(tools.polygon_area(triangle), 60_000.0, delta=1e-9)

    def test_the_winding_direction_does_not_change_the_area(self) -> None:
        square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        self.assertEqual(tools.polygon_area(square),
                         tools.polygon_area(list(reversed(square))))

    def test_fewer_than_three_vertices_have_no_area(self) -> None:
        self.assertEqual(tools.polygon_area([(0.0, 0.0), (1.0, 1.0)]), 0.0)

    def test_a_measurement_is_written_with_its_unit(self) -> None:
        self.assertIn("km", tools.format_distance(2500.0, "metre"))
        self.assertIn("m", tools.format_distance(250.0, "metre"))
        self.assertIn("km²", tools.format_area(4e6, "metre"))
        self.assertIn("m²", tools.format_area(400.0, "metre"))


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TheCanvasMode(unittest.TestCase):
    def _item(self):
        from geopotential_app.render.geocanvas.map_item import MapItem

        _app()
        item = MapItem()
        item.setWidth(400)
        item.setHeight(300)
        return item

    def test_it_starts_in_navigate(self) -> None:
        self.assertEqual(self._item().toolMode, tools.NAVIGATE)

    def test_exactly_one_mode_is_active(self) -> None:
        """P-113. Setting a mode replaces the previous one; there is one value
        and the toolbar reads it, so the two cannot disagree."""
        item = self._item()
        for mode in tools.MODES:
            item.toolMode = mode
            self.assertEqual(item.toolMode, mode)

    def test_an_unknown_mode_is_ignored(self) -> None:
        item = self._item()
        item.toolMode = "teleport"
        self.assertEqual(item.toolMode, tools.NAVIGATE)

    def test_leaving_a_mode_leaves_no_sketch_behind(self) -> None:
        """P-109. The defect: a polygon that outlived the tool that drew it."""
        item = self._item()
        item.beginAoi()
        item.setAoiPolygon([[0, 0], [1, 0], [1, 1]])
        self.assertEqual(item.aoiPointCount, 3)
        item.toolMode = tools.NAVIGATE
        self.assertEqual(item.aoiPointCount, 0)
        self.assertFalse(item.aoiDrawing)

    def test_cancelling_an_aoi_records_nothing(self) -> None:
        item = self._item()
        item.beginAoi()
        item.setAoiPolygon([[0, 0], [1, 0], [1, 1]])
        item.cancelAoi()
        self.assertEqual(item.aoiPolygon(), [])
        self.assertEqual(item.aoiPointCount, 0)

    def test_undo_takes_back_one_vertex(self) -> None:
        item = self._item()
        item.beginAoi()
        item.setAoiPolygon([[0, 0], [1, 0], [1, 1]])
        item._aoi.drawing = True                  # as it is while drawing
        self.assertTrue(item.undoAoiVertex())
        self.assertEqual(item.aoiPointCount, 2)

    def test_the_stack_is_reconciled_in_one_call(self) -> None:
        """`applyStack` is idempotent: the display stack is the authority and
        the canvas keeps no second opinion."""
        self.assertTrue(RASTER.exists(), "the smoke raster is missing")
        item = self._item()
        snapshot = [{"layerId": "L1", "path": str(RASTER), "name": "one",
                     "unit": "m", "colormap": "magma", "invert": False,
                     "vmin": None, "vmax": None, "opacity": 1.0,
                     "visible": True}]
        item.applyStack(snapshot)
        self.assertEqual(item.layerCount, 1)
        item.applyStack(snapshot)
        self.assertEqual(item.layerCount, 1)
        item.applyStack([])
        self.assertEqual(item.layerCount, 0)
        self.assertFalse(item.hasLayer)


class TheToolbarsIcons(unittest.TestCase):
    """Every button on the toolbar names an icon that exists.

    This was the glyph test: it rendered each `➤`, `◎`, `⬠` and failed if the
    interface font had no glyph for it, because an empty box is a button whose
    meaning is gone. Two shipped that way in the first capture of E3 — `⛶` and
    `⭳` — and were found by looking, which is the expensive way.

    The buttons are SVG now, so the failure mode moved: a typo in a path is a
    magenta square at runtime, and it is caught here instead. The rule is the
    same one, and stricter — a font either has a codepoint or it does not, but
    a file either is there or is not.
    """

    QML = (Path(__file__).resolve().parents[2] / "app" / "geopotential_app"
           / "qml" / "GeoPotential")
    ICONS = QML / "icons"

    def _names(self, filename: str) -> list[str]:
        source = (self.QML / filename).read_text(encoding="utf-8")
        return re.findall(r'iconName:\s*"([^"]+)"', source)

    def test_every_toolbar_button_names_an_icon_file(self) -> None:
        names = self._names("MapToolBar.qml")
        self.assertTrue(names, "no icons found on the toolbar")
        for name in names:
            self.assertTrue((self.ICONS / f"{name}.svg").is_file(),
                            f"{name}.svg is named by MapToolBar.qml and is "
                            f"not in {self.ICONS}")

    def test_every_icon_named_anywhere_in_the_shell_exists(self) -> None:
        """The toolbar is not the only place icons are named."""
        named = 0
        for qml in sorted(self.QML.glob("*.qml")):
            for name in self._names(qml.name):
                named += 1
                self.assertTrue(
                    (self.ICONS / f"{name}.svg").is_file(),
                    f"{qml.name} names {name}, which is not a file")
        self.assertGreater(named, 20,
                           "the shell should name more icons than this; a "
                           "regex that stopped matching would also pass")

    def test_no_button_still_carries_a_text_glyph(self) -> None:
        """The reason the glyph test existed is the reason not to go back."""
        source = (self.QML / "MapToolBar.qml").read_text(encoding="utf-8")
        self.assertNotIn('text: "', source,
                         "a toolbar button went back to a text glyph")

    def test_every_icon_button_says_what_it_is(self) -> None:
        """An icon without a tooltip is a rebus.

        This is the whole contract of replacing words with pictures: the word
        does not disappear, it moves to the hover. `IconButton` declares `tip`
        required, which catches a use that omits it entirely — it does not
        catch one that sets it to `""`, and that is what this is for.
        """
        pattern = re.compile(
            r"IconButton\s*\{(.*?)\n(\s*)\}", re.S)
        checked = 0
        for qml in sorted(self.QML.glob("*.qml")):
            source = qml.read_text(encoding="utf-8")
            # `component Tool: IconButton { ... }` re-exports it; the uses of
            # `Tool` are checked through their own `tip:` below.
            for block in re.findall(r"(?:IconButton|Tool)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
                                    source):
                if "iconName:" not in block:
                    continue      # the component declaration, not a use
                checked += 1
                found = re.search(r"tip:\s*(.+)", block)
                self.assertIsNotNone(
                    found, f"{qml.name}: an icon button carries no tip")
                self.assertNotIn(
                    found.group(1).strip(), ('""', "''"),
                    f"{qml.name}: an icon button's tip is empty")
        self.assertGreater(checked, 15,
                           "too few icon buttons found; a regex that stopped "
                           "matching would also pass this")

    def test_the_icon_set_matches_its_generator(self) -> None:
        """`tools/make_icons.py` is the source; the files are its output.

        An icon edited by hand is an icon that the next regeneration silently
        reverts, and the whole point of one generator is that 35 icons stay
        one family.
        """
        import subprocess

        root = Path(__file__).resolve().parents[2]
        done = subprocess.run(
            [sys.executable, str(root / "tools" / "make_icons.py"), "--check"],
            capture_output=True, text=True)
        self.assertEqual(done.returncode, 0,
                         done.stderr.strip() or done.stdout.strip())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TheIconsAreDrawnAndTinted(unittest.TestCase):
    """The provider renders a file and paints it the colour asked for.

    The obvious way to recolour an icon is a shader — `ColorOverlay`, or
    `MultiEffect`. Both were tried and **both draw nothing under the offscreen
    platform**, which is the platform every storyboard is captured with: the
    evidence would have been blank squares in frames the gate still passed.
    So the tint is a `QPainter` composition, and this checks it on the render
    path a headless run actually uses.
    """

    def setUp(self) -> None:
        _app()
        from geopotential_app.icons import IconProvider

        root = (Path(__file__).resolve().parents[2] / "app"
                / "geopotential_app" / "qml" / "GeoPotential" / "icons")
        self.provider = IconProvider(root)

    def _request(self, request_id: str, side: int = 24):
        from PySide6.QtCore import QSize

        return self.provider.requestImage(request_id, QSize(), QSize(side, side))

    def test_an_icon_is_painted_in_the_colour_requested(self) -> None:
        image = self._request("tools/identify?color=ff0000")
        self.assertEqual((image.width(), image.height()), (24, 24))
        seen = {image.pixelColor(x, y).name()
                for x in range(24) for y in range(24)
                if image.pixelColor(x, y).alpha() > 200}
        self.assertTrue(seen, "the icon rendered nothing at all")
        self.assertEqual(seen, {"#ff0000"},
                         f"the tint left other colours behind: {sorted(seen)}")

    def test_the_same_icon_in_two_colours_differs(self) -> None:
        """A theme change has to actually change the picture."""
        light = self._request("app/run?color=ffffff")
        dark = self._request("app/run?color=101010")
        self.assertNotEqual(light.pixelColor(12, 12), dark.pixelColor(12, 12))

    def test_a_missing_icon_is_loud_not_silent(self) -> None:
        """A blank square passes every screenshot check ever written."""
        image = self._request("tools/there-is-no-such-icon?color=ffffff")
        self.assertEqual(image.pixelColor(12, 12).name(), "#ff00ff")

    def test_a_request_cannot_climb_out_of_the_icons_directory(self) -> None:
        """The id is a string from QML; a provider that resolves `..` is a
        file read with a URL in front of it."""
        image = self._request("../../../../etc/passwd?color=ffffff")
        self.assertEqual(image.pixelColor(12, 12).name(), "#ff00ff")

    def test_an_absurd_size_is_capped(self) -> None:
        image = self._request("app/run?color=ffffff", side=9000)
        self.assertLessEqual(image.width(), 256)


if __name__ == "__main__":
    unittest.main()
