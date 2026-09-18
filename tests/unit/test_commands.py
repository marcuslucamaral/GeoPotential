"""Level 1 — the command stack.

The rule under test throughout: **undo reverts project state, never science.**
A completed run is immutable, so a command that commits one is a barrier the
stack will not walk back past.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from geopotential_app.commands import (
    Command,
    CommandError,
    CommandStack,
    ImportDatasetCommand,
    RelinkDatasetCommand,
    RunOperatorCommand,
)
from geopotential_app.project.store import ProjectStore


class Reversible(Command):
    """A minimal reversible command, for testing the stack itself."""

    name = "set value"
    reversible = True

    def __init__(self, sink: dict, key: str, value: object) -> None:
        super().__init__()
        self.sink, self.key, self.value = sink, key, value
        self.previous: object = None
        self._payload = {"key": key, "value": value}

    def execute(self) -> object:
        self.previous = self.sink.get(self.key)
        self.sink[self.key] = self.value
        return self.value

    def undo(self) -> None:
        if self.previous is None:
            self.sink.pop(self.key, None)
        else:
            self.sink[self.key] = self.previous


class Irreversible(Command):
    name = "commit run"
    reversible = False

    def __init__(self, sink: list) -> None:
        super().__init__()
        self.sink = sink

    def execute(self) -> None:
        self.sink.append("committed")


class Refusing(Command):
    name = "always refuses"

    def validate(self) -> None:
        raise CommandError("this input is not where the project expects it")

    def execute(self) -> None:  # pragma: no cover - never reached
        raise AssertionError("execute must not run after validate refused")


class StackCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gpcmd-"))
        self.store = ProjectStore.create(self.tmp / "P.gpot", "P")
        self.store.open_session("0.1.00")
        self.stack = CommandStack(self.store)

    def tearDown(self) -> None:
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class UndoRedo(StackCase):
    def test_undo_restores_the_previous_value(self) -> None:
        sink: dict = {}
        self.stack.run(Reversible(sink, "crs", "EPSG:26912"))
        self.assertEqual(sink["crs"], "EPSG:26912")
        self.stack.undo()
        self.assertNotIn("crs", sink)

    def test_redo_reapplies(self) -> None:
        sink: dict = {}
        self.stack.run(Reversible(sink, "crs", "EPSG:26912"))
        self.stack.undo()
        self.stack.redo()
        self.assertEqual(sink["crs"], "EPSG:26912")

    def test_a_new_command_clears_the_redo_branch(self) -> None:
        sink: dict = {}
        self.stack.run(Reversible(sink, "a", 1))
        self.stack.undo()
        self.assertTrue(self.stack.canRedo)
        self.stack.run(Reversible(sink, "b", 2))
        self.assertFalse(self.stack.canRedo)

    def test_undo_on_an_empty_stack_is_a_no_op(self) -> None:
        self.stack.undo()
        self.stack.redo()
        self.assertEqual(self.stack.depth, (0, 0))

    def test_the_labels_name_the_command(self) -> None:
        sink: dict = {}
        self.assertEqual(self.stack.undoText, "Nothing to undo")
        self.stack.run(Reversible(sink, "a", 1))
        self.assertEqual(self.stack.undoText, "Undo set value")


class ScienceIsNotUndoable(StackCase):
    def test_an_irreversible_command_is_a_barrier(self) -> None:
        """Undoing past a committed run would misrepresent what the project has."""
        sink: dict = {}
        committed: list = []
        self.stack.run(Reversible(sink, "a", 1))
        self.assertTrue(self.stack.canUndo)

        self.stack.run(Irreversible(committed))

        self.assertFalse(self.stack.canUndo,
                         "nothing before a committed run may be undone")
        self.assertEqual(self.stack.depth, (0, 0))
        self.assertEqual(committed, ["committed"])

    def test_the_barrier_says_why_undo_is_unavailable(self) -> None:
        self.stack.run(Irreversible([]))
        self.assertEqual(self.stack.undoText, "Cannot undo commit run")

    def test_an_irreversible_command_refuses_undo_by_name(self) -> None:
        command = Irreversible([])
        with self.assertRaises(CommandError) as ctx:
            command.undo()
        self.assertIn("immutable", str(ctx.exception))


class Validation(StackCase):
    def test_validate_runs_before_execute(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.stack.run(Refusing())
        self.assertIn("not where the project expects", str(ctx.exception))
        self.assertEqual(self.stack.depth, (0, 0))

    def test_a_refused_command_is_not_logged_as_done(self) -> None:
        with self.assertRaises(CommandError):
            self.stack.run(Refusing())
        self.assertEqual(self.store.commands(), [])


class AuditTrail(StackCase):
    def test_every_direction_reaches_the_command_log(self) -> None:
        sink: dict = {}
        self.stack.run(Reversible(sink, "a", 1))
        self.stack.undo()
        self.stack.redo()
        directions = [c["direction"] for c in self.store.commands()]
        self.assertEqual(directions, ["do", "undo", "redo"])
        self.assertEqual({c["name"] for c in self.store.commands()}, {"set value"})

    def test_the_payload_is_recorded(self) -> None:
        self.stack.run(Reversible({}, "crs", "EPSG:26912"))
        payload = self.store.commands()[0]["payload_json"]
        self.assertIn("EPSG:26912", payload)


class DatasetCommands(StackCase):
    def test_import_refuses_a_missing_file_with_an_actionable_message(self) -> None:
        command = ImportDatasetCommand(self.store, self.tmp / "nope.tif", "raster")
        with self.assertRaises(CommandError) as ctx:
            self.stack.run(command)
        self.assertIn("nope.tif", str(ctx.exception))

    def test_import_refuses_an_unknown_kind(self) -> None:
        source = self.tmp / "a.tif"
        source.write_bytes(b"x")
        with self.assertRaises(CommandError) as ctx:
            self.stack.run(ImportDatasetCommand(self.store, source, "pointcloud"))
        self.assertIn("raster, vector or table", str(ctx.exception))

    def test_import_is_undoable_while_no_run_uses_it(self) -> None:
        source = self.tmp / "a.tif"
        source.write_bytes(b"x")
        self.stack.run(ImportDatasetCommand(self.store, source, "raster"))
        self.assertEqual(len(self.store.datasets()), 1)
        self.stack.undo()
        self.assertEqual(len(self.store.datasets()), 0)
        self.assertTrue(source.exists(), "undo must not delete the user's file")

    def test_import_cannot_be_undone_once_a_run_references_it(self) -> None:
        """A completed run keeps its inputs."""
        source = self.tmp / "a.tif"
        source.write_bytes(b"x")
        command = ImportDatasetCommand(self.store, source, "raster")
        self.stack.run(command)

        job_id = self.store.create_job("op", {}, [str(source)])
        self.store.commit_run(job_id, {
            "operator_version": "1.0.0",
            "inputs": [{"path": str(source.resolve())}],
        })

        with self.assertRaises(CommandError) as ctx:
            command.undo()
        self.assertIn("completed run", str(ctx.exception))
        self.assertEqual(len(self.store.datasets()), 1)

    def test_relink_is_undoable(self) -> None:
        source = self.tmp / "a.bin"
        source.write_bytes(b"content")
        dataset_id = self.store.add_dataset(source, "raster")
        moved = self.tmp / "b.bin"
        moved.write_bytes(b"content")

        command = RelinkDatasetCommand(self.store, dataset_id, moved)
        self.stack.run(command)
        self.assertEqual(self.store.datasets()[0]["path"], str(moved.resolve()))

        self.stack.undo()
        self.assertEqual(self.store.datasets()[0]["path"], str(source.resolve()))

    def test_relink_refuses_a_path_that_does_not_exist(self) -> None:
        source = self.tmp / "a.bin"
        source.write_bytes(b"x")
        dataset_id = self.store.add_dataset(source, "raster")
        with self.assertRaises(CommandError) as ctx:
            self.stack.run(
                RelinkDatasetCommand(self.store, dataset_id, self.tmp / "gone.bin")
            )
        self.assertIn("nothing at", str(ctx.exception))


class RunOperatorValidation(StackCase):
    def test_a_missing_input_is_named_before_anything_is_submitted(self) -> None:
        class Sink:
            submitted = False

            def submit(self, *_args):  # pragma: no cover - must not run
                Sink.submitted = True
                return "job"

        command = RunOperatorCommand(
            Sink(), "decision.membership", {}, [str(self.tmp / "absent.tif")]
        )
        with self.assertRaises(CommandError) as ctx:
            self.stack.run(command)
        self.assertIn("absent.tif", str(ctx.exception))
        self.assertIn("Relink", str(ctx.exception))
        self.assertFalse(Sink.submitted)

    def test_running_an_operator_is_never_undoable(self) -> None:
        self.assertFalse(RunOperatorCommand(None, "op", {}, []).reversible)


class Lineage(StackCase):
    """P-116 — repeating a job creates a **child** run and preserves the parent.

    A run whose parameters and inputs are the same as another's is still a
    different run: it happened at a different time, and the lineage is what
    says which came first. A child that did not record its parent is an
    orphan, and the graph loses the branch entirely.
    """

    def _committed(self, parent: str | None = None) -> str:
        job_id = self.store.create_job("decision.membership", {}, [])
        return self.store.commit_run(
            job_id, {"operator_version": "1.0.0"}, parent_run_id=parent)

    def test_a_child_run_records_its_parent(self) -> None:
        parent = self._committed()
        child = self._committed(parent)
        by_id = {run.id: run for run in self.store.runs()}
        self.assertEqual(by_id[child].parent_run_id, parent)
        self.assertIsNone(by_id[parent].parent_run_id)

    def test_the_parent_survives_the_child(self) -> None:
        parent = self._committed()
        self._committed(parent)
        ids = [run.id for run in self.store.runs()]
        self.assertIn(parent, ids)
        self.assertEqual(len(ids), 2)

    def test_the_command_carries_the_parent_to_the_submission(self) -> None:
        """The seam that was missing: `retry` knew the parent and the job
        never heard about it."""
        seen: dict = {}

        class Sink:
            def submit(self, operator, params, inputs, *, parent_run_id=None):  # noqa: ANN001
                seen["parent"] = parent_run_id
                return "job"

        self.stack.run(RunOperatorCommand(
            Sink(), "decision.membership", {}, [], "run-42"))
        self.assertEqual(seen["parent"], "run-42")

    def test_a_run_that_starts_something_new_has_no_parent(self) -> None:
        """Inventing a parent would be worse than recording none: it would
        put a branch in the lineage that nobody derived."""
        seen: dict = {}

        class Sink:
            def submit(self, operator, params, inputs, *, parent_run_id=None):  # noqa: ANN001
                seen["parent"] = parent_run_id
                return "job"

        self.stack.run(RunOperatorCommand(Sink(), "decision.membership", {}, []))
        self.assertIsNone(seen["parent"])


if __name__ == "__main__":
    unittest.main()
