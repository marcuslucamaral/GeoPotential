"""M5.6 — sparse data onto an analysis grid. MSP-06.

Three operators, and the line between them is the point of this suite:

    grid.idw                 **estimates** a value where nothing was measured
    grid.euclidean_distance  measures a fact
    grid.rasterize           transfers a fact

Only the first interpolates. The other two must never be described as
interpolation, and the manifest each writes has to say which it is.

The declared tolerances, fixed here before anything is measured against them:
the distance transform is exact and is held to 1e-6 of the analytic answer;
IDW's weighted mean is held to 1e-9 where symmetry gives a closed form.
"""
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from affine import Affine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.domain.crs import CrsInfo  # noqa: E402
from geopotential_worker.domain.grid import TargetGrid  # noqa: E402
from geopotential_worker.grid import distance as distance_grid  # noqa: E402
from geopotential_worker.grid import idw as idw_grid  # noqa: E402
from geopotential_worker.grid import rasterize as rasterize_grid  # noqa: E402
from geopotential_worker.grid import spec as grid_spec  # noqa: E402

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
TABLE = DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
SHAPEFILE = DATA / "synthetic" / "blocks.shp"

#: Declared before measuring, and not adjusted afterwards.
EXACT = 1e-6
CLOSED_FORM = 1e-9

METRIC = CrsInfo.from_user_input("EPSG:26912", source="test")
GEOGRAPHIC = CrsInfo.from_user_input("EPSG:4326", source="test")


def _grid(px=10.0, py=10.0, width=21, height=21, left=0.0, top=210.0):
    return TargetGrid(transform=Affine(px, 0.0, left, 0.0, -py, top),
                      crs=METRIC, width=width, height=height)


class TheGridIsDeclared(unittest.TestCase):
    """A1-A4 — pixel and area are chosen, and the cost is known first."""

    BOX = (0.0, 0.0, 1000.0, 1000.0)

    def test_without_bounds_the_grid_covers_the_data(self) -> None:
        grid, _, prov = grid_spec.build(
            target_crs=METRIC, pixel_size=(100.0, 100.0), data_bounds=self.BOX)
        self.assertEqual((grid.width, grid.height), (10, 10))
        self.assertEqual(prov["extent_source"], "data")

    def test_bounds_grid_exactly_the_area_asked_for(self) -> None:
        """Cutting the analysis to a region is a decision, and it is also the
        cheapest thing to change when a grid does not fit."""
        grid, _, prov = grid_spec.build(
            target_crs=METRIC, pixel_size=(100.0, 100.0), data_bounds=self.BOX,
            bounds=(200.0, 200.0, 700.0, 700.0))
        self.assertEqual((grid.width, grid.height), (5, 5))
        self.assertEqual(prov["extent_source"], "chosen")
        left, bottom, right, top = grid.bounds
        self.assertAlmostEqual(left, 200.0, delta=EXACT)
        self.assertAlmostEqual(top, 700.0, delta=EXACT)

    def test_bounds_in_another_crs_are_transformed_and_recorded(self) -> None:
        grid, _, prov = grid_spec.build(
            target_crs=METRIC, pixel_size=(1000.0, 1000.0),
            data_bounds=(300000.0, 4200000.0, 400000.0, 4300000.0),
            bounds=(-113.0, 38.0, -112.5, 38.5), bounds_crs=GEOGRAPHIC)
        self.assertEqual(prov["extent_source"], "chosen")
        self.assertEqual(prov["bounds_crs"], GEOGRAPHIC.name)
        # It landed in metres, not degrees.
        self.assertGreater(grid.bounds[2] - grid.bounds[0], 1000.0)

    def test_a_grid_that_cannot_fit_is_refused_before_allocating(self) -> None:
        """A2/A3. The message has to name what to reduce: a refusal that only
        says "too large" leaves the person with nothing to do."""
        with self.assertRaises(grid_spec.GridRefused) as ctx:
            grid_spec.build(target_crs=METRIC, pixel_size=(0.001, 0.001),
                            data_bounds=(0.0, 0.0, 1e6, 1e6))
        message = str(ctx.exception)
        self.assertIn("bounds", message)
        self.assertRegex(message, r"resolution|pixel")

    def test_a_geographic_target_is_refused_for_a_measuring_grid(self) -> None:
        with self.assertRaises(grid_spec.GridRefused) as ctx:
            grid_spec.build(target_crs=GEOGRAPHIC, pixel_size=(0.001, 0.001),
                            data_bounds=(-113.0, 38.0, -112.0, 39.0))
        self.assertIn("geographic", str(ctx.exception))

    def test_a_geographic_target_is_allowed_when_nothing_is_measured(self) -> None:
        grid, _, _ = grid_spec.build(
            target_crs=GEOGRAPHIC, pixel_size=(0.01, 0.01),
            data_bounds=(-113.0, 38.0, -112.0, 39.0), require_metric=False)
        self.assertEqual((grid.width, grid.height), (100, 100))

    def test_a_bad_pixel_or_extent_is_refused_by_name(self) -> None:
        for pixel, bounds in (((0.0, 10.0), None), ((-1.0, 1.0), None),
                              ((10.0, 10.0), (100.0, 0.0, 0.0, 100.0)),
                              ((10.0, 10.0), (0.0, 0.0, 0.0, 100.0))):
            with self.subTest(pixel=pixel, bounds=bounds):
                with self.assertRaises(grid_spec.GridRefused):
                    grid_spec.build(target_crs=METRIC, pixel_size=pixel,
                                    data_bounds=self.BOX, bounds=bounds)

    def test_cell_centres_are_half_a_pixel_in(self) -> None:
        grid = _grid(px=10.0, py=10.0, width=2, height=2, left=0.0, top=20.0)
        x, y = grid_spec.cell_centres(grid, 0, 2)
        np.testing.assert_allclose(x, [5.0, 15.0, 5.0, 15.0], atol=EXACT)
        np.testing.assert_allclose(y, [15.0, 15.0, 5.0, 5.0], atol=EXACT)

    def test_the_blocks_cover_every_row_exactly_once(self) -> None:
        """However the planner splits it, the loop is over blocks and every
        row is visited once — a gap would leave a band of the grid unwritten."""
        from geopotential_worker.grid.planner import Plan, Policy

        grid = _grid(height=100)
        for policy, rows in ((Policy.IN_MEMORY, None), (Policy.BLOCKED, 7)):
            plan = Plan("t", 0, 1, 0, 0, 0, 0, policy, rows, "", [])
            covered = []
            for start, stop in grid_spec.row_blocks(grid, plan):
                covered.extend(range(start, stop))
            self.assertEqual(covered, list(range(100)), f"{policy} left a gap")


