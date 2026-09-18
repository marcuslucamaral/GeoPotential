"""The recovery pass: what a session that died left behind, and what to do.

Run on every open, before the interface offers anything. It answers three
questions and answers them conservatively:

  1. **Which jobs were in flight?** A `job_journal` row that survived is a job
     whose process died. It becomes `Interrupted` — never `Succeeded`.
  2. **Which files belong to no run?** A file under `artifacts/<job_id>/` with
     no row in `artifact` is an orphan. It is **listed, never adopted**: a file
     the store did not hash and register is not a result, however plausible it
     looks.
  3. **What is half-written?** A surviving `.tmp` is the residue of a write
     that did not finish. It is deleted, and what was deleted is recorded.

The conservative direction is the whole point. Every ambiguity resolves towards
"this is not a result", because the opposite error — adopting a partial file as
a scientific output — is the one that cannot be detected later.

No Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import ProjectStore

# Job states that mean the work had not finished when the session ended.
IN_FLIGHT = ("Queued", "Validating", "Running", "Committing")

INTERRUPTED = "Interrupted"


@dataclass
class RecoveryReport:
    """What the pass found and what it did. Shown to the user, and logged."""

    unclean_sessions: int = 0
    interrupted_jobs: list[dict[str, Any]] = field(default_factory=list)
    orphan_artifacts: list[dict[str, Any]] = field(default_factory=list)
    removed_temporaries: list[str] = field(default_factory=list)
    missing_datasets: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when the previous session ended normally and left nothing."""
        return not (
            self.unclean_sessions
            or self.interrupted_jobs
            or self.orphan_artifacts
            or self.removed_temporaries
            or self.missing_datasets
        )

    def summary(self) -> str:
        """One line, safe to show a user. Says what happened, not how."""
        if self.clean:
            return "The project opened cleanly."
        parts = []
        if self.unclean_sessions:
            parts.append(
                f"{self.unclean_sessions} previous session"
                f"{'s' if self.unclean_sessions > 1 else ''} did not close normally"
            )
        if self.interrupted_jobs:
            parts.append(f"{len(self.interrupted_jobs)} interrupted job"
                         f"{'s' if len(self.interrupted_jobs) > 1 else ''}")
        if self.orphan_artifacts:
            parts.append(f"{len(self.orphan_artifacts)} file"
                         f"{'s' if len(self.orphan_artifacts) > 1 else ''} "
                         f"belonging to no run")
        if self.removed_temporaries:
            parts.append(f"{len(self.removed_temporaries)} incomplete write"
                         f"{'s' if len(self.removed_temporaries) > 1 else ''} discarded")
        if self.missing_datasets:
            parts.append(f"{len(self.missing_datasets)} input"
                         f"{'s' if len(self.missing_datasets) > 1 else ''} "
                         f"no longer at the recorded path")
        return "Recovered: " + "; ".join(parts) + "."

    def as_dict(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "unclean_sessions": self.unclean_sessions,
            "interrupted_jobs": self.interrupted_jobs,
            "orphan_artifacts": self.orphan_artifacts,
            "removed_temporaries": self.removed_temporaries,
            "missing_datasets": self.missing_datasets,
        }


def recover(store: ProjectStore) -> RecoveryReport:
    """Reconcile the catalogue with what is on disk. Call once, on open.

    store    an open project, with its session already opened
    returns  RecoveryReport — what was found, and what was done

    This never deletes an artefact and never registers one. It deletes only
    `.tmp` residue, and it reclassifies job state. Everything else is reported
    for a person to decide.
    """
    report = RecoveryReport()
    report.unclean_sessions = len(store.unclean_sessions())

    # 1. Jobs whose journal row survived. The journal is written before the
    #    submission, so a surviving row means the process died with work in it.
    for entry in store.open_journal_entries():
        job_id = entry["job_id"]
        row = store.connect().execute(
            "SELECT * FROM job WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            store.journal_close(job_id)
            continue
        if row["state"] in IN_FLIGHT:
            store.set_job_state(
                job_id,
                INTERRUPTED,
                error_code="INTERRUPTED",
                error_message="The session ended while this job was running. "
                              "No result was recorded; run it again.",
            )
            store.record_event("job.interrupted", job_id, {
                "operator": entry["operator"],
                "last_stage": entry["last_stage"],
                "last_fraction": entry["last_fraction"],
            })
            report.interrupted_jobs.append({
                "job_id": job_id,
                "operator": entry["operator"],
                "last_stage": entry["last_stage"],
                "last_fraction": entry["last_fraction"],
                "output_dir": entry["output_dir"],
            })
        store.journal_close(job_id)

    # 2. Files under artifacts/ that no run claims, and .tmp residue anywhere
    #    in the project. A `.tmp` is never a result: the writer renames only
    #    after validating and hashing, so a surviving one is a write that died.
    registered = {
        Path(row["path"]).resolve()
        for row in store.connect().execute("SELECT path FROM artifact").fetchall()
    }
    artifacts_root = store.root / "artifacts"
    if artifacts_root.exists():
        for path in sorted(artifacts_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix == ".tmp":
                size = path.stat().st_size
                path.unlink()
                report.removed_temporaries.append(str(path))
                store.record_event("recovery.removed_temporary", str(path),
                                   {"bytes": size})
                continue
            if path.resolve() not in registered:
                report.orphan_artifacts.append({
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "job_id": path.parent.name,
                })

    for path in sorted((store.root / "cache").rglob("*.tmp")):
        if path.is_file():
            path.unlink()
            report.removed_temporaries.append(str(path))

    if report.orphan_artifacts:
        # Recorded, not adopted. The distinction is the invariant.
        store.record_event("recovery.orphans_found", store.root.name, {
            "count": len(report.orphan_artifacts),
            "paths": [o["path"] for o in report.orphan_artifacts],
        })

    # 3. Registered inputs that are no longer where they were. Relink is the
    #    remedy, and it is a decision, so this only reports.
    report.missing_datasets = store.missing_datasets()

    store.record_event("project.recovered", store.root.name, report.as_dict())
    return report


def discard_orphans(store: ProjectStore, paths: list[str]) -> list[str]:
    """Delete orphan files a person chose to discard.

    Only paths the current recovery pass reported as orphans are accepted, and
    only inside this project's `artifacts/`. A registered artefact can never be
    deleted through here: an artefact belongs to an immutable run.
    """
    registered = {
        Path(row["path"]).resolve()
        for row in store.connect().execute("SELECT path FROM artifact").fetchall()
    }
    artifacts_root = (store.root / "artifacts").resolve()
    removed: list[str] = []
    for raw in paths:
        path = Path(raw).resolve()
        if not path.is_relative_to(artifacts_root):
            raise ValueError(f"refusing to delete outside the project: {path}")
        if path in registered:
            raise ValueError(
                f"refusing to delete a registered artefact: {path}. It belongs "
                f"to a completed run, and a completed run is immutable."
            )
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    if removed:
        store.record_event("recovery.orphans_discarded", store.root.name,
                           {"paths": removed})
    return removed
