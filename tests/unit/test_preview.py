"""The preview: bounded, declared, and never an input. ADR-MSP-004.

P-117 — the `preview` block respects its ceiling, declares decimation, and is
        not accepted by any operator.
P-118 — previewing creates no row in the store and commits no run (checked in
        `--only import`; here the preview itself is proved harmless).

And the drawing side: a table has to become *visible*, or importing a CSV adds
a row to the project and nothing to the screen — which reads as nothing having
happened, and did.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

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
sys.path.insert(0, str(ROOT / "worker"))
sys.path.insert(0, str(ROOT / "app"))

from geopotential_app.render import geometry as geometry_render  # noqa: E402
from geopotential_app.render import points as point_render  # noqa: E402
from geopotential_worker.io import preview  # noqa: E402
from geopotential_worker.io.describe import describe  # noqa: E402

TABLE = _DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
VECTOR = _DATA / "synthetic" / "blocks.shp"


class Ceilings(unittest.TestCase):
    def test_a_point_cloud_is_capped(self) -> None:
        n = preview.MAX_POINTS * 7
        x = np.linspace(0.0, 1000.0, n)
        block = preview.points(x, x, x)
        self.assertLessEqual(len(block["points"]), preview.MAX_POINTS)
        self.assertTrue(block["decimated"])
        self.assertEqual(block["source_rows"], n)

    def test_a_small_cloud_is_not_decimated(self) -> None:
        x = np.linspace(0.0, 10.0, 100)
        block = preview.points(x, x, x)
        self.assertEqual(len(block["points"]), 100)
        self.assertFalse(block["decimated"])

    def test_the_sample_spans_the_whole_file(self) -> None:
        """Taking the first n would preview one corner of a survey and call it
        the survey."""
        n = preview.MAX_POINTS * 4
        x = np.linspace(0.0, 1000.0, n)
        taken = [p[0] for p in preview.points(x, x, x)["points"]]
        self.assertLess(taken[0], 1.0)
        self.assertGreater(taken[-1], 900.0)

    def test_a_null_value_stays_null(self) -> None:
        """A point with no measurement is not a point with a low value."""
        x = np.array([0.0, 1.0, 2.0])
        values = np.array([1.0, np.nan, 3.0])
        block = preview.points(x, x, values)
        self.assertIsNone(block["points"][1][2])

    def test_a_non_finite_coordinate_is_dropped(self) -> None:
        x = np.array([0.0, np.nan, 2.0])
        block = preview.points(x, x, None)
        self.assertEqual(block["source_rows"], 2)

    def test_the_block_is_json(self) -> None:
        """It crosses the IPC boundary, so it has to encode."""
        x = np.linspace(0.0, 1.0, 50)
        json.dumps(preview.points(x, x, x))


@unittest.skipUnless(TABLE.exists(), "the smoke table is missing")
class ARealTable(unittest.TestCase):
    def test_a_csv_previews_its_rows_and_its_points(self) -> None:
        block = describe(TABLE).as_dict()["preview"]
        self.assertEqual(block["kind"], "points")
        self.assertLessEqual(len(block["rows"]), preview.MAX_ROWS)
        self.assertLessEqual(len(block["points"]), preview.MAX_POINTS)
        self.assertEqual(block["columns"], ["easting", "northing", "gCBGA"])

    def test_the_description_still_encodes_as_json(self) -> None:
        payload = json.dumps(describe(TABLE).as_dict())
        self.assertLess(len(payload), 4_000_000, "the description got huge")

    def test_the_preview_is_not_an_operator_input(self) -> None:
        """P-117. No operator declares a `preview` parameter, and none reads
        one: it exists to be looked at, and every number the project uses is
        read from the file."""
        import geopotential_worker.operators as operators
        from geopotential_worker.operators import registry

        described = json.dumps(registry.describe_all())
        self.assertNotIn("preview", described,
                         "an operator declares a preview parameter")

        package = Path(operators.__file__).parent
        for module in sorted(package.glob("*.py")):
            source = module.read_text(encoding="utf-8")
            self.assertNotIn('["preview"]', source, f"{module.name} reads a preview")
            self.assertNotIn('"preview"', source.replace('"preview" ', ""),
                             f"{module.name} mentions a preview")


class DrawingPoints(unittest.TestCase):
    def test_points_land_where_the_extent_says(self) -> None:
        rgba = point_render.to_rgba(
            np.array([0.0]), np.array([0.0]), None,
            width=101, height=101, extent=(-1.0, -1.0, 1.0, 1.0), radius=0,
        )
        self.assertEqual(int(rgba[50, 50, 3]), 255)      # the centre is drawn
        self.assertEqual(int(rgba[0, 0, 3]), 0)          # and only the centre

    def test_north_is_up(self) -> None:
        rgba = point_render.to_rgba(
            np.array([0.0]), np.array([0.9]), None,
            width=101, height=101, extent=(-1.0, -1.0, 1.0, 1.0), radius=0,
        )
        drawn = np.argwhere(rgba[..., 3] > 0)
        self.assertLess(drawn[0][0], 50, "a northern point drew below centre")

    def test_a_point_outside_the_extent_is_dropped_not_clamped(self) -> None:
        """Clamping would pile a survey's outliers onto the edge and invent a
        cluster that is not in the data."""
        rgba = point_render.to_rgba(
            np.array([50.0]), np.array([50.0]), None,
            width=64, height=64, extent=(-1.0, -1.0, 1.0, 1.0), radius=0,
        )
        self.assertEqual(int(rgba[..., 3].sum()), 0)

    def test_a_point_with_no_value_is_not_coloured_as_a_low_one(self) -> None:
        rgba = point_render.to_rgba(
            np.array([-0.5, 0.5]), np.array([0.0, 0.0]),
            np.array([np.nan, 10.0]),
            width=101, height=101, extent=(-1.0, -1.0, 1.0, 1.0), radius=0,
        )
        drawn = np.argwhere(rgba[..., 3] > 0)
        colours = {tuple(rgba[r, c, :3]) for r, c in drawn}
        self.assertIn((160, 160, 160), colours)

    def test_nothing_finite_draws_nothing(self) -> None:
        rgba = point_render.to_rgba(
            np.array([np.nan]), np.array([np.nan]), None,
            width=16, height=16, extent=(0.0, 0.0, 1.0, 1.0),
        )
        self.assertEqual(int(rgba[..., 3].sum()), 0)

    def test_bounds_give_a_single_point_an_area(self) -> None:
        box = point_render.bounds(np.array([5.0]), np.array([7.0]))
        self.assertIsNotNone(box)
        left, bottom, right, top = box
        self.assertLess(left, right)
        self.assertLess(bottom, top)

    def test_the_draw_path_holds_no_python_loop_over_points(self) -> None:
        """ADR-007. Every loop in `to_rgba` walks the marker's own footprint —
        at most (2r+1)² offsets — and never the points themselves.

        Checked by what the loop iterates, not by the text of the line: the
        footprint used to be spelled `range(-radius, …)` and is now a list of
        offsets, and the rule was never about the spelling.
        """
        source = (Path(point_render.__file__)).read_text(encoding="utf-8")
        body = source.split("def to_rgba", 1)[1].split("def bounds", 1)[0]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("for "):
                continue
            iterated = stripped.split(" in ", 1)[-1].rstrip(":")
            self.assertIn("footprint(", iterated,
                          f"a loop over something other than the marker's "
                          f"footprint: {stripped}")


@unittest.skipUnless(TABLE.exists(), "the smoke table is missing")
class ATableAloneIsDrawn(unittest.TestCase):
    """A project holding only tables has to paint.

    The guard in `paint` asked for a raster, so a point-only stack drew
    nothing — and every earlier check happened to have a raster in the stack,
    which is exactly why it survived.
    """

    def _drawn(self, item) -> int:
        from PySide6.QtGui import QImage, QPainter

        image = QImage(320, 240, QImage.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter)
        painter.end()
        buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
        pixels = buffer.reshape(240, 320, 4)
        return int((pixels[..., :3].sum(axis=2) > 30).sum())

    def test_a_point_layer_paints_with_no_raster_in_the_stack(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        block = describe(TABLE).as_dict()["preview"]
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        self.assertTrue(item.addPointLayer("P", block["points"], "t", "mGal",
                                           "EPSG:26912"))
        self.assertGreater(self._drawn(item), 100,
                           "a point-only stack painted nothing")

    def test_a_bigger_marker_draws_more(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        block = describe(TABLE).as_dict()["preview"]
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        item.addPointLayer("P", block["points"], "t", "mGal", "EPSG:26912")
        small = self._drawn(item)
        item.setLayerStyle("P", {"pointSize": 4, "outline": True})
        self.assertGreater(self._drawn(item), small)


class TheSixFormatsHaveAPreview(unittest.TestCase):
    """A22 — each of MSP-03's six formats opens the preview that suits it.

    The six collapse to three drawable kinds, and `PreviewMap.qml` has a branch
    for each. This asserts the mapping rather than trusting it: a seventh
    suffix added to `classify` without a branch would draw nothing and say
    nothing, which is the failure this catches.
    """

    #: The suffix each of the six formats arrives as, and the kind it must
    #: classify to. MSP-03: CSV, XYZ, GeoTIFF, COG, GeoPackage, Shapefile.
    SIX = {
        ".csv": "table", ".xyz": "table",
        ".tif": "raster", ".cog": "raster",
        ".gpkg": "vector", ".shp": "vector",
    }

    #: The kinds `PreviewMap.reload()` knows how to draw.
    DRAWABLE = {"raster", "vector", "table"}

    def test_every_format_classifies_to_a_drawable_kind(self) -> None:
        from geopotential_worker.io.describe import classify

        for suffix, expected in self.SIX.items():
            with self.subTest(suffix=suffix):
                kind = classify(Path(f"a{suffix}"))
                self.assertEqual(kind, expected)
                self.assertIn(kind, self.DRAWABLE)

    def test_the_preview_map_branches_on_every_drawable_kind(self) -> None:
        source = (ROOT / "app" / "geopotential_app" / "qml" / "GeoPotential"
                  / "PreviewMap.qml").read_text(encoding="utf-8")
        body = source.split("function reload()", 1)[1]
        for kind in self.DRAWABLE:
            self.assertIn(f'd.kind === "{kind}"', body,
                          f"PreviewMap draws nothing for a {kind}")


class GeometryCeilings(unittest.TestCase):
    """The silhouette obeys the same ceiling the points do (P-117)."""

    @staticmethod
    def _frame(parts):
        """A GeoDataFrame of line strings, without importing geopandas at
        module scope — the gate declares its dependencies per suite."""
        import geopandas as gpd
        import shapely
        return gpd.GeoDataFrame(
            {"id": list(range(len(parts)))},
            geometry=[shapely.LineString(p) for p in parts],
            crs="EPSG:31982",
        )

    def test_a_dense_geometry_is_capped_and_says_so(self) -> None:
        dense = np.column_stack([
            np.linspace(0.0, 1000.0, preview.MAX_VERTICES * 3),
            np.linspace(0.0, 1000.0, preview.MAX_VERTICES * 3),
        ])
        block = preview.geometry(self._frame([dense]))
        vertices = sum(len(part) for part in block["parts"])
        self.assertLessEqual(vertices, preview.MAX_VERTICES)
        self.assertTrue(block["decimated"])

    def test_many_features_are_sampled_and_declared(self) -> None:
        many = [[[float(i), 0.0], [float(i), 1.0]]
                for i in range(preview.MAX_FEATURES * 3)]
        block = preview.geometry(self._frame(many))
        self.assertLessEqual(block["shown"], preview.MAX_FEATURES)
        self.assertTrue(block["decimated"])
        self.assertEqual(block["source_features"], len(many))

    def test_a_small_layer_is_not_decimated(self) -> None:
        block = preview.geometry(self._frame([[[0, 0], [1, 1], [2, 0]]]))
        self.assertFalse(block["decimated"])
        self.assertEqual(block["shown"], 1)

    def test_the_block_is_json(self) -> None:
        json.dumps(preview.geometry(self._frame([[[0, 0], [1, 1]]])))


class DrawingGeometry(unittest.TestCase):
    """Values in, pixels out — the same contract `points` is held to."""

    RING = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]

    def test_a_ring_lands_where_the_extent_says(self) -> None:
        rgba = geometry_render.to_rgba(
            [self.RING], width=64, height=64, extent=(0, 0, 10, 10),
            thickness=0)
        drawn = rgba[..., 3] > 0
        # The ring is the border of the buffer, and nothing is in the middle.
        self.assertTrue(drawn[0].all() and drawn[-1].all())
        self.assertTrue(drawn[:, 0].all() and drawn[:, -1].all())
        self.assertFalse(drawn[32, 32])

    def test_north_is_up(self) -> None:
        """A part in the north half draws in the top half of the buffer."""
        north = [[0.0, 9.0], [10.0, 9.0]]
        rgba = geometry_render.to_rgba(
            [north], width=32, height=32, extent=(0, 0, 10, 10), thickness=0)
        rows = np.nonzero(rgba[..., 3] > 0)[0]
        self.assertLess(rows.max(), 16)

    def test_a_segment_is_continuous(self) -> None:
        """One sample per pixel crossed: a diagonal has no gaps in it.

        A rasteriser that samples by a fixed count leaves a dashed line on the
        long segments, which reads as a different geometry.
        """
        rgba = geometry_render.to_rgba(
            [[[0.0, 0.0], [10.0, 10.0]]], width=64, height=64,
            extent=(0, 0, 10, 10), thickness=0)
        rows, columns = np.nonzero(rgba[..., 3] > 0)
        self.assertEqual(len(set(rows.tolist())), 64, "the diagonal has gaps")
        # Every drawn pixel is on the true anti-diagonal.
        self.assertEqual(set((rows + columns).tolist()), {63})

    def test_a_part_outside_the_extent_is_dropped_not_clamped(self) -> None:
        """Clamping would draw a boundary that is not in the file."""
        rgba = geometry_render.to_rgba(
            [[[100.0, 100.0], [110.0, 110.0]]], width=32, height=32,
            extent=(0, 0, 10, 10))
        self.assertEqual(int((rgba[..., 3] > 0).sum()), 0)

    def test_parts_do_not_join_to_each_other(self) -> None:
        """Two separate lines are two lines, not a polyline through both.

        The segment index is built from every vertex except the last of each
        part; getting that wrong draws a connecting stroke across the map.
        """
        left = [[0.0, 0.0], [1.0, 0.0]]
        right = [[9.0, 10.0], [10.0, 10.0]]
        rgba = geometry_render.to_rgba(
            [left, right], width=64, height=64, extent=(0, 0, 10, 10),
            thickness=0)
        drawn = rgba[..., 3] > 0
        # Nothing in the middle of the buffer, where a joining segment would be.
        self.assertFalse(drawn[20:44, 20:44].any())

    def test_nothing_drawable_draws_nothing(self) -> None:
        for parts in ([], None, [[[0.0, 0.0]]], [[]]):
            rgba = geometry_render.to_rgba(
                parts, width=8, height=8, extent=(0, 0, 1, 1))
            self.assertEqual(int((rgba[..., 3] > 0).sum()), 0)

    def test_a_non_finite_vertex_drops_its_segment(self) -> None:
        rgba = geometry_render.to_rgba(
            [[[0.0, 0.0], [np.nan, 5.0], [10.0, 10.0]]],
            width=32, height=32, extent=(0, 0, 10, 10), thickness=0)
        self.assertEqual(int((rgba[..., 3] > 0).sum()), 0)

    def test_the_stroke_comes_from_the_layers_ramp(self) -> None:
        """A vector carries no per-vertex value, so the colormap control would
        be inert unless the stroke is taken from the ramp."""
        one = geometry_render.stroke_colour("viridis")
        other = geometry_render.stroke_colour("magma")
        self.assertFalse(np.array_equal(one, other))
        self.assertFalse(np.array_equal(
            geometry_render.stroke_colour("viridis"),
            geometry_render.stroke_colour("viridis", invert=True)))

    def test_a_pathological_preview_stays_bounded(self) -> None:
        """The sample budget is a number here, not the caller's good intent."""
        long_lines = [[[0.0, float(i)], [10_000.0, float(i)]]
                      for i in range(400)]
        rgba = geometry_render.to_rgba(
            long_lines, width=2048, height=2048, extent=(0, 0, 10_000, 400))
        self.assertEqual(rgba.shape, (2048, 2048, 4))

    def test_bounds_give_a_straight_line_an_area(self) -> None:
        box = geometry_render.bounds([[[5.0, 0.0], [5.0, 10.0]]])
        self.assertIsNotNone(box)
        self.assertGreater(box[2] - box[0], 0.0)
        self.assertGreater(box[3] - box[1], 0.0)

    def test_the_draw_path_holds_no_python_loop_over_vertices(self) -> None:
        """ADR-007, the same rule `points` is held to: every loop in `to_rgba`
        walks the stroke's footprint, never the geometry."""
        source = Path(geometry_render.__file__).read_text(encoding="utf-8")
        body = source.split("def to_rgba", 1)[1].split("def _footprint", 1)[0]
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("for "):
                continue
            iterated = stripped.split(" in ", 1)[-1].rstrip(":")
            self.assertIn("_footprint(", iterated,
                          f"a loop over something other than the stroke's "
                          f"footprint: {stripped}")