class Idw(unittest.TestCase):
    """A5-A10 — Shepard (1968), and the refusals that keep it honest."""

    # A unit square with a different value at each corner.
    X = np.array([0.0, 10.0, 0.0, 10.0])
    Y = np.array([0.0, 0.0, 10.0, 10.0])
    V = np.array([1.0, 2.0, 3.0, 4.0])

    def _at(self, x, y, **kwargs):
        kwargs.setdefault("radius", 50.0)
        return idw_grid.interpolate(
            self.X, self.Y, self.V, np.atleast_1d(x), np.atleast_1d(y), **kwargs)

    def test_a_cell_on_a_sample_takes_that_sample(self) -> None:
        """A5. `1/0` is inf and a sum of infs divides to NaN, so the cells that
        are best known are exactly the ones a careless implementation blanks."""
        for x, y, expected in zip(self.X, self.Y, self.V):
            with self.subTest(x=x, y=y):
                self.assertAlmostEqual(float(self._at(x, y)[0]), expected,
                                       delta=EXACT)

    def test_the_centre_is_the_mean_by_symmetry(self) -> None:
        """Four corners equidistant from the centre weigh the same, whatever
        the power — a closed form to check the weighting against."""
        for power in (1.0, 2.0, 3.5):
            with self.subTest(power=power):
                self.assertAlmostEqual(float(self._at(5.0, 5.0, power=power)[0]),
                                       2.5, delta=CLOSED_FORM)

    def test_it_never_leaves_the_interval_of_its_samples(self) -> None:
        """A8, P-148. A weighted mean cannot exceed the values it averages,
        and this is what makes IDW safe where an extrapolating method is not."""
        rng = np.random.default_rng(7)
        cx = rng.uniform(-2.0, 12.0, 2000)
        cy = rng.uniform(-2.0, 12.0, 2000)
        out = idw_grid.interpolate(self.X, self.Y, self.V, cx, cy, radius=50.0)
        finite = out[np.isfinite(out)]
        self.assertGreater(finite.size, 0)
        self.assertGreaterEqual(float(finite.min()), float(self.V.min()) - EXACT)
        self.assertLessEqual(float(finite.max()), float(self.V.max()) + EXACT)

    def test_outside_the_radius_the_cell_stays_null(self) -> None:
        """A7, P-149. Filling it from the nearest sample however far produces
        a map with no holes and no survey behind them."""
        self.assertTrue(np.isnan(self._at(1000.0, 1000.0, radius=50.0)[0]))

    def test_too_few_neighbours_leaves_the_cell_null(self) -> None:
        self.assertTrue(np.isnan(self._at(5.0, 5.0, min_points=5)[0]))
        self.assertFalse(np.isnan(self._at(5.0, 5.0, min_points=4)[0]))

    def test_a_high_power_tends_to_the_nearest_sample(self) -> None:
        """A6, measured rather than asserted: p -> inf is nearest-neighbour."""
        near_corner = float(self._at(1.0, 1.0, power=30.0)[0])
        self.assertAlmostEqual(near_corner, 1.0, delta=1e-3)

    def test_a_power_near_zero_tends_to_the_plain_mean(self) -> None:
        flat = float(self._at(1.0, 1.0, power=0.01)[0])
        self.assertAlmostEqual(flat, float(self.V.mean()), delta=0.05)

    def test_a_non_finite_sample_is_dropped_not_propagated(self) -> None:
        x = np.array([0.0, 10.0, np.nan])
        y = np.array([0.0, 0.0, 5.0])
        v = np.array([1.0, 2.0, 99.0])
        out = idw_grid.interpolate(x, y, v, np.array([5.0]), np.array([0.0]),
                                   radius=50.0)
        self.assertAlmostEqual(float(out[0]), 1.5, delta=CLOSED_FORM)

    def test_a_sample_with_no_value_is_dropped(self) -> None:
        v = np.array([1.0, 2.0, np.nan, 4.0])
        out = idw_grid.interpolate(self.X, self.Y, v, np.array([0.0]),
                                   np.array([10.0]), radius=50.0)
        self.assertTrue(np.isfinite(out[0]))

    def test_no_samples_gives_an_empty_field_not_an_error(self) -> None:
        out = idw_grid.interpolate(np.array([]), np.array([]), np.array([]),
                                   np.array([1.0]), np.array([1.0]), radius=5.0)
        self.assertTrue(np.isnan(out[0]))

    def test_a_non_positive_radius_is_refused(self) -> None:
        for radius in (0.0, -1.0, float("nan")):
            with self.subTest(radius=radius):
                with self.assertRaises(ValueError):
                    self._at(5.0, 5.0, radius=radius)

    def test_the_gridding_path_holds_no_loop_over_cells_or_points(self) -> None:
        """A10, P-153. Checked by what each loop iterates, not by its
        spelling — the same rule `points.py` and `geometry.py` are held to."""
        for module in (idw_grid, distance_grid, rasterize_grid, grid_spec):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped.startswith("for "):
                    continue
                iterated = stripped.split(" in ", 1)[-1].rstrip(":")
                # Loops over parameters, features and row blocks are fine;
                # a loop over cells or over samples is not.
                self.assertNotRegex(
                    iterated, r"cell|pixel|point[^s_]|sample",
                    f"{Path(module.__file__).name}: {stripped}")


