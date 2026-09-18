"""Coordinates and display reprojection. ADR-MSP-003, ADR-006.

P-119 — declaring a CRS, reprojecting the data and reprojecting the view are
        three different things, and only the third happens here.
P-120 — the display transform is unreachable from `project/` and `commands/`
        (checked by the architecture gate; the import graph is checked here).
P-121 — every coordinate is shown with what it is in, in the chosen format.
P-129 — a layer drawn in another CRS is warped for the picture only: the file
        is byte-identical, and the value under the cursor still comes from the
        source at full resolution.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

import numpy as np

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
sys.path.insert(0, str(ROOT / "app"))

from geopotential_app.geo import coordinates as C  # noqa: E402

RASTER = _DATA / "utah_forge" / "Distance_to_fault.tif"
UTM = "EPSG:26912"          # NAD83 / UTM zone 12N — two numbers in the name
POINT = (335430.8, 4263804.4)

try:
    from PySide6.QtGui import QGuiApplication
    HAVE_QT = True
except ImportError:                                      # pragma: no cover
    HAVE_QT = False


class Transforms(unittest.TestCase):
    def test_a_round_trip_closes(self) -> None:
        """Tolerance declared before the test: 1 mm, which is far below any
        survey's own accuracy and far above float64 noise."""
        lon, lat = C.transform(*POINT, UTM, C.GEOGRAPHIC)
        back = C.transform(lon, lat, C.GEOGRAPHIC, UTM)
        self.assertAlmostEqual(back[0], POINT[0], delta=1e-3)
        self.assertAlmostEqual(back[1], POINT[1], delta=1e-3)

    def test_the_same_crs_is_not_transformed(self) -> None:
        self.assertEqual(C.transform(*POINT, UTM, UTM), POINT)

    def test_arrays_go_through_in_one_call(self) -> None:
        x = np.array([POINT[0], POINT[0] + 100.0])
        y = np.array([POINT[1], POINT[1] + 100.0])
        lon, lat = C.transform_arrays(x, y, UTM, C.GEOGRAPHIC)
        self.assertEqual(lon.shape, x.shape)
        self.assertTrue(np.all(lon < 0))          # Utah is west of Greenwich
        self.assertTrue(np.all(lat > 0))

    def test_an_extent_is_densified_not_cornered(self) -> None:
        box = (POINT[0], POINT[1], POINT[0] + 50_000.0, POINT[1] + 50_000.0)
        moved = C.transform_extent(box, UTM, C.GEOGRAPHIC)
        corners = [C.transform(box[0], box[1], UTM, C.GEOGRAPHIC),
                   C.transform(box[2], box[3], UTM, C.GEOGRAPHIC)]
        # The densified box contains the corner-only one; a projection bends
        # the edges outward, and four corners understate the extent.
        self.assertLessEqual(moved[0], min(c[0] for c in corners) + 1e-9)
        self.assertGreaterEqual(moved[3], max(c[1] for c in corners) - 1e-9)

    def test_an_unreadable_crs_is_named(self) -> None:
        with self.assertRaises(C.CrsUnknown) as refusal:
            C.transform(*POINT, "EPSG:not-a-crs", UTM)
        self.assertIn("not-a-crs", str(refusal.exception))


class Writing(unittest.TestCase):
    def test_the_utm_zone_comes_from_the_crs_not_from_its_name(self) -> None:
        """`NAD83 / UTM zone 12N` holds two numbers; reading the first gives
        zone 83, which is not a zone."""
        self.assertEqual(C.utm_zone(UTM), (12, True))
        self.assertEqual(C.utm_zone("EPSG:31982"), (22, False))
        self.assertIsNone(C.utm_zone(C.GEOGRAPHIC))

    def test_utm_carries_its_zone(self) -> None:
        text = C.format_position(*POINT, UTM, "metre", C.UTM)
        self.assertIn("UTM 12N", text)
        self.assertIn("m E", text)

    def test_degrees_carry_their_hemisphere(self) -> None:
        text = C.format_position(*POINT, UTM, "metre", C.DECIMAL)
        self.assertIn("N", text)
        self.assertIn("W", text)          # Utah is west
        self.assertIn("°", text)

    def test_dms_is_degrees_minutes_seconds(self) -> None:
        text = C.format_position(*POINT, UTM, "metre", C.DMS)
        self.assertIn("°", text)
        self.assertIn("'", text)
        self.assertIn('"', text)

    def test_seconds_never_reach_sixty(self) -> None:
        """59.9996 seconds is a minute, and `59.999″` is not a coordinate."""
        text = C.format_dms(0.0, 1.0 - 1e-9)
        self.assertNotIn("60.00", text)

    def test_native_precision_is_not_noise(self) -> None:
        """Six decimals of a UTM metre is a micrometre."""
        self.assertEqual(C.format_native(*POINT, "metre"), "335,430.8, 4,263,804.4")
        self.assertIn(".", C.format_native(-48.5, -1.2, "degree"))

    def test_a_readout_says_what_it_is_in(self) -> None:
        """P-121. Degrees are in WGS 84 whatever the layer is."""
        self.assertEqual(C.label_for(C.DECIMAL, UTM), C.GEOGRAPHIC)
        self.assertEqual(C.label_for(C.NATIVE, UTM), UTM)


