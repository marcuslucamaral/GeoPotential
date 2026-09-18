"""Level 1 — the domain guards.

These are the rules that make the legacy tree's defect classes impossible
before any method is written. Each test names the defect it forecloses.
"""
from __future__ import annotations

import unittest

import numpy as np
from affine import Affine

from geopotential_worker.domain.crs import CrsInfo, MissingCrsError, NotMetricError
from geopotential_worker.domain.criterion import (
    Criterion,
    CriterionStack,
    Stage,
    StageError,
)
from geopotential_worker.domain.grid import TargetGrid


def utm_grid(width: int = 8, height: int = 8, px: float = 10.0, py: float = 10.0):
    return TargetGrid(
        transform=Affine(px, 0.0, 500000.0, 0.0, -py, 4_500_000.0),
        crs=CrsInfo.from_user_input("EPSG:26912", source="test"),
        width=width,
        height=height,
    )


class Crs(unittest.TestCase):
    def test_absent_crs_is_refused_by_name(self) -> None:
        """Defect D-02: EPSG:31982 as a silent .get() fallback in three modules."""
        for value in (None, "", "   "):
            with self.assertRaises(MissingCrsError) as ctx:
                CrsInfo.from_user_input(value, source="bouguer.csv")
            self.assertIn("bouguer.csv", str(ctx.exception))

    def test_unparseable_crs_is_refused(self) -> None:
        with self.assertRaises(MissingCrsError):
            CrsInfo.from_user_input("EPSG:not-a-code", source="density.tif")

    def test_unit_follows_the_crs(self) -> None:
        """Defect D-03: a pixel size labelled 'm' beside a geographic CRS."""
        self.assertEqual(CrsInfo.from_user_input("EPSG:26912", source="t").unit, "metre")
        self.assertEqual(CrsInfo.from_user_input("EPSG:4326", source="t").unit, "degree")

    def test_metric_operation_refused_on_a_geographic_crs(self) -> None:
        geographic = CrsInfo.from_user_input("EPSG:4326", source="t")
        with self.assertRaises(NotMetricError) as ctx:
            geographic.require_metric("euclidean distance")
        self.assertIn("euclidean distance", str(ctx.exception))
        self.assertIn("degree", str(ctx.exception))

    def test_metric_operation_allowed_on_a_projected_crs(self) -> None:
        CrsInfo.from_user_input("EPSG:26912", source="t").require_metric("IDW radius")


class Grid(unittest.TestCase):
    def test_pixel_size_is_two_numbers(self) -> None:
        """Defect D-04: collapsing px and py into one scalar by averaging."""
        grid = utm_grid(px=30.0, py=10.0)
        self.assertEqual(grid.pixel_size, (30.0, 10.0))
        self.assertFalse(grid.is_square_pixel)

    def test_square_pixel_is_recognised(self) -> None:
        self.assertTrue(utm_grid(px=10.0, py=10.0).is_square_pixel)

    def test_shape_is_rows_then_cols(self) -> None:
        grid = utm_grid(width=5, height=3)
        self.assertEqual(grid.shape, (3, 5))

    def test_bounds_follow_a_north_up_transform(self) -> None:
        grid = utm_grid(width=10, height=4, px=10.0, py=10.0)
        left, bottom, right, top = grid.bounds
        self.assertAlmostEqual(left, 500000.0)
        self.assertAlmostEqual(right, 500100.0)
        self.assertAlmostEqual(top, 4_500_000.0)
        self.assertAlmostEqual(bottom, 4_499_960.0)

    def test_degenerate_size_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            TargetGrid(Affine.identity(),
                       CrsInfo.from_user_input("EPSG:26912", source="t"), 0, 5)

    def test_memory_estimate(self) -> None:
        """MSP-06: no high-cost operation runs without a resource estimate."""
        grid = utm_grid(width=1000, height=1000)
        self.assertEqual(grid.estimated_bytes(), 4_000_000)