class EuclideanDistance(unittest.TestCase):
    """A11-A14 — it measures. Nothing here estimates anything."""

    def _single_point(self):
        mask = np.zeros((21, 21), dtype=bool)
        mask[10, 10] = True
        return mask

    def test_the_distance_on_the_feature_is_zero(self) -> None:
        out = distance_grid.to_features(self._single_point(), (10.0, 10.0))
        self.assertEqual(float(out[10, 10]), 0.0)

    def test_it_matches_the_analytic_answer(self) -> None:
        """A12. Three cells across and four down from a single point is the
        3-4-5 triangle, and the transform has to give exactly 50 m."""
        out = distance_grid.to_features(self._single_point(), (10.0, 10.0))
        self.assertAlmostEqual(float(out[10, 13]), 30.0, delta=EXACT)
        self.assertAlmostEqual(float(out[14, 13]), math.hypot(30.0, 40.0),
                               delta=EXACT)

    def test_an_anisotropic_pixel_is_carried_through(self) -> None:
        """A13, P-151. And the averaged answer is a different number, so this
        distinguishes "handled" from "happens to look right"."""
        out = distance_grid.to_features(self._single_point(), (10.0, 40.0))
        self.assertAlmostEqual(float(out[9, 10]), 40.0, delta=EXACT)
        self.assertAlmostEqual(float(out[10, 11]), 10.0, delta=EXACT)

        averaged = distance_grid.to_features(self._single_point(), (25.0, 25.0))
        self.assertNotAlmostEqual(float(averaged[9, 10]), 40.0, delta=1.0)

    def test_an_empty_mask_is_null_everywhere_not_zero(self) -> None:
        """"No feature anywhere" is not "the feature is everywhere", and zero
        would read as the second."""
        out = distance_grid.to_features(np.zeros((4, 4), dtype=bool), (10.0, 10.0))
        self.assertTrue(np.all(np.isnan(out)))

    def test_max_distance_cuts_to_null(self) -> None:
        out = distance_grid.to_features(self._single_point(), (10.0, 10.0),
                                        max_distance=25.0)
        self.assertTrue(np.isnan(float(out[10, 13])))     # 30 m away
        self.assertAlmostEqual(float(out[10, 12]), 20.0, delta=EXACT)

    def test_a_bad_pixel_or_cap_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            distance_grid.to_features(self._single_point(), (0.0, 10.0))
        with self.assertRaises(ValueError):
            distance_grid.to_features(self._single_point(), (10.0, 10.0),
                                      max_distance=-5.0)


