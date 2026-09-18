"""The display stack is display, and nothing else.

P-106 — the stack's order enters no manifest and no aggregation.
P-107 — hiding or reordering changes no value read from the source.
P-108 — removing a layer from the view removes nothing from the project.
P-111 — a colormap or a limit repaints; it never rewrites an artefact.
P-112 — every ramp keeps nodata transparent, and the diverging one has an odd
        number of entries centred exactly on zero.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from geopotential_app.models.layer_model import (  # noqa: E402
    ROLES,
    DisplayLayer,
    LayerStackModel,
)
from geopotential_app.render.colormap import (  # noqa: E402
    AVAILABLE,
    DIVERGING,
    lookup_table,
    names,
    to_rgba,
)

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


def _stack() -> LayerStackModel:
    _app()
    model = LayerStackModel()
    model.add(DisplayLayer("A", "alpha", path="/tmp/a.tif", role="original"))
    model.add(DisplayLayer("B", "beta", path="/tmp/b.tif", role="membership"))
    return model


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class WhatALayerCarries(unittest.TestCase):
    def test_it_carries_display_decisions_and_nothing_else(self) -> None:
        """ADR-MSP-002. The fields are the contract: anything that could enter
        a computation must not be here."""
        layer = DisplayLayer("A", "alpha")
        forbidden = ("values", "array", "data", "pixels", "grid", "criterion",
                     "weight", "nodata", "geometry")
        for name in forbidden:
            self.assertFalse(hasattr(layer, name),
                             f"a display layer must not carry {name}")

    def test_a_role_is_a_label_and_not_a_rule(self) -> None:
        self.assertIn("original", ROLES)
        self.assertIn("membership", ROLES)
        # Nothing branches on it: the style of two layers with different roles
        # is decided the same way.
        one = DisplayLayer("A", "alpha", role="original", colormap="magma")
        two = DisplayLayer("B", "beta", role="result", colormap="magma")
        self.assertEqual(one.style(), two.style())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TheStack(unittest.TestCase):
    def test_order_is_the_draw_order_and_carries_nothing_else(self) -> None:
        """P-106. Moving a layer changes what is on top and no number."""
        stack = _stack()
        before = [one.style() for one in stack.layers]
        stack.move("A", 1)
        self.assertEqual([one.layer_id for one in stack.layers], ["B", "A"])
        self.assertEqual([one.style() for one in stack.layers][::-1], before)

    def test_the_snapshot_holds_no_values(self) -> None:
        """P-106. What crosses to the canvas is a display description."""
        for entry in _stack().snapshot():
            self.assertEqual(
                set(entry) - {
                    "layerId", "path", "name", "unit", "kind", "role",
                    "visible", "opacity", "colormap", "invert", "vmin", "vmax",
                    # Symbol, for a point layer. Display, like the rest: it
                    # changes the drawing and never a value.
                    "pointSize", "symbol", "outline",
                },
                set(),
            )

    def test_removing_a_layer_removes_it_from_the_view_only(self) -> None:
        """P-108. The file it referenced is untouched, and so is the id."""
        stack = _stack()
        self.assertTrue(RASTER.exists(), "the smoke raster is missing")
        stack.add(DisplayLayer("R", RASTER.stem, path=str(RASTER)))
        before = RASTER.stat().st_size
        self.assertTrue(stack.remove("R"))
        self.assertEqual([one.layer_id for one in stack.layers], ["A", "B"])
        self.assertTrue(RASTER.exists())
        self.assertEqual(RASTER.stat().st_size, before)

    def test_the_active_layer_survives_removing_another(self) -> None:
        stack = _stack()
        stack.setActive("A")
        stack.remove("B")
        self.assertEqual(stack.activeId, "A")

    def test_removing_the_active_layer_promotes_another(self) -> None:
        stack = _stack()
        stack.setActive("B")
        stack.remove("B")
        self.assertEqual(stack.activeId, "A")

    def test_hiding_changes_visibility_and_nothing_about_the_value(self) -> None:
        """P-107, on the model's side: what a hidden layer references and how
        it is read are unchanged."""
        stack = _stack()
        before = dict(stack.snapshot()[0])
        stack.setVisible("A", False)
        after = dict(stack.snapshot()[0])
        self.assertFalse(after["visible"])
        for key in ("path", "unit", "vmin", "vmax"):
            self.assertEqual(before[key], after[key])

    def test_every_change_bumps_the_revision(self) -> None:
        """QML binds to `revision`; a change that does not bump it is a change
        the panel never sees."""
        stack = _stack()
        seen = stack.revision
        for action in (lambda: stack.setVisible("A", False),
                       lambda: stack.setOpacity("A", 0.5),
                       lambda: stack.setColormap("A", "magma"),
                       lambda: stack.setInvert("A", True),
                       lambda: stack.move("A", 1),
                       lambda: stack.setActive("A")):
            action()
            self.assertGreater(stack.revision, seen, "a change went unannounced")
            seen = stack.revision

    def test_limits_reset_to_automatic(self) -> None:
        stack = _stack()
        stack.setLimits("A", 10.0, 20.0)
        self.assertEqual((stack.layer("A").vmin, stack.layer("A").vmax), (10.0, 20.0))
        stack.resetLimits("A")
        self.assertIsNone(stack.layer("A").vmin)
        self.assertIsNone(stack.layer("A").vmax)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class EveryControlReachesThePicture(unittest.TestCase):
    """A control that moves and changes nothing is worse than no control.

    `applyStack` used to rebuild the style by hand and listed six of the nine
    fields, so the colormap worked and the marker's shape and size did not:
    the model changed, the panel changed, and the map did not.
    """

    def _canvas_and_stack(self):  # noqa: ANN202
        import csv

        from geopotential_app.render.geocanvas.map_item import MapItem

        _app()
        table = _data_dir() / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
        if not table.exists():
            self.skipTest("the smoke table is missing")
        points = [[float(row["easting"]), float(row["northing"]),
                   float(row["gCBGA"])]
                  for row in csv.DictReader(table.open())][:800]
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        item.addPointLayer("P", points, "b", "mGal", "EPSG:26912", "metre")
        stack = LayerStackModel()
        stack.add(DisplayLayer("P", "b", kind="points"))
        return item, stack

    @staticmethod
    def _ink(item) -> int:
        """Pixels that are not the map's ground: what was actually drawn."""
        from PySide6.QtGui import QImage, QPainter

        image = QImage(320, 240, QImage.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter)
        painter.end()
        pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(240, 320, 4)
        return int((pixels[..., :3].sum(axis=2) > 20).sum())

    def test_the_canvas_is_handed_every_style_field(self) -> None:
        """The list of fields lives in one place, and the snapshot is passed
        through it rather than retyped."""
        from geopotential_app.render.geocanvas.map_item import STYLE_KEYS

        entry = _stack().snapshot()[0]
        style_fields = {k for k in entry
                        if k not in ("layerId", "path", "name", "unit", "kind",
                                     "role")}
        self.assertEqual(style_fields - set(STYLE_KEYS), set(),
                         "the stack publishes a display field the canvas "
                         "never receives")

    def test_a_bigger_marker_draws_more(self) -> None:
        item, stack = self._canvas_and_stack()
        item.applyStack(stack.snapshot())
        small = self._ink(item)
        stack.setPointSize("P", 5)
        item.applyStack(stack.snapshot())
        self.assertGreater(self._ink(item), small,
                           "the point size never reached the canvas")

    def test_the_shape_changes_the_picture(self) -> None:
        item, stack = self._canvas_and_stack()
        stack.setPointSize("P", 5)
        item.applyStack(stack.snapshot())
        drawn: dict[str, int] = {}
        for symbol in ("circle", "square", "cross", "triangle"):
            stack.setSymbol("P", symbol)
            item.applyStack(stack.snapshot())
            drawn[symbol] = self._ink(item)
        self.assertGreater(drawn["square"], drawn["circle"])
        self.assertLess(drawn["cross"], drawn["circle"])
        self.assertEqual(len(set(drawn.values())), len(drawn),
                         f"two shapes drew the same picture: {drawn}")

    def test_the_outline_reaches_the_canvas_too(self) -> None:
        item, stack = self._canvas_and_stack()
        stack.setPointSize("P", 3)
        item.applyStack(stack.snapshot())
        plain = self._ink(item)
        stack.setOutline("P", True)
        item.applyStack(stack.snapshot())
        self.assertGreater(self._ink(item), plain)


