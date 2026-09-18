"""The workflow's state is derived, never written.

P-103 — the state of every step comes from facts the Project Store holds.
P-104 — a blocked step names what is missing and executes nothing.

`derive` is a pure function, so these run without Qt, without a window and
without a worker. The second half of P-103 — that the controller's snapshot
matches what the store really contains — is checked in the interface gate,
where there is a real store to read.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from geopotential_app.viewmodels.workflow_model import (  # noqa: E402
    AVAILABLE,
    BLOCKED,
    DONE,
    RUNNING,
    ATTENTION,
    Facts,
    derive,
)

RASTER = "/data/utah_forge/Distance_to_fault.tif"


def states(facts: Facts) -> dict[str, str]:
    return {step.key: step.state for step in derive(facts)}


def reasons(facts: Facts) -> dict[str, str]:
    return {step.key: step.reason_key for step in derive(facts)}


class ClosedProject(unittest.TestCase):
    def test_only_the_first_step_is_open(self) -> None:
        s = states(Facts())
        self.assertEqual(s["project"], AVAILABLE)
        self.assertEqual(
            [s[k] for k in ("data", "qc", "harmonize", "membership",
                            "weights", "aggregate", "results")],
            [BLOCKED] * 7,
        )

    def test_every_blocked_step_names_what_is_missing(self) -> None:
        """P-104. A padlock with no reason is the defect this test exists for."""
        for step in derive(Facts()):
            if step.state == BLOCKED:
                self.assertTrue(
                    step.reason_key.strip(),
                    f"step {step.key} is blocked and says nothing about why",
                )


class OpenProject(unittest.TestCase):
    def test_an_empty_project_opens_the_data_step(self) -> None:
        s = states(Facts(project_open=True))
        self.assertEqual(s["project"], DONE)
        self.assertEqual(s["data"], AVAILABLE)
        self.assertEqual(s["qc"], BLOCKED)

    def test_an_imported_dataset_opens_qa_qc(self) -> None:
        s = states(Facts(project_open=True, datasets=({"path": RASTER},)))
        self.assertEqual(s["data"], DONE)
        self.assertEqual(s["qc"], AVAILABLE)
        self.assertEqual(s["harmonize"], BLOCKED)

    def test_an_approved_verdict_opens_harmonisation_and_membership(self) -> None:
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            verdicts=({"dataset_path": RASTER, "usable": True, "warnings": False},),
        )
        s = states(facts)
        self.assertEqual(s["qc"], DONE)
        self.assertEqual(s["harmonize"], AVAILABLE)
        self.assertEqual(s["membership"], AVAILABLE)
        self.assertEqual(s["weights"], BLOCKED)

    def test_a_refused_verdict_does_not_open_the_grid(self) -> None:
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            verdicts=({"dataset_path": RASTER, "usable": False, "warnings": True},),
        )
        s = states(facts)
        self.assertEqual(s["qc"], ATTENTION)
        self.assertEqual(s["harmonize"], BLOCKED)
        self.assertEqual(reasons(facts)["harmonize"],
                         "workflow.blocked.nothingApproved")

    def test_a_warning_informs_without_blocking(self) -> None:
        """P-60's shape, seen from the workflow: a warning is not a wall."""
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            verdicts=({"dataset_path": RASTER, "usable": True, "warnings": True},),
        )
        s = states(facts)
        self.assertEqual(s["qc"], ATTENTION)
        self.assertEqual(s["membership"], AVAILABLE)


