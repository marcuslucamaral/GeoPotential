"""Level 5 — atomic writes, null semantics, and rendering.

The rules here are the ones a clean run hides: a file that assembled perfectly
and declares no nodata, a null painted as the low end of a ramp, a temporary
file left behind by a failed write.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from geopotential_app.render.colormap import (
    default_colormap,
    lookup_table,
    stretch_limits,
    to_rgba,
)
from geopotential_app.render.geocanvas.viewport import Extent, Viewport
from geopotential_worker.domain.crs import CrsInfo
from geopotential_worker.domain.grid import TargetGrid
from geopotential_worker.io.readers import describe_raster, read_raster
from geopotential_worker.io.writers import sha256_file, write_geotiff


def grid(width: int = 16, height: int = 12) -> TargetGrid:
    return TargetGrid(
        transform=Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 4_500_000.0),
        crs=CrsInfo.from_user_input("EPSG:26912", source="test"),
        width=width,
        height=height,
    )


class AtomicWrites(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpio-"))
        self.grid = grid()
        self.values = np.linspace(0, 1, self.grid.pixel_count, dtype=np.float32)
        self.values = self.values.reshape(self.grid.shape)
        self.values[0, 0] = np.nan

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nodata_is_declared_as_nan(self) -> None:
        """Defect D-05: every save_geotiff call omitted nodata while the array
        carried NaN, so every downstream reader treated NaN as data."""
        artifact = write_geotiff(self.values, self.grid, self.tmp / "a.tif")
        with rasterio.open(artifact.path) as src:
            self.assertIsNotNone(src.nodata)
            self.assertTrue(np.isnan(src.nodata))

    def test_the_hash_matches_the_bytes_on_disk(self) -> None:
        artifact = write_geotiff(self.values, self.grid, self.tmp / "a.tif")
        self.assertEqual(artifact.hash, sha256_file(artifact.path))
        self.assertEqual(artifact.bytes, artifact.path.stat().st_size)

    def test_no_temporary_file_survives_a_success(self) -> None:
        write_geotiff(self.values, self.grid, self.tmp / "a.tif")
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])

    def test_no_temporary_file_survives_a_failure(self) -> None:
        """A failed write leaves nothing a recovery pass could mistake for a
        result."""
        with self.assertRaises(TypeError):
            write_geotiff(self.values.astype(np.float64), self.grid, self.tmp / "b.tif")
        self.assertEqual(list(self.tmp.glob("*")), [])

    def test_shape_mismatch_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            write_geotiff(np.zeros((3, 3), np.float32), self.grid, self.tmp / "c.tif")

    def test_the_grid_round_trips(self) -> None:
        artifact = write_geotiff(self.values, self.grid, self.tmp / "a.tif")
        source = read_raster(artifact.path)
        self.assertEqual(source.grid.shape, self.grid.shape)
        self.assertEqual(source.grid.crs, self.grid.crs)
        self.assertEqual(source.grid.pixel_size, self.grid.pixel_size)

    def test_a_sentinel_nodata_becomes_nan_on_read(self) -> None:
        """NaN is the single in-memory null. A -9999 left in the array makes
        every statistic wrong by a number that looks like data."""
        path = self.tmp / "sentinel.tif"
        values = np.full(self.grid.shape, 5.0, dtype=np.float32)
        values[0, :] = -9999.0
        with rasterio.open(
            path, "w", driver="GTiff", height=self.grid.height,
            width=self.grid.width, count=1, dtype="float32",
            crs=self.grid.crs.crs, transform=self.grid.transform, nodata=-9999.0,
        ) as dst:
            dst.write(values, 1)
        source = read_raster(path)
        self.assertTrue(np.isnan(source.values[0, :]).all())
        self.assertEqual(source.nodata, -9999.0, "the sentinel is kept for provenance")
        self.assertAlmostEqual(float(np.nanmean(source.values)), 5.0, places=5)

    def test_describe_reports_metadata_without_reading_pixels(self) -> None:
        artifact = write_geotiff(self.values, self.grid, self.tmp / "a.tif")
        info = describe_raster(artifact.path)
        self.assertEqual(info["crs"], "EPSG:26912")
        self.assertEqual(info["crs_unit"], "metre")
        self.assertFalse(info["geographic"])
        self.assertEqual(info["pixel_size_x"], 10.0)
        self.assertEqual(info["pixel_size_y"], 10.0)


class Rendering(unittest.TestCase):
    def test_nodata_is_transparent(self) -> None:
        """A null painted as the ramp's low colour states a measurement that
        was never made."""
        values = np.array([[0.0, np.nan], [0.5, 1.0]], dtype=np.float32)
        rgba = to_rgba(values)
        self.assertEqual(rgba[0, 1, 3], 0)
        self.assertTrue((rgba[np.isfinite(values)][:, 3] == 255).all())

    def test_a_signed_field_gets_a_diverging_ramp(self) -> None:
        self.assertEqual(default_colormap(np.array([-2.0, 0.5, 3.0], np.float32)), "rdbu")

    def test_a_non_negative_field_gets_a_sequential_ramp(self) -> None:
        self.assertEqual(default_colormap(np.array([0.0, 0.5, 1.0], np.float32)), "viridis")

    def test_a_diverging_ramp_is_centred_on_zero(self) -> None:
        """Otherwise the white midpoint sits somewhere that means nothing.

        Two properties, and the second is the one that matters: zero lands on
        the ramp's centre entry, and values equidistant from zero land
        equidistant from that centre — even when the data is lopsided, as
        [-1, 4] is.
        """
        values = np.array([[-1.0, 0.0, 4.0, -4.0]], dtype=np.float32)
        rgba = to_rgba(values, colormap="rdbu")
        table = lookup_table("rdbu")
        np.testing.assert_array_equal(rgba[0, 1, :3], table[len(table) // 2])

        low = np.where((table == rgba[0, 3, :3]).all(axis=1))[0][0]
        high = np.where((table == rgba[0, 2, :3]).all(axis=1))[0][0]
        centre = len(table) // 2
        self.assertEqual(centre - low, high - centre,
                         "-4 and +4 must sit equidistant from the midpoint")

    def test_an_all_null_field_renders_fully_transparent(self) -> None:
        rgba = to_rgba(np.full((4, 4), np.nan, np.float32))
        self.assertTrue((rgba[..., 3] == 0).all())

    def test_a_constant_field_does_not_divide_by_zero(self) -> None:
        rgba = to_rgba(np.full((4, 4), 7.0, np.float32))
        self.assertTrue(np.isfinite(rgba).all())

    def test_stretch_limits_come_from_percentiles(self) -> None:
        values = np.concatenate([np.zeros(98), np.full(2, 1000.0)]).astype(np.float32)
        lo, hi = stretch_limits(values.reshape(10, 10))
        self.assertLess(hi, 1000.0, "the outlier must not set the display maximum")

    def test_an_unknown_colormap_is_refused_by_name(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            lookup_table("rainbow")
        self.assertIn("viridis", str(ctx.exception))


class ViewportArithmetic(unittest.TestCase):
    """Gate M4 rests on this: the coordinate and the value under the cursor."""

    def setUp(self) -> None:
        self.viewport = Viewport(Extent(0.0, 0.0, 1000.0, 500.0), 400, 200)

    def test_screen_and_map_round_trip(self) -> None:
        for x, y in ((0.0, 500.0), (1000.0, 0.0), (250.0, 125.0)):
            px, py = self.viewport.to_screen(x, y)
            bx, by = self.viewport.to_map(px, py)
            self.assertAlmostEqual(float(bx), x, places=6)
            self.assertAlmostEqual(float(by), y, places=6)

    def test_north_is_up(self) -> None:
        """A higher northing must be a smaller screen y."""
        _, top = self.viewport.to_screen(0.0, 500.0)
        _, bottom = self.viewport.to_screen(0.0, 0.0)
        self.assertLess(float(top), float(bottom))

    def test_scale_is_uniform_in_both_axes(self) -> None:
        """Anisotropic screen scaling makes a measured distance depend on its
        direction."""
        narrow = Viewport(Extent(0.0, 0.0, 1000.0, 100.0), 400, 200)
        x0, y0 = narrow.to_screen(0.0, 0.0)
        x1, y1 = narrow.to_screen(100.0, 100.0)
        self.assertAlmostEqual(abs(float(x1 - x0)), abs(float(y1 - y0)), places=6)

    def test_zoom_holds_the_anchor_fixed(self) -> None:
        anchor = (250.0, 125.0)
        before = self.viewport.to_screen(*anchor)
        after = self.viewport.zoomed(0.5, at=anchor).to_screen(*anchor)
        self.assertAlmostEqual(float(before[0]), float(after[0]), places=6)
        self.assertAlmostEqual(float(before[1]), float(after[1]), places=6)

    def test_degenerate_extent_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Extent(10.0, 0.0, 10.0, 5.0)

    def test_zero_pixel_viewport_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Viewport(Extent(0, 0, 1, 1), 0, 100)


if __name__ == "__main__":
    unittest.main()
