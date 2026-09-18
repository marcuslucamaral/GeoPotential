"""The jobs model, exposed to QML.

`QAbstractListModel` rather than a list of dicts pushed across: QML binds to the
model, and a progress update repaints one delegate instead of rebuilding the
panel. QtCore only — a model that can name a QColor is choosing a style.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.qtcore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot


@dataclass
class JobRow:
    """One job, as the panel shows it. `state` follows the section 13 machine."""

    job_id: str
    operator: str
    state: str = "Queued"
    stage: str = ""
    fraction: float = 0.0
    message: str = ""
    error_code: str = ""
    detail_ref: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # What the job was asked to do. Shown in the detail, so a job that failed
    # can be read without opening the store: the panel that only shows a state
    # is the panel that made `job failed` mean nothing.
    inputs: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    elapsed: float = 0.0


class JobListModel(QAbstractListModel):
    """Jobs, newest last. The only writer of job rows."""

    # A job in one of these has not finished. Everything else is a fact about
    # the past, and the panel's "active" filter turns on exactly this.
    IN_FLIGHT = ("Queued", "Validating", "Running", "Committing")

    JobIdRole = Qt.UserRole + 1
    OperatorRole = Qt.UserRole + 2
    StateRole = Qt.UserRole + 3
    StageRole = Qt.UserRole + 4
    FractionRole = Qt.UserRole + 5
    MessageRole = Qt.UserRole + 6
    ErrorRole = Qt.UserRole + 7
    ArtifactCountRole = Qt.UserRole + 8
    InputsRole = Qt.UserRole + 9
    ElapsedRole = Qt.UserRole + 10
    ActiveRole = Qt.UserRole + 11
    DetailRefRole = Qt.UserRole + 12

    countChanged = Signal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001 - Qt parent
        super().__init__(parent)
        self._rows: list[JobRow] = []
        self._index: dict[str, int] = {}

    # ---- Qt model interface --------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, ANN001
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {
            self.JobIdRole: QByteArray(b"jobId"),
            self.OperatorRole: QByteArray(b"operator"),
            self.StateRole: QByteArray(b"state"),
            self.StageRole: QByteArray(b"stage"),
            self.FractionRole: QByteArray(b"fraction"),
            self.MessageRole: QByteArray(b"message"),
            self.ErrorRole: QByteArray(b"errorCode"),
            self.ArtifactCountRole: QByteArray(b"artifactCount"),
            self.InputsRole: QByteArray(b"inputs"),
            self.ElapsedRole: QByteArray(b"elapsed"),
            self.ActiveRole: QByteArray(b"isActive"),
            self.DetailRefRole: QByteArray(b"detailRef"),
        }

    def data(self, index, role=Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return {
            self.JobIdRole: row.job_id,
            self.OperatorRole: row.operator,
            self.StateRole: row.state,
            self.StageRole: row.stage,
            self.FractionRole: row.fraction,
            self.MessageRole: row.message,
            self.ErrorRole: row.error_code,
            self.ArtifactCountRole: len(row.artifacts),
            self.InputsRole: list(row.inputs),
            self.ElapsedRole: row.elapsed,
            self.ActiveRole: row.state in self.IN_FLIGHT,
            self.DetailRefRole: row.detail_ref,
            Qt.DisplayRole: f"{row.operator} — {row.state}",
        }.get(role)

    # ---- writing --------------------------------------------------------

    def add(self, job_id: str, operator: str, *,
            inputs: list[str] | None = None,
            params: dict[str, Any] | None = None) -> None:
        if job_id in self._index:
            raise ValueError(f"job {job_id} is already in the model")
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append(JobRow(
            job_id=job_id, operator=operator,
            inputs=list(inputs or []), params=dict(params or {}),
        ))
        self._index[job_id] = position
        self.endInsertRows()
        self.countChanged.emit()

    def update_progress(self, job_id: str, stage: str, fraction: float, message: str) -> None:
        row, position = self._find(job_id)
        if row is None:
            return
        # Progress is monotonic per stage. A fraction going backwards inside one
        # stage means the worker is reporting something other than work done.
        if stage == row.stage and fraction < row.fraction - 1e-9:
            return
        row.state = "Running"
        row.stage = stage
        row.fraction = fraction
        row.message = message
        self._emit(position, [self.StateRole, self.StageRole, self.FractionRole,
                              self.MessageRole])

    def set_state(self, job_id: str, state: str, *, message: str = "",
                  error_code: str = "", detail_ref: str = "") -> None:
        row, position = self._find(job_id)
        if row is None:
            return
        row.state = state
        if message:
            row.message = message
        row.error_code = error_code
        row.detail_ref = detail_ref
        if state == "Succeeded":
            row.fraction = 1.0
        self._emit(position, [self.StateRole, self.MessageRole, self.ErrorRole,
                              self.FractionRole])

    def add_artifact(self, job_id: str, artifact: dict[str, Any]) -> None:
        row, position = self._find(job_id)
        if row is None:
            return
        row.artifacts.append(artifact)
        self._emit(position, [self.ArtifactCountRole])

    # ---- reading --------------------------------------------------------

    @Slot(str, result="QVariant")
    def artifactsOf(self, job_id: str) -> list[dict[str, Any]]:  # noqa: N802
        row, _ = self._find(job_id)
        return list(row.artifacts) if row else []

    def row(self, job_id: str) -> JobRow | None:
        return self._find(job_id)[0]

    @Slot(str, result="QVariant")
    def detail(self, job_id: str) -> dict[str, Any]:
        """Everything the panel shows about one job.

        The failure message belongs to **this** job. The defect this replaces
        was a single global status string, written by whatever happened last,
        that read `job failed` beside a job that had succeeded.
        """
        row, _ = self._find(job_id)
        if row is None:
            return {}
        return {
            "jobId": row.job_id,
            "operator": row.operator,
            "state": row.state,
            "stage": row.stage,
            "fraction": row.fraction,
            "message": row.message,
            "errorCode": row.error_code,
            "detailRef": row.detail_ref,
            "inputs": list(row.inputs),
            "params": dict(row.params),
            "artifacts": [
                {"id": a.get("artifact_id", a.get("id", "")),
                 "path": a.get("path", ""),
                 "role": a.get("role", "")}
                for a in row.artifacts
            ],
            "elapsed": row.elapsed,
            "active": row.state in self.IN_FLIGHT,
        }

    def set_elapsed(self, job_id: str, seconds: float) -> None:
        row, position = self._find(job_id)
        if row is None:
            return
        row.elapsed = float(seconds)
        self._emit(position, [self.ElapsedRole])

    @property
    def rows(self) -> list[JobRow]:
        """Every job, in submission order. Read-only: the model is the only
        writer of job rows."""
        return list(self._rows)

    def _find(self, job_id: str) -> tuple[JobRow | None, int]:
        position = self._index.get(job_id)
        if position is None:
            return None, -1
        return self._rows[position], position

    def _emit(self, position: int, roles: list[int]) -> None:
        index = self.index(position, 0)
        self.dataChanged.emit(index, index, roles)
