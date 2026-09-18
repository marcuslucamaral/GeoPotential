"""Commands: every action that changes the domain.

Section 7.4. A long command validates, returns a `job_id`, runs
asynchronously, updates an observable model, records provenance, and ends in an
explicit state. QML never has to know whether the result came from Python, from
C++, or from a cache.

## The rule that shapes the whole stack

**Undo reverts project state. It never reverts science.**

A completed run is immutable, and undoing a `RunOperatorCommand` does not
delete it — that would make the record of what was computed depend on a UI
gesture. Undoing a run means *forgetting it from the working view*, and the
run, its artefacts, its hash and its lineage all stay exactly where they are.
This is why commands split into two kinds:

  - **reversible** — ordering, selection, linking, naming. `undo()` restores
    the previous value.
  - **irreversible** — anything that commits a run. It reports
    `reversible = False`, the stack does not offer to undo it, and the
    interface disables Undo with that reason visible.

A stack that silently refused to undo would be worse than one that says why.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..utils.qtcore import QObject, Property, Signal, Slot


class CommandError(RuntimeError):
    """A command could not be validated, or could not be undone."""


class Command(ABC):
    """One domain-changing action.

    name         shown in the Undo/Redo tooltip; a verb phrase
    reversible   whether `undo()` is defined and meaningful
    payload      what goes to the command log, for the audit trail
    """

    name: str = ""
    reversible: bool = True

    def __init__(self) -> None:
        self._payload: dict[str, Any] = {}

    @property
    def payload(self) -> dict[str, Any]:
        return dict(self._payload)

    def validate(self) -> None:
        """Refuse before anything changes, naming the field that is wrong.

        raises  CommandError with an actionable message

        Step 1 of section 7.4. Validating inside `execute` means a command can
        fail halfway, which is the state the stack cannot represent.
        """

    @abstractmethod
    def execute(self) -> Any:
        """Do it. Returns a `job_id` for a long command, else whatever it made."""

    def undo(self) -> None:
        """Put it back. Only called when `reversible` is True."""
        raise CommandError(
            f"{self.name}: this action cannot be undone. "
            + (
                "It committed a run, and a completed run is immutable."
                if not self.reversible
                else "No undo was implemented."
            )
        )

    def describe(self) -> str:
        return self.name


class CommandStack(QObject):
    """Undo/redo over reversible commands, with every step logged.

    An irreversible command **clears the redo branch and is not pushed**: it is
    a barrier. Leaving it on the stack would let a later undo walk past a
    committed run, and the first thing a user would try is undoing exactly
    that.
    """

    changed = Signal()
    commandFailed = Signal(str)

    def __init__(self, store=None, logs=None, parent: QObject | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._store = store
        self._logs = logs
        self._done: list[Command] = []
        self._undone: list[Command] = []
        self._barrier: str = ""

    # ---- properties QML binds to ---------------------------------------

    def _can_undo(self) -> bool:
        return bool(self._done)

    def _can_redo(self) -> bool:
        return bool(self._undone)

    def _undo_text(self) -> str:
        if self._done:
            return f"Undo {self._done[-1].describe()}"
        if self._barrier:
            return f"Cannot undo {self._barrier}"
        return "Nothing to undo"

    def _redo_text(self) -> str:
        return f"Redo {self._undone[-1].describe()}" if self._undone else "Nothing to redo"

    canUndo = Property(bool, _can_undo, notify=changed)
    canRedo = Property(bool, _can_redo, notify=changed)
    undoText = Property(str, _undo_text, notify=changed)
    redoText = Property(str, _redo_text, notify=changed)

    # ---- running --------------------------------------------------------

    def run(self, command: Command) -> Any:
        """Validate, execute, log, and push if it can be undone.

        raises  CommandError, already carrying an actionable message
        """
        command.validate()
        result = command.execute()
        self._log(command, "do")

        if command.reversible:
            self._done.append(command)
            self._barrier = ""
        else:
            # A barrier. Everything before it stays undoable only up to here,
            # because undoing past a committed run would misrepresent what the
            # project contains.
            self._done.clear()
            self._barrier = command.describe()
        self._undone.clear()
        self.changed.emit()
        return result

    @Slot()
    def undo(self) -> None:
        if not self._done:
            return
        command = self._done.pop()
        try:
            command.undo()
        except CommandError as exc:
            self._done.append(command)
            self.commandFailed.emit(str(exc))
            return
        self._undone.append(command)
        self._log(command, "undo")
        self.changed.emit()

    @Slot()
    def redo(self) -> None:
        if not self._undone:
            return
        command = self._undone.pop()
        try:
            command.execute()
        except (CommandError, ValueError, RuntimeError) as exc:
            self._undone.append(command)
            self.commandFailed.emit(str(exc))
            return
        self._done.append(command)
        self._log(command, "redo")
        self.changed.emit()

    def _log(self, command: Command, direction: str) -> None:
        if self._store is not None:
            self._store.log_command(command.name, direction, command.payload)
        if self._logs is not None:
            self._logs.application(
                "info", f"{direction} {command.describe()}",
                command=command.name, payload=command.payload,
            )

    @property
    def depth(self) -> tuple[int, int]:
        """(undoable, redoable). For the gate, not for the interface."""
        return len(self._done), len(self._undone)
