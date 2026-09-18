"""What a QA/QC check returns, and what makes a message acceptable.

Section MSP-04: **"Não reduza QA/QC a warning genérico."** Section 33 says what
a message must answer, when it can:

  what failed · why · which dataset · which parameter · what to correct ·
  where the technical detail is

So a `Finding` is not a string. It carries those fields separately, and the
rendered message is assembled from them. That is the only way a test can assert
that a message is actionable rather than merely present — and there is such a
test.

Severity is three levels, and the distinction is operational, not decorative:

  BLOCKER  the operation is refused. Not a redder warning.
  WARNING  the operation proceeds, and the operator has to know.
  INFO     context worth recording, no decision attached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Phrases that make a message useless. A check whose `fix` reads like one of
# these is not actionable, and `Finding.is_actionable` says so.
VAGUE = (
    "check your data",
    "something went wrong",
    "invalid input",
    "an error occurred",
    "see the log",
    "unknown error",
    "please try again",
)


class Severity(str, Enum):
    """Three levels, ordered INFO < WARNING < BLOCKER.

    This is a `str` Enum so it serializes cleanly, and that inheritance is a
    trap: `str` already defines the comparison operators, so `max()` over these
    members sorts them **alphabetically** unless the order is supplied
    explicitly. Alphabetically, "WARNING" beats "BLOCKER", and a report with a
    blocking defect reports itself as a warning. Use `rank`, never `<` or
    `max` on the members directly.
    """

    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"

    @property
    def blocks(self) -> bool:
        return self is Severity.BLOCKER

    @property
    def rank(self) -> int:
        return {Severity.INFO: 0, Severity.WARNING: 1, Severity.BLOCKER: 2}[self]


@dataclass(frozen=True)
class Finding:
    """One QA/QC verdict about one dataset.

    rule      stable identifier, e.g. 'nodata.declared'; what a fixture asserts
    severity  BLOCKER refuses the operation; WARNING proceeds with notice
    dataset   the file or layer the finding is about, by name
    what      what is wrong, in one clause
    why       why it matters scientifically
    fix       what the operator can do about it — the actionable part
    field     the column, band or parameter involved, when there is one
    observed  the value that triggered it, for the record
    expected  what would have been acceptable
    """

    rule: str
    severity: Severity
    dataset: str
    what: str
    why: str
    fix: str
    field: str | None = None
    observed: Any = None
    expected: Any = None
    detail_ref: str = ""

    @property
    def message(self) -> str:
        """The line a user reads. Assembled, never a bare string."""
        head = f"{self.dataset}"
        if self.field:
            head += f" ({self.field})"
        return f"{head}: {self.what} {self.why} {self.fix}"

    @property
    def is_actionable(self) -> bool:
        """Whether this finding tells someone what to do.

        A finding that names no dataset, or whose `fix` is a stock phrase, has
        failed the point of MSP-04 even though it technically reported
        something. The gate asserts this over every finding the rules produce.
        """
        if not self.dataset or not self.what or not self.fix:
            return False
        lowered = f"{self.what} {self.fix}".lower()
        return not any(phrase in lowered for phrase in VAGUE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "dataset": self.dataset,
            "field": self.field,
            "what": self.what,
            "why": self.why,
            "fix": self.fix,
            "observed": self.observed,
            "expected": self.expected,
            "message": self.message,
        }


@dataclass
class Report:
    """Every finding about one dataset, and the verdict that follows."""

    dataset: str
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.BLOCKER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def usable(self) -> bool:
        """Whether the dataset may enter the project or feed an operation.

        A BLOCKER means no. This is the property the Import Wizard and the job
        submission both consult, so "impede operação inválida" is one rule in
        one place rather than two that can disagree.
        """
        return not self.blockers

    @property
    def severity(self) -> Severity:
        # `key=rank`, because these members compare as strings by default and
        # "WARNING" > "BLOCKER" alphabetically.
        return max((f.severity for f in self.findings), key=lambda s: s.rank,
                   default=Severity.INFO)

    def summary(self) -> str:
        """One line, safe to show. States the verdict, then the counts."""
        if not self.findings:
            return f"{self.dataset}: no problems found."
        blockers, warnings = len(self.blockers), len(self.warnings)
        verdict = "cannot be used" if blockers else "can be used, with notes"
        parts = []
        if blockers:
            parts.append(f"{blockers} blocking problem" + ("s" if blockers > 1 else ""))
        if warnings:
            parts.append(f"{warnings} warning" + ("s" if warnings > 1 else ""))
        return f"{self.dataset} {verdict}: " + ", ".join(parts) + "."

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "usable": self.usable,
            "severity": self.severity.value,
            "summary": self.summary(),
            "findings": [f.as_dict() for f in self.findings],
            "metadata": self.metadata,
        }
