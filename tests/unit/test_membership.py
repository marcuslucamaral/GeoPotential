"""Level 1 — membership functions.

Two properties are asserted on every function in the family, because they are
what everything downstream assumes: the result is in [0, 1] on a valid pixel,
and NaN on an invalid one. A function that quietly returns 1.2 makes a
suitability map that is wrong and looks right.
"""
from __future__ import annotations

import unittest

import numpy as np

from geopotential_worker.decision import membership as mf


class MembershipRange(unittest.TestCase):
    """Every function, both properties."""

    def setUp(self) -> None:
        rng = np.random.default_rng(20260901)  # seeded: the gate is reproducible
        self.values = rng.normal(50.0, 20.0, size=(64, 64)).astype(np.float32)
        self.values[::7, ::5] = np.nan  # a realistic scatter of nulls
        self.valid = np.isfinite(self.values)

    def _assert_contract(self, result: np.ndarray, name: str) -> None:
        self.assertEqual(result.dtype, np.float32, f"{name}: must return float32")
        self.assertEqual(result.shape, self.values.shape, f"{name}: shape changed")
        self.assertTrue(
            np.isnan(result[~self.valid]).all(),
            f"{name}: a null pixel came back as a number",
        )
        v = result[self.valid]
        self.assertTrue(np.isfinite(v).all(), f"{name}: a valid pixel came back NaN")
        self.assertGreaterEqual(v.min(), 0.0, f"{name}: below 0")
        self.assertLessEqual(v.max(), 1.0, f"{name}: above 1")

    def test_linear_increasing(self) -> None:
        self._assert_contract(mf.linear_increasing(self.values), "linear_increasing")

    def test_linear_decreasing(self) -> None:
        self._assert_contract(mf.linear_decreasing(self.values), "linear_decreasing")

    def test_sigmoidal_both_directions(self) -> None:
        for direction in ("increasing", "decreasing"):
            self._assert_contract(
                mf.sigmoidal(self.values, direction=direction), f"sigmoidal {direction}"
            )

    def test_gaussian(self) -> None:
        self._assert_contract(mf.gaussian(self.values), "gaussian")

    def test_small_and_large(self) -> None:
        positive = np.abs(self.values)
        positive[~self.valid] = np.nan
        for fn, name in ((mf.small, "small"), (mf.large, "large")):
            result = fn(positive, midpoint=50.0)
            self.assertTrue(np.isnan(result[~self.valid]).all(), f"{name}: null lost")
            v = result[self.valid]
            self.assertGreaterEqual(v.min(), 0.0)
            self.assertLessEqual(v.max(), 1.0)


class MembershipValues(unittest.TestCase):
    """Values at points the formula pins exactly."""

    def test_linear_increasing_anchors(self) -> None:
        values = np.array([[0.0, 5.0, 10.0, 20.0, -5.0]], dtype=np.float32)
        result = mf.linear_increasing(values, x_min=0.0, x_max=10.0)
        np.testing.assert_allclose(
            result, [[0.0, 0.5, 1.0, 1.0, 0.0]], atol=1e-6,
            err_msg="mu = 0 below x_min, 1 above x_max, linear between",
        )

    def test_linear_decreasing_is_the_mirror(self) -> None:
        values = np.array([[0.0, 5.0, 10.0]], dtype=np.float32)
        up = mf.linear_increasing(values, x_min=0.0, x_max=10.0)
        down = mf.linear_decreasing(values, x_min=0.0, x_max=10.0)
        np.testing.assert_allclose(up + down, 1.0, atol=1e-6)

    def test_sigmoidal_is_half_at_the_centre(self) -> None:
        values = np.array([[7.0]], dtype=np.float32)
        self.assertAlmostEqual(
            float(mf.sigmoidal(values, center=7.0, slope=1.0)[0, 0]), 0.5, places=6
        )

    def test_sigmoidal_direction_reverses(self) -> None:
        values = np.array([[0.0, 10.0]], dtype=np.float32)
        up = mf.sigmoidal(values, center=5.0, slope=1.0, direction="increasing")
        down = mf.sigmoidal(values, center=5.0, slope=1.0, direction="decreasing")
        np.testing.assert_allclose(up + down, 1.0, atol=1e-6)

    def test_gaussian_peaks_at_the_mean(self) -> None:
        values = np.array([[10.0, 12.0, 8.0]], dtype=np.float32)
        result = mf.gaussian(values, mean=10.0, std=2.0)
        self.assertAlmostEqual(float(result[0, 0]), 1.0, places=6)
        # exp(-0.5) at one standard deviation, both sides, symmetric
        self.assertAlmostEqual(float(result[0, 1]), float(np.exp(-0.5)), places=6)
        self.assertAlmostEqual(float(result[0, 1]), float(result[0, 2]), places=6)

    def test_small_and_large_are_half_at_the_midpoint(self) -> None:
        values = np.array([[25.0]], dtype=np.float32)
        self.assertAlmostEqual(float(mf.small(values, midpoint=25.0)[0, 0]), 0.5, places=6)
        self.assertAlmostEqual(float(mf.large(values, midpoint=25.0)[0, 0]), 0.5, places=6)