class Ramps(unittest.TestCase):
    def test_the_ten_ramps_are_offered(self) -> None:
        self.assertEqual(set(names()), set(AVAILABLE))
        for expected in ("viridis", "plasma", "inferno", "magma", "cividis",
                         "turbo", "grey", "rdbu"):
            self.assertIn(expected, names())

    def test_a_diverging_ramp_has_an_odd_number_of_entries(self) -> None:
        """P-112. With an even count zero has no entry of its own and equal
        departures either side get different colours."""
        for name in DIVERGING:
            table = lookup_table(name)
            self.assertEqual(table.shape[0] % 2, 1)

    def test_zero_lands_on_the_centre_entry(self) -> None:
        values = np.array([[-5.0, 0.0, 5.0]])
        rgba = to_rgba(values, colormap="rdbu")
        centre = lookup_table("rdbu")[lookup_table("rdbu").shape[0] // 2]
        np.testing.assert_array_equal(rgba[0, 1, :3], centre)

    def test_equal_departures_land_symmetrically_about_the_centre(self) -> None:
        """Equal distances either side of zero pick entries equally far from
        the ramp's middle. The ramp's own colours need not be mirror images —
        `RdBu` is not symmetric — but the *indices* must be."""
        table = lookup_table("rdbu")
        size = table.shape[0]
        rgba = to_rgba(np.array([[-3.0, 0.0, 3.0]]), colormap="rdbu")
        lookup = {tuple(int(c) for c in entry): i for i, entry in enumerate(table)}
        low = lookup[tuple(int(c) for c in rgba[0, 0, :3])]
        high = lookup[tuple(int(c) for c in rgba[0, 2, :3])]
        self.assertEqual(low + high, size - 1)

    def test_every_ramp_keeps_nodata_transparent(self) -> None:
        """P-112, extended to the ramps added at M5.5."""
        values = np.array([[0.0, np.nan, 1.0]])
        for name in names():
            rgba = to_rgba(values, colormap=name)
            self.assertEqual(int(rgba[0, 1, 3]), 0, f"{name} painted a null")
            self.assertEqual(int(rgba[0, 0, 3]), 255)

    def test_inverting_reverses_the_ramp_and_keeps_its_length(self) -> None:
        for name in names():
            straight = lookup_table(name)
            reversed_ = lookup_table(name, invert=True)
            self.assertEqual(straight.shape, reversed_.shape)
            np.testing.assert_array_equal(straight[0], reversed_[-1])

    def test_an_inverted_diverging_ramp_still_centres_on_zero(self) -> None:
        table = lookup_table("rdbu", invert=True)
        self.assertEqual(table.shape[0] % 2, 1)
        rgba = to_rgba(np.array([[-1.0, 0.0, 1.0]]), colormap="rdbu", invert=True)
        np.testing.assert_array_equal(rgba[0, 1, :3], table[table.shape[0] // 2])

    def test_opacity_applies_to_valid_pixels_only(self) -> None:
        values = np.array([[0.0, np.nan]])
        rgba = to_rgba(values, colormap="viridis", opacity=0.5)
        self.assertEqual(int(rgba[0, 0, 3]), 128)
        self.assertEqual(int(rgba[0, 1, 3]), 0)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class StyleWritesNothing(unittest.TestCase):
    """P-111. The artefact's bytes are the same before and after a restyle."""

    def test_restyling_a_layer_leaves_the_file_byte_identical(self) -> None:
        self.assertTrue(RASTER.exists(), "the smoke raster is missing")
        from geopotential_app.render.geocanvas.map_item import MapItem

        _app()
        digest = hashlib.sha256(RASTER.read_bytes()).hexdigest()
        item = MapItem()
        item.setWidth(320)
        item.setHeight(240)
        self.assertTrue(item.addLayer("L1", str(RASTER), RASTER.stem, "m"))
        for ramp in names():
            item.setLayerStyle("L1", {"colormap": ramp, "invert": True,
                                      "vmin": 0.0, "vmax": 10.0, "opacity": 0.4})
        item.removeLayer("L1")
        self.assertEqual(hashlib.sha256(RASTER.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