class Rasterize(unittest.TestCase):
    """A15-A17 — it transfers a value that already exists."""

    def _square(self, value=7.0):
        import shapely

        return [(shapely.box(20.0, 20.0, 180.0, 180.0), value)]

    def test_the_value_inside_is_the_features_own(self) -> None:
        out = rasterize_grid.burn(self._square(7.0), _grid())
        self.assertAlmostEqual(float(out[10, 10]), 7.0, delta=EXACT)

    def test_outside_every_feature_is_null_not_zero(self) -> None:
        """Zero is a value. A cell no feature covers has none, and painting a
        zero there would put "seven kilometres from nothing" into a criterion."""
        out = rasterize_grid.burn(self._square(), _grid())
        self.assertTrue(np.isnan(float(out[0, 0])))

    def test_all_touched_changes_the_boundary(self) -> None:
        import shapely

        thin = [(shapely.LineString([(5.0, 5.0), (200.0, 200.0)]), 3.0)]
        centres = rasterize_grid.burn(thin, _grid(), all_touched=False)
        touched = rasterize_grid.burn(thin, _grid(), all_touched=True)
        self.assertGreater(int(np.isfinite(touched).sum()),
                           int(np.isfinite(centres).sum()))

    def test_a_feature_with_no_value_is_dropped(self) -> None:
        import shapely

        shapes = [(shapely.box(0.0, 0.0, 210.0, 210.0), 5.0),
                  (shapely.box(20.0, 20.0, 180.0, 180.0), float("nan"))]
        out = rasterize_grid.burn(shapes, _grid())
        self.assertAlmostEqual(float(out[10, 10]), 5.0, delta=EXACT,
                               msg="a NaN feature painted over a real one")

    def test_nothing_to_burn_gives_a_null_grid(self) -> None:
        out = rasterize_grid.burn([], _grid())
        self.assertTrue(np.all(np.isnan(out)))

    def test_a_point_mask_finds_the_cells_the_points_fall_in(self) -> None:
        grid = _grid()
        mask = rasterize_grid.points_mask(
            np.array([5.0, 15.0, -50.0]), np.array([205.0, 205.0, 205.0]), grid)
        self.assertTrue(mask[0, 0])
        self.assertTrue(mask[0, 1])
        self.assertEqual(int(mask.sum()), 2, "a point outside was counted")

    def test_a_mask_keeps_a_thin_feature(self) -> None:
        """A fault line one metre wide on a 10 m grid crosses no cell centre.
        Losing it would make every distance measured from it a distance to
        something else."""
        import shapely

        line = [shapely.LineString([(5.0, 100.0), (205.0, 100.0)])]
        self.assertTrue(rasterize_grid.mask(line, _grid()).any())


