"""The commands M2 implements.

Section 7.4 names nine. These are the ones whose domain exists at M2; the rest
are named in `PLANNED` with the milestone that brings the domain they act on,
so the interface can disable them with a reason instead of failing after a
click.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..project.recovery import discard_orphans
from .base import Command, CommandError


class RunOperatorCommand(Command):
    """Submit a job to the scientific worker.

    Irreversible: it can commit a run, and a completed run is immutable.
    Undoing it would either delete a scientific record on a UI gesture or lie
    about what the project contains. Both are worse than a disabled button.
    """

    name = "run operator"
    reversible = False

    def __init__(self, job_controller, operator: str, params: dict[str, Any],
                 inputs: list[str],
                 parent_run_id: str | None = None) -> None:  # noqa: ANN001
        super().__init__()
        self._jobs = job_controller
        self._operator = operator
        self._params = dict(params)
        self._inputs = [str(p) for p in inputs]
        # The run this one derives from, when there is one. Repeating a job
        # produces a child of the run it repeats (P-116); starting something
        # new produces a root, and there is no parent to invent.
        self._parent_run_id = parent_run_id
        self._payload = {"operator": operator, "params": self._params,
                         "inputs": self._inputs,
                         "parent_run_id": parent_run_id}

    def validate(self) -> None:
        missing = [p for p in self._inputs if not Path(p).exists()]
        if missing:
            raise CommandError(
                "These inputs are not where the project expects them: "
                + ", ".join(Path(p).name for p in missing)
                + ". Relink them, or choose different files."
            )

    def execute(self) -> str:
        return self._jobs.submit(self._operator, self._params, self._inputs,
                                 parent_run_id=self._parent_run_id)

    def describe(self) -> str:
        return f"run {self._operator}"


class CancelJobCommand(Command):
    """Ask the worker to stop a job. Nothing partial is recorded.

    Irreversible in the stack's sense: "un-cancelling" is running it again,
    which is a different command with a different job id.
    """

    name = "cancel job"
    reversible = False

    def __init__(self, job_controller, job_id: str) -> None:  # noqa: ANN001
        super().__init__()
        self._jobs = job_controller
        self._job_id = job_id
        self._payload = {"job_id": job_id}

    def execute(self) -> None:
        self._jobs.cancel(self._job_id)

    def describe(self) -> str:
        return f"cancel job {self._job_id[:8]}"


class ImportDatasetCommand(Command):
    """Register an external input, with its size, timestamp and hash.

    Reversible: removing the catalogue row does not touch the file, and no run
    can reference it yet. Once a run does, the run holds the path in its
    manifest and the row is no longer what makes the input findable.
    """

    name = "import dataset"
    reversible = True

    def __init__(self, store, path: Path, kind: str, **metadata: Any) -> None:  # noqa: ANN001
        super().__init__()
        self._store = store
        self._path = Path(path)
        self._kind = kind
        self._metadata = metadata
        self._dataset_id: str | None = None
        self._payload = {"path": str(self._path), "kind": kind, **metadata}

    def validate(self) -> None:
        if not self._path.exists():
            raise CommandError(
                f"{self._path.name} is not at {self._path.parent}. "
                f"Check the path, or copy the file into the project first."
            )
        if self._kind not in ("raster", "vector", "table"):
            raise CommandError(
                f"kind must be raster, vector or table; got {self._kind!r}"
            )

    def execute(self) -> str:
        self._dataset_id = self._store.add_dataset(
            self._path, self._kind, **self._metadata
        )
        self._payload["dataset_id"] = self._dataset_id
        return self._dataset_id

    def undo(self) -> None:
        if self._dataset_id is None:
            return
        used = self._store.connect().execute(
            "SELECT COUNT(*) FROM run WHERE manifest_json LIKE ?",
            (f"%{self._path.resolve()}%",),
        ).fetchone()[0]
        if used:
            raise CommandError(
                f"{self._path.name} is referenced by {used} completed run"
                f"{'s' if used > 1 else ''} and cannot be removed from the "
                f"catalogue. A completed run keeps its inputs."
            )
        conn = self._store.connect()
        conn.execute("DELETE FROM dataset WHERE id=?", (self._dataset_id,))
        conn.commit()
        self._store.record_event("dataset.removed", str(self._path),
                                 {"dataset_id": self._dataset_id})

    def describe(self) -> str:
        return f"import {self._path.name}"


class RelinkDatasetCommand(Command):
    """Point a registered input at a file that moved.

    Reversible: the previous path is kept in `relinked_from`, so undo puts it
    back. Whether the hash still matches is reported, not enforced — a file
    that moved *and* changed is a legitimate deliberate act and an
    illegitimate accident, and only the operator can tell which.
    """

    name = "relink dataset"
    reversible = True

    def __init__(self, store, dataset_id: str, new_path: Path) -> None:  # noqa: ANN001
        super().__init__()
        self._store = store
        self._dataset_id = dataset_id
        self._new_path = Path(new_path)
        self._old_path: str | None = None
        self._payload = {"dataset_id": dataset_id, "new_path": str(new_path)}
        self.result: dict[str, Any] = {}

    def validate(self) -> None:
        if not self._new_path.exists():
            raise CommandError(
                f"There is nothing at {self._new_path}. Choose the file's new "
                f"location."
            )

    def execute(self) -> dict[str, Any]:
        self.result = self._store.relink_dataset(self._dataset_id, self._new_path)
        self._old_path = self.result["old_path"]
        self._payload |= self.result
        return self.result

    def undo(self) -> None:
        if self._old_path is None:
            return
        if not Path(self._old_path).exists():
            raise CommandError(
                f"The previous location {self._old_path} no longer exists, so "
                f"the relink cannot be undone. Relink again if it was wrong."
            )
        self._store.relink_dataset(self._dataset_id, Path(self._old_path))

    def describe(self) -> str:
        return f"relink to {self._new_path.name}"


class DiscardOrphansCommand(Command):
    """Delete files the recovery pass found that belong to no run.

    Irreversible: the files are gone. It refuses to touch anything registered
    against a run, and anything outside the project's `artifacts/`.
    """

    name = "discard orphan files"
    reversible = False

    def __init__(self, store, paths: list[str]) -> None:  # noqa: ANN001
        super().__init__()
        self._store = store
        self._paths = list(paths)
        self._payload = {"paths": self._paths}

    def validate(self) -> None:
        if not self._paths:
            raise CommandError("No files were selected to discard.")

    def execute(self) -> list[str]:
        try:
            return discard_orphans(self._store, self._paths)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def describe(self) -> str:
        return f"discard {len(self._paths)} orphan file" + (
            "s" if len(self._paths) != 1 else ""
        )


#: Commands section 7.4 names whose domain does not exist yet, with the
#: milestone that brings it. The interface shows these disabled and says which.
PLANNED_COMMANDS: dict[str, str] = {
    "CreateScenarioCommand": "M6",
    "CloneScenarioCommand": "M6",
    "ExportRunCommand": "M6",
    "GenerateReportCommand": "M8",
}