class CriterionStages(unittest.TestCase):
    """Defect D-01: `array` holding raw and normalized values under one key."""

    def test_normalized_may_not_carry_a_unit(self) -> None:
        grid = utm_grid()
        with self.assertRaises(ValueError) as ctx:
            Criterion("m", np.zeros(grid.shape, np.float32), grid,
                      Stage.NORMALIZED, unit="mGal")
        self.assertIn("dimensionless", str(ctx.exception))

    def test_raw_must_declare_a_unit(self) -> None:
        grid = utm_grid()
        with self.assertRaises(ValueError) as ctx:
            Criterion("d", np.zeros(grid.shape, np.float32), grid, Stage.RAW)
        self.assertIn("unit", str(ctx.exception))

    def test_normalized_outside_range_is_refused_at_construction(self) -> None:
        grid = utm_grid()
        values = np.full(grid.shape, 1.4, dtype=np.float32)
        with self.assertRaises(ValueError) as ctx:
            Criterion("m", values, grid, Stage.NORMALIZED)
        self.assertIn("[0, 1]", str(ctx.exception))

    def test_wrong_dtype_is_refused(self) -> None:
        grid = utm_grid()
        with self.assertRaises(TypeError):
            Criterion("m", np.zeros(grid.shape, np.float64), grid,
                      Stage.NORMALIZED)

    def test_wrong_shape_is_refused(self) -> None:
        grid = utm_grid()
        with self.assertRaises(ValueError):
            Criterion("m", np.zeros((3, 3), np.float32), grid, Stage.NORMALIZED)

    def test_all_null_normalized_is_allowed(self) -> None:
        """A criterion with no valid pixel is empty, not out of range."""
        grid = utm_grid()
        Criterion("m", np.full(grid.shape, np.nan, np.float32), grid, Stage.NORMALIZED)


class Stack(unittest.TestCase):
    def _criterion(self, name: str, stage: Stage, grid=None) -> Criterion:
        grid = grid or utm_grid()
        if stage is Stage.RAW:
            return Criterion(name, np.full(grid.shape, 2.5, np.float32), grid,
                             stage, unit="g/cm3")
        return Criterion(name, np.full(grid.shape, 0.5, np.float32), grid, stage)

    def test_raw_criterion_cannot_be_aggregated(self) -> None:
        """Defect D-01 again: passing a raw layer to Gamma Fuzzy must raise."""
        grid = utm_grid()
        stack = CriterionStack([
            self._criterion("heat_flow", Stage.NORMALIZED, grid),
            self._criterion("density", Stage.RAW, grid),
        ])
        with self.assertRaises(StageError) as ctx:
            stack.require_normalized()
        self.assertIn("density", str(ctx.exception))
        self.assertNotIn("heat_flow", str(ctx.exception))

    def test_all_normalized_passes(self) -> None:
        grid = utm_grid()
        CriterionStack([
            self._criterion("a", Stage.NORMALIZED, grid),
            self._criterion("b", Stage.NORMALIZED, grid),
        ]).require_normalized()

    def test_names_are_the_canonical_order(self) -> None:
        """Defect D-06: weights bound to list(some_dict.keys()) at two sites."""
        grid = utm_grid()
        stack = CriterionStack([
            self._criterion("gravity", Stage.NORMALIZED, grid),
            self._criterion("magnetics", Stage.NORMALIZED, grid),
            self._criterion("faults", Stage.NORMALIZED, grid),
        ])
        self.assertEqual(stack.names, ["gravity", "magnetics", "faults"])
        self.assertEqual(stack.stacked().shape, (3, *grid.shape))
        # position i of `names` is row i of `stacked`, and that is the binding
        for i, name in enumerate(stack.names):
            self.assertEqual(stack[i].name, name)

    def test_mixed_grids_are_refused(self) -> None:
        """A second transform per layer is a second representation."""
        with self.assertRaises(ValueError) as ctx:
            CriterionStack([
                self._criterion("a", Stage.NORMALIZED, utm_grid(8, 8)),
                self._criterion("b", Stage.NORMALIZED, utm_grid(16, 16)),
            ])
        self.assertIn("different grid", str(ctx.exception))

    def test_duplicate_name_is_refused(self) -> None:
        grid = utm_grid()
        stack = CriterionStack([self._criterion("a", Stage.NORMALIZED, grid)])
        with self.assertRaises(ValueError):
            stack.add(self._criterion("a", Stage.NORMALIZED, grid))


if __name__ == "__main__":
    unittest.main()
