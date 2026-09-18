"""Reading a raster at the resolution the screen actually needs.

Section 10.1: pyramids, overviews, tiles, an LRU cache, level of detail.
The rule it opens with governs everything here:

    "Evite carregar raster inteiro na memória gráfica sem necessidade."

A canvas 800 pixels wide showing a 40 000-pixel raster needs one pixel in fifty.
Reading all of them is not slow, it is wrong: it fails at exactly the size where
the application stops being a demo.

Two things this module keeps strictly apart, because conflating them is the
defect the M4 gate exists to catch:

  **display** — a decimated window, chosen by scale, cached, thrown away freely
  **measurement** — one pixel read from the source at full resolution, never
  from a decimated tile

`read_window` serves the first. `sample` serves the second. A readout that came
from a tile is reporting the average of sixty-four pixels and calling it a
measurement.

This is the I/O layer of the canvas. `render/` stays numpy-in, pixels-out, so
the drawing can still be gated without a window.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# How much decimated imagery to keep. Tiles are pure cache: dropping one costs
# a re-read and nothing else, so the budget is about responsiveness, not
# correctness.
DEFAULT_CACHE_BYTES = 128 << 20  # 128 MiB

# Never ask GDAL for a window smaller than this on a side; the per-read
# overhead starts to dominate below it.
MIN_WINDOW = 16


@dataclass(frozen=True)
class Level:
    """One level of the pyramid.

    factor    decimation; 1 is full resolution, 2 is every second pixel
    width     columns at this level
    height    rows at this level
    native    True when the file itself carries this overview, so the read is
              a lookup rather than a decimation
    """

    factor: int
    width: int
    height: int
    native: bool

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class Window:
    """A rectangle of source pixels, and the level it is read at."""

    row_off: int
    col_off: int
    rows: int
    cols: int
    factor: int

    def key(self) -> tuple[int, int, int, int, int]:
        return (self.factor, self.row_off, self.col_off, self.rows, self.cols)


@dataclass
class Tile:
    """Decimated pixels, plus where they came from.

    values    (out_rows, out_cols) float32, NaN for null
    window    the source rectangle and level
    transform the affine of *this tile*, so it can be placed on screen without
              asking the source again
    """

    values: np.ndarray
    window: Window
    transform: Any

    @property
    def nbytes(self) -> int:
        return int(self.values.nbytes)


class LruCache:
    """Bounded by bytes, not by entry count.

    Counting entries would be meaningless here: a tile can be a hundred pixels
    or a hundred megabytes, and the resource that runs out is memory.
    """

    def __init__(self, max_bytes: int = DEFAULT_CACHE_BYTES) -> None:
        self.max_bytes = max_bytes
        self._entries: OrderedDict[Any, Tile] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Any) -> Tile | None:
        with self._lock:
            tile = self._entries.get(key)
            if tile is None:
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return tile

    def put(self, key: Any, tile: Tile) -> None:
        with self._lock:
            if key in self._entries:
                self._bytes -= self._entries[key].nbytes
                del self._entries[key]
            self._entries[key] = tile
            self._bytes += tile.nbytes
            while self._bytes > self.max_bytes and len(self._entries) > 1:
                _, evicted = self._entries.popitem(last=False)
                self._bytes -= evicted.nbytes

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0

    @property
    def nbytes(self) -> int:
        return self._bytes

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._entries),
            "bytes": self._bytes,
            "mb": round(self._bytes / (1 << 20), 2),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }


class RasterSource:
    """A raster on disk, read at whatever resolution is asked for.

    Opens the file once and keeps the handle: reopening per tile costs more
    than the read itself on a tiled GeoTIFF.
    """

    def __init__(self, path: str | Path, *, band: int = 1,
                 cache_bytes: int = DEFAULT_CACHE_BYTES) -> None:
        import rasterio

        self.path = Path(path)
        self.band = band
        self._dataset = rasterio.open(self.path)
        self.width = self._dataset.width
        self.height = self._dataset.height
        self.transform = self._dataset.transform
        self.crs = self._dataset.crs
        self.nodata = self._dataset.nodata
        # What the file says its numbers mean. Every artefact this project
        # writes stamps `GEOPOTENTIAL_UNIT`, so a raster it produced carries
        # its own unit and nothing has to be told twice.
        try:
            self.unit = self._dataset.tags().get("GEOPOTENTIAL_UNIT") or ""
        except Exception:                            # noqa: BLE001
            self.unit = ""
        self.cache = LruCache(cache_bytes)
        self.pixels_read = 0  # what the gate measures
        self._levels = self._build_levels()

    # ---- the pyramid ----------------------------------------------------

    def _build_levels(self) -> list[Level]:
        """The levels available, from the file's overviews where they exist.

        A GeoTIFF written with overviews already holds the decimated pyramid;
        using it is a lookup rather than a resampling, and it is why the
        packaging rule cares whether a file is cloud-optimized. Where the file
        has none, decimated reads synthesize the same levels at read time —
        slower, correct, and the `native` flag says which happened.
        """
        native = set(self._dataset.overviews(self.band))
        levels = [Level(1, self.width, self.height, True)]
        factor = 2
        while max(self.width // factor, self.height // factor) >= MIN_WINDOW:
            levels.append(Level(
                factor,
                max(1, self.width // factor),
                max(1, self.height // factor),
                factor in native,
            ))
            factor *= 2
        return levels

    @property
    def levels(self) -> list[Level]:
        return list(self._levels)

    def level_for_scale(self, map_units_per_pixel: float) -> Level:
        """Pick the level whose pixel is at most one screen pixel.

        map_units_per_pixel  the viewport's scale, in the raster's CRS units
        returns              the coarsest level that still resolves the screen

        Choosing the *coarsest sufficient* level is the whole point: one level
        finer doubles the read for detail the screen cannot show. Ties go to
        the finer level, so a boundary never loses detail.
        """
        source_pixel = abs(self.transform.a)
        if source_pixel <= 0 or map_units_per_pixel <= 0:
            return self._levels[0]
        wanted = map_units_per_pixel / source_pixel
        chosen = self._levels[0]
        for level in self._levels:
            if level.factor <= wanted:
                chosen = level
            else:
                break
        return chosen

    # ---- display reads --------------------------------------------------

    def read_window(
        self,
        left: float,
        bottom: float,
        right: float,
        top: float,
        map_units_per_pixel: float,
    ) -> Tile | None:
        """Read the part of the raster covering a map extent, decimated to scale.

        left..top            the extent wanted, in the raster's CRS
        map_units_per_pixel  the viewport scale, to choose the level
        returns              a Tile, or None when the extent misses the raster

        The result is cached by (level, window). Nulls are already NaN.
        **Never use this for a measurement** — see `sample`.
        """
        import rasterio
        from rasterio.windows import Window as RioWindow

        level = self.level_for_scale(map_units_per_pixel)
        inverse = ~self.transform
        col_a, row_a = inverse * (left, top)
        col_b, row_b = inverse * (right, bottom)

        col_off = max(0, int(np.floor(min(col_a, col_b))))
        row_off = max(0, int(np.floor(min(row_a, row_b))))
        col_end = min(self.width, int(np.ceil(max(col_a, col_b))))
        row_end = min(self.height, int(np.ceil(max(row_a, row_b))))
        if col_end <= col_off or row_end <= row_off:
            return None

        window = Window(row_off, col_off, row_end - row_off, col_end - col_off,
                        level.factor)
        cached = self.cache.get(window.key())
        if cached is not None:
            return cached

        out_rows = max(1, window.rows // level.factor)
        out_cols = max(1, window.cols // level.factor)
        values = self._dataset.read(
            self.band,
            window=RioWindow(window.col_off, window.row_off, window.cols, window.rows),
            out_shape=(out_rows, out_cols),
            resampling=rasterio.enums.Resampling.average,
            masked=False,
        ).astype(np.float32)
        if self.nodata is not None and not np.isnan(self.nodata):
            values = np.where(values == np.float32(self.nodata), np.nan, values)
        self.pixels_read += out_rows * out_cols

        tile_transform = self._dataset.window_transform(
            RioWindow(window.col_off, window.row_off, window.cols, window.rows)
        ) * rasterio.Affine.scale(
            window.cols / out_cols, window.rows / out_rows
        )
        tile = Tile(np.ascontiguousarray(values), window, tile_transform)
        self.cache.put(window.key(), tile)
        return tile

    # ---- measurement ----------------------------------------------------

    def sample(self, x: float, y: float) -> float | None:
        """The value at a map coordinate, read from the source at full resolution.

        x, y     map coordinates in the raster's CRS
        returns  the pixel's value, or None outside the grid or on a null

        **Always full resolution, whatever the canvas is displaying.** The tile
        on screen may be decimated 64:1; its pixel is an average of 4096 source
        pixels, and reporting that as the value at a point would be reporting a
        number that exists nowhere in the data.

        Nearest pixel, no interpolation: the readout reports what is stored.
        """
        from rasterio.windows import Window as RioWindow

        col, row = (~self.transform) * (x, y)
        col, row = int(np.floor(col)), int(np.floor(row))
        if not (0 <= row < self.height and 0 <= col < self.width):
            return None
        value = float(
            self._dataset.read(
                self.band, window=RioWindow(col, row, 1, 1), masked=False
            )[0, 0]
        )
        self.pixels_read += 1
        if self.nodata is not None and not np.isnan(self.nodata) and value == self.nodata:
            return None
        return None if not np.isfinite(value) else value

    # ---- lifecycle ------------------------------------------------------

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        b = self._dataset.bounds
        return (b.left, b.bottom, b.right, b.top)

    def describe(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "pixels": self.width * self.height,
            "levels": [
                {"factor": l.factor, "width": l.width, "height": l.height,
                 "native": l.native}
                for l in self._levels
            ],
            "native_overviews": sum(1 for l in self._levels if l.native and l.factor > 1),
            "crs": str(self.crs) if self.crs else None,
            "nodata": self.nodata,
            "cache": self.cache.stats(),
            "pixels_read": self.pixels_read,
        }

    def close(self) -> None:
        self._dataset.close()
        self.cache.clear()

    def __enter__(self) -> "RasterSource":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
