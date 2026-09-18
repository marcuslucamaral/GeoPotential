"""Level 5 — the Project Store's integrity rules.

Section 14.4 lists twelve. These are the ones that already have code behind
them; the rest arrive with M2 and are named in the milestone rather than
asserted here against nothing.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from geopotential_app.project.store import (
    ProjectStore,
    canonical_params,
    content_key,
)


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpstore-"))
        self.store = ProjectStore.create(self.tmp / "P.gpot", "P")

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _committed_run(self) -> str:
        job = self.store.create_job("decision.membership", {"function": "large"}, [])
        return self.store.commit_run(job, {"operator_version": "1.0.0"})


class Layout(StoreCase):
    def test_a_project_is_a_directory_with_the_declared_subdirectories(self) -> None:
        for sub in ("data", "artifacts", "cache", "previews", "reports",
                    "recovery", "logs"):
            self.assertTrue((self.store.root / sub).is_dir(), f"{sub}/ missing")
        self.assertTrue((self.store.root / "manifest.json").exists())

    def test_creating_over_an_existing_project_is_refused(self) -> None:
        with self.assertRaises(FileExistsError):
            ProjectStore.create(self.store.root, "P again")

    def test_opening_a_non_project_is_refused(self) -> None:
        with self.assertRaises(FileNotFoundError):
            ProjectStore.open(self.tmp / "nothing")

    def test_reopening_preserves_the_catalogue(self) -> None:
        run_id = self._committed_run()
        self.store.close()
        reopened = ProjectStore.open(self.store.root)
        self.assertEqual([r.id for r in reopened.runs()], [run_id])
        reopened.close()


class Immutability(StoreCase):
    def test_a_committed_run_cannot_be_updated(self) -> None:
        """Rule 1. Enforced by a trigger, not by a convention."""
        run_id = self._committed_run()
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.store.connect().execute(
                "UPDATE run SET manifest_json='{}' WHERE id=?", (run_id,)
            )
        self.assertIn("immutable", str(ctx.exception))

    def test_a_committed_run_cannot_be_deleted(self) -> None:
        run_id = self._committed_run()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connect().execute("DELETE FROM run WHERE id=?", (run_id,))

    def test_an_output_is_never_silently_overwritten(self) -> None:
        """Rule 3. A second artefact at the same path raises."""
        run_a = self._committed_run()
        run_b = self._committed_run()
        path = str(self.store.root / "artifacts" / "result.tif")
        self.store.register_artifact(run_a, "r", path, "GeoTIFF", "sha256:aa", 10)
        with self.assertRaises(ValueError) as ctx:
            self.store.register_artifact(run_b, "r", path, "GeoTIFF", "sha256:bb", 10)
        self.assertIn("never overwrites", str(ctx.exception))

    def test_an_artefact_needs_a_run(self) -> None:
        """The foreign key forbids the orphan a mid-commit crash would leave."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connect().execute(
                "INSERT INTO artifact (id, run_id, artifact_id, path, artifact_type, "
                "hash, size_bytes, created_at) VALUES "
                "('x','no-such-run','a','/tmp/a.tif','GeoTIFF','sha256:0',1,'now')"
            )


class ContentAddressing(StoreCase):
    def test_parameter_order_does_not_change_the_key(self) -> None:
        """Rule 5: canonical serialization. Same run, same key."""
        a = canonical_params({"gamma": 0.7, "alpha": 1})
        b = canonical_params({"alpha": 1, "gamma": 0.7})
        self.assertEqual(a, b)

    def test_a_changed_parameter_changes_the_key(self) -> None:
        """Rule 4: parameters enter the hash."""
        base = content_key("op", "1.0.0", ["/a.tif"], {"gamma": 0.7})
        changed = content_key("op", "1.0.0", ["/a.tif"], {"gamma": 0.8})
        self.assertNotEqual(base, changed)

    def test_a_changed_operator_version_changes_the_key(self) -> None:
        self.assertNotEqual(
            content_key("op", "1.0.0", ["/a.tif"], {}),
            content_key("op", "1.1.0", ["/a.tif"], {}),
        )

    def test_input_order_does_not_change_the_key(self) -> None:
        self.assertEqual(
            content_key("op", "1.0.0", ["/a.tif", "/b.tif"], {}),
            content_key("op", "1.0.0", ["/b.tif", "/a.tif"], {}),
        )

    def test_a_run_is_findable_by_content(self) -> None:
        run_id = self._committed_run()
        record = self.store.runs()[0]
        found = self.store.find_run_by_content(record.content_key)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, run_id)


