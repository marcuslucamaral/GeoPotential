"""Level 1 and 3 — AHP, the fuzzy operators, and double counting.

Every numerical claim is checked against a value computed independently — by
hand from the published formula, or from a matrix whose answer is known — not
against what the code returned last time. A golden file would only prove the
code has not changed.
"""
from __future__ import annotations

import unittest

import numpy as np
from affine import Affine

from geopotential_worker.decision import aggregate as agg
from geopotential_worker.decision.ahp import (
    InconsistentMatrixError,
    RANDOM_INDEX,
    group_weights,
    reciprocal_matrix,
    weights,
)
from geopotential_worker.decision.correlation import correlations, double_counting
from geopotential_worker.domain.crs import CrsInfo
from geopotential_worker.domain.criterion import Criterion, CriterionStack, Stage
from geopotential_worker.domain.grid import TargetGrid


def grid(width: int = 8, height: int = 8) -> TargetGrid:
    return TargetGrid(
        transform=Affine(10.0, 0, 500_000.0, 0, -10.0, 4_500_000.0),
        crs=CrsInfo.from_user_input("EPSG:26912", source="test"),
        width=width, height=height,
    )


def criterion(name: str, values, g=None) -> Criterion:  # noqa: ANN001
    g = g or grid()
    array = np.asarray(values, dtype=np.float32)
    if array.shape != g.shape:
        array = np.full(g.shape, float(values), dtype=np.float32)
    return Criterion(name, array, g, Stage.NORMALIZED)


class AhpArithmetic(unittest.TestCase):
    """Saaty (1980) ch. 3, against values that can be worked out by hand."""

    def test_a_consistent_matrix_has_zero_ci(self) -> None:
        """A perfectly consistent matrix: a_ij = w_i / w_j exactly."""
        w = np.array([0.5, 0.3, 0.2])
        matrix = np.outer(w, 1.0 / w)
        result = weights(matrix, ["a", "b", "c"])
        np.testing.assert_allclose(result.weights, w, atol=1e-9)
        self.assertAlmostEqual(result.lambda_max, 3.0, places=9)
        self.assertAlmostEqual(result.ci, 0.0, places=9)
        self.assertAlmostEqual(result.cr, 0.0, places=9)
        self.assertTrue(result.consistent)

    def test_weights_sum_to_one(self) -> None:
        matrix = reciprocal_matrix(4, {(0, 1): 3, (0, 2): 5, (0, 3): 7,
                                       (1, 2): 3, (1, 3): 5, (2, 3): 3})
        result = weights(matrix, list("abcd"))
        self.assertAlmostEqual(float(result.weights.sum()), 1.0, places=12)

    def test_the_saaty_random_index_table(self) -> None:
        """The published values, to n = 10. Not recomputed, not extrapolated."""
        self.assertEqual(RANDOM_INDEX[3], 0.58)
        self.assertEqual(RANDOM_INDEX[5], 1.12)
        self.assertEqual(RANDOM_INDEX[10], 1.49)
        self.assertEqual(max(RANDOM_INDEX), 10)

    def test_cr_matches_the_formula(self) -> None:
        matrix = reciprocal_matrix(3, {(0, 1): 2, (0, 2): 5, (1, 2): 3})
        result = weights(matrix, list("abc"))
        expected_ci = (result.lambda_max - 3) / 2
        self.assertAlmostEqual(result.ci, expected_ci, places=12)
        self.assertAlmostEqual(result.cr, expected_ci / 0.58, places=12)

    def test_a_two_by_two_is_consistent_by_construction(self) -> None:
        """One judgment has nothing to contradict."""
        result = weights(reciprocal_matrix(2, {(0, 1): 9}), ["a", "b"])
        self.assertTrue(result.consistent)
        self.assertEqual(result.cr, 0.0)
        np.testing.assert_allclose(result.weights, [0.9, 0.1], atol=1e-9)

    def test_row_i_binds_to_criterion_i(self) -> None:
        """Defect D-06: weights landing on the wrong layer with no error."""
        w = np.array([0.6, 0.3, 0.1])
        matrix = np.outer(w, 1.0 / w)
        result = weights(matrix, ["heat_flow", "faults", "resistivity"])
        self.assertAlmostEqual(result.weights_by_name["heat_flow"], 0.6, places=9)
        self.assertAlmostEqual(result.weights_by_name["resistivity"], 0.1, places=9)