@unittest.skipUnless(TABLE.exists() and SHAPEFILE.exists(),
                     "the real fixtures are absent")
class TheSurveysOwnSpacing(unittest.TestCase):
    """A search radius is unguessable from a file name; the data knows it.

    The median distance from a sample to its nearest neighbour is a fact about
    the survey. Below it an interpolation leaves almost every cell null — which
    is what a person sees as "it produced nothing" — and no screen can propose
    a starting point without it.
    """

    @unittest.skipUnless(TABLE.exists(), "the smoke table is missing")
    def test_a_table_reports_how_far_apart_its_samples_are(self) -> None:
        from geopotential_worker.io.describe import describe

        spacing = describe(TABLE).as_dict()["median_spacing"]
        self.assertIsNotNone(spacing)
        self.assertGreater(spacing, 0.0)

    def test_a_regular_grid_of_samples_reports_its_own_step(self) -> None:
        """An analytic case: samples on a 10 m lattice are 10 m apart."""
        from geopotential_worker.io.describe import _median_spacing

        x, y = np.meshgrid(np.arange(0.0, 100.0, 10.0),
                           np.arange(0.0, 100.0, 10.0))
        self.assertAlmostEqual(
            _median_spacing(x.ravel(), y.ravel()), 10.0, delta=EXACT)

    def test_a_single_sample_has_no_spacing(self) -> None:
        from geopotential_worker.io.describe import _median_spacing

        self.assertIsNone(_median_spacing(np.array([1.0]), np.array([2.0])))

    def test_duplicated_coordinates_do_not_report_zero(self) -> None:
        """Two readings at one station are 0 m apart and say nothing about the
        survey's spacing; a zero radius would be proposed from them."""
        from geopotential_worker.io.describe import _median_spacing

        x = np.array([0.0, 0.0, 10.0, 20.0])
        y = np.array([0.0, 0.0, 0.0, 0.0])
        self.assertGreater(_median_spacing(x, y), 0.0)


class ARasterCarriesItsOwnUnit(unittest.TestCase):
    """Every artefact stamps `GEOPOTENTIAL_UNIT`; reading it back closes the
    loop, so a produced raster never shows a number with no unit beside it."""

    @unittest.skipUnless(TABLE.exists(), "the smoke table is missing")
    def test_the_tag_is_read_back_by_describe(self) -> None:
        import tempfile as tf

        from geopotential_worker.io.describe import describe
        from geopotential_worker.io.writers import write_geotiff

        out = Path(tf.mkdtemp(prefix="gp-unit-"))
        grid = _grid(width=4, height=4)
        values = np.full(grid.shape, 2.5, dtype=np.float32)
        artifact = write_geotiff(values, grid, out / "field.tif",
                                 tags={"GEOPOTENTIAL_UNIT": "g/cm3"})
        self.assertEqual(describe(artifact.path).unit, "g/cm3")

    def test_a_declared_unit_still_wins(self) -> None:
        """The operator's statement outranks the file's own tag: declaring is
        how a wrong tag gets corrected."""
        import tempfile as tf

        from geopotential_worker.io.describe import describe
        from geopotential_worker.io.writers import write_geotiff

        out = Path(tf.mkdtemp(prefix="gp-unit-"))
        grid = _grid(width=4, height=4)
        artifact = write_geotiff(
            np.zeros(grid.shape, dtype=np.float32), grid, out / "f.tif",
            tags={"GEOPOTENTIAL_UNIT": "g/cm3"})
        self.assertEqual(
            describe(artifact.path, overrides={"unit": "mGal"}).unit, "mGal")

    def test_a_file_with_no_tag_reports_no_unit(self) -> None:
        """Absent is absent. Inventing one would put a unit on a raster that
        never claimed it."""
        import tempfile as tf

        from geopotential_worker.io.describe import describe
        from geopotential_worker.io.writers import write_geotiff

        out = Path(tf.mkdtemp(prefix="gp-unit-"))
        grid = _grid(width=4, height=4)
        artifact = write_geotiff(
            np.zeros(grid.shape, dtype=np.float32), grid, out / "bare.tif")
        self.assertIn(describe(artifact.path).unit, (None, ""))


