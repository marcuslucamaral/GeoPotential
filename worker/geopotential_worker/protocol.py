"""IPC protocol, version 1.

JSON Lines over stdin/stdout. One message per line, UTF-8, no HTTP.
Schemas: `schemas/ipc/v1/`. Changing a message obliges the seven steps of
IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 29.

This module is imported by both sides of the boundary, and is the only thing
that is. It must stay free of numpy, rasterio and Qt.
"""
from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = "1.0.0"

# Message kinds. app -> worker
SUBMIT_JOB = "submit_job"
CANCEL_JOB = "cancel_job"
SHUTDOWN = "shutdown"

# worker -> app
HELLO = "hello"
JOB_PROGRESS = "job_progress"
JOB_ARTIFACT = "job_artifact"
JOB_SUCCEEDED = "job_succeeded"
JOB_FAILED = "job_failed"
GOODBYE = "goodbye"

APP_TO_WORKER = frozenset({SUBMIT_JOB, CANCEL_JOB, SHUTDOWN})
WORKER_TO_APP = frozenset(
    {HELLO, JOB_PROGRESS, JOB_ARTIFACT, JOB_SUCCEEDED, JOB_FAILED, GOODBYE}
)

# Required fields per message kind. A message missing one is a protocol error,
# not a warning: the sender and the receiver disagree about the contract.
REQUIRED: dict[str, tuple[str, ...]] = {
    HELLO: ("protocol", "app", "worker", "capabilities"),
    SUBMIT_JOB: ("job_id", "operator", "params", "inputs", "output_dir"),
    JOB_PROGRESS: ("job_id", "stage", "fraction", "message"),
    # Section 12.3 names the artefact's format field `type`. The envelope
    # already owns `type` as the message kind, so the artefact's is
    # `artifact_type` here. Recorded rather than silently reconciled:
    # `schemas/ipc/v1/job_artifact.json` states the deviation.
    JOB_ARTIFACT: ("job_id", "artifact_id", "path", "artifact_type", "hash"),
    JOB_SUCCEEDED: ("job_id", "manifest"),
    JOB_FAILED: ("job_id", "code", "safe_message", "detail_ref"),
    CANCEL_JOB: ("job_id", "reason"),
    SHUTDOWN: ("deadline",),
    GOODBYE: ("reason",),
}

# Job states. IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 13.
QUEUED = "Queued"
VALIDATING = "Validating"
RUNNING = "Running"
COMMITTING = "Committing"
SUCCEEDED = "Succeeded"
CANCELLED = "Cancelled"
FAILED = "Failed"

TERMINAL_STATES = frozenset({SUCCEEDED, CANCELLED, FAILED})

# Only these transitions are legal. `Succeeded` is reachable only from
# `Committing`, so a partial output can never be published as a result.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({VALIDATING, CANCELLED, FAILED}),
    VALIDATING: frozenset({RUNNING, CANCELLED, FAILED}),
    RUNNING: frozenset({COMMITTING, CANCELLED, FAILED}),
    COMMITTING: frozenset({SUCCEEDED, FAILED}),
    SUCCEEDED: frozenset(),
    CANCELLED: frozenset(),
    FAILED: frozenset(),
}


class ProtocolError(ValueError):
    """A message violated the contract. Never recovered from silently."""


def message(kind: str, **fields: Any) -> dict[str, Any]:
    """Build a protocol message and check it against REQUIRED.

    kind      one of the module-level message constants
    fields    the message body
    returns   the message dict, with `type` and `protocol` set
    raises    ProtocolError when a required field is absent
    """
    if kind not in REQUIRED:
        raise ProtocolError(f"unknown message kind {kind!r}")
    missing = [f for f in REQUIRED[kind] if f not in fields]
    if missing:
        raise ProtocolError(
            f"message {kind!r} is missing required field(s): {', '.join(missing)}"
        )
    # The envelope keys go last so a body field can never shadow the message
    # kind. `type` shadowed by an artefact's format is exactly how the first
    # `job_artifact` of this project went out labelled "GeoTIFF".
    return {**fields, "type": kind, "protocol": PROTOCOL_VERSION}


def encode(msg: dict[str, Any]) -> str:
    """One message, one line. `separators` keeps the line free of newlines."""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))


def decode(line: str) -> dict[str, Any]:
    """Parse one line into a message and validate its required fields.

    line      a single JSON Lines record
    returns   the message dict
    raises    ProtocolError on malformed JSON, missing `type`, or a missing
              required field
    """
    line = line.strip()
    if not line:
        raise ProtocolError("empty line is not a message")
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"malformed JSON: {exc}") from exc
    if not isinstance(msg, dict):
        raise ProtocolError(f"message must be an object, got {type(msg).__name__}")
    kind = msg.get("type")
    if kind not in REQUIRED:
        raise ProtocolError(f"unknown message kind {kind!r}")
    missing = [f for f in REQUIRED[kind] if f not in msg]
    if missing:
        raise ProtocolError(
            f"message {kind!r} is missing required field(s): {', '.join(missing)}"
        )
    return msg


def compatible(their_version: str) -> bool:
    """Whether a peer's protocol version can be talked to.

    their_version   the `protocol` field of their `hello`
    returns         True when the MAJOR components agree

    A mismatch blocks execution. Section 12.3: incompatibility is a refusal,
    never a degraded mode.
    """
    try:
        return their_version.split(".")[0] == PROTOCOL_VERSION.split(".")[0]
    except AttributeError:
        return False
