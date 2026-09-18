"""Level 1 — the GeoCanvas, per section 10.4.

Six kinds of test the specification asks for: snapshots, numerical coordinates,
numerical sampling, picking, level of detail, visual export. All but the
snapshot run without a window, because `raster/` and `render/` were split
precisely so they could.

The test that matters most is `SamplingComesFromTheSource`. Everything else
here is arithmetic; that one is the difference between a readout and a lie.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from geopotential_app.raster import LruCache, RasterSource, Tile, Window
from geopotential_app.render.colormap import to_rgba
from geopotential_app.render.geocanvas.viewport import Extent, Viewport

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
CANVAS = _DATA / "synthetic" / "msp" / "canvas"
LARGE = CANVAS / "large_field.tif"


@unittest.skipUnless(LARGE.exists(), "run tools/make_canvas_fixtures.py first")
class LevelOfDetail(unittest.TestCase):
    """Gate M4 G1, and the §10.4 LOD test."""

    def setUp(self) -> None:
        self.source = RasterSource(LARGE)

    def tearDown(self) -> None:
        self.source.close()

    def test_the_file_carries_native_overviews(self) -> None:
        native = [l.factor for l in self.source.levels if l.native and l.factor > 1]
        self.assertEqual(native, [2, 4, 8, 16, 32])

    def test_a_coarser_scale_chooses_a_coarser_level(self) -> None:
        """The level is a function of scale, and monotone in it."""
        factors = [
            self.source.level_for_scale(scale).factor
            for scale in (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0)
        ]
        self.assertEqual(factors, sorted(factors))
        self.assertEqual(factors[0], 1, "at finer than the pixel, read full res")
        self.assertGreater(factors[-1], 8)

    def test_the_same_scale_always_chooses_the_same_level(self) -> None:
        """Otherwise a pan would flicker between levels at a constant zoom."""
        for scale in (7.3, 41.0, 199.0):
            self.assertEqual(
                self.source.level_for_scale(scale).factor,
                self.source.level_for_scale(scale).factor,
            )

    def test_the_level_never_under_resolves_the_screen(self) -> None:
        """The chosen level's pixel is at most one screen pixel."""
        source_pixel = abs(self.source.transform.a)
        for scale in (12.0, 33.0, 97.0, 260.0):
            factor = self.source.level_for_scale(scale).factor
            self.assertLessEqual(factor * source_pixel, scale + 1e-9)

    def test_filling_a_screen_reads_a_fraction_of_the_raster(self) -> None:
        """G1: 'raster grande abre sem bloquear UI'.

        The claim is not about milliseconds — it is that the work done is
        proportional to the screen, not to the file.
        """
        left, bottom, right, top = self.source.bounds
        viewport = Viewport(Extent(left, bottom, right, top), 800, 600)
        tile = self.source.read_window(
            *viewport.fitted_extent.as_tuple(), viewport.scale
        )
        self.assertIsNotNone(tile)
        total = self.source.width * self.source.height
        self.assertLess(
            self.source.pixels_read, total * 0.10,
            f"read {self.source.pixels_read} of {total}; a screen-sized view "
            f"must not read the whole raster",
        )

    def test_zooming_in_reads_full_resolution(self) -> None:
        """The other half of the claim: detail appears when it is asked for."""
        left, bottom, right, top = self.source.bounds
        viewport = Viewport(Extent(left, bottom, right, top), 800, 600).zoomed(0.02)
        self.assertEqual(self.source.level_for_scale(viewport.scale).factor, 1)

    def test_an_extent_off_the_raster_returns_nothing(self) -> None:
        left, bottom, right, top = self.source.bounds
        far = self.source.read_window(
            left + 1e6, bottom + 1e6, right + 1e6, top + 1e6, 10.0
        )
        self.assertIsNone(far)