class TheScreenSendsTheDocumentedDefaults(unittest.TestCase):
    """§16 — a default that exists only in the interface is a silent default.

    The gridding screen sent `min_points: 3` while the operator documents 1.
    That is a stricter analysis than the one the contract describes, and on a
    line survey it took the coverage from 45 % to 12 % with nothing on screen
    saying a different default had been chosen for the person.
    """

    DIALOG = (ROOT / "app" / "geopotential_app" / "qml" / "GeoPotential"
              / "GriddingDialog.qml")

    def _operator_default(self, name: str, parameter: str):
        from geopotential_worker.operators import registry

        for p in registry.get(name).parameters:
            if p.name == parameter:
                return p.default
        raise AssertionError(f"{name} has no parameter {parameter}")

    def _dialog_default(self, prop: str) -> str:
        import re

        source = self.DIALOG.read_text(encoding="utf-8")
        match = re.search(rf'property string {prop}: "([^"]*)"', source)
        self.assertIsNotNone(match, f"{prop} is not a property of the dialog")
        return match.group(1)

    def test_min_points_matches_the_operator(self) -> None:
        self.assertEqual(int(self._dialog_default("minPoints")),
                         int(self._operator_default("grid.idw", "min_points")))

    def test_power_matches_the_operator(self) -> None:
        self.assertEqual(float(self._dialog_default("power")),
                         float(self._operator_default("grid.idw", "power")))


