"""Level 5 — the recovery pass, and the M2 integrity rules around it.

These test the store-and-recovery half of M2 without a worker: the pass is
pure reconciliation between the catalogue and the disk, so it can be driven by
constructing exactly the damaged state each case is about. The kill tests that
need a real child process live in `--self-test`.

Every case asserts the conservative direction: an ambiguity resolves towards
"this is not a result".
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from geopotential_app.project.logging import CHANNELS, ProjectLogs
from geopotential_app.project.recovery import discard_orphans, recover
from geopotential_app.project.store import SCHEMA_VERSION, ProjectStore


class RecoveryCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gprec-"))
        self.store = ProjectStore.create(self.tmp / "P.gpot", "P")
        self.store.open_session("0.1.00")

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _job(self, operator: str = "decision.membership") -> str:
        job_id = self.store.create_job(operator, {"function": "large"}, [])
        self.store.journal_open(job_id, operator, self.store.artifact_dir(job_id))
        return job_id

    def _committed_run(self, job_id: str) -> str:
        run_id = self.store.commit_run(job_id, {"operator_version": "1.0.0"})
        self.store.journal_close(job_id)
        return run_id


class CleanOpen(RecoveryCase):
    def test_a_clean_project_reports_clean(self) -> None:
        report = recover(self.store)
        self.assertTrue(report.clean)
        self.assertEqual(report.summary(), "The project opened cleanly.")


class InterruptedJobs(RecoveryCase):
    def test_a_job_in_flight_becomes_interrupted_never_succeeded(self) -> None:
        """The invariant M2 exists for."""
        job_id = self._job()
        self.store.set_job_state(job_id, "Running")

        report = recover(self.store)

        state = self.store.connect().execute(
            "SELECT state FROM job WHERE id=?", (job_id,)
        ).fetchone()["state"]
        self.assertEqual(state, "Interrupted")
        self.assertNotEqual(state, "Succeeded")
        self.assertEqual(len(report.interrupted_jobs), 1)
        self.assertEqual(report.interrupted_jobs[0]["job_id"], job_id)

    def test_interruption_is_recorded_as_provenance(self) -> None:
        job_id = self._job()
        self.store.set_job_state(job_id, "Committing")
        recover(self.store)
        kinds = [
            r["kind"]
            for r in self.store.connect().execute(
                "SELECT kind FROM provenance_event"
            ).fetchall()
        ]
        self.assertIn("job.interrupted", kinds)

    def test_the_journal_is_cleared_so_recovery_is_idempotent(self) -> None:
        job_id = self._job()
        self.store.set_job_state(job_id, "Running")
        recover(self.store)
        second = recover(self.store)
        self.assertEqual(second.interrupted_jobs, [])
        self.assertEqual(self.store.open_journal_entries(), [])

    def test_a_finished_job_is_not_reclassified(self) -> None:
        """A job that finished before the crash keeps its outcome."""
        job_id = self._job()
        self._committed_run(job_id)
        self.store.set_job_state(job_id, "Succeeded")
        recover(self.store)
        state = self.store.connect().execute(
            "SELECT state FROM job WHERE id=?", (job_id,)
        ).fetchone()["state"]
        self.assertEqual(state, "Succeeded")


class Orphans(RecoveryCase):
    def test_a_file_belonging_to_no_run_is_listed_not_adopted(self) -> None:
        """The distinction is the invariant: reported, never registered."""
        job_id = self._job()
        orphan = self.store.artifact_dir(job_id) / "half.tif"
        orphan.write_bytes(b"not a result")

        report = recover(self.store)

        self.assertEqual(len(report.orphan_artifacts), 1)
        self.assertEqual(report.orphan_artifacts[0]["path"], str(orphan))
        self.assertTrue(orphan.exists(), "recovery must not delete an orphan")
        registered = self.store.connect().execute(
            "SELECT COUNT(*) FROM artifact"
        ).fetchone()[0]
        self.assertEqual(registered, 0, "recovery must not register an orphan")

    def test_a_registered_artefact_is_not_an_orphan(self) -> None:
        job_id = self._job()
        run_id = self._committed_run(job_id)
        real = self.store.artifact_dir(job_id) / "result.tif"
        real.write_bytes(b"result")
        self.store.register_artifact(
            run_id, "r", str(real), "GeoTIFF", "sha256:aa", real.stat().st_size
        )
        report = recover(self.store)
        self.assertEqual(report.orphan_artifacts, [])

    def test_a_surviving_temporary_is_deleted_and_recorded(self) -> None:
        """A .tmp is never a result: the writer renames only after hashing."""
        job_id = self._job()
        residue = self.store.artifact_dir(job_id) / "result.tif.tmp"
        residue.write_bytes(b"half written")

        report = recover(self.store)

        self.assertFalse(residue.exists())
        self.assertEqual(len(report.removed_temporaries), 1)
        kinds = [
            r["kind"]
            for r in self.store.connect().execute(
                "SELECT kind FROM provenance_event"
            ).fetchall()
        ]
        self.assertIn("recovery.removed_temporary", kinds)

    def test_discarding_an_orphan_is_allowed(self) -> None:
        job_id = self._job()
        orphan = self.store.artifact_dir(job_id) / "half.tif"
        orphan.write_bytes(b"x")
        recover(self.store)
        removed = discard_orphans(self.store, [str(orphan)])
        self.assertEqual(removed, [str(orphan)])
        self.assertFalse(orphan.exists())

    def test_discarding_a_registered_artefact_is_refused(self) -> None:
        """It belongs to an immutable run."""
        job_id = self._job()
        run_id = self._committed_run(job_id)
        real = self.store.artifact_dir(job_id) / "result.tif"
        real.write_bytes(b"result")
        self.store.register_artifact(run_id, "r", str(real), "GeoTIFF", "sha256:aa", 6)
        with self.assertRaises(ValueError) as ctx:
            discard_orphans(self.store, [str(real)])
        self.assertIn("immutable", str(ctx.exception))
        self.assertTrue(real.exists())

    def test_discarding_outside_the_project_is_refused(self) -> None:
        outside = self.tmp / "not_mine.tif"
        outside.write_bytes(b"x")
        with self.assertRaises(ValueError) as ctx:
            discard_orphans(self.store, [str(outside)])
        self.assertIn("outside the project", str(ctx.exception))
        self.assertTrue(outside.exists())


class Sessions(RecoveryCase):
    def test_a_session_that_never_closed_is_visible_to_the_next_one(self) -> None:
        self.store.close()
        reopened = ProjectStore.open(self.tmp / "P.gpot")
        reopened.open_session("0.1.00")
        self.assertEqual(len(reopened.unclean_sessions()), 1)
        reopened.close()

    def test_a_closed_session_is_clean(self) -> None:
        self.store.close_session()
        self.store.close()
        reopened = ProjectStore.open(self.tmp / "P.gpot")
        reopened.open_session("0.1.00")
        self.assertEqual(reopened.unclean_sessions(), [])
        reopened.close()

    def test_a_journal_row_needs_a_session(self) -> None:
        """Write-ahead only means something if it is bound to who wrote it."""
        store = ProjectStore.create(self.tmp / "Q.gpot", "Q")
        job_id = store.create_job("op", {}, [])
        with self.assertRaises(RuntimeError):
            store.journal_open(job_id, "op", store.artifact_dir(job_id))
        store.close()


class Relink(RecoveryCase):
    def test_a_moved_input_is_reported_missing(self) -> None:
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        self.store.add_dataset(source, "raster")
        source.unlink()
        report = recover(self.store)
        self.assertEqual(len(report.missing_datasets), 1)
        self.assertFalse(report.clean)

    def test_relink_reports_whether_the_content_still_matches(self) -> None:
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        dataset_id = self.store.add_dataset(source, "raster")

        moved = self.tmp / "moved" / "input.bin"
        moved.parent.mkdir()
        shutil.move(source, moved)
        result = self.store.relink_dataset(dataset_id, moved)

        self.assertTrue(result["hash_matches"])
        self.assertEqual(result["new_path"], str(moved.resolve()))
        self.assertEqual(self.store.missing_datasets(), [])

    def test_relink_to_changed_content_is_reported_not_refused(self) -> None:
        """Deliberate and accidental look identical here; only the operator knows."""
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        dataset_id = self.store.add_dataset(source, "raster")

        replacement = self.tmp / "other.bin"
        replacement.write_bytes(b"different content entirely")
        result = self.store.relink_dataset(dataset_id, replacement)

        self.assertFalse(result["hash_matches"])
        self.assertNotEqual(result["old_hash"], result["new_hash"])

    def test_relink_keeps_the_previous_path(self) -> None:
        source = self.tmp / "input.bin"
        source.write_bytes(b"x")
        dataset_id = self.store.add_dataset(source, "raster")
        other = self.tmp / "elsewhere.bin"
        other.write_bytes(b"x")
        self.store.relink_dataset(dataset_id, other)
        row = self.store.connect().execute(
            "SELECT relinked_from FROM dataset WHERE id=?", (dataset_id,)
        ).fetchone()
        self.assertEqual(row["relinked_from"], str(source.resolve()))

    def test_relink_to_nothing_is_refused(self) -> None:
        source = self.tmp / "input.bin"
        source.write_bytes(b"x")
        dataset_id = self.store.add_dataset(source, "raster")
        with self.assertRaises(FileNotFoundError):
            self.store.relink_dataset(dataset_id, self.tmp / "nowhere.bin")


class Logs(RecoveryCase):
    def setUp(self) -> None:
        super().setUp()
        self.logs = ProjectLogs(self.store.root, "0.1.00")

    def test_the_four_channels_are_separate_files(self) -> None:
        self.logs.application("info", "opened")
        self.logs.scientific("run committed", run_id="r1")
        self.logs.worker("error", "traceback here")
        self.logs.crash("died")
        for channel in CHANNELS:
            path = self.store.root / "logs" / f"{channel}.jsonl"
            self.assertTrue(path.exists(), f"{channel} log missing")
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_a_reference_resolves_to_its_record(self) -> None:
        """This is what a `detail_ref` shown in the interface has to find."""
        ref = self.logs.worker("error", "the real traceback", job_id="J1")
        record = self.logs.resolve(ref)
        self.assertIsNotNone(record)
        self.assertEqual(record["msg"], "the real traceback")
        self.assertEqual(record["job_id"], "J1")
        self.assertEqual(record["channel"], "worker")

    def test_an_unknown_channel_is_refused_by_name(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            self.logs["packaging"]
        self.assertIn("application", str(ctx.exception))

    def test_the_diagnostic_carries_no_scientific_data(self) -> None:
        """A user sends this to support; it must not be their survey."""
        job_id = self._job()
        run_id = self._committed_run(job_id)
        artefact = self.store.artifact_dir(job_id) / "result.tif"
        artefact.write_bytes(b"PIXELS-THAT-MUST-NOT-LEAK" * 100)
        self.store.register_artifact(
            run_id, "r", str(artefact), "GeoTIFF", "sha256:aa",
            artefact.stat().st_size,
        )
        self.logs.scientific("run committed", run_id=run_id)

        out = self.logs.export_diagnostic(self.tmp / "diag.zip", self.store.summary())

        with zipfile.ZipFile(out) as archive:
            names = archive.namelist()
            blob = b"".join(archive.read(n) for n in names)
        self.assertIn("environment.json", names)
        self.assertTrue(any(n.startswith("logs/") for n in names))
        self.assertNotIn(b"PIXELS-THAT-MUST-NOT-LEAK", blob)
        self.assertFalse(
            [n for n in names if n.endswith((".tif", ".tiff", ".gpkg", ".npy"))],
            "no scientific artefact may be in the diagnostic",
        )

    def test_the_diagnostic_carries_the_environment(self) -> None:
        out = self.logs.export_diagnostic(self.tmp / "d.zip", self.store.summary())
        with zipfile.ZipFile(out) as archive:
            import json

            env = json.loads(archive.read("environment.json"))
        self.assertIn("packages", env)
        self.assertIn("platform", env)
        self.assertIn("store", env)
        self.assertEqual(env["app_version"], "0.1.00")


class Summary(RecoveryCase):
    def test_the_summary_counts_what_the_diagnostic_reports(self) -> None:
        job_id = self._job()
        self.store.set_job_state(job_id, "Running")
        summary = self.store.summary()
        self.assertEqual(summary["jobs"], 1)
        self.assertEqual(summary["open_journal_entries"], 1)
        self.assertEqual(summary["job_states"], {"Running": 1})
        # Against the constant, not a literal: the claim is that the summary
        # reports the store's schema version, not what that version happens
        # to be this month.
        self.assertEqual(summary["schema_version"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
