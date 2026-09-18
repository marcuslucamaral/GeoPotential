"""The basemap: open tiles, off by default. ADR-MSP-006.

The only part of the product that touches the network, and only when a source
is chosen. A basemap is a picture under the data: it carries no unit, has no
value under the cursor, is not an operator's input, and appears in a run's
manifest as provenance of the *image*, never as an input to the science.
"""
from .sources import NONE, SOURCES, TILE_CRS, Source, get, names
from .tiles import TileCache, mosaic, zoom_for

__all__ = ["NONE", "SOURCES", "TILE_CRS", "Source", "TileCache", "get",
           "mosaic", "names", "zoom_for"]