class ExternalInputs(StoreCase):
    def test_a_dataset_records_size_timestamp_and_hash(self) -> None:
        """Rules 6-8: enough to detect that an input changed."""
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        self.store.add_dataset(source, "raster", crs="EPSG:26912", unit="mGal")
        row = self.store.connect().execute("SELECT * FROM dataset").fetchone()
        self.assertEqual(row["size_bytes"], 12)
        self.assertTrue(row["hash"].startswith("sha256:"))
        self.assertIsNotNone(row["mtime"])
        self.assertEqual(row["crs"], "EPSG:26912")
        self.assertEqual(row["unit"], "mGal")

    def test_importing_the_same_file_again_is_the_same_dataset(self) -> None:
        """A project keeps its catalogue, so a file imported once and then
        again on the next session is the same dataset — not a second one.

        Inserting a row per import made the catalogue grow every time the
        project was reopened, and the harmonize dialog offered the same
        raster four times.
        """
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        first = self.store.add_dataset(source, "raster", unit="mGal")
        again = self.store.add_dataset(source, "raster", unit="mGal")
        self.assertEqual(first, again)
        self.assertEqual(len(self.store.datasets()), 1)

    def test_the_same_path_with_different_content_is_a_new_dataset(self) -> None:
        """The hash is what decides. A file that changed under the project is
        different data, and runs that used the old bytes recorded the old
        hash — collapsing the two would erase that."""
        source = self.tmp / "input.bin"
        source.write_bytes(b"geopotential")
        first = self.store.add_dataset(source, "raster")
        source.write_bytes(b"geopotential, edited")
        second = self.store.add_dataset(source, "raster")
        self.assertNotEqual(first, second)
        hashes = {row["hash"] for row in self.store.datasets()}
        self.assertEqual(len(hashes), 2)

    def test_two_different_files_stay_two_datasets(self) -> None:
        (self.tmp / "a.bin").write_bytes(b"a")
        (self.tmp / "b.bin").write_bytes(b"b")
        self.store.add_dataset(self.tmp / "a.bin", "raster")
        self.store.add_dataset(self.tmp / "b.bin", "raster")
        self.assertEqual(len(self.store.datasets()), 2)


class Provenance(StoreCase):
    def test_creating_a_project_records_an_event(self) -> None:
        rows = self.store.connect().execute(
            "SELECT kind FROM provenance_event"
        ).fetchall()
        self.assertIn("project.created", [r["kind"] for r in rows])

    def test_the_build_and_environment_are_recorded(self) -> None:
        self.store.record_build("0.1.00", "worker 0.1.00", "1.0.0", {"numpy": "2.4.1"})
        row = self.store.connect().execute(
            "SELECT * FROM software_build ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["app_version"], "0.1.00")
        self.assertIn("numpy", row["packages"])
        self.assertTrue(row["python"])
        self.assertTrue(row["platform"])


class CacheIsDiscardable(StoreCase):
    def test_deleting_the_cache_does_not_destroy_a_run(self) -> None:
        """Rule 11. The cache is recreatable; the lineage is not."""
        run_id = self._committed_run()
        cache = self.store.root / "cache"
        (cache / "something.tif").write_bytes(b"x")
        shutil.rmtree(cache)
        cache.mkdir()
        self.assertEqual([r.id for r in self.store.runs()], [run_id])


if __name__ == "__main__":
    unittest.main()
