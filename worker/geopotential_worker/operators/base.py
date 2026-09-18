"""What an operator is, and what it promises.

An operator declares its name, version, parameters — with type, unit,
documented default and range — inputs, outputs, tolerance and reference.
A silent default is forbidden by section 16: every default is documented,
editable, visible and versioned.

Progress is real. `Context.progress` is called from inside the computation with
the fraction actually completed. Section 12.3: do not simulate progress.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from ..io.writers import Artifact


class Cancelled(Exception):
    """The job was cancelled cooperatively. Nothing partial is registered."""


class ParameterError(ValueError):
    """A parameter is missing, of the wrong type, or out of range."""


@dataclass(frozen=True)
class Parameter:
    """One declared parameter of an operator.

    name      as it appears in `params`
    type      'float' | 'int' | 'str' | 'bool' | 'list'
    unit      physical unit, or 'dimensionless', or None for non-numeric
    default   the documented default; None means the parameter is required
    choices   allowed values, for an enumerated parameter
    minimum   inclusive lower bound, for a numeric parameter
    maximum   inclusive upper bound, for a numeric parameter
    doc       one line saying what it does
    """

    name: str
    type: str
    doc: str
    unit: str | None = None
    default: Any = None
    required: bool = False
    choices: tuple[Any, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None

    def coerce(self, value: Any, *, operator: str) -> Any:
        """Validate one value against this declaration.

        raises  ParameterError naming the operator, the parameter and the fault
        """
        where = f"{operator}.{self.name}"
        if value is None:
            if self.required:
                raise ParameterError(f"{where}: required, and not given")
            return self.default
        if self.choices is not None and value not in self.choices:
            raise ParameterError(
                f"{where}: {value!r} is not one of "
                + ", ".join(repr(c) for c in self.choices)
            )
        if self.type in ("float", "int"):
            try:
                value = float(value) if self.type == "float" else int(value)
            except (TypeError, ValueError) as exc:
                raise ParameterError(f"{where}: {value!r} is not a {self.type}") from exc
            if self.minimum is not None and value < self.minimum:
                raise ParameterError(
                    f"{where}: {value} is below the minimum {self.minimum} "
                    f"{self.unit or ''}".rstrip()
                )
            if self.maximum is not None and value > self.maximum:
                raise ParameterError(
                    f"{where}: {value} is above the maximum {self.maximum} "
                    f"{self.unit or ''}".rstrip()
                )
        elif self.type == "bool":
            value = bool(value)
        return value

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "unit": self.unit,
            "default": self.default,
            "required": self.required,
            "choices": list(self.choices) if self.choices else None,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "doc": self.doc,
        }


@dataclass
class Context:
    """What an operator is handed: where to write, and how to report.

    output_dir  the job's directory; artefacts land here
    progress    progress(stage, fraction, message) — real, monotonic per stage
    check_cancel  raises Cancelled if the app asked to stop; call it between
                  stages and inside long loops
    """

    output_dir: Path
    progress: Callable[[str, float, str], None]
    check_cancel: Callable[[], None]
    artifacts: list[tuple[str, Artifact]] = field(default_factory=list)

    def emit(self, artifact_id: str, artifact: Artifact) -> None:
        """Record a closed, validated, hashed artefact."""
        self.artifacts.append((artifact_id, artifact))


class Operator(ABC):
    """One versioned unit of scientific work.

    Subclasses declare `name`, `version`, `parameters`, `reference`, and
    implement `run`. Nothing else in the worker knows how the work is done.
    """

    name: str = ""
    version: str = ""
    summary: str = ""
    reference: str = ""
    parameters: Sequence[Parameter] = ()

    #: A read-only probe produces no artefact and commits no run. It answers a
    #: question about a dataset — section 9.2 requires that answer *before* the
    #: dataset enters the project, so recording a run for it would make
    #: describing a form of importing. Its result is a ValidationResult
    #: instead (section 14.3).
    read_only: bool = False

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Coerce and check `params` against the declaration.

        returns  the resolved parameter set, defaults filled in
        raises   ParameterError on an unknown, missing or out-of-range value

        The resolved set — not what the caller sent — is what goes into the
        manifest and into the cache key, so a run made on a default is
        reproducible from its record.
        """
        declared = {p.name: p for p in self.parameters}
        unknown = sorted(set(params) - set(declared))
        if unknown:
            raise ParameterError(
                f"{self.name}: unknown parameter(s) {', '.join(unknown)}; "
                f"declared: {', '.join(sorted(declared)) or 'none'}"
            )
        return {
            spec.name: spec.coerce(params.get(spec.name), operator=self.name)
            for spec in self.parameters
        }

    @abstractmethod
    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        """Do the work and emit artefacts through `ctx`.

        inputs   input paths, in the order the operator documents
        params   the resolved parameter set from `validate`
        ctx      progress, cancellation and artefact emission
        returns  the manifest body for this run
        """

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "summary": self.summary,
            "reference": self.reference,
            "read_only": self.read_only,
            "parameters": [p.describe() for p in self.parameters],
        }
