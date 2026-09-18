"""Raster I/O for the canvas: windowed reads, level of detail, LRU cache.

This layer exists so `render/` can stay numpy-in, pixels-out. Section 10.1's
pyramids and tiles need to read a file at several resolutions, and putting that
in the renderer would mean the drawing could no longer be gated without one.
"""
from .tiles import DEFAULT_CACHE_BYTES, Level, LruCache, RasterSource, Tile, Window
from .warp import reproject_tile, source_window

__all__ = [
    "reproject_tile",
    "source_window",
    "RasterSource",
    "Tile",
    "Window",
    "Level",
    "LruCache",
    "DEFAULT_CACHE_BYTES",
]