class MembershipRefusals(unittest.TestCase):
    """What the functions refuse, and why refusing is the right answer."""

    def test_degenerate_range_is_refused(self) -> None:
        """A constant field has no ordering to map onto [0, 1].

        The legacy tree returned 0.5 everywhere and said nothing, which turns
        an absent gradient into a stated middling suitability.
        """
        flat = np.full((8, 8), 3.0, dtype=np.float32)
        with self.assertRaises(mf.DegenerateRangeError):
            mf.linear_increasing(flat)

    def test_gaussian_without_spread_is_refused(self) -> None:
        flat = np.full((8, 8), 3.0, dtype=np.float32)
        with self.assertRaises(mf.DegenerateRangeError):
            mf.gaussian(flat)

    def test_all_null_returns_all_null(self) -> None:
        empty = np.full((4, 4), np.nan, dtype=np.float32)
        self.assertTrue(np.isnan(mf.linear_increasing(empty)).all())

    def test_bad_direction_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            mf.sigmoidal(np.zeros((2, 2), np.float32), direction="sideways")

    def test_unmapped_class_is_refused(self) -> None:
        """Scoring an unmapped class zero turns a data gap into a claim."""
        codes = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        with self.assertRaises(ValueError) as ctx:
            mf.categorical(codes, {1.0: 0.2, 2.0: 0.8})
        self.assertIn("3", str(ctx.exception))

    def test_categorical_score_outside_range_is_refused(self) -> None:
        codes = np.array([[1.0]], dtype=np.float32)
        with self.assertRaises(ValueError):
            mf.categorical(codes, {1.0: 1.5})

    def test_categorical_maps_and_keeps_nulls(self) -> None:
        codes = np.array([[1.0, 2.0], [np.nan, 1.0]], dtype=np.float32)
        result = mf.categorical(codes, {1.0: 0.25, 2.0: 0.75})
        np.testing.assert_allclose(result[0], [0.25, 0.75], atol=1e-6)
        self.assertTrue(np.isnan(result[1, 0]))


class PercentileClamping(unittest.TestCase):
    def test_clamping_changes_the_result(self) -> None:
        """A map made with [2, 98] is not the map made with the full range.

        Asserted rather than assumed, because the difference is exactly what
        the manifest has to record.
        """
        rng = np.random.default_rng(7)
        values = rng.normal(0, 1, (100, 100)).astype(np.float32)
        values[0, 0] = 500.0  # one outlier is enough to move the full-range anchor
        full = mf.linear_increasing(values)
        clamped = mf.linear_increasing(values, clamp_percentiles=(2.0, 98.0))
        self.assertFalse(np.allclose(full, clamped, atol=1e-3))


if __name__ == "__main__":
    unittest.main()