@unittest.skipUnless(LARGE.exists(), "canvas fixtures absent")
class SamplingComesFromTheSource(unittest.TestCase):
    """Gate M4 G3, and the §10.4 sampling test.

    The trap this exists for: a canvas showing a 32:1 decimated tile answering
    "what is the value here" from that tile. Its pixel is the average of 1024
    source pixels — a number that appears nowhere in the dataset.
    """

    def setUp(self) -> None:
        self.source = RasterSource(LARGE)

    def tearDown(self) -> None:
        self.source.close()

    def test_a_sample_equals_the_source_pixel(self) -> None:
        import rasterio

        with rasterio.open(LARGE) as src:
            values = src.read(1)
        for row, col in ((100, 200), (2048, 2048), (4000, 100), (1234, 3456)):
            x, y = self.source.transform * (col + 0.5, row + 0.5)
            expected = float(values[row, col])
            sampled = self.source.sample(x, y)
            if np.isnan(expected):
                self.assertIsNone(sampled, f"null at ({row}, {col}) must read None")
            else:
                self.assertAlmostEqual(sampled, expected, places=5)

    def test_a_sample_ignores_the_displayed_level(self) -> None:
        """The whole point. Read a coarse tile, then sample, and compare.

        The chosen point is one where the decimated value genuinely differs
        from the source value, so an implementation that answered from the tile
        would fail rather than coincide.
        """
        left, bottom, right, top = self.source.bounds
        viewport = Viewport(Extent(left, bottom, right, top), 400, 300)
        tile = self.source.read_window(
            *viewport.fitted_extent.as_tuple(), viewport.scale
        )
        self.assertGreater(tile.window.factor, 1, "the test needs a decimated tile")

        import rasterio

        with rasterio.open(LARGE) as src:
            values = src.read(1)

        # Find a source pixel whose value differs from its tile's average.
        factor = tile.window.factor
        row, col = 1500, 2500
        tile_row, tile_col = row // factor, col // factor
        tile_value = float(tile.values[tile_row, tile_col])
        source_value = float(values[row, col])
        self.assertNotAlmostEqual(
            tile_value, source_value, places=3,
            msg="pick a point where decimation actually changes the value",
        )

        x, y = self.source.transform * (col + 0.5, row + 0.5)
        sampled = self.source.sample(x, y)
        self.assertAlmostEqual(sampled, source_value, places=5)
        self.assertNotAlmostEqual(sampled, tile_value, places=3)

    def test_a_sample_outside_the_grid_is_none(self) -> None:
        left, bottom, right, top = self.source.bounds
        self.assertIsNone(self.source.sample(left - 1000, bottom - 1000))
        self.assertIsNone(self.source.sample(right + 1000, top + 1000))

    def test_a_sample_on_a_null_is_none(self) -> None:
        """The fixture carries a nodata hole; a null is absent, not zero."""
        import rasterio

        with rasterio.open(LARGE) as src:
            values = src.read(1)
        rows, cols = np.where(np.isnan(values))
        self.assertGreater(rows.size, 0, "the fixture should contain nulls")
        row, col = int(rows[rows.size // 2]), int(cols[rows.size // 2])
        x, y = self.source.transform * (col + 0.5, row + 0.5)
        self.assertIsNone(self.source.sample(x, y))


@unittest.skipUnless(LARGE.exists(), "canvas fixtures absent")
class Coordinates(unittest.TestCase):
    """Gate M4 G2, and the §10.4 coordinate test — under pan and zoom."""

    def setUp(self) -> None:
        source = RasterSource(LARGE)
        left, bottom, right, top = source.bounds
        source.close()
        self.viewport = Viewport(Extent(left, bottom, right, top), 800, 600)

    def test_round_trip_is_exact_at_the_initial_view(self) -> None:
        for px, py in ((0, 0), (800, 600), (400, 300), (123, 456)):
            x, y = self.viewport.to_map(px, py)
            bx, by = self.viewport.to_screen(x, y)
            self.assertAlmostEqual(float(bx), px, places=6)
            self.assertAlmostEqual(float(by), py, places=6)

    def test_round_trip_survives_pan(self) -> None:
        panned = self.viewport.panned(137.0, -89.0)
        for px, py in ((0, 0), (799, 599), (400, 300)):
            x, y = panned.to_map(px, py)
            bx, by = panned.to_screen(x, y)
            self.assertAlmostEqual(float(bx), px, places=6)
            self.assertAlmostEqual(float(by), py, places=6)

    def test_round_trip_survives_zoom(self) -> None:
        for factor in (0.1, 0.5, 2.0, 10.0):
            zoomed = self.viewport.zoomed(factor)
            x, y = zoomed.to_map(311, 207)
            bx, by = zoomed.to_screen(x, y)
            self.assertAlmostEqual(float(bx), 311, places=6)
            self.assertAlmostEqual(float(by), 207, places=6)

    def test_panning_moves_the_map_with_the_hand(self) -> None:
        """Dragging right must move the view left, or the map fights the mouse."""
        before = self.viewport.fitted_extent.left
        after = self.viewport.panned(100.0, 0.0).fitted_extent.left
        self.assertLess(after, before)

    def test_zoom_holds_the_anchor_under_the_cursor(self) -> None:
        anchor = self.viewport.to_map(600, 150)
        anchor = (float(anchor[0]), float(anchor[1]))
        zoomed = self.viewport.zoomed(0.4, at=anchor)
        px, py = zoomed.to_screen(*anchor)
        self.assertAlmostEqual(float(px), 600, places=5)
        self.assertAlmostEqual(float(py), 150, places=5)


class TileCache(unittest.TestCase):
    """A tile is cache, never a result: evicting one must cost only time."""

    def _tile(self, size: int) -> Tile:
        values = np.zeros((size, size), dtype=np.float32)
        return Tile(values, Window(0, 0, size, size, 1), None)

    def test_a_hit_returns_the_same_tile(self) -> None:
        cache = LruCache(1 << 20)
        tile = self._tile(8)
        cache.put("a", tile)
        self.assertIs(cache.get("a"), tile)
        self.assertEqual(cache.stats()["hits"], 1)

    def test_a_miss_is_counted(self) -> None:
        cache = LruCache(1 << 20)
        self.assertIsNone(cache.get("absent"))
        self.assertEqual(cache.stats()["misses"], 1)

    def test_it_is_bounded_by_bytes_not_entries(self) -> None:
        """A tile can be a hundred pixels or a hundred megabytes; what runs
        out is memory, not entry count."""
        cache = LruCache(4 * 64 * 64 * 4)  # room for about four 64x64 tiles
        for i in range(10):
            cache.put(i, self._tile(64))
        self.assertLessEqual(cache.nbytes, cache.max_bytes)
        self.assertLess(len(cache._entries), 10)

    def test_the_least_recently_used_goes_first(self) -> None:
        cache = LruCache(2 * 64 * 64 * 4)
        cache.put("old", self._tile(64))
        cache.put("new", self._tile(64))
        cache.get("old")           # touch it, so "new" becomes the oldest
        cache.put("newest", self._tile(64))
        self.assertIsNotNone(cache.get("old"))
        self.assertIsNone(cache.get("new"))

    @unittest.skipUnless(LARGE.exists(), "canvas fixtures absent")
    def test_re_reading_the_same_window_hits_the_cache(self) -> None:
        source = RasterSource(LARGE)
        try:
            left, bottom, right, top = source.bounds
            viewport = Viewport(Extent(left, bottom, right, top), 800, 600)
            args = (*viewport.fitted_extent.as_tuple(), viewport.scale)
            source.read_window(*args)
            after_first = source.pixels_read
            source.read_window(*args)
            self.assertEqual(source.pixels_read, after_first,
                             "a cached window must not be read again")
            self.assertEqual(source.cache.stats()["hits"], 1)
        finally:
            source.close()

    @unittest.skipUnless(LARGE.exists(), "canvas fixtures absent")
    def test_clearing_the_cache_changes_nothing_but_time(self) -> None:
        source = RasterSource(LARGE)
        try:
            left, bottom, right, top = source.bounds
            viewport = Viewport(Extent(left, bottom, right, top), 400, 300)
            args = (*viewport.fitted_extent.as_tuple(), viewport.scale)
            first = source.read_window(*args).values.copy()
            source.cache.clear()
            second = source.read_window(*args).values
            np.testing.assert_array_equal(
                np.nan_to_num(first, nan=-9e9), np.nan_to_num(second, nan=-9e9)
            )
        finally:
            source.close()


@unittest.skipUnless(LARGE.exists(), "canvas fixtures absent")
class Snapshots(unittest.TestCase):
    """§10.4 snapshots: the same input draws the same image."""

    def test_the_same_view_renders_identically(self) -> None:
        source = RasterSource(LARGE)
        try:
            left, bottom, right, top = source.bounds
            viewport = Viewport(Extent(left, bottom, right, top), 320, 240)
            args = (*viewport.fitted_extent.as_tuple(), viewport.scale)
            first = to_rgba(source.read_window(*args).values, colormap="viridis")
            source.cache.clear()
            second = to_rgba(source.read_window(*args).values, colormap="viridis")
            np.testing.assert_array_equal(first, second)
        finally:
            source.close()

    def test_nulls_stay_transparent_at_every_level(self) -> None:
        """A hole must not fill in as the level coarsens."""
        source = RasterSource(LARGE)
        try:
            left, bottom, right, top = source.bounds
            for pixels in (128, 400, 900):
                viewport = Viewport(Extent(left, bottom, right, top), pixels, pixels)
                tile = source.read_window(
                    *viewport.fitted_extent.as_tuple(), viewport.scale
                )
                rgba = to_rgba(tile.values)
                self.assertTrue(
                    (rgba[..., 3] == 0).any(),
                    f"the nodata hole vanished at level {tile.window.factor}",
                )
        finally:
            source.close()


@unittest.skipUnless((CANVAS / "MANIFEST.json").exists(), "canvas fixtures absent")
class Fixtures(unittest.TestCase):
    def test_the_manifest_describes_what_was_generated(self) -> None:
        manifest = json.loads((CANVAS / "MANIFEST.json").read_text())
        self.assertEqual(len(manifest["fixtures"]), 2)
        for entry in manifest["fixtures"]:
            self.assertEqual(entry["pixels"], 4096 * 4096)
            self.assertTrue(entry["tiled"], "a striped file defeats windowed reads")
            self.assertEqual(entry["overviews"], [2, 4, 8, 16, 32])


if __name__ == "__main__":
    unittest.main()
