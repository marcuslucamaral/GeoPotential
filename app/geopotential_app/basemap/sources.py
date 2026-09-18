"""The basemap sources, and what each one obliges. ADR-MSP-006.

Only open sources are here, and each carries its licence and the attribution
that licence requires. All five are rendered from OpenStreetMap data: the
standard style, the Humanitarian style, the German style, a public-transport
style, and a topographic one. The attribution is not decoration: ODbL and CC-BY both
oblige it, and a printed map without it breaks the terms the tiles came under.

Google, Bing, Esri and Mapbox are deliberately absent. Their terms forbid using
the tiles outside their own applications, or require a contract and a key, and
embedding that would hand a legal problem to whoever runs this.
"""
from __future__ import annotations

from dataclasses import dataclass

# Web Mercator: what every XYZ tile service serves in. A basemap is only ever
# drawn through the display reprojection (ADR-MSP-003), never by pretending the
# data is in this CRS.
TILE_CRS = "EPSG:3857"
TILE_SIZE = 256


@dataclass(frozen=True)
class Source:
    """One tile service, with the obligations that come with it."""

    key: str
    name: str
    template: str            # {z}/{x}/{y}
    attribution: str         # shown on the map and in the exported image
    licence: str
    max_zoom: int = 19
    #: How many tiles to fetch at once. OSM's tile usage policy asks for no
    #: more than two download threads, and two is plenty for a screen.
    max_concurrent: int = 2

    def url(self, z: int, x: int, y: int) -> str:
        return self.template.format(z=z, x=x, y=y)


SOURCES: dict[str, Source] = {
    "osm": Source(
        key="osm",
        name="OpenStreetMap",
        template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors",
        licence="ODbL 1.0",
        max_zoom=19,
    ),
    "osm-hot": Source(
        key="osm-hot",
        name="OSM Humanitarian",
        template="https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors · Tiles: Humanitarian OSM "
                    "Team, hosted by OpenStreetMap France",
        licence="ODbL 1.0",
        max_zoom=19,
    ),
    "osm-de": Source(
        key="osm-de",
        name="OpenStreetMap (DE)",
        template="https://a.tile.openstreetmap.de/{z}/{x}/{y}.png",
        attribution="© OpenStreetMap contributors · Tiles: OpenStreetMap "
                    "Deutschland",
        licence="ODbL 1.0",
        max_zoom=18,
    ),
    "opnvkarte": Source(
        key="opnvkarte",
        name="ÖPNVKarte (transporte)",
        template="https://tileserver.memomaps.de/tilegen/{z}/{x}/{y}.png",
        attribution="Map memomaps.de (CC-BY-SA) · © OpenStreetMap contributors",
        licence="CC-BY-SA 2.0",
        max_zoom=18,
    ),
    "opentopomap": Source(
        key="opentopomap",
        name="OpenTopoMap",
        template="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution="© OpenTopoMap (CC-BY-SA) · © OpenStreetMap contributors",
        licence="CC-BY-SA 3.0",
        max_zoom=17,
    ),
}

# Off. The application opens without touching the network, and turning a
# basemap on is a deliberate act (ADR-MSP-006).
NONE = ""


def get(key: str) -> Source | None:
    return SOURCES.get(key)


def names() -> list[dict[str, str]]:
    """The sources, for a menu: key, name, licence and attribution."""
    return [
        {"key": s.key, "name": s.name, "licence": s.licence,
         "attribution": s.attribution}
        for s in SOURCES.values()
    ]