class TheSeam(unittest.TestCase):
    def test_the_recording_layers_do_not_import_it(self) -> None:
        """P-120. A transform on the way to a manifest would be a reprojection
        nobody asked for and nobody recorded."""
        app = ROOT / "app" / "geopotential_app"
        for layer in ("project", "commands"):
            for module in (app / layer).rglob("*.py"):
                source = module.read_text(encoding="utf-8")
                self.assertNotIn("geo.coordinates", source,
                                 f"{layer}/{module.name} reaches the display "
                                 f"transform")

    def test_it_reads_and_writes_nothing(self) -> None:
        """Checked on the code, not on the prose: the docstring says the module
        writes nothing, and a text search finds the word "writes" in it."""
        import ast

        module = (ROOT / "app" / "geopotential_app" / "geo" / "coordinates.py")
        tree = ast.parse(module.read_text(encoding="utf-8"))

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("rasterio", "geopandas", "fiona", "osgeo", "pandas",
                          "sqlite3", "pathlib", "shutil"):
            self.assertNotIn(forbidden, imported,
                             f"the display transform imports {forbidden}")

        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("open", called, "the display transform opens a file")


@unittest.skipUnless(HAVE_QT and RASTER.exists(), "Qt or the raster is absent")
class TheView(unittest.TestCase):
    def _item(self):
        from geopotential_app.render.geocanvas.map_item import MapItem

        QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        return item

    def _drawn(self, item) -> int:
        from PySide6.QtGui import QImage, QPainter

        image = QImage(320, 240, QImage.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter)
        painter.end()
        pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(240, 320, 4)
        return int((pixels[..., 3] > 0).sum())

    def test_the_view_follows_the_layer_until_it_is_told_otherwise(self) -> None:
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        self.assertEqual(item.viewCrs, UTM)

    def test_a_layer_is_drawn_in_the_chosen_view_crs(self) -> None:
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        native = self._drawn(item)
        for crs in (C.GEOGRAPHIC, "EPSG:3857"):
            item.viewCrs = crs
            self.assertEqual(item.viewCrs, crs)
            self.assertGreater(self._drawn(item), native * 0.5,
                               f"the layer nearly vanished in {crs}")

    def test_warping_the_view_leaves_the_file_untouched(self) -> None:
        """ADR-006. Reprojecting the data is a run with a manifest; this is a
        picture, and the bytes on disk are the same afterwards."""
        digest = hashlib.sha256(RASTER.read_bytes()).hexdigest()
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        for crs in (C.GEOGRAPHIC, "EPSG:3857", UTM):
            item.viewCrs = crs
            self._drawn(item)
        self.assertEqual(hashlib.sha256(RASTER.read_bytes()).hexdigest(), digest)

    def test_the_value_under_the_cursor_survives_the_view_crs(self) -> None:
        """P-70 through a warped view: the readout comes from the source, at
        the cursor's real place, whatever the view is drawn in."""
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        native = item.sample(*POINT)
        self.assertIsNotNone(native)
        for crs in (C.GEOGRAPHIC, "EPSG:3857"):
            item.viewCrs = crs
            moved = C.transform(*POINT, UTM, crs)
            self.assertAlmostEqual(item.sample(*moved), native, places=6,
                                   msg=f"the readout changed in {crs}")

    def test_two_layers_in_two_crs_share_one_view(self) -> None:
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        item.addPointLayer(
            "P", [[POINT[0], POINT[1], 1.0],
                  [POINT[0] + 5000.0, POINT[1] + 5000.0, 2.0]],
            "p", "mGal", UTM, "metre",
        )
        item.viewCrs = C.GEOGRAPHIC
        self.assertGreater(self._drawn(item), 100)

    def test_the_readout_is_written_in_the_chosen_format(self) -> None:
        item = self._item()
        item.addLayer("R", str(RASTER), "d", "m")
        item.coordinateStyle = C.UTM
        self.assertIn("UTM 12N", item.formatPosition(*POINT))
        item.coordinateStyle = C.DMS
        self.assertIn('"', item.formatPosition(*POINT))
        self.assertEqual(item.positionLabel(), C.GEOGRAPHIC)


if __name__ == "__main__":
    unittest.main()
