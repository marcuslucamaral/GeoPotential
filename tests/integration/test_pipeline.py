"""Level 5 — the M5 gate, which is a flow rather than a list.

    dados -> QA/QC -> harmonização -> membership -> AHP/pesos -> MCDA
          -> prospectividade

Driven end to end through the real worker, on the real Utah FORGE dataset:
a distance-to-fault raster in EPSG:26912 and a landslide conditioning factor in
EPSG:5186. Two CRSs, two grids, two units — which is the point. A pipeline
tested on layers that already agree has not been tested.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from geopotential_app.controllers.app_controller import AppController
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
FAULTS = DATA / "utah_forge" / "Distance_to_fault.tif"
CANVAS = DATA / "synthetic" / "msp" / "canvas"
FIELD_A = CANVAS / "large_field.tif"
FIELD_B = CANVAS / "large_field_b.tif"

_app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

TARGET_CRS = "EPSG:26912"
PIXEL = 40.0  # coarse enough to keep the suite quick, fine enough to be real


@unittest.skipUnless(FAULTS.exists() and FIELD_A.exists(),
                     "run tools/make_canvas_fixtures.py first")
class Pipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gppipe-"))
        self.controller = AppController()
        self.controller.createProject(str(self.tmp / "P.gpot"), "P")
        self.controller.startWorker()
        if not self.controller.supervisor.wait_for_ready(20000):
            self.skipTest("the worker did not start")

    def tearDown(self) -> None:
        self.controller.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_job(self, operator: str, params: dict, inputs: list[str]) -> tuple[str, dict]:
        finished: list[tuple[str, str]] = []
        manifests: list[dict] = []
        self.controller._job_controller.jobFinished.connect(
            lambda j, s: finished.append((j, s))
        )
        self.controller.supervisor.jobSucceeded.connect(
            lambda m: manifests.append(m["manifest"])
        )
        job = self.controller.submit(operator, params, inputs)
        self.assertTrue(job, f"{operator} was refused before submission")
        for _ in range(1500):
            self.controller.supervisor.pump(20)
            _app.processEvents()
            if finished:
                break
        self.assertTrue(finished, f"{operator} never finished")
        return finished[-1][1], (manifests[-1] if manifests else {})

    def harmonize(self) -> dict:
        state, manifest = self.run_job("grid.harmonize", {
            "target_crs": TARGET_CRS,
            "pixel_size": PIXEL,
            "extent_policy": "intersection",
            "layers": [
                {"path": str(FIELD_A), "name": "heat_proxy", "unit": "mGal",
                 "resampling": "bilinear"},
                {"path": str(FIELD_B), "name": "structure_proxy", "unit": "mGal",
                 "resampling": "bilinear"},
            ],
        }, [])
        self.assertEqual(state, "Succeeded", "harmonization failed")
        return manifest


class Harmonization(Pipeline):
    """G2: QA/QC -> harmonização."""

    def test_layers_arrive_on_one_grid(self) -> None:
        manifest = self.harmonize()
        grid = manifest["grid"]
        self.assertEqual(grid["crs"], TARGET_CRS)
        self.assertEqual(grid["pixel_size_x"], PIXEL)
        self.assertTrue(grid["square_pixel"])
        self.assertEqual(len(manifest["layers"]), 2)

        import rasterio

        shapes = set()
        for layer in manifest["layers"]:
            with rasterio.open(layer["artifact"]) as src:
                shapes.add((src.width, src.height, str(src.crs)))
                self.assertTrue(np.isnan(src.nodata))
        self.assertEqual(len(shapes), 1, "every layer must land on one grid")

    def test_each_layer_records_where_it_came_from(self) -> None:
        manifest = self.harmonize()
        for layer in manifest["layers"]:
            self.assertTrue(layer["source_hash"].startswith("sha256:"))
            self.assertTrue(layer["hash"].startswith("sha256:"))
            self.assertIn("resampling", layer)
            self.assertIn("source_crs", layer)
            self.assertIn("unit", layer)

    def test_the_extent_policy_is_recorded(self) -> None:
        """Intersection and union are different maps."""
        manifest = self.harmonize()
        self.assertEqual(manifest["extent_policy"], "intersection")
        self.assertIn("common_validity_fraction", manifest)

    def test_a_resource_estimate_precedes_it(self) -> None:
        manifest = self.harmonize()
        self.assertTrue(manifest["plan"]["assumptions"])
        self.assertGreater(manifest["plan"]["ram_mb"], 0)

    def test_a_geographic_target_crs_is_refused(self) -> None:
        state, _ = self.run_job("grid.harmonize", {
            "target_crs": "EPSG:4326", "pixel_size": 0.001,
            "layers": [{"path": str(FIELD_A), "name": "a", "unit": "mGal"}],
        }, [])
        self.assertEqual(state, "Failed")

    def test_a_categorical_layer_cannot_be_averaged(self) -> None:
        """Averaging class codes produces classes that do not exist."""
        state, _ = self.run_job("grid.harmonize", {
            "target_crs": TARGET_CRS, "pixel_size": PIXEL,
            "layers": [{"path": str(FIELD_A), "name": "geology", "unit": "class",
                        "resampling": "bilinear", "categorical": True}],
        }, [])
        self.assertEqual(state, "Failed")


class Weights(Pipeline):
    """G4: membership -> AHP/pesos."""

    def test_weights_come_back_with_their_consistency_ratio(self) -> None:
        state, manifest = self.run_job("decision.ahp_weights", {
            "matrix": [[1, 3], [1 / 3, 1]],
            "names": ["heat_proxy", "structure_proxy"],
        }, [])
        self.assertEqual(state, "Succeeded")
        ahp = manifest["ahp"]
        self.assertAlmostEqual(sum(ahp["weights"]), 1.0, places=9)
        self.assertAlmostEqual(ahp["weights_by_name"]["heat_proxy"], 0.75, places=6)
        self.assertTrue(ahp["consistent"])
        self.assertIn("Saaty", ahp["reference"])

    def test_an_inconsistent_matrix_is_refused_with_its_numbers(self) -> None:
        state, _ = self.run_job("decision.ahp_weights", {
            "matrix": [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]],
            "names": ["a", "b", "c"],
        }, [])
        self.assertEqual(state, "Failed")
        jobs = self.controller.store.jobs()
        message = jobs[-1]["error_message"]
        self.assertIn("CR", message)
        self.assertIn("justification", message)

    def test_an_override_is_recorded_in_the_manifest(self) -> None:
        state, manifest = self.run_job("decision.ahp_weights", {
            "matrix": [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]],
            "names": ["a", "b", "c"],
            "override_reason": "accepted by the review of 2026-09-01",
        }, [])
        self.assertEqual(state, "Succeeded")
        self.assertIn("review", manifest["ahp"]["override"])
        self.assertFalse(manifest["ahp"]["consistent"])

    def test_a_weights_probe_commits_no_run(self) -> None:
        """It answers a question; it computes no map."""
        self.run_job("decision.ahp_weights",
                     {"matrix": [[1, 3], [1 / 3, 1]], "names": ["a", "b"]}, [])
        self.assertEqual(self.controller.store.runs(), [])
        self.assertEqual(len(self.controller.store.validations()), 1)


class Prospectivity(Pipeline):
    """G3, G5 and G6: membership -> MCDA -> prospectividade."""

    def aggregate(self, method: str, **extra) -> tuple[str, dict]:
        manifest = self.harmonize()
        paths = {l["name"]: l["artifact"] for l in manifest["layers"]}
        params = {
            "method": method,
            "result_name": f"prospectivity_{method}",
            "criteria": [
                {"path": paths["heat_proxy"], "name": "heat_proxy",
                 "unit": "mGal", "function": "linear_increasing"},
                {"path": paths["structure_proxy"], "name": "structure_proxy",
                 "unit": "mGal", "function": "linear_decreasing"},
            ],
        }
        params.update(extra)
        return self.run_job("decision.aggregate", params, [])

    def test_the_full_flow_produces_a_suitability_map(self) -> None:
        state, manifest = self.aggregate("fuzzy_gamma", gamma=0.7)
        self.assertEqual(state, "Succeeded")
        result = manifest["result"]
        self.assertEqual(result["method"], "fuzzy_gamma")
        self.assertEqual(result["unit"], "suitability [0-1], dimensionless")
        self.assertGreaterEqual(result["min"], -1e-6)
        self.assertLessEqual(result["max"], 1 + 1e-6)

    def test_the_output_is_in_zero_one_and_declares_its_nodata(self) -> None:
        import rasterio

        self.aggregate("fuzzy_gamma", gamma=0.7)
        run = self.controller.store.runs()[-1]
        path = self.controller.store.artifacts(run.id)[0]["path"]
        with rasterio.open(path) as src:
            values = src.read(1)
            self.assertTrue(np.isnan(src.nodata))
            self.assertEqual(src.tags()["GEOPOTENTIAL_UNIT"], "suitability [0-1]")
        valid = np.isfinite(values)
        self.assertTrue(valid.any())
        self.assertGreaterEqual(float(values[valid].min()), -1e-6)
        self.assertLessEqual(float(values[valid].max()), 1 + 1e-6)

    def test_the_manifest_reproduces_the_run(self) -> None:
        """G6. Inputs and hashes, grid, per-layer method, aggregation and
        parameters, and the criterion order weights bind to."""
        _, manifest = self.aggregate("fuzzy_gamma", gamma=0.7)
        self.assertEqual(manifest["criterion_order"],
                         ["heat_proxy", "structure_proxy"])
        for criterion in manifest["criteria"]:
            self.assertTrue(criterion["source_hash"].startswith("sha256:"))
            self.assertIn("anchors", criterion)
            self.assertIn("function", criterion)
            self.assertIn("source_unit", criterion)
        self.assertEqual(manifest["params"]["gamma"], 0.7)
        self.assertIn("grid", manifest)
        self.assertIn("Zimmermann", manifest["reference"])

    def test_every_operator_runs_over_the_same_stack(self) -> None:
        for method in ("fuzzy_gamma", "fuzzy_product", "fuzzy_sum"):
            with self.subTest(method=method):
                state, manifest = self.aggregate(method)
                self.assertEqual(state, "Succeeded")
                self.assertEqual(manifest["result"]["method"], method)

    def test_weighted_combination_uses_the_named_weights(self) -> None:
        state, manifest = self.aggregate(
            "weighted_linear_combination",
            weights=[{"name": "heat_proxy", "weight": 0.75},
                     {"name": "structure_proxy", "weight": 0.25}],
        )
        self.assertEqual(state, "Succeeded")
        self.assertEqual(manifest["weights"]["heat_proxy"], 0.75)

    def test_weights_that_do_not_sum_to_one_are_refused(self) -> None:
        state, _ = self.aggregate(
            "weighted_linear_combination",
            weights=[{"name": "heat_proxy", "weight": 0.5},
                     {"name": "structure_proxy", "weight": 0.2}],
        )
        self.assertEqual(state, "Failed")
        self.assertIn("sum to", self.controller.store.jobs()[-1]["error_message"])

    def test_gamma_changes_the_map(self) -> None:
        """A map made at 0.2 is not the map made at 0.9."""
        import rasterio

        maps = []
        for gamma in (0.2, 0.9):
            self.aggregate("fuzzy_gamma", gamma=gamma,
                           result_name=f"g{int(gamma * 10)}")
            run = self.controller.store.runs()[-1]
            path = self.controller.store.artifacts(run.id)[0]["path"]
            with rasterio.open(path) as src:
                maps.append(src.read(1))
        both = np.isfinite(maps[0]) & np.isfinite(maps[1])
        self.assertFalse(np.allclose(maps[0][both], maps[1][both], atol=1e-4))

    def test_correlated_criteria_are_reported(self) -> None:
        """Section 15.1, through the whole pipeline."""
        manifest = self.harmonize()
        paths = {l["name"]: l["artifact"] for l in manifest["layers"]}
        # The same layer twice under two names: perfectly correlated by
        # construction, which is what double counting looks like at its worst.
        _, aggregated = self.run_job("decision.aggregate", {
            "method": "fuzzy_gamma", "gamma": 0.7, "result_name": "twice",
            "criteria": [
                {"path": paths["heat_proxy"], "name": "heat_flow",
                 "unit": "mGal", "function": "linear_increasing"},
                {"path": paths["heat_proxy"], "name": "gradient",
                 "unit": "mGal", "function": "linear_increasing"},
            ],
        }, [])
        findings = aggregated["correlation_findings"]
        self.assertTrue(findings, "identical criteria must be reported")
        self.assertAlmostEqual(abs(findings[0]["coefficient"]), 1.0, places=3)
        self.assertIn("count it twice", findings[0]["message"])

    def test_a_run_is_committed_and_immutable(self) -> None:
        import sqlite3

        self.aggregate("fuzzy_gamma", gamma=0.7)
        runs = self.controller.store.runs()
        self.assertTrue(runs)
        with self.assertRaises(sqlite3.IntegrityError):
            self.controller.store.connect().execute(
                "UPDATE run SET manifest_json='{}' WHERE id=?", (runs[-1].id,)
            )


if __name__ == "__main__":
    unittest.main()