class AhpRefusals(unittest.TestCase):
    """MSP-08: an inconsistent matrix does not silently produce a map."""

    def test_an_inconsistent_matrix_is_refused(self) -> None:
        # a > b, b > c, and yet c > a: a cycle no weighting can express.
        matrix = reciprocal_matrix(3, {(0, 1): 9, (1, 2): 9, (0, 2): 1 / 9})
        with self.assertRaises(InconsistentMatrixError) as ctx:
            weights(matrix, list("abc"))
        message = str(ctx.exception)
        self.assertIn("CR", message)
        self.assertIn("0.10", message)
        self.assertIn("justification", message)

    def test_an_override_records_the_reason_and_proceeds(self) -> None:
        matrix = reciprocal_matrix(3, {(0, 1): 9, (1, 2): 9, (0, 2): 1 / 9})
        result = weights(matrix, list("abc"),
                         override_reason="field team insists; see note 2026-09-01")
        self.assertFalse(result.consistent)
        self.assertIn("field team", result.override)
        self.assertTrue(any("override" in w for w in result.warnings))

    def test_beyond_ten_criteria_is_refused(self) -> None:
        """Reusing RI(10) would manufacture a consistency the table lacks."""
        w = np.ones(11) / 11
        with self.assertRaises(ValueError) as ctx:
            weights(np.outer(w, 1.0 / w), [f"c{i}" for i in range(11)])
        self.assertIn("random index", str(ctx.exception))
        self.assertIn("55 pairwise", str(ctx.exception))

    def test_a_non_reciprocal_matrix_is_refused(self) -> None:
        matrix = np.array([[1.0, 3.0], [3.0, 1.0]])  # both say "I am bigger"
        with self.assertRaises(ValueError) as ctx:
            weights(matrix, ["a", "b"])
        self.assertIn("not reciprocal", str(ctx.exception))

    def test_a_non_positive_judgment_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            weights([[1.0, 0.0], [0.0, 1.0]], ["a", "b"])

    def test_a_judgment_off_saatys_scale_is_refused(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            reciprocal_matrix(2, {(0, 1): 25})
        self.assertIn("fundamental scale", str(ctx.exception))

    def test_a_name_count_mismatch_is_refused(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            weights(reciprocal_matrix(3, {(0, 1): 2}), ["a", "b"])
        self.assertIn("Row i binds to criterion i", str(ctx.exception))


class HierarchicalGroups(unittest.TestCase):
    """Section 15.1's remedy: correlated evidence shares one weight."""

    def test_group_weights_multiply_through_and_sum_to_one(self) -> None:
        groups = weights(np.outer([0.6, 0.4], 1.0 / np.array([0.6, 0.4])),
                         ["thermal", "structural"])
        thermal = weights(np.outer([0.5, 0.3, 0.2], 1.0 / np.array([0.5, 0.3, 0.2])),
                          ["heat_flow", "gradient", "temperature"])
        structural = weights(np.outer([0.7, 0.3], 1.0 / np.array([0.7, 0.3])),
                             ["faults", "lineaments"])

        combined = group_weights(groups, {"thermal": thermal,
                                          "structural": structural})
        self.assertAlmostEqual(sum(combined.values()), 1.0, places=12)
        self.assertAlmostEqual(combined["heat_flow"], 0.6 * 0.5, places=9)
        self.assertAlmostEqual(combined["faults"], 0.4 * 0.7, places=9)

        # The point: three thermal criteria draw 0.6 between them, not 3 x 0.6.
        thermal_total = sum(
            combined[n] for n in ("heat_flow", "gradient", "temperature")
        )
        self.assertAlmostEqual(thermal_total, 0.6, places=9)


class FuzzyOperators(unittest.TestCase):
    """Zimmermann and Zysno (1980), against hand-computed values."""

    def setUp(self) -> None:
        g = grid(2, 2)
        self.a = Criterion("a", np.array([[0.2, 0.5], [0.8, np.nan]], np.float32),
                           g, Stage.NORMALIZED)
        self.b = Criterion("b", np.array([[0.6, 0.5], [0.4, 0.9]], np.float32),
                           g, Stage.NORMALIZED)
        self.stack = CriterionStack([self.a, self.b])

    def test_product_is_the_product(self) -> None:
        out = agg.fuzzy_product(self.stack)
        self.assertAlmostEqual(float(out[0, 0]), 0.2 * 0.6, places=6)
        self.assertAlmostEqual(float(out[1, 0]), 0.8 * 0.4, places=6)

    def test_sum_is_one_minus_the_product_of_complements(self) -> None:
        out = agg.fuzzy_sum(self.stack)
        self.assertAlmostEqual(float(out[0, 0]), 1 - (1 - 0.2) * (1 - 0.6), places=6)

    def test_gamma_zero_is_the_product(self) -> None:
        np.testing.assert_allclose(
            agg.fuzzy_gamma(self.stack, 0.0)[np.isfinite(agg.fuzzy_gamma(self.stack, 0.0))],
            agg.fuzzy_product(self.stack)[np.isfinite(agg.fuzzy_product(self.stack))],
            atol=1e-6,
        )

    def test_gamma_one_is_the_sum(self) -> None:
        one = agg.fuzzy_gamma(self.stack, 1.0)
        total = agg.fuzzy_sum(self.stack)
        np.testing.assert_allclose(one[np.isfinite(one)],
                                   total[np.isfinite(total)], atol=1e-6)

    def test_gamma_matches_the_published_formula(self) -> None:
        g = 0.7
        out = agg.fuzzy_gamma(self.stack, g)
        expected = ((1 - (1 - 0.2) * (1 - 0.6)) ** g) * ((0.2 * 0.6) ** (1 - g))
        self.assertAlmostEqual(float(out[0, 0]), expected, places=6)

    def test_gamma_lies_between_product_and_sum(self) -> None:
        product = agg.fuzzy_product(self.stack)
        total = agg.fuzzy_sum(self.stack)
        middle = agg.fuzzy_gamma(self.stack, 0.5)
        valid = np.isfinite(middle)
        self.assertTrue((middle[valid] >= product[valid] - 1e-6).all())
        self.assertTrue((middle[valid] <= total[valid] + 1e-6).all())

    def test_gamma_outside_zero_one_is_refused(self) -> None:
        for bad in (-0.1, 1.5):
            with self.assertRaises(ValueError) as ctx:
                agg.fuzzy_gamma(self.stack, bad)
            self.assertIn("Zimmermann", str(ctx.exception))

    def test_every_operator_agrees_about_nulls(self) -> None:
        """A score is defined only where every criterion is valid."""
        for out in (agg.fuzzy_product(self.stack), agg.fuzzy_sum(self.stack),
                    agg.fuzzy_gamma(self.stack, 0.5),
                    agg.weighted_linear_combination(self.stack,
                                                    {"a": 0.5, "b": 0.5})):
            self.assertTrue(np.isnan(out[1, 1]),
                            "a null in any criterion must null the score")
            self.assertTrue(np.isfinite(out[0, 0]))

    def test_a_raw_criterion_cannot_be_aggregated(self) -> None:
        g = grid(2, 2)
        raw = Criterion("density", np.full((2, 2), 2.5, np.float32), g,
                        Stage.RAW, unit="g/cm3")
        stack = CriterionStack([self.a, raw])
        for operator in (agg.fuzzy_product, agg.fuzzy_sum):
            with self.assertRaises(TypeError):
                operator(stack)


class WeightedCombination(unittest.TestCase):
    def setUp(self) -> None:
        g = grid(2, 2)
        self.stack = CriterionStack([
            Criterion("a", np.full((2, 2), 0.4, np.float32), g, Stage.NORMALIZED),
            Criterion("b", np.full((2, 2), 0.8, np.float32), g, Stage.NORMALIZED),
        ])

    def test_it_is_the_weighted_mean(self) -> None:
        out = agg.weighted_linear_combination(self.stack, {"a": 0.25, "b": 0.75})
        self.assertAlmostEqual(float(out[0, 0]), 0.25 * 0.4 + 0.75 * 0.8, places=6)

    def test_weights_must_sum_to_one(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            agg.weighted_linear_combination(self.stack, {"a": 0.3, "b": 0.3})
        self.assertIn("Renormalizing them here", str(ctx.exception))

    def test_a_missing_weight_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            agg.weighted_linear_combination(self.stack, {"a": 1.0})
        self.assertIn("'b'", str(ctx.exception))

    def test_an_unknown_weight_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            agg.weighted_linear_combination(
                self.stack, {"a": 0.4, "b": 0.4, "gravity": 0.2}
            )
        self.assertIn("'gravity'", str(ctx.exception))

    def test_a_constraint_multiplies_and_a_factor_is_weighted(self) -> None:
        excluded = np.array([[True, False], [True, True]])
        out = agg.weighted_linear_combination(
            self.stack, {"a": 0.5, "b": 0.5}, constraints=[excluded]
        )
        self.assertAlmostEqual(float(out[0, 0]), 0.6, places=6)
        self.assertAlmostEqual(float(out[0, 1]), 0.0, places=6)

    def test_a_continuous_constraint_is_refused(self) -> None:
        """A soft preference silently becoming a veto is the defect."""
        continuous = np.array([[0.3, 0.7], [1.0, 0.0]])
        with self.assertRaises(ValueError) as ctx:
            agg.weighted_linear_combination(
                self.stack, {"a": 0.5, "b": 0.5}, constraints=[continuous]
            )
        self.assertIn("boolean", str(ctx.exception))


class Masking(unittest.TestCase):
    def test_outside_a_mask_is_null_not_zero(self) -> None:
        """Outside an AOI a score was not computed; zero would read as
        'computed, and unfavourable'."""
        values = np.full((2, 2), 0.7, dtype=np.float32)
        mask = np.array([[True, False], [True, True]])
        out = agg.apply_mask(values, mask)
        self.assertTrue(np.isnan(out[0, 1]))
        self.assertAlmostEqual(float(out[0, 0]), 0.7, places=6)


class DoubleCounting(unittest.TestCase):
    """Section 15.1, on the document's own example."""

    def setUp(self) -> None:
        rng = np.random.default_rng(20260901)
        g = grid(40, 40)
        base = rng.random(g.shape).astype(np.float32)
        # Three views of one piece of evidence, plus one independent criterion.
        self.stack = CriterionStack([
            Criterion("heat_flow", base, g, Stage.NORMALIZED),
            Criterion("gradient", np.clip(base * 0.97 + 0.01, 0, 1).astype(np.float32),
                      g, Stage.NORMALIZED),
            Criterion("temperature", np.clip(base * 0.95 + 0.02, 0, 1).astype(np.float32),
                      g, Stage.NORMALIZED),
            Criterion("faults", rng.random(g.shape).astype(np.float32),
                      g, Stage.NORMALIZED),
        ])

    def test_the_correlated_trio_is_reported(self) -> None:
        findings = double_counting(self.stack, threshold=0.85)
        pairs = {tuple(sorted((f.a, f.b))) for f in findings}
        self.assertIn(("gradient", "heat_flow"), pairs)
        self.assertIn(("heat_flow", "temperature"), pairs)
        self.assertNotIn(("faults", "heat_flow"), pairs)

    def test_the_message_names_the_pair_and_says_what_to_do(self) -> None:
        finding = double_counting(self.stack, threshold=0.85)[0]
        self.assertIn(finding.a, finding.message)
        self.assertIn(finding.b, finding.message)
        self.assertIn("count it twice", finding.message)
        self.assertIn("group", finding.message)

    def test_the_combined_weight_is_reported_when_known(self) -> None:
        findings = double_counting(
            self.stack, threshold=0.85,
            weights={"heat_flow": 0.3, "gradient": 0.3, "temperature": 0.2,
                     "faults": 0.2},
        )
        self.assertTrue(any(f.combined_weight for f in findings))
        self.assertIn("%", findings[0].message)

    def test_a_shared_group_silences_the_warning(self) -> None:
        """Grouping them is the documented remedy; nagging afterwards is noise."""
        groups = {"heat_flow": "thermal", "gradient": "thermal",
                  "temperature": "thermal", "faults": "structural"}
        self.assertEqual(double_counting(self.stack, threshold=0.85, groups=groups), [])

    def test_correlation_is_computed_over_jointly_valid_pixels(self) -> None:
        result = correlations(self.stack)
        for (a, b), (coefficient, samples) in result.items():
            self.assertEqual(samples, 1600)
            self.assertTrue(-1.0 <= coefficient <= 1.0)


if __name__ == "__main__":
    unittest.main()
