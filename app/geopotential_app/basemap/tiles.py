"""Fetching and caching basemap tiles. ADR-MSP-006.

The only place in the product that speaks to the network, and it speaks HTTPS
to a declared tile service and nothing else. There is no server here, no port
listening, no WebView, no web framework — those stay forbidden, and the
architecture gate keeps checking.

Three rules the code holds to:

- **Nothing happens unless a source is chosen.** With no basemap selected, no
  connection is opened at all.
- **A fetched tile is cached on disk**, with its source and the date. The map
  that supported a decision reopens without a network, and the record of where
  the picture came from survives with it.
- **A failure is not an error in the work.** No network means no background,
  said plainly; every scientific path is untouched.

Tiles are pictures. They never become values: `basemap/` is not readable by any
operator, carries no unit, and has no value under the cursor.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .sources import TILE_SIZE, Source

# Identifies the product to the tile service. OSM's policy requires a real
# identifying agent, and an anonymous scraper is what gets a client blocked.
USER_AGENT = "GeoPotentialProfessional/0.2 (+geoscience desktop; contact: local install)"

# Politeness, and self-defence: a screen never needs more than a few dozen
# tiles, and anything beyond this is a bulk download, which OSM's terms forbid.
MAX_TILES_PER_VIEW = 64
TIMEOUT_SECONDS = 6.0


def deg_to_tile(longitude: float, latitude: float, zoom: int) -> tuple[int, int]:
    """Which tile a coordinate falls in.

    reference the standard slippy-map scheme (OSM wiki, "Slippy map
    tilenames"): x from longitude, y from the Mercator projection of latitude.
    """
    n = 2 ** zoom
    x = int((longitude + 180.0) / 360.0 * n)
    lat = math.radians(max(-85.05112878, min(85.05112878, latitude)))
    y = int((1.0 - math.asinh(math.tan(lat)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """A tile's extent in Web Mercator metres."""
    n = 2 ** zoom
    span = 20037508.342789244
    size = 2 * span / n
    left = -span + x * size
    top = span - y * size
    return left, top - size, left + size, top


def zoom_for(metres_per_pixel: float, latitude: float) -> int:
    """The zoom level whose tiles are about the size the screen is drawing.

    A level too low is a blurred picture; too high is sixteen times the tiles
    for no more detail on screen.
    """
    if metres_per_pixel <= 0:
        return 12
    ground = 156543.03392804097 * math.cos(math.radians(
        max(-85.0, min(85.0, latitude))))
    zoom = math.log2(ground / metres_per_pixel)
    return int(max(0, min(19, round(zoom))))


class TileCache:
    """Tiles on disk, with where each came from and when.

    Inside the project, so the map that supported a decision reopens with it —
    and so the record of the source survives beside the data it was drawn under.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def _path(self, source: Source, z: int, x: int, y: int) -> Path:
        digest = hashlib.sha256(source.template.encode()).hexdigest()[:8]
        return self.root / source.key / digest / str(z) / str(x) / f"{y}.png"

    def read(self, source: Source, z: int, x: int, y: int) -> bytes | None:
        path = self._path(source, z, x, y)
        try:
            return path.read_bytes() if path.exists() else None
        except OSError:
            return None

    def write(self, source: Source, z: int, x: int, y: int, payload: bytes) -> None:
        path = self._path(source, z, x, y)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".part")
            temporary.write_bytes(payload)
            temporary.replace(path)
            self._record(source)
        except OSError:
            return                    # a cache that cannot be written is a
                                      # slower map, never a failed run

    def _record(self, source: Source) -> None:
        """Which source this cache holds, and when it was last filled."""
        manifest = self.root / "SOURCES.json"
        with self._lock:
            try:
                known = json.loads(manifest.read_text()) if manifest.exists() else {}
            except (OSError, json.JSONDecodeError):
                known = {}
            known[source.key] = {
                "name": source.name,
                "template": source.template,
                "licence": source.licence,
                "attribution": source.attribution,
                "last_fetched": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
            }
            try:
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(json.dumps(known, indent=2), encoding="utf-8")
            except OSError:
                return


def fetch(source: Source, z: int, x: int, y: int,
          cache: TileCache | None = None) -> bytes | None:
    """One tile, from the cache when possible and from the network otherwise.

    output  the PNG bytes, or None when there is no network and no cached copy

    A failure returns None. Nothing here raises into the drawing path: a map
    without its background is a map, and a run that failed because a tile
    server was down would be absurd.
    """
    if cache is not None:
        cached = cache.read(source, z, x, y)
        if cached is not None:
            return cached
    request = urllib.request.Request(
        source.url(z, x, y), headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if cache is not None:
        cache.write(source, z, x, y, payload)
    return payload


def tiles_for_extent(
    extent: tuple[float, float, float, float], zoom: int
) -> list[tuple[int, int]]:
    """Which tiles cover a Web Mercator extent, capped.

    The cap is politeness and self-defence at once: a screen needs a few dozen
    tiles, and a request for thousands is a bulk download, which the sources'
    terms forbid.
    """
    span = 20037508.342789244
    n = 2 ** zoom
    size = 2 * span / n
    left, bottom, right, top = extent
    x0 = max(0, int((left + span) / size))
    x1 = min(n - 1, int((right + span) / size))
    y0 = max(0, int((span - top) / size))
    y1 = min(n - 1, int((span - bottom) / size))
    wanted = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return wanted[:MAX_TILES_PER_VIEW]


def decode(payload: bytes) -> np.ndarray | None:
    """A PNG tile as (h, w, 4) uint8 RGBA, or None when it will not decode."""
    from PySide6.QtGui import QImage

    image = QImage()
    if not image.loadFromData(payload):
        return None
    image = image.convertToFormat(QImage.Format_RGBA8888)
    width, height = image.width(), image.height()
    if width <= 0 or height <= 0:
        return None
    buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
    return buffer.reshape(height, image.bytesPerLine() // 4, 4)[:, :width].copy()


def mosaic(
    source: Source,
    extent: tuple[float, float, float, float],
    zoom: int,
    cache: TileCache | None = None,
) -> tuple[np.ndarray, tuple[float, float, float, float]] | None:
    """Every tile covering an extent, stitched, with the mosaic's own extent.

    output  (rgba, extent in Web Mercator) — the mosaic is tile-aligned, so its
            extent is larger than the one asked for; the caller warps it into
            the view rather than assuming the two match.
    """
    wanted = tiles_for_extent(extent, zoom)
    if not wanted:
        return None
    xs = [x for x, _ in wanted]
    ys = [y for _, y in wanted]
    columns = max(xs) - min(xs) + 1
    rows = max(ys) - min(ys) + 1
    canvas = np.zeros((rows * TILE_SIZE, columns * TILE_SIZE, 4), dtype=np.uint8)

    # Fetched a few at a time, not one after another: nine tiles at 200 ms of
    # latency each is two seconds of staring at nothing. The pool is small on
    # purpose — OSM's usage policy asks for no more than two download threads,
    # and politeness here is what keeps the source available.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=max(1, source.max_concurrent)) as pool:
        payloads = list(pool.map(
            lambda tile: fetch(source, zoom, tile[0], tile[1], cache), wanted
        ))

    drawn = 0
    for (x, y), payload in zip(wanted, payloads):
        if payload is None:
            continue
        tile = decode(payload)
        if tile is None or tile.shape[0] != TILE_SIZE:
            continue
        row = (y - min(ys)) * TILE_SIZE
        column = (x - min(xs)) * TILE_SIZE
        canvas[row:row + TILE_SIZE, column:column + TILE_SIZE] = tile
        drawn += 1

    if drawn == 0:
        return None
    left, bottom, _, _ = tile_bounds(min(xs), max(ys), zoom)
    _, _, right, top = tile_bounds(max(xs), min(ys), zoom)
    return canvas, (left, bottom, right, top)
