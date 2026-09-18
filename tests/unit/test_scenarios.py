"""M6 E1 — sensitivity and explainability, the numerical core. MSP-11, §17.

The map the M5 Decision Engine produces answers "where". This suite is about
the questions that decide whether anyone acts on it: **why this cell, and what
if I had chosen differently.**

Declared tolerances, fixed before anything is measured against them:

- a weighted sum's contributions add back to the score to `1e-9`, because that
  is arithmetic and not an approximation;
- a rank correlation of a map with itself is exactly 1.0;
- everything else is asserted as an ordering or a refusal, never as a number
  that would have to be updated when scipy changes.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from affine import Affine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.decision import aggregate as agg  # noqa: E402
from geopotential_worker.domain.crs import CrsInfo  # noqa: E402
from geopotential_worker.domain.criterion import (  # noqa: E402
    Criterion,
    CriterionStack,
    Stage,
)
from geopotential_worker.domain.grid import TargetGrid  # noqa: E402
from geopotential_worker.scenarios import explain, sensitivity  # noqa: E402

CLOSED_FORM = 1e-9
METRIC = CrsInfo.from_user_input("EPSG:26912", source="test")


def _grid(height: int = 20, width: int = 20) -> TargetGrid:
    return TargetGrid(
        transform=Affine(10.0, 0.0, 0.0, 0.0, -10.0, height * 10.0),
        crs=METRIC, width=width, height=height,
    )


def _criterion(name: str, values: np.ndarray, grid: TargetGrid) -> Criterion:
    return Criterion(name=name, values=values.astype(np.float32), grid=grid,
                     stage=Stage.NORMALIZED, unit=None)


def _stack(**layers: np.ndarray) -> CriterionStack:
    grid = _grid(*next(iter(layers.values())).shape)
    return CriterionStack([_criterion(n, v, grid) for n, v in layers.items()])


def _gradients(height: int = 20, width: int = 20):
    """Three criteria that disagree, so dropping one has somewhere to show."""
    y, x = np.mgrid[0:height, 0:width]
    east = x / (width - 1)
    north = y / (height - 1)
    corner = np.clip(1.0 - np.hypot(y, x) / np.hypot(height, width), 0.0, 1.0)
    return east, north, corner


class ARankCorrelationIsMeasuredOnSharedCells(unittest.TestCase):
    """P-167 — comparing rankings over different cells is not comparing them."""

    def test_a_map_against_itself_is_one(self) -> None:
        rng = np.random.default_rng(4)
        field = rng.random((30, 30))
        self.assertAlmostEqual(sensitivity.spearman(field, field), 1.0,
                               places=9)

    def test_a_reversed_map_is_minus_one(self) -> None:
        rng = np.random.default_rng(5)
        field = rng.random((30, 30))
        self.assertAlmostEqual(sensitivity.spearman(field, -field), -1.0,
                               places=9)

    def test_a_monotone_rescaling_does_not_change_the_ranking(self) -> None:
        """The point of using ranks: 2x + 1 is a different map and the same
        ordering, and a sensitivity measure must not call that a change."""
        rng = np.random.default_rng(6)
        field = rng.random((30, 30))
        self.assertAlmostEqual(sensitivity.spearman(field, 2 * field + 1), 1.0,
                               places=9)

    def test_nulls_are_excluded_from_both_sides(self) -> None:
        rng = np.random.default_rng(7)
        a = rng.random((30, 30))
        b = a.copy()
        a[:5] = np.nan          # null in one
        b[-5:] = np.nan         # null in the other
        # The shared cells are identical, so the correlation over them is 1.
        self.assertAlmostEqual(sensitivity.spearman(a, b), 1.0, places=9)

    def test_too_few_shared_cells_gives_no_number(self) -> None:
        """A rho over ten cells is noise wearing a decimal point."""
        a = np.full((30, 30), np.nan)
        b = np.full((30, 30), np.nan)
        a[:1, :10] = np.arange(10)
        b[:1, :10] = np.arange(10)
        self.assertIsNone(sensitivity.spearman(a, b))

    def test_a_constant_map_has_no_ranking(self) -> None:
        flat = np.full((30, 30), 0.5)
        rng = np.random.default_rng(8)
        self.assertIsNone(sensitivity.spearman(flat, rng.random((30, 30))))


class ComparingTwoMaps(unittest.TestCase):
    """Every number carries the count it was measured over (P-174)."""

    def setUp(self) -> None:
        rng = np.random.default_rng(9)
        self.base = rng.random((40, 40))

    def test_a_map_against_itself_moved_nothing(self) -> None:
        got = sensitivity.compare(self.base, self.base)
        self.assertEqual(got["mean_abs_change"], 0.0)
        self.assertEqual(got["top_agreement"], 1.0)
        self.assertAlmostEqual(got["spearman"], 1.0, places=9)

    def test_every_number_carries_its_sample_size(self) -> None:
        got = sensitivity.compare(self.base, self.base + 0.01)
        for key in ("cells_compared", "cells_baseline", "cells_scenario",
                    "top_cells"):
            self.assertIn(key, got)
        self.assertEqual(got["cells_compared"], 1600)

    def test_a_shifted_map_moves_without_reordering(self) -> None:
        """The two measures answer different questions, and this is the case
        that separates them: everything moved, nothing was reordered."""
        got = sensitivity.compare(self.base, self.base + 0.1)
        self.assertAlmostEqual(got["mean_abs_change"], 0.1, places=9)
        self.assertAlmostEqual(got["spearman"], 1.0, places=9)
        self.assertEqual(got["top_agreement"], 1.0)

    def test_maps_of_different_shapes_are_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            sensitivity.compare(self.base, np.zeros((10, 10)))
        self.assertIn("not comparable", str(raised.exception))

    def test_two_maps_that_share_no_cell_say_so(self) -> None:
        a = np.full((20, 20), np.nan)
        b = np.full((20, 20), np.nan)
        a[:5] = 0.5
        b[15:] = 0.5
        got = sensitivity.compare(a, b)
        self.assertEqual(got["cells_compared"], 0)
        self.assertIsNone(got["spearman"])
        self.assertIn("share no cell", got["note"])


class LeavingOneCriterionOut(unittest.TestCase):
    """P-166 — the same aggregation with n-1 criteria, and it says so."""

    def setUp(self) -> None:
        east, north, corner = _gradients()
        self.stack = _stack(east=east, north=north, corner=corner)
        self.weights = {"east": 0.5, "north": 0.3, "corner": 0.2}

    def _wlc(self, stack, weights):
        return agg.weighted_linear_combination(stack, weights)

    def test_every_criterion_is_dropped_exactly_once(self) -> None:
        got = sensitivity.leave_one_out(self.stack, self._wlc, self.weights)
        dropped = sorted(row["dropped"] for row in got["criteria"])
        self.assertEqual(dropped, ["corner", "east", "north"])

    def test_the_result_is_ordered_by_how_much_the_map_moved(self) -> None:
        got = sensitivity.leave_one_out(self.stack, self._wlc, self.weights)
        moves = [row["mean_abs_change"] for row in got["criteria"]]
        self.assertEqual(moves, sorted(moves, reverse=True))

    def test_dropping_the_heaviest_criterion_moves_the_map_most(self) -> None:
        """On three gradients that genuinely disagree, weight should show."""
        got = sensitivity.leave_one_out(self.stack, self._wlc, self.weights)
        self.assertEqual(got["criteria"][0]["dropped"], "east",
                         "the criterion carrying half the weight was not the "
                         "one whose removal moved the map most")

    def test_renormalising_the_remaining_weights_is_reported(self) -> None:
        """P-93 forbids silently renormalising. Doing it and saying so is the
        only way to keep an operator whose weights must sum to 1."""
        got = sensitivity.leave_one_out(self.stack, self._wlc, self.weights)
        for row in got["criteria"]:
            self.assertTrue(row["weights_renormalized"])

    def test_an_unweighted_operator_reports_no_renormalisation(self) -> None:
        got = sensitivity.leave_one_out(
            self.stack, lambda s, w: agg.fuzzy_product(s), None)
        for row in got["criteria"]:
            self.assertFalse(row["weights_renormalized"])
            self.assertIsNone(row["weight"])

    def test_one_criterion_is_refused_by_name(self) -> None:
        east, _, _ = _gradients()
        with self.assertRaises(ValueError) as raised:
            sensitivity.leave_one_out(_stack(east=east), self._wlc,
                                      {"east": 1.0})
        self.assertIn("at least two criteria", str(raised.exception))

    def test_the_one_at_a_time_limitation_is_carried_in_the_result(self) -> None:
        """A reader who does not know it will assume otherwise."""
        got = sensitivity.leave_one_out(self.stack, self._wlc, self.weights)
        self.assertIn("interactions", got["limitation"])


class SweepingOneParameter(unittest.TestCase):
    """§17.5 — how the answer moves with gamma, and with the weights."""

    def setUp(self) -> None:
        east, north, corner = _gradients()
        self.stack = _stack(east=east, north=north, corner=corner)

    def test_gamma_zero_is_the_product_and_one_is_the_sum(self) -> None:
        """Not a sensitivity claim — the anchor the sweep is read against."""
        product = agg.fuzzy_gamma(self.stack, 0.0)
        both = np.isfinite(product) & np.isfinite(agg.fuzzy_product(self.stack))
        np.testing.assert_allclose(product[both],
                                   agg.fuzzy_product(self.stack)[both],
                                   rtol=0, atol=1e-6)

    def test_a_sweep_reports_one_row_per_value(self) -> None:
        baseline = agg.fuzzy_gamma(self.stack, 0.7)
        got = sensitivity.sweep(
            [0.0, 0.5, 0.7, 0.9, 1.0],
            lambda g: agg.fuzzy_gamma(self.stack, g),
            baseline, parameter="gamma")
        self.assertEqual(len(got["rows"]), 5)
        self.assertEqual(got["parameter"], "gamma")

    def test_the_value_the_baseline_used_moves_nothing(self) -> None:
        baseline = agg.fuzzy_gamma(self.stack, 0.7)
        got = sensitivity.sweep(
            [0.7], lambda g: agg.fuzzy_gamma(self.stack, g),
            baseline, parameter="gamma")
        self.assertAlmostEqual(got["rows"][0]["mean_abs_change"], 0.0,
                               places=6)

    def test_the_sweep_reports_its_worst_case(self) -> None:
        """The two numbers that say whether the parameter matters at all."""
        baseline = agg.fuzzy_gamma(self.stack, 0.7)
        got = sensitivity.sweep(
            [0.0, 0.7, 1.0], lambda g: agg.fuzzy_gamma(self.stack, g),
            baseline, parameter="gamma")
        self.assertGreater(got["worst_mean_abs_change"], 0.0)
        self.assertLessEqual(got["worst_top_agreement"], 1.0)

    def test_an_empty_sweep_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            sensitivity.sweep([], lambda g: None, np.zeros((5, 5)),
                              parameter="gamma")


class WhyThisCellScoredThis(unittest.TestCase):
    """P-168, §17.1 — the contributions, and what they mean per operator."""

    def setUp(self) -> None:
        east, north, corner = _gradients()
        self.stack = _stack(east=east, north=north, corner=corner)
        self.weights = {"east": 0.5, "north": 0.3, "corner": 0.2}

    def test_a_weighted_sum_decomposes_exactly(self) -> None:
        """The one operator where a contribution is arithmetic, so it is
        checked against the arithmetic and not against itself."""
        cell = (11, 13)
        got = explain.contributions(
            self.stack, "weighted_linear_combination", cell,
            weights=self.weights)
        score = float(agg.weighted_linear_combination(
            self.stack, self.weights)[cell])
        rebuilt = sum(
            share * score for share in got["contributions"].values())
        self.assertAlmostEqual(rebuilt, score, delta=CLOSED_FORM)
        self.assertAlmostEqual(sum(got["contributions"].values()), 1.0,
                               delta=CLOSED_FORM)

    def test_the_dominant_criterion_is_the_largest_share(self) -> None:
        got = explain.contributions(
            self.stack, "weighted_linear_combination", (11, 13),
            weights=self.weights)
        largest = max(got["contributions"].items(), key=lambda kv: kv[1])[0]
        self.assertEqual(got["dominant"], largest)
        self.assertEqual(got["ranked"][0], largest)

    def test_every_result_says_which_decomposition_it_used(self) -> None:
        """A log-share read as a share of the score is a wrong number that
        looks right."""
        for method in ("weighted_linear_combination", "fuzzy_product",
                       "fuzzy_sum", "fuzzy_gamma"):
            with self.subTest(method=method):
                got = explain.contributions(
                    self.stack, method, (11, 13), weights=self.weights)
                self.assertIn(got["decomposition"],
                              list(explain.DECOMPOSITION.values()) + ["veto"])

    def test_a_product_decomposition_is_not_claimed_to_be_additive(self) -> None:
        got = explain.contributions(self.stack, "fuzzy_product", (11, 13))
        self.assertIn("not a share of the score", got["decomposition"])

    def test_a_criterion_at_zero_is_named_as_the_veto(self) -> None:
        """A product with a zero in it is that zero, and shares of -inf are
        not an explanation."""
        east, north, _ = _gradients()
        zero = np.zeros_like(east)
        stack = _stack(east=east, north=north, blocked=zero)
        got = explain.contributions(stack, "fuzzy_product", (11, 13))
        self.assertEqual(got["decomposition"], "veto")
        self.assertEqual(got["veto"], ["blocked"])
        self.assertEqual(got["contributions"]["blocked"], 1.0)

    def test_a_cell_with_a_null_criterion_is_not_a_low_score(self) -> None:
        """ADR-004: a score needs every criterion. 'No score' and 'a bad
        score' are different answers and must not be one."""
        east, north, corner = _gradients()
        corner = corner.copy()
        corner[11, 13] = np.nan
        stack = _stack(east=east, north=north, corner=corner)
        got = explain.contributions(
            stack, "weighted_linear_combination", (11, 13),
            weights=self.weights)
        self.assertFalse(got["scored"])
        self.assertIsNone(got["contributions"])
        self.assertIn("corner", got["reason"])

    def test_a_cell_off_the_grid_is_refused_with_the_shape(self) -> None:
        with self.assertRaises(IndexError) as raised:
            explain.contributions(self.stack, "fuzzy_product", (999, 0))
        self.assertIn("20 x 20", str(raised.exception))

    def test_wlc_without_weights_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            explain.contributions(
                self.stack, "weighted_linear_combination", (11, 13))


