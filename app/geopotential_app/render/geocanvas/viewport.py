"""Viewport arithmetic: map coordinates to screen pixels and back.

No Qt. This is the part of the canvas a numerical gate can check without a
window, and the part that has to be right for the readout under the cursor to
mean anything (gate M4: coordinate under cursor correct, value under cursor
correct).

Convention, stated because both orderings look right in a debugger:
  - map coordinates are (x, y) with y increasing north
  - screen coordinates are (px, py) with py increasing down
  - arrays are (row, col), row 0 at the top, matching a north-up transform
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Extent:
    """An axis-aligned box in one CRS. All four in that CRS's unit."""

    left: float
    bottom: float
    right: float
    top: float

    def __post_init__(self) -> None:
        if self.right <= self.left or self.top <= self.bottom:
            raise ValueError(
                f"degenerate extent: ({self.left}, {self.bottom}, "
                f"{self.right}, {self.top})"
            )

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def centre(self) -> tuple[float, float]:
        return (self.left + self.right) / 2.0, (self.bottom + self.top) / 2.0

    def expanded(self, factor: float) -> "Extent":
        cx, cy = self.centre
        w, h = self.width * factor / 2.0, self.height * factor / 2.0
        return Extent(cx - w, cy - h, cx + w, cy + h)

    def union(self, other: "Extent") -> "Extent":
        return Extent(
            min(self.left, other.left),
            min(self.bottom, other.bottom),
            max(self.right, other.right),
            max(self.top, other.top),
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.left, self.bottom, self.right, self.top


@dataclass(frozen=True)
class Viewport:
    """A map extent shown in a widget of a given pixel size.

    The extent is fitted to the widget's aspect ratio, so a square kilometre is
    square on screen. Scale is uniform in x and y — anisotropic screen scaling
    would make a measured distance depend on its direction.
    """

    extent: Extent
    pixel_width: int
    pixel_height: int

    def __post_init__(self) -> None:
        if self.pixel_width <= 0 or self.pixel_height <= 0:
            raise ValueError(
                f"viewport must have positive pixel size, got "
                f"{self.pixel_width}x{self.pixel_height}"
            )

    @property
    def scale(self) -> float:
        """Map units per screen pixel. One number, both axes."""
        return max(
            self.extent.width / self.pixel_width,
            self.extent.height / self.pixel_height,
        )

    @property
    def fitted_extent(self) -> Extent:
        """The extent actually shown, after fitting to the widget's aspect."""
        s = self.scale
        cx, cy = self.extent.centre
        half_w = s * self.pixel_width / 2.0
        half_h = s * self.pixel_height / 2.0
        return Extent(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    def to_screen(self, x: np.ndarray | float, y: np.ndarray | float):
        """Map (x, y) to screen (px, py). Vectorized; never called per point."""
        e = self.fitted_extent
        s = self.scale
        return (np.asarray(x) - e.left) / s, (e.top - np.asarray(y)) / s

    def to_map(self, px: np.ndarray | float, py: np.ndarray | float):
        """Screen (px, py) back to map (x, y). The readout under the cursor."""
        e = self.fitted_extent
        s = self.scale
        return e.left + np.asarray(px) * s, e.top - np.asarray(py) * s

    def zoomed(self, factor: float, *, at: tuple[float, float] | None = None) -> "Viewport":
        """Zoom about a map point, keeping that point under the same pixel.

        factor  < 1 zooms in, > 1 zooms out
        at      the map point to hold fixed; the centre if absent
        """
        e = self.fitted_extent
        ax, ay = at if at is not None else e.centre
        left = ax + (e.left - ax) * factor
        right = ax + (e.right - ax) * factor
        bottom = ay + (e.bottom - ay) * factor
        top = ay + (e.top - ay) * factor
        return Viewport(Extent(left, bottom, right, top), self.pixel_width, self.pixel_height)

    def panned(self, dx_pixels: float, dy_pixels: float) -> "Viewport":
        e = self.fitted_extent
        s = self.scale
        return Viewport(
            Extent(e.left - dx_pixels * s, e.bottom + dy_pixels * s,
                   e.right - dx_pixels * s, e.top + dy_pixels * s),
            self.pixel_width,
            self.pixel_height,
        )

    def resized(self, pixel_width: int, pixel_height: int) -> "Viewport":
        return Viewport(self.fitted_extent, pixel_width, pixel_height)


def extent_from_transform(transform, width: int, height: int) -> Extent:
    """Extent of a north-up affine grid. `transform` is an affine.Affine."""
    left, top = transform * (0, 0)
    right, bottom = transform * (width, height)
    return Extent(left, bottom, right, top)
