"""Level 5 — AOI persistence (gate M4 G4) and the difference map (G5).

The AOI half runs against the store directly; the difference half runs through
the real worker, because the refusals it makes are the point and they have to
hold across the process boundary.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from geopotential_app.controllers.app_controller import AppController
from geopotential_app.project.store import ProjectStore
from geopotential_app.utils.qt import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
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
CANVAS = DATA / "synthetic" / "msp" / "canvas"
A = CANVAS / "large_field.tif"
B = CANVAS / "large_field_b.tif"

_app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

SQUARE = [[330_100.0, 4_269_900.0], [330_600.0, 4_269_900.0],
          [330_600.0, 4_269_400.0], [330_100.0, 4_269_400.0]]


class AoiPersistence(unittest.TestCase):
    """Gate M4 G4: an AOI survives closing and reopening the project."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpaoi-"))
        self.root = self.tmp / "P.gpot"
        self.store = ProjectStore.create(self.root, "P")
        self.store.open_session("0.1.00")

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_an_aoi_survives_close_and_reopen(self) -> None:
        saved = self.store.save_aoi("survey", SQUARE, "EPSG:26912",
                                    note="the area of interest")
        self.store.close_session()
        self.store.close()

        reopened = ProjectStore.open(self.root)
        try:
            recovered = reopened.latest_aoi("survey")
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered["geometry"], SQUARE)
            self.assertEqual(recovered["crs"], "EPSG:26912")
            self.assertEqual(recovered["version"], saved["version"])
            self.assertEqual(recovered["note"], "the area of interest")
        finally:
            reopened.close()

    def test_editing_creates_a_version_and_keeps_the_old_one(self) -> None:
        """MSP-09 versioning. A run made inside v1 must stay interpretable."""
        first = self.store.save_aoi("survey", SQUARE, "EPSG:26912")
        wider = [[x + (500 if i in (1, 2) else 0), y] for i, (x, y) in enumerate(SQUARE)]
        second = self.store.save_aoi("survey", wider, "EPSG:26912")

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["parent_id"], first["id"])
        self.assertEqual(self.store.latest_aoi("survey")["version"], 2)

        # v1 is still there, and still says what it said.
        self.assertEqual(self.store.aoi(first["id"])["geometry"], SQUARE)
        self.assertEqual(len(self.store.aois(latest_only=False)), 2)
        self.assertEqual(len(self.store.aois()), 1, "only the latest by default")

    def test_the_area_is_reported(self) -> None:
        saved = self.store.save_aoi("survey", SQUARE, "EPSG:26912")
        self.assertAlmostEqual(saved["area"], 500.0 * 500.0, places=3)

    def test_vertex_order_does_not_change_the_area(self) -> None:
        clockwise = self.store.save_aoi("cw", SQUARE, "EPSG:26912")
        anticlockwise = self.store.save_aoi("acw", SQUARE[::-1], "EPSG:26912")
        self.assertAlmostEqual(clockwise["area"], anticlockwise["area"], places=6)

    def test_saving_records_provenance(self) -> None:
        self.store.save_aoi("survey", SQUARE, "EPSG:26912")
        events = self.store.connect().execute(
            "SELECT * FROM provenance_event WHERE kind='aoi.saved'"
        ).fetchall()
        self.assertEqual(len(events), 1)
        self.assertIn("EPSG:26912", events[0]["detail_json"])

    def test_an_aoi_without_a_crs_is_refused(self) -> None:
        """Coordinates without a CRS are pairs of numbers (ADR-004)."""
        with self.assertRaises(ValueError) as ctx:
            self.store.save_aoi("survey", SQUARE, "")
        self.assertIn("no default", str(ctx.exception))

    def test_a_degenerate_aoi_is_refused(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.store.save_aoi("line", [[0.0, 0.0], [1.0, 1.0]], "EPSG:26912")
        self.assertIn("three vertices", str(ctx.exception))

    def test_the_aoi_is_bound_to_the_session_that_drew_it(self) -> None:
        saved = self.store.save_aoi("survey", SQUARE, "EPSG:26912")
        self.assertIsNotNone(saved["session_id"])


@unittest.skipUnless(A.exists() and B.exists(),
                     "run tools/make_canvas_fixtures.py first")
class DifferenceMap(unittest.TestCase):
    """Gate M4 G5: the comparison is computed, not implied."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpdiff-"))
        self.controller = AppController()
        self.controller.createProject(str(self.tmp / "P.gpot"), "P")
        self.controller.startWorker()
        if not self.controller.supervisor.wait_for_ready(20000):
            self.skipTest("the worker did not start")

    def tearDown(self) -> None:
        self.controller.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, inputs: list[str], params: dict) -> tuple[str, str]:
        finished: list[tuple[str, str]] = []
        self.controller._job_controller.jobFinished.connect(
            lambda j, s: finished.append((j, s))
        )
        job = self.controller.submit("grid.difference", params, inputs)
        self.assertTrue(job, "the job was refused before submission")
        for _ in range(900):
            self.controller.supervisor.pump(20)
            _app.processEvents()
            if finished:
                break
        self.assertTrue(finished, "the job never finished")
        return job, finished[0][1]

    def test_a_difference_is_computed_and_committed(self) -> None:
        job, state = self._run(
            [str(A), str(B)], {"result_name": "delta", "unit": "mGal"}
        )
        self.assertEqual(state, "Succeeded")
        runs = self.controller.store.runs()
        self.assertEqual(len(runs), 1)
        artifacts = self.controller.store.artifacts(runs[0].id)
        self.assertEqual(len(artifacts), 1)
        self.assertTrue(Path(artifacts[0]["path"]).exists())

    def test_the_result_is_a_minus_b_pixel_by_pixel(self) -> None:
        """Checked against numpy, not against itself."""
        import rasterio

        self._run([str(A), str(B)], {"result_name": "delta", "unit": "mGal"})
        runs = self.controller.store.runs()
        out = self.controller.store.artifacts(runs[0].id)[0]["path"]

        with rasterio.open(A) as fa, rasterio.open(B) as fb, rasterio.open(out) as fd:
            # One window is enough and keeps the test fast; the operator works
            # in chunks, so a window that spans several chunk boundaries also
            # checks the chunking.
            window = rasterio.windows.Window(1000, 1000, 600, 600)
            va = fa.read(1, window=window)
            vb = fb.read(1, window=window)
            vd = fd.read(1, window=window)
        expected = va - vb
        both = np.isfinite(va) & np.isfinite(vb)
        np.testing.assert_allclose(vd[both], expected[both], rtol=1e-6, atol=1e-5)

    def test_the_difference_is_null_where_either_input_is_null(self) -> None:
        """A difference against a null is not zero.

        Treating it as zero paints 'no change' over exactly the pixels where
        nothing is known.
        """
        import rasterio

        self._run([str(A), str(B)], {"result_name": "delta", "unit": "mGal"})
        out = self.controller.store.artifacts(
            self.controller.store.runs()[0].id
        )[0]["path"]

        with rasterio.open(A) as fa, rasterio.open(B) as fb, rasterio.open(out) as fd:
            window = rasterio.windows.Window(2800, 800, 700, 700)
            va, vb, vd = (f.read(1, window=window) for f in (fa, fb, fd))
        either_null = ~np.isfinite(va) | ~np.isfinite(vb)
        self.assertTrue(either_null.any(), "the window should include the hole")
        self.assertTrue(np.isnan(vd[either_null]).all(),
                        "a difference against a null must be null, not zero")

    def test_the_output_declares_its_nodata_and_crs(self) -> None:
        import rasterio

        self._run([str(A), str(B)], {"result_name": "delta", "unit": "mGal"})
        out = self.controller.store.artifacts(
            self.controller.store.runs()[0].id
        )[0]["path"]
        with rasterio.open(out) as src:
            self.assertTrue(np.isnan(src.nodata))
            self.assertEqual(src.crs.to_epsg(), 26912)
            self.assertEqual(src.tags()["GEOPOTENTIAL_UNIT"], "mGal")

    def test_mismatched_grids_are_refused_by_name(self) -> None:
        """Resampling to make the subtraction possible would hide the
        misalignment inside the result."""
        other = DATA / "utah_forge" / "Distance_to_fault.tif"
        job, state = self._run(
            [str(A), str(other)], {"result_name": "bad", "unit": "m"}
        )
        self.assertEqual(state, "Failed")
        row = self.controller.job_model.row(job)
        self.assertIn("one grid", row.message)
        self.assertIn("large_field.tif", row.message)
        self.assertEqual(self.controller.store.runs(), [],
                         "a refused difference commits nothing")

    def test_one_input_is_refused(self) -> None:
        job, state = self._run([str(A)], {"result_name": "x", "unit": "mGal"})
        self.assertEqual(state, "Failed")
        self.assertIn("two rasters", self.controller.job_model.row(job).message)


if __name__ == "__main__":
    unittest.main()
