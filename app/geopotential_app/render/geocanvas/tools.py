"""What the map's tools are, as state and arithmetic. No Qt, no I/O.

A sketch is a list of vertices in **map coordinates**. Everything a tool
measures is computed here so it can be gated without a window, and so the
canvas keeps only the plumbing.

Two rules the gate holds to:

- **A metric operation on a geographic CRS is refused, not approximated**
  (P-14). A length in degrees is not a length; latitude changes what a degree
  of longitude is worth, and averaging that away silently is how a map ends up
  quoting a distance nobody can reproduce.
- **A mode that draws must be a mode that shows.** `Sketch` carries whether it
  is being drawn, so the canvas has something to ask before painting anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The modes a click can mean. Exactly one is active at a time; the canvas
# refuses to be in two.
NAVIGATE = "navigate"
IDENTIFY = "identify"
AOI = "aoi"
MEASURE_DISTANCE = "measure-distance"
MEASURE_AREA = "measure-area"

MODES = (NAVIGATE, IDENTIFY, AOI, MEASURE_DISTANCE, MEASURE_AREA)
SKETCHING = (AOI, MEASURE_DISTANCE, MEASURE_AREA)


class GeographicCrsRefused(ValueError):
    """A distance or an area was asked for in degrees."""


@dataclass
class Sketch:
    """Vertices being placed, and whether placing is happening.

    `drawing` is not decoration: the AOI defect this replaces was a polygon
    that stayed on the map for the rest of the session because ending the draw
    lowered a flag and cleared nothing.
    """

    points: list[tuple[float, float]] = field(default_factory=list)
    drawing: bool = False

    def begin(self) -> None:
        self.points = []
        self.drawing = True

    def add(self, x: float, y: float) -> None:
        if self.drawing:
            self.points.append((float(x), float(y)))

    def undo(self) -> bool:
        """Remove the last vertex. True when one was there to remove."""
        if self.drawing and self.points:
            self.points.pop()
            return True
        return False

    def cancel(self) -> None:
        """Leave nothing behind. A cancelled drawing records nothing at all."""
        self.points = []
        self.drawing = False

    def finish(self) -> list[tuple[float, float]]:
        """Stop drawing and hand back the vertices."""
        self.drawing = False
        return list(self.points)

    def clear(self) -> None:
        self.points = []
        self.drawing = False

    def __len__(self) -> int:
        return len(self.points)


def require_metric(crs_is_geographic: bool, crs_name: str) -> None:
    """Refuse a metric operation on a geographic CRS, naming the CRS.

    inputs   whether the layer's CRS is geographic, and its name
    raises   GeographicCrsRefused
    """
    if crs_is_geographic:
        named = crs_name or "a geographic CRS"
        raise GeographicCrsRefused(
            f"a distance or an area cannot be measured in {named}: its "
            f"coordinates are degrees, not metres. Reproject to a metric CRS "
            f"first."
        )


def polyline_length(points: list[tuple[float, float]]) -> float:
    """Total length of a polyline, in the CRS's own linear unit.

    inputs   vertices in map coordinates, at least two
    output   sum of the Euclidean segment lengths
    reference plane geometry; valid because the CRS is projected, which
              `require_metric` has already established.
    """
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Area of a closed polygon, in the CRS's linear unit squared.

    inputs   vertices in map coordinates, at least three; the ring is closed
             implicitly
    output   absolute area
    reference the shoelace formula (Gauss's area formula); the absolute value
              makes the winding direction irrelevant.
    """
    if len(points) < 3:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def format_distance(metres: float, unit: str) -> str:
    """A distance with its unit, at a precision a person can read.

    Six decimals of a UTM metre is noise; a kilometre is written as one when
    the number earns it.
    """
    if unit in ("metre", "meter", "m") and metres >= 1000.0:
        return f"{metres / 1000.0:,.3f} km"
    return f"{metres:,.1f} {unit or 'units'}"


def format_area(square_units: float, unit: str) -> str:
    """An area with its unit squared, in km² once it stops being readable."""
    if unit in ("metre", "meter", "m"):
        if square_units >= 1e6:
            return f"{square_units / 1e6:,.3f} km²"
        return f"{square_units:,.1f} m²"
    return f"{square_units:,.1f} {unit or 'units'}²"