class TheOperatorsOnRealData(unittest.TestCase):
    """A18-A19 — the three run on `../data/`, and the manifest reproduces it."""

    @classmethod
    def setUpClass(cls) -> None:
        from geopotential_worker.operators import registry

        cls.registry = registry
        cls.out = Path(tempfile.mkdtemp(prefix="gp-gridding-"))

    def _run(self, name: str, inputs, params):
        from geopotential_worker.operators.base import Context

        class Recording(Context):
            def __init__(self, directory):
                self.output_dir = directory
                self.artifacts = []

            def progress(self, stage, fraction, message=""):  # noqa: ANN001
                pass

            def check_cancel(self):
                pass

            def emit(self, name, artifact):  # noqa: ANN001
                self.artifacts.append((name, artifact))

        operator = self.registry.get(name)
        coerced = {p.name: p.coerce(params.get(p.name), operator=name)
                   for p in operator.parameters}
        ctx = Recording(self.out)
        return operator.run([str(p) for p in inputs], coerced, ctx), ctx

    IDW = {
        "target_crs": "EPSG:26912", "pixel_size": 200.0, "unit": "mGal",
        "source_crs": "EPSG:26912", "x_field": "easting",
        "y_field": "northing", "value_field": "gCBGA",
        "radius": 1000.0, "power": 2.0, "min_points": 3, "max_points": 12,
    }

    def test_the_three_are_registered_and_none_is_still_planned(self) -> None:
        capabilities = self.registry.capabilities()
        for name in ("grid.idw", "grid.euclidean_distance", "grid.rasterize"):
            self.assertIn(name, capabilities)
            self.assertNotIn(name, self.registry.PLANNED,
                             f"{name} runs and is still announced as planned")

    def test_a_real_csv_becomes_a_raster(self) -> None:
        manifest, ctx = self._run(
            "grid.idw", [TABLE], {**self.IDW, "result_name": "idw_real"})
        self.assertEqual(len(ctx.artifacts), 1)
        self.assertTrue(ctx.artifacts[0][1].path.exists())
        self.assertGreater(manifest["statistics"]["valid"], 0)
        self.assertTrue(manifest["gridding"]["interpolates"])
        self.assertEqual(manifest["gridding"]["extent_source"], "data")

    def test_the_interpolated_field_stays_inside_the_samples(self) -> None:
        import pandas as pd

        frame = pd.read_csv(TABLE)
        low, high = frame["gCBGA"].min(), frame["gCBGA"].max()
        manifest, _ = self._run(
            "grid.idw", [TABLE], {**self.IDW, "result_name": "idw_range"})
        self.assertGreaterEqual(manifest["statistics"]["min"], low - EXACT)
        self.assertLessEqual(manifest["statistics"]["max"], high + EXACT)

    def test_a_chosen_area_grids_only_that_area(self) -> None:
        whole, _ = self._run(
            "grid.idw", [TABLE], {**self.IDW, "result_name": "idw_whole"})
        part, _ = self._run("grid.idw", [TABLE], {
            **self.IDW, "result_name": "idw_part",
            "bounds": [330000.0, 4260000.0, 335000.0, 4265000.0]})
        self.assertEqual(part["gridding"]["extent_source"], "chosen")
        self.assertLess(part["grid"]["width"] * part["grid"]["height"],
                        whole["grid"]["width"] * whole["grid"]["height"])

    def test_a_table_without_a_declared_crs_is_refused_by_name(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        params = {**self.IDW, "result_name": "x", "source_crs": None}
        with self.assertRaises(ParameterError) as ctx:
            self._run("grid.idw", [TABLE], params)
        self.assertIn("no default", str(ctx.exception))

    def test_an_undeclared_column_is_refused_listing_the_real_ones(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        params = {**self.IDW, "result_name": "x", "value_field": "gravity"}
        with self.assertRaises(ParameterError) as ctx:
            self._run("grid.idw", [TABLE], params)
        message = str(ctx.exception)
        self.assertIn("gravity", message)
        self.assertIn("gCBGA", message)

    def test_a_pixel_too_fine_is_refused_before_it_allocates(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError):
            self._run("grid.idw", [TABLE],
                      {**self.IDW, "result_name": "x", "pixel_size": 0.001})

    def test_distance_and_rasterize_declare_that_they_do_not_interpolate(self) -> None:
        """The manifest has to say which of the three made a field. A distance
        called an interpolation would put an estimate in a lineage that has
        none."""
        distance, _ = self._run("grid.euclidean_distance", [SHAPEFILE], {
            "target_crs": "EPSG:31982", "pixel_size": 50.0,
            "result_name": "dist_real", "source_crs": "EPSG:31982"})
        burned, _ = self._run("grid.rasterize", [SHAPEFILE], {
            "target_crs": "EPSG:31982", "pixel_size": 50.0,
            "result_name": "burn_real", "unit": "km2",
            "value_field": "area_km2", "source_crs": "EPSG:31982"})
        self.assertFalse(distance["gridding"]["interpolates"])
        self.assertFalse(burned["gridding"]["interpolates"])
        self.assertEqual(distance["gridding"]["method"], "euclidean_distance")
        self.assertEqual(burned["gridding"]["method"], "rasterize")

    def test_the_distance_field_starts_at_zero_on_the_features(self) -> None:
        manifest, _ = self._run("grid.euclidean_distance", [SHAPEFILE], {
            "target_crs": "EPSG:31982", "pixel_size": 50.0,
            "result_name": "dist_zero", "source_crs": "EPSG:31982"})
        self.assertAlmostEqual(manifest["statistics"]["min"], 0.0, delta=EXACT)
        self.assertGreater(manifest["gridding"]["cells_on_feature"], 0)

    def test_a_geographic_target_is_refused_for_all_three(self) -> None:
        for name, extra in (
            ("grid.idw", {**self.IDW}),
            ("grid.euclidean_distance", {"source_crs": "EPSG:26912"}),
            ("grid.rasterize", {"unit": "km2", "value_field": "area_km2",
                                "source_crs": "EPSG:26912"}),
        ):
            with self.subTest(operator=name):
                with self.assertRaises(Exception) as ctx:
                    self._run(name, [TABLE], {
                        **extra, "result_name": "x",
                        "target_crs": "EPSG:4326", "pixel_size": 0.001})
                self.assertIn("geographic", str(ctx.exception).lower())

    def test_the_manifest_reproduces_the_grid(self) -> None:
        """A19. Method, radius, power, pixel and area — enough to build the
        same grid again without asking anyone what was done."""
        manifest, _ = self._run(
            "grid.idw", [TABLE], {**self.IDW, "result_name": "idw_manifest"})
        for key in ("operator", "operator_version", "reference", "params",
                    "grid", "gridding", "statistics", "inputs"):
            self.assertIn(key, manifest)
        params = manifest["params"]
        for key in ("target_crs", "pixel_size", "radius", "power",
                    "min_points", "max_points"):
            self.assertIn(key, params)
        self.assertIn("plan", manifest["gridding"])
        self.assertEqual(manifest["inputs"][0]["path"], str(TABLE.resolve()))


if __name__ == "__main__":
    unittest.main()
