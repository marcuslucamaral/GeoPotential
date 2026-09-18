"""JobController — submits jobs and turns worker events into recorded state.

This is the only place that writes a job's outcome to the Project Store, and it
writes in the order the contract requires: an artefact is registered against a
run, and a run is committed only once `job_succeeded` has arrived. Nothing
partial is ever recorded.

Section 13: a job in flight has its artefacts held here, not written to the
database, until the run commits. A crash between the last artefact and the
commit therefore leaves no half-run in the catalogue — the files are on disk in
`artifacts/<job_id>/` and the recovery pass (M2) can see they belong to no run.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from ..models.job_model import JobListModel
from ..project.store import ProjectStore
from ..utils.qtcore import QObject, Signal
from .worker_supervisor import WorkerSupervisor


class JobController(QObject):
    """Owns the job lifecycle from submission to committed run."""

    runCommitted = Signal(str, str)   # job_id, run_id
    jobFinished = Signal(str, str)    # job_id, final state
    artifactReady = Signal(str, str)  # job_id, path
    probeCompleted = Signal(str, dict)  # job_id, manifest of a read-only probe

    def __init__(
        self,
        supervisor: WorkerSupervisor,
        store: ProjectStore,
        model: JobListModel,
        logs=None,  # noqa: ANN001 - ProjectLogs; optional so the store stays testable
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._supervisor = supervisor
        self._store = store
        self._model = model
        self._logs = logs
        self._pending_artifacts: dict[str, list[dict[str, Any]]] = {}
        # The run each job derives from, kept only until its own run is
        # committed. Empty for every job that starts something new.
        self._parent_runs: dict[str, str] = {}
        self._started_at: dict[str, float] = {}

        supervisor.progressReceived.connect(self._on_progress)
        supervisor.artifactReceived.connect(self._on_artifact)
        supervisor.jobSucceeded.connect(self._on_succeeded)
        supervisor.jobFailed.connect(self._on_failed)
        supervisor.stateChanged.connect(self._on_worker_state)

    # ---- submitting -----------------------------------------------------

    def submit(self, operator: str, params: dict[str, Any], inputs: list[str],
               *, parent_run_id: str | None = None) -> str:
        """Validate what can be validated here, record the job, and send it.

        parent_run_id  the run this one derives from, when there is one. It
                       is carried to the commit so the child run records its
                       parent: repeating a job must produce a **child**, and a
                       child with no parent recorded is an orphan with a
                       docstring claiming otherwise (P-116).

        returns  the job id
        raises   RuntimeError when the worker cannot run the operator

        Refusing an operator the worker did not announce is not defensive
        clutter: it turns a mismatched pair of builds into one clear message
        instead of a failure inside the worker three stages later.
        """
        if self._supervisor.state != WorkerSupervisor.READY:
            raise RuntimeError(
                f"the worker is {self._supervisor.state}; no job can be submitted"
            )
        if operator not in self._supervisor.capabilities:
            planned = self._supervisor.planned.get(operator)
            hint = f" It is planned for milestone {planned}." if planned else ""
            raise RuntimeError(
                f"the worker does not provide {operator!r}.{hint} "
                f"Available: {', '.join(self._supervisor.capabilities)}"
            )

        job_id = uuid.uuid4().hex
        output_dir = self._store.artifact_dir(job_id)
        self._store.create_job(operator, params, inputs, job_id=job_id)
        self._model.add(job_id, operator, inputs=inputs, params=params)
        self._pending_artifacts[job_id] = []
        self._started_at[job_id] = time.monotonic()
        if parent_run_id:
            self._parent_runs[job_id] = parent_run_id

        # Write-ahead. The journal row goes down BEFORE the submission, so a
        # process killed between the two leaves a record that the job existed
        # and names the directory whose contents are then orphans. Written
        # after, that window would produce a running job with no trace.
        self._store.journal_open(job_id, operator, output_dir)
        self._store.set_job_state(job_id, "Validating")
        if self._logs is not None:
            self._logs.application(
                "info", f"submitted {operator}",
                job_id=job_id, operator=operator, inputs=inputs, params=params,
            )
        self._supervisor.submit(job_id, operator, params, inputs, output_dir)
        return job_id

    def cancel(self, job_id: str) -> None:
        self._supervisor.cancel(job_id)
        if self._logs is not None:
            self._logs.application("info", "cancel requested", job_id=job_id)

    # ---- receiving ------------------------------------------------------

    def _on_progress(self, msg: dict[str, Any]) -> None:
        self._model.update_progress(
            msg["job_id"], msg["stage"], float(msg["fraction"]), msg["message"]
        )
        self._store.set_job_state(msg["job_id"], "Running")
        # Autosave, and nothing more. This records what was in flight; it never
        # records what was produced.
        self._store.journal_progress(
            msg["job_id"], msg["stage"], float(msg["fraction"])
        )

    def _on_artifact(self, msg: dict[str, Any]) -> None:
        # Held, not written. The run does not exist yet, and an artefact row
        # without a run is exactly the orphan the schema's foreign key forbids.
        self._pending_artifacts.setdefault(msg["job_id"], []).append(msg)
        self._model.add_artifact(msg["job_id"], msg)
        self.artifactReady.emit(msg["job_id"], msg["path"])

    def _on_succeeded(self, msg: dict[str, Any]) -> None:
        job_id = msg["job_id"]
        manifest = msg["manifest"]

        # A read-only probe answers a question about a dataset, usually before
        # that dataset is in the project at all. Committing a run for it would
        # make describing a form of importing, which section 9.2 forbids — and
        # would put a run in the lineage that computed nothing.
        if manifest.get("read_only"):
            self._record_probe(job_id, manifest)
            return

        run_id = self._store.commit_run(
            job_id, manifest,
            parent_run_id=self._parent_runs.pop(job_id, None),
        )
        for artifact in self._pending_artifacts.pop(job_id, []):
            self._store.register_artifact(
                run_id,
                artifact["artifact_id"],
                artifact["path"],
                artifact["artifact_type"],
                artifact["hash"],
                int(artifact.get("bytes", 0)),
            )
        self._store.set_job_state(job_id, "Succeeded")
        # The journal closes only after the run and its artefacts are recorded.
        # Closing it earlier would open a window in which a crash left a
        # committed run that recovery believed had never started.
        self._store.journal_close(job_id)
        self._model.set_state(job_id, "Succeeded", message="run committed")

        if self._logs is not None:
            self._logs.scientific(
                f"run committed: {manifest.get('operator')}",
                job_id=job_id,
                run_id=run_id,
                operator=manifest.get("operator"),
                operator_version=manifest.get("operator_version"),
                duration_s=self._duration(job_id),
                grid=manifest.get("grid"),
                criterion=manifest.get("criterion"),
                anchors=manifest.get("anchors"),
                artifacts=[a.get("hash") for a in manifest.get("artifacts", [])],
                reference=manifest.get("reference"),
            )
        self.runCommitted.emit(job_id, run_id)
        self.jobFinished.emit(job_id, "Succeeded")

    def _on_failed(self, msg: dict[str, Any]) -> None:
        job_id = msg["job_id"]
        state = "Cancelled" if msg["code"] == "CANCELLED" else "Failed"
        # A failed or cancelled job registers nothing. The files its operator
        # may have written stay on disk unreferenced, for the recovery pass.
        self._pending_artifacts.pop(job_id, None)
        self._store.set_job_state(
            job_id,
            state,
            error_code=msg["code"],
            error_message=msg["safe_message"],
            detail_ref=msg["detail_ref"],
        )
        self._store.journal_close(job_id)
        self._model.set_state(
            job_id,
            state,
            message=msg["safe_message"],
            error_code=msg["code"],
            detail_ref=msg["detail_ref"],
        )
        if self._logs is not None:
            self._logs.application(
                "warning" if state == "Cancelled" else "error",
                msg["safe_message"],
                job_id=job_id, error=msg["code"], detail_ref=msg["detail_ref"],
                duration_s=self._duration(job_id),
            )
        self.jobFinished.emit(job_id, state)

    def _record_probe(self, job_id: str, manifest: dict[str, Any]) -> None:
        """Record a read-only probe's answer: a ValidationResult, not a run.

        The verdict is kept whatever it says. A dataset that was refused is
        precisely the one someone asks about later, and "we checked and said
        no, for these reasons" has to survive the refusal — that is gate M3 G5.
        """
        report = manifest.get("report")
        inputs = json.loads(
            self._store.connect().execute(
                "SELECT inputs_json FROM job WHERE id=?", (job_id,)
            ).fetchone()["inputs_json"]
        )
        dataset_path = inputs[0] if inputs else ""

        if report is not None:
            self._store.record_validation(
                dataset_path,
                manifest.get("operator", ""),
                manifest.get("operator_version", ""),
                report,
                declared=manifest.get("declared") or {},
                plan=manifest.get("plan"),
            )

        self._store.set_job_state(job_id, "Succeeded")
        self._store.journal_close(job_id)
        summary = (
            report.get("summary") if report else
            f"described {Path(dataset_path).name}"
        )
        self._model.set_state(job_id, "Succeeded", message=summary)

        if self._logs is not None:
            self._logs.scientific(
                summary,
                job_id=job_id,
                operator=manifest.get("operator"),
                operator_version=manifest.get("operator_version"),
                dataset=dataset_path,
                duration_s=self._duration(job_id),
                usable=None if report is None else report.get("usable"),
                severity=None if report is None else report.get("severity"),
                declared=manifest.get("declared") or {},
            )
        self.probeCompleted.emit(job_id, manifest)
        self.jobFinished.emit(job_id, "Succeeded")

    def _on_worker_state(self, state: str) -> None:
        """A worker that dies takes every job in flight with it.

        Without this, a killed worker leaves jobs sitting at `Running` for the
        rest of the session and the interface keeps showing a progress bar for
        work nobody is doing. Recovery would eventually reclassify them on the
        next open — but the user is still in this one.
        """
        if state != WorkerSupervisor.CRASHED:
            return
        for job_id in list(self._pending_artifacts):
            self._pending_artifacts.pop(job_id, None)
            self._store.set_job_state(
                job_id,
                "Interrupted",
                error_code="WORKER_LOST",
                error_message="The scientific worker stopped while this job was "
                              "running. No result was recorded; run it again.",
            )
            self._store.journal_close(job_id)
            self._model.set_state(
                job_id, "Interrupted",
                message="worker stopped; nothing was recorded",
                error_code="WORKER_LOST",
            )
            self.jobFinished.emit(job_id, "Interrupted")
        if self._logs is not None:
            self._logs.crash("the scientific worker exited unexpectedly")

    def _duration(self, job_id: str) -> float | None:
        """How long the job took, and it also reaches the panel.

        The panel shows elapsed time per job because "it is taking long" and
        "it is stuck" are different states, and only a number tells them apart.
        """
        started = self._started_at.pop(job_id, None)
        if started is None:
            return None
        seconds = round(time.monotonic() - started, 3)
        self._model.set_elapsed(job_id, seconds)
        return seconds
