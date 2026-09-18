"""The scientific worker's message loop.

Runs as a child process of the GUI, never inside it (section 11). stdin carries
app -> worker messages, stdout carries worker -> app messages, stderr carries
the worker log. Nothing else is written to stdout, ever: one stray print and
the protocol desynchronizes.

Cancellation is cooperative and real. A reader thread drains stdin into a queue
so that a `cancel_job` arriving while a job is running is seen; the operator
calls `check_cancel` between stages and inside its loops.
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from . import protocol as P
from ._version import VERSION
from .operators import registry
from .operators.base import Cancelled, Context, ParameterError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JobState:
    """The state machine of section 13, with the illegal transitions refused."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.state = P.QUEUED
        self.history: list[tuple[str, str]] = [(_now(), P.QUEUED)]

    def to(self, state: str) -> None:
        if state not in P.LEGAL_TRANSITIONS[self.state]:
            raise RuntimeError(
                f"job {self.job_id}: illegal transition {self.state} -> {state}"
            )
        self.state = state
        self.history.append((_now(), state))


class Worker:
    """One worker process. Owns stdout and the cancellation flags."""

    def __init__(
        self,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self._in = stdin or sys.stdin
        self._out = stdout or sys.stdout
        self._log = stderr or sys.stderr
        self._inbox: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._cancelled: set[str] = set()
        self._current: str | None = None
        self._running = True

    # ---- transport ------------------------------------------------------

    def send(self, msg: dict[str, Any]) -> None:
        self._out.write(P.encode(msg) + "\n")
        self._out.flush()

    def log(self, level: str, text: str, **fields: Any) -> str:
        """Write one structured line to stderr and return its reference id.

        The reference is what a `job_failed` carries as `detail_ref`: the UI
        gets a safe message, the log keeps the traceback.
        """
        ref = uuid.uuid4().hex[:12]
        record = {"ts": _now(), "level": level, "ref": ref, "msg": text, **fields}
        self._log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._log.flush()
        return ref

    def _reader(self) -> None:
        for line in self._in:
            if not line.strip():
                continue
            try:
                msg = P.decode(line)
            except P.ProtocolError as exc:
                ref = self.log("error", f"protocol error: {exc}", line=line[:400])
                self.send(
                    P.message(
                        P.JOB_FAILED,
                        job_id="",
                        code="PROTOCOL_ERROR",
                        safe_message="The application sent a message this worker "
                        "could not read. The run was not started.",
                        detail_ref=ref,
                    )
                )
                continue
            # A cancel is acted on the moment it arrives, not when the queue
            # reaches it: the job it targets may be running right now.
            if msg["type"] == P.CANCEL_JOB:
                self._cancelled.add(msg["job_id"])
                self.log("info", "cancel requested", job_id=msg["job_id"],
                         reason=msg.get("reason", ""))
                continue
            self._inbox.put(msg)
        self._inbox.put(None)  # stdin closed: the parent is gone

    # ---- job execution --------------------------------------------------

    def _check_cancel(self) -> None:
        if self._current and self._current in self._cancelled:
            raise Cancelled(self._current)

    def _run_job(self, msg: dict[str, Any]) -> None:
        job_id = msg["job_id"]
        state = JobState(job_id)
        self._current = job_id

        def progress(stage: str, fraction: float, text: str) -> None:
            self.send(
                P.message(
                    P.JOB_PROGRESS,
                    job_id=job_id,
                    stage=stage,
                    fraction=max(0.0, min(1.0, float(fraction))),
                    message=text,
                )
            )

        try:
            state.to(P.VALIDATING)
            operator = registry.get(msg["operator"])
            params = operator.validate(dict(msg["params"]))
            inputs = list(msg["inputs"])
            for path in inputs:
                if not Path(path).exists():
                    raise FileNotFoundError(f"input not found: {path}")
            output_dir = Path(msg["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            self._check_cancel()

            state.to(P.RUNNING)
            ctx = Context(
                output_dir=output_dir,
                progress=progress,
                check_cancel=self._check_cancel,
            )
            body = operator.run(inputs, params, ctx)
            self._check_cancel()

            # Committing. Artefacts are already closed, validated and hashed by
            # the writer; this is where they become part of the record. Nothing
            # is announced before this point.
            state.to(P.COMMITTING)
            for artifact_id, artifact in ctx.artifacts:
                self.send(
                    P.message(
                        P.JOB_ARTIFACT,
                        job_id=job_id,
                        **artifact.as_message_fields(artifact_id),
                    )
                )

            state.to(P.SUCCEEDED)
            self.send(
                P.message(
                    P.JOB_SUCCEEDED,
                    job_id=job_id,
                    manifest={
                        "job_id": job_id,
                        "worker_version": VERSION,
                        "protocol": P.PROTOCOL_VERSION,
                        "read_only": operator.read_only,
                        "states": [{"at": t, "state": s} for t, s in state.history],
                        "artifacts": [
                            a.as_message_fields(i) for i, a in ctx.artifacts
                        ],
                        **body,
                    },
                )
            )

        except Cancelled:
            state.to(P.CANCELLED)
            self.log("info", "job cancelled", job_id=job_id)
            self.send(
                P.message(
                    P.JOB_FAILED,
                    job_id=job_id,
                    code="CANCELLED",
                    safe_message="The run was cancelled. No result was recorded.",
                    detail_ref="",
                )
            )
        except (ParameterError, KeyError, FileNotFoundError, ValueError, TypeError) as exc:
            ref = self.log(
                "error",
                str(exc),
                job_id=job_id,
                operator=msg.get("operator"),
                traceback=traceback.format_exc(),
            )
            state.to(P.FAILED)
            self.send(
                P.message(
                    P.JOB_FAILED,
                    job_id=job_id,
                    code=type(exc).__name__,
                    safe_message=str(exc),
                    detail_ref=ref,
                )
            )
        except Exception as exc:  # noqa: BLE001 - the boundary; nothing escapes
            ref = self.log(
                "error",
                f"unhandled: {exc}",
                job_id=job_id,
                traceback=traceback.format_exc(),
            )
            state.to(P.FAILED)
            self.send(
                P.message(
                    P.JOB_FAILED,
                    job_id=job_id,
                    code="INTERNAL_ERROR",
                    safe_message="The run failed inside the worker. The technical "
                    "detail is in the worker log.",
                    detail_ref=ref,
                )
            )
        finally:
            self._current = None
            self._cancelled.discard(job_id)

    # ---- lifecycle ------------------------------------------------------

    def serve(self) -> int:
        """Announce, then serve until stdin closes or `shutdown` arrives."""
        reader = threading.Thread(target=self._reader, name="ipc-reader", daemon=True)
        reader.start()

        self.send(
            P.message(
                P.HELLO,
                protocol=P.PROTOCOL_VERSION,
                app="GeoPotential Professional",
                worker=f"geopotential_worker {VERSION}",
                capabilities=registry.capabilities(),
                planned=registry.PLANNED,
                pid=__import__("os").getpid(),
            )
        )
        self.log("info", "worker ready", capabilities=registry.capabilities())

        while self._running:
            msg = self._inbox.get()
            if msg is None:
                self.log("info", "stdin closed; shutting down")
                break
            kind = msg["type"]
            if kind == P.SUBMIT_JOB:
                self._run_job(msg)
            elif kind == P.SHUTDOWN:
                self.log("info", "shutdown requested", deadline=msg["deadline"])
                self.send(P.message(P.GOODBYE, reason="shutdown requested"))
                self._running = False
            else:
                self.log("warning", f"ignoring {kind!r} from the app")
        return 0
