"""The eight-step workflow, and where the project actually stands in it.

The state of a step is **derived** from facts the Project Store already holds —
datasets registered, verdicts recorded, runs committed, jobs in flight. Nothing
here is written by hand, and nothing here is remembered: `derive` is a pure
function of a `Facts` snapshot, so the same project always produces the same
workflow, and a panel that disagrees with the store is a bug in the panel.

QtCore only. The model carries no colour: a step publishes its state as a name
and QML decides what that looks like.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.qtcore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot

# ---- the vocabulary of a step's state -----------------------------------
#
# Six states, and the difference between two of them matters: `blocked` means
# a precondition is missing and the step names it; `not_started` means the step
# can be entered and nobody has. A step is never enabled into a modal warning.
NOT_STARTED = "not_started"
AVAILABLE = "available"
RUNNING = "running"
DONE = "done"
ATTENTION = "attention"
BLOCKED = "blocked"


@dataclass(frozen=True)
class Facts:
    """What the store knows, reduced to what the workflow needs.

    Every field is a fact with a single source. `committed_operators` comes
    from runs, not from jobs: a job that ran and did not commit produced
    nothing, and a workflow that counted it would claim work that was never
    recorded.
    """

    project_open: bool = False
    datasets: tuple[dict[str, Any], ...] = ()
    verdicts: tuple[dict[str, Any], ...] = ()
    committed_operators: tuple[str, ...] = ()
    running_operators: tuple[str, ...] = ()
    failed_operators: tuple[str, ...] = ()

    def committed(self, operator: str) -> bool:
        return operator in self.committed_operators


@dataclass
class Step:
    """One step, as the panel shows it.

    Everything the person reads is a **catalogue key**, never a sentence: the
    model publishes what a step is, and `i18n/` decides in which language it
    is said. A step carrying literal text could only ever be right in one.
    """

    key: str
    number: int
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    action: str
    operators: tuple[str, ...] = ()
    state: str = BLOCKED
    reason_key: str = ""
    nexts: tuple[str, ...] = ()

    @property
    def title_key(self) -> str:
        return f"workflow.{self.key}.title"

    @property
    def purpose_key(self) -> str:
        return f"workflow.{self.key}.purpose"


# The eight steps. `action` is a token the shell maps to a screen; the model
# names no screen and opens nothing. Every human-readable field is a key into
# `i18n/catalog.py`.
_STEPS: tuple[dict[str, Any], ...] = (
    {
        "key": "project", "number": 1, "action": "projectHub",
        "inputs": ("workflow.project.in.folder",),
        "outputs": ("workflow.project.out.open", "workflow.project.out.session"),
        "nexts": ("workflow.data.title",),
    },
    {
        "key": "data", "number": 2, "action": "importWizard",
        "inputs": ("workflow.data.in.project", "workflow.data.in.file"),
        "outputs": ("workflow.data.out.dataset",),
        "operators": ("io.describe_dataset",),
        "nexts": ("workflow.qc.title",),
    },
    {
        "key": "qc", "number": 3, "action": "importWizard",
        "inputs": ("workflow.qc.in.dataset",),
        "outputs": ("workflow.qc.out.verdict",),
        "operators": ("qc.validate_dataset",),
        "nexts": ("workflow.harmonize.title",),
    },
    {
        "key": "harmonize", "number": 4, "action": "harmonize",
        "inputs": ("workflow.harmonize.in.approved", "workflow.harmonize.in.crs"),
        "outputs": ("workflow.harmonize.out.grid",),
        "operators": ("grid.harmonize",),
        "nexts": ("workflow.membership.title",),
    },
    {
        "key": "membership", "number": 5, "action": "membershipEditor",
        "inputs": ("workflow.membership.in.layer", "workflow.membership.in.sense"),
        "outputs": ("workflow.membership.out.criterion",),
        "operators": ("decision.membership",),
        "nexts": ("workflow.weights.title",),
    },
    {
        "key": "weights", "number": 6, "action": "decisionModel",
        "inputs": ("workflow.weights.in.criteria",),
        "outputs": ("workflow.weights.out.weights", "workflow.weights.out.cr"),
        "operators": ("decision.ahp_weights",),
        "nexts": ("workflow.aggregate.title",),
    },
    {
        "key": "aggregate", "number": 7, "action": "decisionModel",
        "inputs": ("workflow.aggregate.in.criteria", "workflow.aggregate.in.weights"),
        "outputs": ("workflow.aggregate.out.map", "workflow.aggregate.out.manifest"),
        "operators": ("decision.aggregate",),
        "nexts": ("workflow.results.title",),
    },
    {
        "key": "results", "number": 8, "action": "results",
        "inputs": ("workflow.results.in.run",),
        "outputs": ("workflow.results.out.map", "workflow.results.out.diagnostic"),
        "nexts": (),
    },
)


def _steps() -> list[Step]:
    return [Step(**spec) for spec in _STEPS]


def derive(facts: Facts) -> list[Step]:
    """The state of every step, from the store's facts alone.

    inputs   a `Facts` snapshot
    output   the eight steps, each with `state`, and `reason` when blocked
    """
    steps = {s.key: s for s in _steps()}

    described = len(facts.datasets)
    verdicts = {v.get("dataset_path"): v for v in facts.verdicts}
    approved = [v for v in verdicts.values() if v.get("usable")]
    warned = [v for v in approved if v.get("warnings")]
    unchecked = [d for d in facts.datasets if d.get("path") not in verdicts]

    # 1 — Projeto
    project = steps["project"]
    project.state = DONE if facts.project_open else AVAILABLE

    # 2 — Dados
    data = steps["data"]
    if not facts.project_open:
        data.state, data.reason_key = BLOCKED, "workflow.blocked.noProject"
    elif described == 0:
        data.state = AVAILABLE
    else:
        data.state = DONE

    # 3 — QA/QC
    qc = steps["qc"]
    if described == 0:
        qc.state = BLOCKED
        qc.reason_key = "workflow.blocked.noDataset"
    elif unchecked:
        qc.state = AVAILABLE
        qc.reason_key = ""
    elif not approved:
        qc.state = ATTENTION
        qc.reason_key = "workflow.attention.qcRefused"
    elif warned:
        qc.state = ATTENTION
        qc.reason_key = "workflow.attention.qcWarned"
    else:
        qc.state = DONE

    # From here on, a committed run is tested **first**. A run that committed
    # is the strongest fact the store holds about a step, and a chain that
    # reported "blocked" over the top of one would be calling a recorded result
    # impossible.

    # 4 — Harmonização
    harmonize = steps["harmonize"]
    if facts.committed("grid.harmonize"):
        harmonize.state = DONE
    elif not approved:
        harmonize.state = BLOCKED
        harmonize.reason_key = "workflow.blocked.nothingApproved"
    else:
        harmonize.state = AVAILABLE

    # 5 — Membership
    membership = steps["membership"]
    if facts.committed("decision.membership"):
        membership.state = DONE
    elif not approved:
        membership.state = BLOCKED
        membership.reason_key = "workflow.blocked.noLayer"
    else:
        membership.state = AVAILABLE

    # 6 — Pesos/AHP. Chained on the *state* of step 5, not on the same fact
    # read twice: two steps deciding independently is how a panel ends up
    # showing step 5 blocked and step 6 open at the same time.
    weights = steps["weights"]
    if facts.committed("decision.ahp_weights"):
        weights.state = DONE
    elif membership.state != DONE:
        weights.state = BLOCKED
        weights.reason_key = "workflow.blocked.noCriterion"
    else:
        weights.state = AVAILABLE

    # 7 — Agregação. It chains on membership, not on weights: Gamma, Product
    # and Sum need no weights at all, and only WLC does.
    aggregate = steps["aggregate"]
    if facts.committed("decision.aggregate"):
        aggregate.state = DONE
    elif membership.state != DONE:
        aggregate.state = BLOCKED
        aggregate.reason_key = "workflow.blocked.nothingToCombine"
    else:
        aggregate.state = AVAILABLE

    # 8 — Resultados
    results = steps["results"]
    if facts.committed("decision.aggregate"):
        results.state = DONE
    else:
        results.state = BLOCKED
        results.reason_key = "workflow.blocked.noAggregation"

    # A job in flight wins over everything: it is the most specific fact
    # available about a step, and it is the one the person is watching.
    for step in steps.values():
        for operator in step.operators:
            if operator in facts.running_operators:
                step.state, step.reason_key = RUNNING, ""
            elif operator in facts.failed_operators and step.state != RUNNING:
                step.state = ATTENTION
                step.reason_key = "workflow.attention.failed"

    return [steps[spec["key"]] for spec in _STEPS]


class WorkflowModel(QAbstractListModel):
    """The eight steps, for QML. It holds no state of its own: `update`
    replaces every row from a fresh `Facts` snapshot."""

    KeyRole = Qt.UserRole + 1
    NumberRole = Qt.UserRole + 2
    TitleRole = Qt.UserRole + 3
    PurposeRole = Qt.UserRole + 4
    StateRole = Qt.UserRole + 5
    ReasonRole = Qt.UserRole + 6
    InputsRole = Qt.UserRole + 7
    OutputsRole = Qt.UserRole + 8
    NextsRole = Qt.UserRole + 9
    ActionRole = Qt.UserRole + 10

    changed = Signal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001 - Qt parent
        super().__init__(parent)
        self._steps: list[Step] = derive(Facts())

    # ---- Qt model interface ---------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, ANN001
        return 0 if parent.isValid() else len(self._steps)

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {
            self.KeyRole: QByteArray(b"key"),
            self.NumberRole: QByteArray(b"number"),
            self.TitleRole: QByteArray(b"titleKey"),
            self.PurposeRole: QByteArray(b"purposeKey"),
            self.StateRole: QByteArray(b"stepState"),
            self.ReasonRole: QByteArray(b"reasonKey"),
            self.InputsRole: QByteArray(b"inputs"),
            self.OutputsRole: QByteArray(b"outputs"),
            self.NextsRole: QByteArray(b"nexts"),
            self.ActionRole: QByteArray(b"stepAction"),
        }

    def data(self, index, role=Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or not 0 <= index.row() < len(self._steps):
            return None
        step = self._steps[index.row()]
        return {
            self.KeyRole: step.key,
            self.NumberRole: step.number,
            self.TitleRole: step.title_key,
            self.PurposeRole: step.purpose_key,
            self.StateRole: step.state,
            self.ReasonRole: step.reason_key,
            self.InputsRole: list(step.inputs),
            self.OutputsRole: list(step.outputs),
            self.NextsRole: list(step.nexts),
            self.ActionRole: step.action,
            Qt.DisplayRole: f"{step.number}. {step.key} — {step.state}",
        }.get(role)

    # ---- updating --------------------------------------------------------

    def update(self, facts: Facts) -> None:
        """Recompute every step. Called whenever the store changes."""
        fresh = derive(facts)
        if [(s.state, s.reason_key) for s in fresh] == [
            (s.state, s.reason_key) for s in self._steps
        ]:
            return
        self.beginResetModel()
        self._steps = fresh
        self.endResetModel()
        self.changed.emit()

    # ---- what QML asks ---------------------------------------------------

    @Slot(str, result="QVariant")
    def step(self, key: str) -> dict[str, Any]:
        """One step as a plain dictionary, for a panel that needs the detail."""
        for s in self._steps:
            if s.key == key:
                return {
                    "key": s.key, "number": s.number,
                    "titleKey": s.title_key, "purposeKey": s.purpose_key,
                    "state": s.state, "reasonKey": s.reason_key,
                    "inputs": list(s.inputs), "outputs": list(s.outputs),
                    "nexts": list(s.nexts), "stepAction": s.action,
                }
        return {}

    @Slot(str, result=bool)
    def isReady(self, key: str) -> bool:  # noqa: N802
        """Whether clicking the step may open anything at all."""
        for s in self._steps:
            if s.key == key:
                return s.state != BLOCKED
        return False

    @Slot(result=str)
    def currentKey(self) -> str:  # noqa: N802
        """The step the person is on: the running one, else the first that is
        not finished. It is derived, never set."""
        for s in self._steps:
            if s.state == RUNNING:
                return s.key
        for s in self._steps:
            if s.state in (AVAILABLE, ATTENTION):
                return s.key
        return self._steps[-1].key if self._steps else ""
