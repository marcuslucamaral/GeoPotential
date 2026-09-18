"""Level 2 — the IPC contract.

Both sides of the boundary are checked against the same module, and the two
copies of that module are checked against each other. A protocol that only
works when both halves came from the same build is not a protocol.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from geopotential_app.ipc import protocol as APP
from geopotential_worker import protocol as WORKER

ROOT = Path(__file__).resolve().parents[2]


class Mirror(unittest.TestCase):
    def test_the_two_copies_are_identical(self) -> None:
        """One contract, mirrored. The architecture gate enforces this too."""
        app_bytes = (ROOT / "app/geopotential_app/ipc/protocol.py").read_bytes()
        worker_bytes = (ROOT / "worker/geopotential_worker/protocol.py").read_bytes()
        self.assertEqual(app_bytes, worker_bytes,
                         "app and worker protocol modules have drifted")

    def test_both_agree_on_the_version(self) -> None:
        self.assertEqual(APP.PROTOCOL_VERSION, WORKER.PROTOCOL_VERSION)


class Encoding(unittest.TestCase):
    def test_a_message_is_exactly_one_line(self) -> None:
        """JSON Lines: a newline inside a message desynchronizes the stream."""
        msg = APP.message(
            APP.JOB_PROGRESS, job_id="J", stage="read",
            fraction=0.5, message="a\nb\nc with a newline",
        )
        self.assertEqual(APP.encode(msg).count("\n"), 0)

    def test_round_trip(self) -> None:
        original = APP.message(
            APP.SUBMIT_JOB, job_id="J1", operator="decision.membership",
            params={"function": "linear_increasing"}, inputs=["a.tif"],
            output_dir="/tmp/out",
        )
        self.assertEqual(APP.decode(APP.encode(original)), original)

    def test_non_ascii_survives(self) -> None:
        msg = APP.message(APP.JOB_FAILED, job_id="J", code="E",
                          safe_message="não foi possível ler o CRS", detail_ref="r")
        self.assertIn("não", APP.decode(APP.encode(msg))["safe_message"])

    def test_the_envelope_is_never_shadowed(self) -> None:
        """An artefact's `artifact_type` must not be able to overwrite `type`.

        The first job_artifact this project emitted went out labelled
        "GeoTIFF" instead of "job_artifact", because the body carried a `type`.
        """
        msg = APP.message(
            APP.JOB_ARTIFACT, job_id="J", artifact_id="a", path="/tmp/a.tif",
            artifact_type="GeoTIFF", hash="sha256:0",
        )
        self.assertEqual(msg["type"], APP.JOB_ARTIFACT)
        self.assertEqual(msg["artifact_type"], "GeoTIFF")


class Validation(unittest.TestCase):
    def test_a_missing_required_field_is_refused_on_build(self) -> None:
        with self.assertRaises(APP.ProtocolError) as ctx:
            APP.message(APP.SUBMIT_JOB, job_id="J1", operator="op")
        for field in ("params", "inputs", "output_dir"):
            self.assertIn(field, str(ctx.exception))

    def test_a_missing_required_field_is_refused_on_decode(self) -> None:
        line = json.dumps({"type": "job_progress", "job_id": "J"})
        with self.assertRaises(APP.ProtocolError):
            APP.decode(line)

    def test_malformed_json_is_refused(self) -> None:
        for line in ("{not json", "", "   ", "[1,2,3]", "null"):
            with self.assertRaises(APP.ProtocolError):
                APP.decode(line)

    def test_unknown_kind_is_refused(self) -> None:
        with self.assertRaises(APP.ProtocolError):
            APP.decode(json.dumps({"type": "compute_everything"}))
        with self.assertRaises(APP.ProtocolError):
            APP.message("compute_everything")

    def test_message_directions_are_disjoint(self) -> None:
        self.assertFalse(APP.APP_TO_WORKER & APP.WORKER_TO_APP)


class VersionCompatibility(unittest.TestCase):
    def test_same_major_is_compatible(self) -> None:
        major = APP.PROTOCOL_VERSION.split(".")[0]
        self.assertTrue(APP.compatible(f"{major}.99.99"))

    def test_different_major_is_refused(self) -> None:
        """Section 12.3: incompatibility blocks; it never degrades."""
        self.assertFalse(APP.compatible("99.0.0"))
        self.assertFalse(APP.compatible("0.9.0"))

    def test_nonsense_version_is_refused(self) -> None:
        for value in (None, 1.0, [], {}):
            self.assertFalse(APP.compatible(value))


class JobStateMachine(unittest.TestCase):
    """Section 13. The illegal transitions are what the test is for."""

    def test_succeeded_is_reachable_only_from_committing(self) -> None:
        for state in (APP.QUEUED, APP.VALIDATING, APP.RUNNING):
            self.assertNotIn(APP.SUCCEEDED, APP.LEGAL_TRANSITIONS[state],
                             f"{state} must not reach Succeeded directly; a "
                             f"partial output would become a result")
        self.assertIn(APP.SUCCEEDED, APP.LEGAL_TRANSITIONS[APP.COMMITTING])

    def test_terminal_states_go_nowhere(self) -> None:
        for state in APP.TERMINAL_STATES:
            self.assertEqual(APP.LEGAL_TRANSITIONS[state], frozenset())

    def test_committing_cannot_be_cancelled(self) -> None:
        """Cancelling mid-commit would leave a half-written artefact."""
        self.assertNotIn(APP.CANCELLED, APP.LEGAL_TRANSITIONS[APP.COMMITTING])

    def test_every_running_state_can_fail(self) -> None:
        for state in (APP.QUEUED, APP.VALIDATING, APP.RUNNING, APP.COMMITTING):
            self.assertIn(APP.FAILED, APP.LEGAL_TRANSITIONS[state])


if __name__ == "__main__":
    unittest.main()