@unittest.skipUnless(VECTOR.exists(), "the synthetic vector is missing")
class AVectorAloneIsDrawn(unittest.TestCase):
    """The gap M4 named and carried: a vector added nothing to the screen."""

    def _item(self, path, layer_id="V"):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        described = describe(path).as_dict()
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        added = item.addGeometryLayer(
            layer_id, described["preview"]["parts"], path.name,
            described["crs"] or "")
        return item, added, described

    def _drawn(self, item) -> int:
        from PySide6.QtGui import QImage, QPainter

        image = QImage(320, 240, QImage.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter)
        painter.end()
        buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
        pixels = buffer.reshape(240, 320, 4)
        return int((pixels[..., :3].sum(axis=2) > 30).sum())

    def test_a_vector_layer_paints_with_no_raster_in_the_stack(self) -> None:
        try:
            import PySide6  # noqa: F401
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        item, added, _ = self._item(VECTOR)
        self.assertTrue(added)
        self.assertGreater(self._drawn(item), 50,
                           "a vector-only stack painted nothing")

    def test_a_thicker_stroke_draws_more(self) -> None:
        try:
            import PySide6  # noqa: F401
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        item, _, _ = self._item(VECTOR)
        thin = self._drawn(item)
        item.setLayerStyle("V", {"pointSize": 5, "outline": True})
        self.assertGreater(self._drawn(item), thin)

    def test_the_summary_reports_a_silhouette_and_no_unit(self) -> None:
        """A silhouette has no values. Reporting a unit or a statistic for one
        would put a measurement on screen that the file never carried."""
        try:
            import PySide6  # noqa: F401
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        item, _, described = self._item(VECTOR)
        summary = item.layerSummary()
        self.assertEqual(summary["kind"], "geometry")
        self.assertGreater(summary["parts"], 0)
        self.assertGreater(summary["vertices"], summary["parts"])
        self.assertNotIn("unit", summary)
        self.assertNotIn("statistics", summary)

    def test_an_empty_silhouette_is_refused(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError:                              # pragma: no cover
            self.skipTest("PySide6 is not installed")
        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        from geopotential_app.render.geocanvas.map_item import MapItem

        item = MapItem()
        self.assertFalse(item.addGeometryLayer("V", [], "empty", "EPSG:31982"))


if __name__ == "__main__":
    unittest.main()
