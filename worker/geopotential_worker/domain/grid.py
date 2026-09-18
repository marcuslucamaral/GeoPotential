"""The target grid of one analysis.

One `TargetGrid` per run owns the transform, the CRS, the size and the pixel
size. Every raster in a run is on it. A second transform living in a per-layer
dictionary is a second representation, which is defect D-01 of the legacy tree.
"""
from __future__ import annotations

from dataclasses import dataclass

from affine import Affine

from .crs import CrsInfo


@dataclass(frozen=True)
class TargetGrid:
    """The single grid every criterion of a run lives on.

    transform  affine, north-up, origin at the top-left of the grid
    crs        the CRS the transform is expressed in
    width      columns
    height     rows

    Arrays on this grid are (height, width) float32, row-major, NaN for null.
    """

    transform: Affine
    crs: CrsInfo
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"grid must have positive size, got {self.width}x{self.height}"
            )

    @property
    def shape(self) -> tuple[int, int]:
        """(rows, cols) — the numpy order, stated because (x, y) also looks right."""
        return self.height, self.width

    @property
    def pixel_size(self) -> tuple[float, float]:
        """(px, py) in the unit of `crs`, both positive.

        Two numbers, never averaged. Anisotropic pixels are legal, and
        collapsing them into one scalar is silently wrong everywhere except
        px == py — defect D-04 of the legacy tree.
        """
        return abs(self.transform.a), abs(self.transform.e)

    @property
    def is_square_pixel(self) -> bool:
        px, py = self.pixel_size
        return abs(px - py) <= 1e-9 * max(px, py)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(left, bottom, right, top) in the grid CRS."""
        left, top = self.transform * (0, 0)
        right, bottom = self.transform * (self.width, self.height)
        return left, bottom, right, top

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    def estimated_bytes(self, bands: int = 1, dtype_size: int = 4) -> int:
        """Memory one full-grid float32 array of `bands` bands would take.

        Used by the grid planner: no high-cost operation runs without a
        resource estimate (MSP-06).
        """
        return self.pixel_count * bands * dtype_size

    def describe(self) -> dict[str, object]:
        px, py = self.pixel_size
        left, bottom, right, top = self.bounds
        return {
            "crs": self.crs.name,
            "crs_unit": self.crs.unit,
            "width": self.width,
            "height": self.height,
            "pixel_size_x": px,
            "pixel_size_y": py,
            "square_pixel": self.is_square_pixel,
            "bounds": [left, bottom, right, top],
            "transform": list(self.transform)[:6],
        }

    def __repr__(self) -> str:
        px, py = self.pixel_size
        return (
            f"TargetGrid({self.width}x{self.height}, {px}x{py} "
            f"{self.crs.unit}, {self.crs.name})"
        )