class CommittedRuns(unittest.TestCase):
    """A committed run is the strongest fact the store holds about a step."""

    approved = Facts(
        project_open=True,
        datasets=({"path": RASTER},),
        verdicts=({"dataset_path": RASTER, "usable": True, "warnings": False},),
    )

    def test_a_membership_run_finishes_its_step_and_opens_the_next_two(self) -> None:
        facts = Facts(
            project_open=self.approved.project_open,
            datasets=self.approved.datasets,
            verdicts=self.approved.verdicts,
            committed_operators=("decision.membership",),
        )
        s = states(facts)
        self.assertEqual(s["membership"], DONE)
        self.assertEqual(s["weights"], AVAILABLE)
        self.assertEqual(s["aggregate"], AVAILABLE)

    def test_a_committed_run_is_never_reported_as_impossible(self) -> None:
        """The defect the first capture of E1 showed: step 5 blocked while
        steps 6 and 7 were open, because each read the same fact separately."""
        facts = Facts(committed_operators=("decision.membership",))
        s = states(facts)
        self.assertEqual(s["membership"], DONE)
        self.assertNotEqual(s["weights"], BLOCKED)
        self.assertNotEqual(s["aggregate"], BLOCKED)

    def test_aggregation_does_not_wait_for_weights(self) -> None:
        """Gamma, Product and Sum need no weights; only WLC does."""
        facts = Facts(committed_operators=("decision.membership",))
        self.assertEqual(states(facts)["aggregate"], AVAILABLE)

    def test_results_need_a_committed_aggregation(self) -> None:
        self.assertEqual(states(Facts())["results"], BLOCKED)
        self.assertEqual(
            states(Facts(committed_operators=("decision.aggregate",)))["results"],
            DONE,
        )

    def test_a_job_in_flight_wins_over_the_derived_state(self) -> None:
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            running_operators=("qc.validate_dataset",),
        )
        self.assertEqual(states(facts)["qc"], RUNNING)

    def test_a_failed_operator_marks_its_step_for_attention(self) -> None:
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            verdicts=({"dataset_path": RASTER, "usable": True, "warnings": False},),
            failed_operators=("grid.harmonize",),
        )
        derived = {s.key: s for s in derive(facts)}
        self.assertEqual(derived["harmonize"].state, ATTENTION)
        self.assertEqual(derived["harmonize"].reason_key,
                         "workflow.attention.failed")


class Purity(unittest.TestCase):
    def test_the_same_facts_always_give_the_same_workflow(self) -> None:
        """P-103. Nothing is remembered between calls: no order, no history,
        no previous answer leaking into the next one."""
        facts = Facts(
            project_open=True,
            datasets=({"path": RASTER},),
            verdicts=({"dataset_path": RASTER, "usable": True, "warnings": False},),
            committed_operators=("decision.membership",),
        )
        first = [(s.key, s.state, s.reason_key) for s in derive(facts)]
        derive(Facts())                      # a different project in between
        second = [(s.key, s.state, s.reason_key) for s in derive(facts)]
        self.assertEqual(first, second)

    def test_every_step_declares_its_inputs_and_outputs(self) -> None:
        for step in derive(Facts()):
            self.assertTrue(step.title_key and step.purpose_key)
            self.assertTrue(step.outputs, f"step {step.key} produces nothing")
            if step.number > 1:
                self.assertTrue(step.inputs, f"step {step.key} needs nothing")

    def test_the_current_step_is_derived_not_stored(self) -> None:
        from geopotential_app.viewmodels.workflow_model import WorkflowModel

        model = WorkflowModel.__new__(WorkflowModel)   # no QObject, no event loop
        model._steps = derive(Facts(project_open=True))
        self.assertEqual(model.currentKey(), "data")
        model._steps = derive(Facts())
        self.assertEqual(model.currentKey(), "project")


class Catalogue(unittest.TestCase):
    """Every key a step names is a key the catalogue answers, in both
    languages. A missing key shows on screen as the key itself."""

    def test_every_step_key_is_translated(self) -> None:
        from geopotential_app.i18n import LANGUAGES, table

        tables = {language: table(language) for language in LANGUAGES}
        for step in derive(Facts()):
            keys = ((step.title_key, step.purpose_key)
                    + step.inputs + step.outputs + step.nexts
                    + ((step.reason_key,) if step.reason_key else ()))
            for key in keys:
                for language, entries in tables.items():
                    self.assertIn(key, entries,
                                  f"{key} has no {language} text")

    def test_every_reason_the_model_can_produce_is_translated(self) -> None:
        from geopotential_app.i18n import LANGUAGES, table

        import geopotential_app.viewmodels.workflow_model as wf

        source = Path(wf.__file__).read_text(encoding="utf-8")
        produced = {
            line.split('"')[1]
            for line in source.splitlines()
            if "reason_key = " in line and '"workflow.' in line
        }
        self.assertTrue(produced, "no reason keys found to check")
        for language in LANGUAGES:
            entries = table(language)
            for key in produced:
                self.assertIn(key, entries, f"{key} has no {language} text")


if __name__ == "__main__":
    unittest.main()