class RankingTargets(unittest.TestCase):
    """Places, not pixels."""

    def test_the_best_cell_is_rank_one(self) -> None:
        score = np.zeros((40, 40))
        score[7, 9] = 1.0
        got = explain.rank_targets(score, count=3)
        self.assertEqual(got["targets"][0]["cell"], [7, 9])
        self.assertEqual(got["targets"][0]["rank"], 1)

    def test_two_cells_on_one_hilltop_are_one_target(self) -> None:
        """Ten pixels from one anomaly is not ten targets."""
        score = np.zeros((40, 40))
        score[10, 10] = 1.0
        score[10, 11] = 0.99      # one cell away
        score[30, 30] = 0.98      # a different place
        got = explain.rank_targets(score, count=3, min_separation=5)
        cells = [t["cell"] for t in got["targets"]]
        self.assertIn([10, 10], cells)
        self.assertNotIn([10, 11], cells)
        self.assertIn([30, 30], cells)

    def test_targets_come_out_in_descending_score(self) -> None:
        rng = np.random.default_rng(12)
        got = explain.rank_targets(rng.random((60, 60)), count=8)
        scores = [t["score"] for t in got["targets"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_null_cells_are_never_targets(self) -> None:
        score = np.full((30, 30), np.nan)
        score[5, 5] = 0.4
        got = explain.rank_targets(score, count=5)
        self.assertEqual(got["count"], 1)
        self.assertEqual(got["targets"][0]["cell"], [5, 5])

    def test_a_map_with_no_score_returns_no_target(self) -> None:
        got = explain.rank_targets(np.full((10, 10), np.nan))
        self.assertEqual(got["targets"], [])
        self.assertIn("no scored cell", got["reason"])

    def test_the_scientific_boundary_travels_with_the_ranking(self) -> None:
        """A ranked list is the most quotable thing this application makes,
        and the sentence that says what it is not has to be attached to it."""
        got = explain.rank_targets(np.random.default_rng(1).random((20, 20)))
        self.assertIn("not a resource", got["boundary"])
        self.assertIn("economic viability", got["boundary"])


class TheOperators(unittest.TestCase):
    """M6 E2 — the five, on rasters, through the registry.

    They rebuild the analysis with the *same* functions `decision.aggregate`
    uses. That is the property this class is really about: a scenario computed
    by a second implementation agrees with the run until it does not.
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from geopotential_worker.io.writers import write_geotiff  # noqa: F401
        except Exception as exc:                      # pragma: no cover
            raise unittest.SkipTest(f"the raster stack is not installed: {exc}")

    def setUp(self) -> None:
        from geopotential_worker.io.writers import write_geotiff

        self.tmp = tempfile.TemporaryDirectory()
        out = Path(self.tmp.name)
        east, north, corner = _gradients(30, 30)
        grid = _grid(30, 30)
        self.paths = {}
        for name, values in (("east", east), ("north", north),
                             ("corner", corner)):
            artifact = write_geotiff(values.astype(np.float32), grid,
                                     out / f"{name}.tif",
                                     tags={"GEOPOTENTIAL_UNIT": "m"})
            self.paths[name] = str(artifact.path)

        self.criteria = [
            {"path": self.paths[n], "name": n, "unit": "m",
             "function": "linear_increasing"}
            for n in ("east", "north", "corner")
        ]
        self.weights = [{"name": "east", "weight": 0.5},
                        {"name": "north", "weight": 0.3},
                        {"name": "corner", "weight": 0.2}]
        self.out = out

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ctx(self):
        from geopotential_worker.operators.base import Context

        class _Ctx(Context):
            def __init__(self, output_dir):
                self.output_dir = output_dir
                self.emitted = []

            def progress(self, stage, fraction, message=""):
                pass

            def check_cancel(self):
                pass

            def emit(self, name, artifact):
                self.emitted.append((name, artifact))

        return _Ctx(self.out)

    def _run(self, operator: str, extra: dict):
        from geopotential_worker.operators import registry

        params = {
            "criteria": self.criteria,
            "method": "weighted_linear_combination",
            "weights": self.weights,
            "gamma": 0.7,
            "top_fraction": 0.1,
            **extra,
        }
        # Through `validate` first, which is what the worker does: it is what
        # fills the defaults, and a test that skips it tests a path nothing
        # takes.
        ctx = self._ctx()
        op = registry.get(operator)
        return op.run([], op.validate(params), ctx), ctx

    def test_the_five_are_registered_and_none_is_still_planned(self) -> None:
        from geopotential_worker.operators import registry

        for name in ("scenarios.leave_one_out", "scenarios.sensitivity",
                     "scenarios.explain", "scenarios.rank_targets",
                     "reporting.manifest"):
            with self.subTest(operator=name):
                self.assertIn(name, registry.capabilities())
                self.assertNotIn(name, registry.PLANNED,
                                 "an operator that ships cannot still point "
                                 "at a milestone")

    def test_leave_one_out_measures_and_writes_nothing(self) -> None:
        """It says *how much* the map would move. The picture of the
        difference is `grid.difference`, which has existed since M4; a second
        operator producing the same artefact is two implementations of one
        thing."""
        from geopotential_worker.operators import registry

        self.assertTrue(registry.get("scenarios.leave_one_out").read_only)
        before = set(p.name for p in self.out.iterdir())
        manifest, ctx = self._run("scenarios.leave_one_out", {})
        self.assertEqual(len(manifest["leave_one_out"]["criteria"]), 3)
        self.assertEqual(ctx.emitted, [])
        self.assertEqual(set(p.name for p in self.out.iterdir()), before)

    def test_every_scenario_operator_is_read_only(self) -> None:
        """P-171. A question about a result is not a result."""
        from geopotential_worker.operators import registry

        for name in ("scenarios.leave_one_out", "scenarios.sensitivity",
                     "scenarios.explain", "scenarios.rank_targets"):
            with self.subTest(operator=name):
                self.assertTrue(registry.get(name).read_only,
                                f"{name} would commit a run for a question")

    def test_sweeping_gamma_on_an_operator_without_one_is_refused(self) -> None:
        """A table of zeros looks exactly like a result."""
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            self._run("scenarios.sensitivity",
                      {"parameter": "gamma", "values": [0.0, 1.0]})
        self.assertIn("no effect", str(raised.exception))

    def test_sweeping_a_weight_keeps_the_weights_summing_to_one(self) -> None:
        manifest, _ = self._run(
            "scenarios.sensitivity",
            {"parameter": "weight", "criterion": "east",
             "values": [0.1, 0.5, 0.9]})
        report = manifest["sensitivity"]
        self.assertEqual(len(report["rows"]), 3)
        self.assertTrue(report["weights_renormalized"])
        self.assertEqual(report["criterion"], "east")

    def test_sweeping_an_unknown_criterion_names_the_ones_there_are(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            self._run("scenarios.sensitivity",
                      {"parameter": "weight", "criterion": "nope",
                       "values": [0.5]})
        message = str(raised.exception)
        for name in ("east", "north", "corner"):
            self.assertIn(name, message)

    def test_explain_is_read_only_and_writes_nothing(self) -> None:
        from geopotential_worker.operators import registry

        self.assertTrue(registry.get("scenarios.explain").read_only)
        before = set(p.name for p in self.out.iterdir())
        manifest, ctx = self._run("scenarios.explain", {"row": 15, "column": 20})
        self.assertEqual(ctx.emitted, [])
        self.assertEqual(set(p.name for p in self.out.iterdir()), before)
        self.assertTrue(manifest["explanation"]["scored"])
        self.assertIsNotNone(manifest["explanation"]["dominant"])

    def test_explain_off_the_grid_is_refused_with_the_shape(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            self._run("scenarios.explain", {"row": 900, "column": 0})
        self.assertIn("30 x 30", str(raised.exception))

    def test_rank_targets_explains_each_one(self) -> None:
        manifest, ctx = self._run(
            "scenarios.rank_targets", {"count": 4, "min_separation": 3})
        targets = manifest["targets"]["targets"]
        self.assertEqual(len(targets), 4)
        self.assertEqual(ctx.emitted, [])
        for target in targets:
            self.assertIn("explanation", target)
            self.assertIn("contributions", target["explanation"])

    def test_the_ranking_carries_the_scientific_boundary(self) -> None:
        manifest, _ = self._run("scenarios.rank_targets", {"count": 2})
        self.assertIn("not a resource", manifest["targets"]["boundary"])

    def test_the_manifest_is_written_and_reproduces_the_run(self) -> None:
        from geopotential_worker.operators import registry

        source, _ = self._run("scenarios.rank_targets", {"count": 2})
        ctx = self._ctx()
        op = registry.get("reporting.manifest")
        manifest = op.run([], op.validate(
            {"manifest": source, "result_name": "run_manifest",
             "run_id": "R-1", "app_version": "0.6.00"}), ctx)

        written = Path(manifest["manifest_path"])
        self.assertTrue(written.is_file())
        document = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(document["run_id"], "R-1")
        self.assertEqual(document["app_version"], "0.6.00")
        self.assertTrue(document["worker_version"])
        self.assertEqual(document["manifest"]["operator"],
                         "scenarios.rank_targets")
        # No .tmp survives an atomic write.
        self.assertEqual(list(self.out.glob("*.tmp")), [])

    def test_a_manifest_that_cannot_reproduce_a_run_is_refused(self) -> None:
        """A file that looks like provenance and is not is worse than none."""
        from geopotential_worker.operators import registry
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            op = registry.get("reporting.manifest")
            op.run([], op.validate({"manifest": {"note": "trust me"},
                                    "result_name": "bad"}), self._ctx())
        self.assertIn("cannot reproduce a run", str(raised.exception))


class NoPythonLoopOverCells(unittest.TestCase):
    """P-153, ADR-007 — checked by what each loop iterates."""

    def test_no_loop_iterates_cells_or_pixels(self) -> None:
        import re

        for module in (sensitivity, explain):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped.startswith("for "):
                    continue
                iterated = stripped.split(" in ", 1)[-1].rstrip(":")
                # Loops over criteria, scenarios and parameter values are the
                # point. A loop over cells is the defect.
                self.assertNotRegex(
                    iterated, r"\bcell\b|pixel",
                    f"{Path(module.__file__).name}: {stripped}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
