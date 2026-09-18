"""Level 5 — the Import Wizard's flow, end to end through the real worker.

Gate M3 as the user meets it: describe, validate, correct, import — and the
refusals along the way. Uses a live worker child, because "impede operação
inválida" has to hold across the process boundary, not just inside a function.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from geopotential_app.controllers.app_controller import AppController
from geopotential_app.controllers.worker_supervisor import WorkerSupervisor
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
CLEAN = DATA / "utah_forge" / "Distance_to_fault.tif"
BROKEN = DATA / "synthetic" / "msp" / "broken"

_app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])


@unittest.skipUnless(CLEAN.exists() and (BROKEN / "MANIFEST.json").exists(),
                     "fixtures absent; run tools/make_broken_fixtures.py")
class ImportFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpimport-"))
        self.controller = AppController()
        self.controller.createProject(str(self.tmp / "P.gpot"), "P")
        self.controller.startWorker()
        if not self.controller.supervisor.wait_for_ready(20000):
            self.skipTest("the worker did not start")

    def tearDown(self) -> None:
        self.controller.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _drive(self, job_id: str, timeout: int = 600) -> None:
        """Pump until the job reaches a terminal state."""
        for _ in range(timeout):
            self.controller.supervisor.pump(20)
            _app.processEvents()
            row = self.controller.job_model.row(job_id)
            if row and row.state in ("Succeeded", "Failed", "Cancelled", "Interrupted"):
                return
        self.fail(f"job {job_id} never finished")

    def describe(self, path: Path, declared: dict | None = None) -> dict:
        seen: list[dict] = []
        self.controller.datasetDescribed.connect(seen.append)
        job = self.controller.describeDataset(str(path), declared or {})
        self.assertTrue(job, "describe was refused")
        self._drive(job)
        return seen[-1] if seen else {}

    def validate(self, path: Path, declared: dict | None = None) -> dict:
        seen: list[dict] = []
        self.controller.datasetValidated.connect(seen.append)
        job = self.controller.validateDataset(str(path), declared or {})
        self.assertTrue(job, "validate was refused")
        self._drive(job)
        return seen[-1] if seen else {}


class Describing(ImportFlow):
    def test_a_raster_is_described_without_being_imported(self) -> None:
        """Section 9.2: the diagnosis happens before the dataset enters."""
        description = self.describe(CLEAN)
        self.assertEqual(description["kind"], "raster")
        self.assertEqual(description["crs"], "EPSG:26912")
        self.assertEqual(description["crs_unit"], "metre")
        self.assertEqual(description["width"], 979)
        self.assertIn("histogram", description["statistics"])
        self.assertEqual(self.controller.store.datasets(), [],
                         "describing must not create a dataset row")
        self.assertEqual(self.controller.store.runs(), [],
                         "a read-only probe must not commit a run")

    def test_a_table_is_described_with_its_columns(self) -> None:
        description = self.describe(DATA / "utah_forge" /
                                    "anomaly_bouger_easting_northin_bouger.csv")
        self.assertEqual(description["kind"], "table")
        self.assertEqual(description["fields"], ["easting", "northing", "gCBGA"])
        self.assertEqual(description["x_field"], "easting")
        self.assertEqual(description["y_field"], "northing")
        self.assertEqual(description["rows"], 3735)

    def test_an_unsupported_format_is_refused_by_name(self) -> None:
        odd = self.tmp / "notes.docx"
        odd.write_bytes(b"x")
        errors: list[tuple[str, str]] = []
        self.controller.errorRaised.connect(lambda m, r: errors.append((m, r)))
        job = self.controller.describeDataset(str(odd), {})
        self._drive(job)
        row = self.controller.job_model.row(job)
        self.assertEqual(row.state, "Failed")
        self.assertIn("docx", row.message)
        self.assertIn("Supported", row.message)


class Validating(ImportFlow):
    def test_a_clean_dataset_is_usable(self) -> None:
        result = self.validate(CLEAN, {"unit": "m"})
        self.assertTrue(result["report"]["usable"], result["report"]["summary"])

    def test_a_blocking_defect_makes_it_unusable(self) -> None:
        result = self.validate(BROKEN / "no_crs.tif")
        self.assertFalse(result["report"]["usable"])
        rules = {f["rule"] for f in result["report"]["findings"]}
        self.assertIn("crs.present", rules)

    def test_the_verdict_is_recorded_as_a_validation_result(self) -> None:
        """G5: preserve the audit trail, including for a refusal."""
        self.validate(BROKEN / "no_crs.tif")
        records = self.controller.store.validations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["usable"], 0)
        self.assertEqual(records[0]["severity"], "BLOCKER")
        self.assertIn("crs.present", records[0]["findings_json"])
        self.assertEqual(records[0]["operator"], "qc.validate_dataset")

    def test_a_raster_verdict_carries_a_resource_plan(self) -> None:
        """MSP-06: no high-cost operation without an estimate."""
        result = self.validate(CLEAN, {"unit": "m"})
        plan = result["plan"]
        self.assertIsNotNone(plan)
        self.assertGreater(plan["ram_mb"], 0)
        self.assertIn(plan["policy"], ("in_memory", "blocked", "refuse"))
        self.assertTrue(plan["assumptions"], "an estimate must state its assumptions")
        self.assertIn("memory", plan["summary"])


class Correcting(ImportFlow):
    """G3: permit correction, and record that a correction was asserted."""

    def test_declaring_a_crs_turns_a_refusal_into_an_import(self) -> None:
        path = BROKEN / "no_crs.tif"

        first = self.validate(path)
        self.assertFalse(first["report"]["usable"])
        self.assertEqual(self.controller.importDataset(str(path), "raster"), "",
                         "an unusable dataset must not import")

        second = self.validate(path, {"crs": "EPSG:26912", "unit": "m"})
        self.assertTrue(second["report"]["usable"],
                        [f["message"] for f in second["report"]["findings"]])

        dataset_id = self.controller.importDataset(str(path), "raster")
        self.assertTrue(dataset_id, "a corrected dataset must import")
        rows = self.controller.store.datasets()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["crs"], "EPSG:26912")

    def test_the_declaration_is_recorded_as_the_operator_s_assertion(self) -> None:
        path = BROKEN / "no_crs.tif"
        self.validate(path, {"crs": "EPSG:26912", "unit": "m"})
        record = self.controller.store.validations()[0]
        declared = json.loads(record["declared_json"])
        self.assertEqual(declared["crs"], "EPSG:26912")
        self.assertEqual(declared["unit"], "m")

        events = [
            e for e in self.controller.store.connect().execute(
                "SELECT * FROM provenance_event WHERE kind='dataset.validated'"
            ).fetchall()
        ]
        self.assertTrue(events)
        self.assertIn("EPSG:26912", events[-1]["detail_json"])


class Refusing(ImportFlow):
    """G4: prevent the invalid operation, on both paths that could allow it."""

    def test_an_unvalidated_dataset_cannot_be_imported(self) -> None:
        errors: list[str] = []
        self.controller.errorRaised.connect(lambda m, r: errors.append(m))
        result = self.controller.importDataset(str(CLEAN), "raster")
        self.assertEqual(result, "")
        self.assertTrue(any("has not been validated" in m for m in errors))

    def test_a_blocked_dataset_cannot_be_imported(self) -> None:
        errors: list[str] = []
        self.controller.errorRaised.connect(lambda m, r: errors.append(m))
        self.validate(BROKEN / "all_null.tif")
        result = self.controller.importDataset(str(BROKEN / "all_null.tif"), "raster")
        self.assertEqual(result, "")
        self.assertTrue(any("cannot be used" in m for m in errors),
                        f"the refusal must quote the verdict; got {errors}")
        self.assertEqual(self.controller.store.datasets(), [])

    def test_the_usability_question_has_one_answer(self) -> None:
        """The wizard and the import path consult the same function."""
        self.validate(BROKEN / "all_null.tif")
        self.assertFalse(self.controller.isDatasetUsable(str(BROKEN / "all_null.tif")))
        self.validate(CLEAN, {"unit": "m"})
        self.assertTrue(self.controller.isDatasetUsable(str(CLEAN)))

    def test_a_warning_does_not_prevent_import(self) -> None:
        path = BROKEN / "anisotropic.tif"
        result = self.validate(path, {"unit": "m"})
        self.assertTrue(result["report"]["usable"])
        self.assertTrue(self.controller.importDataset(str(path), "raster"))


class CrossLayerChecks(ImportFlow):
    def test_a_disjoint_layer_is_reported_and_still_importable(self) -> None:
        """Overlap is only answerable across layers, so the context is real.

        ADR-MSP-005: it is a warning here and a refusal at harmonization. At
        import the layer may be reference data or another area, and refusing it
        refuses work nobody asked to have refused.
        """
        self.validate(CLEAN, {"unit": "m"})
        self.controller.importDataset(str(CLEAN), "raster")

        result = self.validate(BROKEN / "disjoint.tif", {"unit": "m"})
        findings = {f["rule"]: f for f in result["report"]["findings"]}
        self.assertIn("extent.overlap", findings)
        self.assertEqual(findings["extent.overlap"]["severity"], "WARNING")
        self.assertTrue(result["report"]["usable"])
        self.assertTrue(
            self.controller.importDataset(str(BROKEN / "disjoint.tif"), "raster"))

    def test_a_coarser_layer_is_detected_against_what_is_imported(self) -> None:
        """Resolution, like overlap, is only answerable across layers."""
        self.validate(CLEAN, {"unit": "m"})
        self.controller.importDataset(str(CLEAN), "raster")

        result = self.validate(BROKEN / "coarse.tif", {"unit": "m"})
        findings = {f["rule"]: f for f in result["report"]["findings"]}
        self.assertIn("grid.resolution_mismatch", findings)
        self.assertEqual(findings["grid.resolution_mismatch"]["severity"], "WARNING")
        self.assertIn("10x coarser", findings["grid.resolution_mismatch"]["what"])
        self.assertTrue(result["report"]["usable"],
                        "a resolution mismatch warns; it does not block")


if __name__ == "__main__":
    unittest.main()
