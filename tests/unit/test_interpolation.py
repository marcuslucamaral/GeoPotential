"""M5.7 — the three interpolators, and choosing between them by measurement.

M5.6 shipped one interpolator, IDW, and the gridding screen offered no other.
IDW is a weighted mean, so it is pulled toward the local average: it flattens a
gradient and it can never return a value it did not see. On samples that lie on
a lattice that is visible as a mottled texture and measurable as error — on
`vp_500_m.csv` its held-out RMSE is 1.9x Clough-Tocher's.

So the two triangulated methods QGIS offers are here as well, and the choice
between the three is **measured** rather than defaulted:

    grid.idw          weighted mean, bounded by a search radius
    grid.tin_linear   barycentric in each Delaunay triangle, never overshoots
    grid.tin_cubic    Clough-Tocher, C1 across edges, may overshoot
    grid.cross_validate  holds samples out and scores each of the three

Declared tolerances, fixed here before anything is measured against them: a
linear interpolant is held to 1e-9 against its closed form on a plane, because
barycentric interpolation of a planar field is exact; the convex-hull and
overshoot assertions are exact comparisons, not tolerances.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.grid import crossval  # noqa: E402
from geopotential_worker.grid import idw as idw_grid  # noqa: E402
from geopotential_worker.grid import triangulated as tin_grid  # noqa: E402
from geopotential_worker.operators import registry  # noqa: E402

def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
LATTICE = DATA / "utah_forge" / "vp_500_m.csv"

#: Barycentric interpolation reproduces a plane exactly; this is arithmetic
#: noise, not a fitted tolerance.
CLOSED_FORM = 1e-9


def _plane(x, y):
    """A field with a known value everywhere: z = 3x - 2y + 7."""
    return 3.0 * x - 2.0 * y + 7.0


def _scattered(n=200, seed=7):
    rng = np.random.default_rng(seed)
    x = rng.uniform(0.0, 100.0, n)
    y = rng.uniform(0.0, 100.0, n)
    return x, y, _plane(x, y)


class ATriangulatedSurfaceIsExactOnAPlane(unittest.TestCase):
    """P-155 — a linear interpolant reproduces a linear field.

    The one case where the right answer is known at every cell, so it is
    checked against the closed form rather than against another interpolator.
    """

    def setUp(self) -> None:
        self.x, self.y, self.v = _scattered()
        # Well inside the hull, so nothing here is about the boundary.
        self.qx = np.array([30.0, 45.5, 60.0, 72.25])
        self.qy = np.array([40.0, 55.5, 20.0, 66.75])

    def test_linear_reproduces_a_plane(self) -> None:
        got = tin_grid.interpolate(self.x, self.y, self.v,
                                   self.qx, self.qy, method="linear")
        np.testing.assert_allclose(got, _plane(self.qx, self.qy),
                                   rtol=0, atol=CLOSED_FORM)

    def test_cubic_reproduces_a_plane(self) -> None:
        """Clough-Tocher is cubic, so a plane is inside what it can represent
        exactly. A cubic that cannot return a plane is not Clough-Tocher."""
        got = tin_grid.interpolate(self.x, self.y, self.v,
                                   self.qx, self.qy, method="cubic")
        np.testing.assert_allclose(got, _plane(self.qx, self.qy),
                                   rtol=0, atol=1e-6)

    def test_idw_does_not_reproduce_a_plane(self) -> None:
        """Not a defect of IDW — it is what a weighted mean does, and it is
        why the method is chosen per survey rather than once in code."""
        got = idw_grid.interpolate(self.x, self.y, self.v, self.qx, self.qy,
                                   radius=30.0, power=2.0)
        self.assertFalse(
            np.allclose(got, _plane(self.qx, self.qy), rtol=0, atol=1e-3),
            "IDW returned a plane exactly; the comparison this suite rests on "
            "would then be meaningless")


class OutsideTheHullThereIsNoAnswer(unittest.TestCase):
    """P-156 — a triangulated method stops at the convex hull.

    Never the nearest sample, however close. Beyond the hull no triangle
    contains the cell and there is no survey behind it, which is the same rule
    `idw.py` states about its radius.
    """

    def setUp(self) -> None:
        self.x, self.y, self.v = _scattered()

    def test_a_cell_outside_the_hull_is_null(self) -> None:
        for method in tin_grid.METHODS:
            with self.subTest(method=method):
                got = tin_grid.interpolate(
                    self.x, self.y, self.v,
                    np.array([-50.0, 200.0]), np.array([-50.0, 200.0]),
                    method=method)
                self.assertTrue(np.all(np.isnan(got)),
                                f"{method} answered outside the hull: {got}")

    def test_max_distance_nulls_a_cell_far_from_every_sample(self) -> None:
        """The optional extra limit: inside the hull, but across a gap."""
        # A ring of samples with an empty middle: the hull covers the middle,
        # the survey does not.
        angle = np.linspace(0.0, 2.0 * np.pi, 40, endpoint=False)
        x, y = 50.0 + 50.0 * np.cos(angle), 50.0 + 50.0 * np.sin(angle)
        v = _plane(x, y)
        centre_x, centre_y = np.array([50.0]), np.array([50.0])

        unbounded = tin_grid.interpolate(x, y, v, centre_x, centre_y,
                                         method="linear")
        self.assertFalse(np.isnan(unbounded[0]),
                         "the hull covers the centre, so QGIS's behaviour is "
                         "to answer there")
        bounded = tin_grid.interpolate(x, y, v, centre_x, centre_y,
                                       method="linear", max_distance=10.0)
        self.assertTrue(np.isnan(bounded[0]),
                        "max_distance did not null a cell 50 units from every "
                        "sample")


class TheCubicMayOvershootAndSaysSo(unittest.TestCase):
    """P-157 — ADR-MSP-007: the overshoot is measured and reported, not clamped.

    `linear` cannot leave the samples' interval and must report zero;
    `cubic` can, and a run that did must be able to say by how much.
    """

    def setUp(self) -> None:
        # A step: two flat halves with a sharp edge. This is where a C1 cubic
        # has to bend past the data to meet its neighbours' derivatives.
        rng = np.random.default_rng(11)
        x = rng.uniform(0.0, 100.0, 400)
        y = rng.uniform(0.0, 100.0, 400)
        self.x, self.y = x, y
        self.v = np.where(x < 50.0, 0.0, 1.0)
        gx, gy = np.meshgrid(np.linspace(5.0, 95.0, 60),
                             np.linspace(5.0, 95.0, 60))
        self.qx, self.qy = gx.ravel(), gy.ravel()

    def test_linear_never_leaves_the_samples_interval(self) -> None:
        got = tin_grid.interpolate(self.x, self.y, self.v, self.qx, self.qy,
                                   method="linear")
        finite = got[np.isfinite(got)]
        self.assertGreaterEqual(float(finite.min()), float(self.v.min()))
        self.assertLessEqual(float(finite.max()), float(self.v.max()))

    def test_the_linear_report_says_the_overshoot_is_zero(self) -> None:
        got = tin_grid.interpolate(self.x, self.y, self.v, self.qx, self.qy,
                                   method="linear")
        report = tin_grid.statistics(
            got, sample_interval=(float(self.v.min()), float(self.v.max())))
        self.assertEqual(report["overshoot"]["below"], 0.0)
        self.assertEqual(report["overshoot"]["above"], 0.0)

    def test_the_cubic_overshoot_is_reported_not_hidden(self) -> None:
        got = tin_grid.interpolate(self.x, self.y, self.v, self.qx, self.qy,
                                   method="cubic")
        report = tin_grid.statistics(
            got, sample_interval=(float(self.v.min()), float(self.v.max())))
        overshoot = report["overshoot"]
        self.assertGreater(overshoot["below"] + overshoot["above"], 0.0,
                           "a cubic across a step that overshot nothing means "
                           "this fixture no longer tests what it claims")
        # Whatever it was, the report has to agree with the array it came from.
        finite = got[np.isfinite(got)]
        self.assertAlmostEqual(overshoot["above"],
                               max(0.0, float(finite.max()) - float(self.v.max())))
        self.assertAlmostEqual(overshoot["below"],
                               max(0.0, float(self.v.min()) - float(finite.min())))


class SamplesThatCannotBeTriangulated(unittest.TestCase):
    """P-158 — the refusal names what is wrong and what to do instead.

    A single survey line has no area. Qhull says so in its own vocabulary,
    which nobody can act on.
    """

    def test_a_single_line_of_samples_is_refused_by_name(self) -> None:
        x = np.linspace(0.0, 100.0, 25)
        y = np.zeros_like(x)
        with self.assertRaises(tin_grid.TriangulationFailed) as raised:
            tin_grid.build(x, y, x * 2.0, method="linear")
        message = str(raised.exception)
        self.assertIn("collinear", message)
        self.assertIn("grid.idw", message,
                      "the refusal must name the method that does work here")

    def test_two_samples_are_refused_before_qhull(self) -> None:
        with self.assertRaises(tin_grid.TriangulationFailed) as raised:
            tin_grid.build(np.array([0.0, 1.0]), np.array([0.0, 1.0]),
                           np.array([1.0, 2.0]), method="linear")
        self.assertIn("at least 3", str(raised.exception))

    def test_an_unknown_method_is_refused(self) -> None:
        with self.assertRaises(tin_grid.TriangulationFailed):
            tin_grid.build(*_scattered(), method="kriging")


class TheComparisonIsMeasuredAndComparable(unittest.TestCase):
    """P-159 — cross-validation scores every method on the same points.

    IDW's radius leaves some held-out samples null where a triangulated method
    still answers. Scoring each on its own subset would reward the method that
    answered least, because the points with the most neighbours are the easy
    ones.
    """

    def setUp(self) -> None:
        self.x, self.y, self.v = _scattered(n=300, seed=3)

    def test_every_method_is_scored_and_ranked(self) -> None:
        result = crossval.compare(self.x, self.y, self.v, radius=25.0)
        names = {row["method"] for row in result["methods"]}
        self.assertEqual(names, {"grid.idw", "grid.tin_linear",
                                 "grid.tin_cubic"})
        self.assertIn(result["recommended"], names)

    def test_the_recommendation_is_the_lowest_rmse(self) -> None:
        result = crossval.compare(self.x, self.y, self.v, radius=25.0)
        scored = [r for r in result["methods"] if r["rmse"] is not None]
        best = min(scored, key=lambda r: r["rmse"])
        self.assertEqual(result["recommended"], best["method"])

    def test_a_plane_is_won_by_the_exact_methods(self) -> None:
        """On a field the triangulated methods reproduce exactly, they must
        win. If IDW wins here the comparison is not measuring what it says."""
        result = crossval.compare(self.x, self.y, self.v, radius=25.0)
        by_name = {r["method"]: r for r in result["methods"]}
        self.assertLess(by_name["grid.tin_linear"]["rmse"],
                        by_name["grid.idw"]["rmse"])

    def test_it_is_deterministic(self) -> None:
        """A recommendation that moves between two runs on one dataset is not
        a measurement, and nobody could act on it."""
        first = crossval.compare(self.x, self.y, self.v, radius=25.0)
        second = crossval.compare(self.x, self.y, self.v, radius=25.0)
        self.assertEqual(first["recommended"], second["recommended"])
        self.assertEqual([r["rmse"] for r in first["methods"]],
                         [r["rmse"] for r in second["methods"]])

    def test_too_few_samples_is_said_not_scored(self) -> None:
        result = crossval.compare(self.x[:5], self.y[:5], self.v[:5],
                                  radius=25.0)
        self.assertIsNone(result["recommended"])
        self.assertIn("too few", result["reason"])

    def test_collinear_samples_leave_the_tin_methods_marked_not_applicable(
            self) -> None:
        x = np.linspace(0.0, 100.0, 60)
        y = np.zeros_like(x)
        result = crossval.compare(x, y, x * 2.0, radius=25.0)
        by_name = {r["method"]: r for r in result["methods"]}
        self.assertFalse(by_name["grid.tin_linear"]["applies"])
        self.assertFalse(by_name["grid.tin_cubic"]["applies"])
        self.assertEqual(result["recommended"], "grid.idw",
                         "IDW is the one that works on a line, so it is what "
                         "the comparison must recommend there")


class TheInterpolatorsAreRegisteredAndDeclared(unittest.TestCase):
    """P-160 — the worker announces them, and says which ones estimate."""

    def test_the_three_interpolators_are_registered(self) -> None:
        for name in ("grid.idw", "grid.tin_linear", "grid.tin_cubic"):
            self.assertIn(name, registry.capabilities())

    def test_cross_validation_is_read_only(self) -> None:
        """P-53 — a decision aid taken before a run cannot half-commit one."""
        self.assertTrue(registry.get("grid.cross_validate").read_only)

    def test_the_gridding_operators_that_estimate_say_so(self) -> None:
        self.assertFalse(registry.get("grid.euclidean_distance").read_only)
        for name in ("grid.tin_linear", "grid.tin_cubic"):
            operator = registry.get(name)
            self.assertIn("QGIS", operator.summary,
                          "the summary must name what this is in QGIS, so "
                          "someone who knows one recognises the other")
            self.assertTrue(operator.reference)

    def test_a_triangulated_operator_takes_no_search_radius(self) -> None:
        """A control that does nothing is worse than a missing one."""
        for name in ("grid.tin_linear", "grid.tin_cubic"):
            names = {p.name for p in registry.get(name).parameters}
            self.assertNotIn("radius", names)
            self.assertNotIn("power", names)
            self.assertIn("max_distance", names)


class ThePathHoldsNoPythonLoop(unittest.TestCase):
    """P-153 — ADR-007. Checked by what each loop iterates."""

    def test_no_loop_over_cells_or_samples(self) -> None:
        for module in (tin_grid, crossval):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped.startswith("for "):
                    continue
                iterated = stripped.split(" in ", 1)[-1].rstrip(":")
                # Loops over methods, folds and parameters are fine; a loop
                # over cells or over samples is not.
                self.assertNotRegex(
                    iterated, r"cell|pixel|point[^s_]|sample",
                    f"{Path(module.__file__).name}: {stripped}")


@unittest.skipUnless(LATTICE.exists(), f"{LATTICE} is not in the repository")
class OnTheRealLatticeData(unittest.TestCase):
    """A18 — the defect this milestone closes, on the file it was seen on.

    `vp_500_m.csv` is 1626 samples on a regular 125 m lattice. This is the
    case the report was about: IDW came out mottled and compressed toward the
    mean, and no other method was offered.
    """

    PARAMS = {
        "target_crs": "EPSG:26912", "source_crs": "EPSG:26912",
        "x_field": "Easting[m]", "y_field": "Northing[m]",
        "value_field": "Vp[km/s]", "unit": "km/s",
    }

    @classmethod
    def setUpClass(cls) -> None:
        import pandas as pd

        frame = pd.read_csv(LATTICE)
        cls.x = frame["Easting[m]"].to_numpy(float)
        cls.y = frame["Northing[m]"].to_numpy(float)
        cls.v = frame["Vp[km/s]"].to_numpy(float)

    def test_the_triangulated_methods_beat_idw_on_this_survey(self) -> None:
        """The measurement that justifies the whole change. It is asserted as
        an ordering, not as a number: the numbers move with scipy, the
        ordering is the finding."""
        result = crossval.compare(self.x, self.y, self.v, radius=375.0)
        by_name = {r["method"]: r for r in result["methods"]}
        self.assertLess(by_name["grid.tin_cubic"]["rmse"],
                        by_name["grid.idw"]["rmse"])
        self.assertEqual(result["recommended"], "grid.tin_cubic")

    def test_idw_compresses_the_range_and_the_cubic_does_not(self) -> None:
        """The visible half of the same defect: a weighted mean cannot reach
        the extremes of the field it is averaging."""
        gx, gy = np.meshgrid(
            np.linspace(self.x.min(), self.x.max(), 120),
            np.linspace(self.y.min(), self.y.max(), 120))
        qx, qy = gx.ravel(), gy.ravel()
        span = float(self.v.max() - self.v.min())

        weighted = idw_grid.interpolate(self.x, self.y, self.v, qx, qy,
                                        radius=375.0, power=2.0)
        cubic = tin_grid.interpolate(self.x, self.y, self.v, qx, qy,
                                     method="cubic")
        idw_span = float(np.nanmax(weighted) - np.nanmin(weighted))
        cubic_span = float(np.nanmax(cubic) - np.nanmin(cubic))
        self.assertLess(idw_span, span)
        self.assertGreater(cubic_span, idw_span)

    def test_the_operator_runs_and_the_manifest_records_the_method(self) -> None:
        from geopotential_worker.operators.base import Context

        class _Ctx(Context):
            def __init__(self, out):
                self.output_dir = out
                self.emitted = []

            def progress(self, stage, fraction, message=""):
                pass

            def check_cancel(self):
                pass

            def emit(self, name, artifact):
                self.emitted.append((name, artifact))

        with tempfile.TemporaryDirectory() as tmp:
            ctx = _Ctx(Path(tmp))
            manifest = registry.get("grid.tin_cubic").run(
                [str(LATTICE)],
                dict(self.PARAMS, pixel_size=42.0, max_distance=None,
                     result_name="vp_tin_cubic"),
                ctx)

        gridding = manifest["gridding"]
        self.assertEqual(gridding["method"], "tin_cubic")
        self.assertTrue(gridding["interpolates"])
        self.assertTrue(gridding["may_overshoot"])
        self.assertEqual(gridding["bounded_by"], "convex hull of the samples")
        self.assertIsNotNone(manifest["statistics"]["overshoot"])
        self.assertEqual(manifest["statistics"]["unit"], "km/s")

    def test_cross_validation_writes_nothing(self) -> None:
        """P-53, on the real path: a probe that left a file behind would be
        an inspection that half-imported a dataset."""
        from geopotential_worker.operators.base import Context

        class _Ctx(Context):
            def __init__(self, out):
                self.output_dir = out
                self.emitted = []

            def progress(self, stage, fraction, message=""):
                pass

            def check_cancel(self):
                pass

            def emit(self, name, artifact):  # pragma: no cover - must not run
                raise AssertionError("a read-only probe emitted an artefact")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = registry.get("grid.cross_validate").run(
                [str(LATTICE)],
                dict(self.PARAMS, radius=375.0, power=2.0, min_points=1,
                     max_points=16, max_distance=None, folds=5),
                _Ctx(out))
            self.assertEqual(list(out.iterdir()), [])
        self.assertIn("cross_validation", manifest)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
