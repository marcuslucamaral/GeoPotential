"""Double counting: criteria derived from the same evidence.

Section 15.1. The example the document gives is the whole problem:

    heat flow
    gradient
    temperature

Three criteria, one piece of evidence. Give each an independent weight and that
evidence carries three times its due — and the map looks better justified than
it is, because three separate lines of support appear to agree.

    "Não permita que evidências correlacionadas recebam pesos independentes
     sem: warning; grupo hierárquico; ou justificativa explícita registrada."

So this module computes the correlation and **names the pair**. It does not
decide: merging two criteria, grouping them, or accepting the overlap are all
legitimate, and only the person who knows where the data came from can choose.
What is not legitimate is not being told.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np

from ..domain.criterion import CriterionStack

#: Above this, two criteria are reported as possibly the same evidence. It is a
#: declared parameter, not a constant: what counts as "too correlated" depends
#: on the domain, and section 16 forbids a silent value.
DEFAULT_THRESHOLD = 0.85

#: Below this many jointly valid pixels a correlation is not worth reporting:
#: it says more about the overlap than about the fields.
MIN_SAMPLES = 100


@dataclass(frozen=True)
class CorrelationFinding:
    """One suspicious pair, with what to do about it."""

    a: str
    b: str
    coefficient: float
    samples: int
    combined_weight: float | None = None

    @property
    def message(self) -> str:
        weight = (
            f" Together they carry {self.combined_weight:.0%} of the total "
            f"weight."
            if self.combined_weight is not None else ""
        )
        return (
            f"{self.a!r} and {self.b!r} correlate at r = {self.coefficient:+.2f} "
            f"over {self.samples:,} shared pixels.{weight} They may be measuring "
            f"the same evidence, in which case independent weights count it "
            f"twice. Put them in one hierarchical group, drop one, or record "
            f"why both belong."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "a": self.a,
            "b": self.b,
            "coefficient": self.coefficient,
            "samples": self.samples,
            "combined_weight": self.combined_weight,
            "message": self.message,
        }


def correlations(stack: CriterionStack) -> dict[tuple[str, str], tuple[float, int]]:
    """Pearson r between every pair, over their jointly valid pixels.

    stack    the criteria, normalized and on one grid
    returns  {(a, b): (r, n)} for every pair

    Computed only where both are valid: a correlation over a union, with the
    nulls filled, would mostly measure where the holes are.
    """
    names = stack.names
    values = stack.stacked()
    result: dict[tuple[str, str], tuple[float, int]] = {}
    for i, j in combinations(range(len(names)), 2):
        a, b = values[i], values[j]
        both = np.isfinite(a) & np.isfinite(b)
        count = int(both.sum())
        if count < MIN_SAMPLES:
            result[(names[i], names[j])] = (float("nan"), count)
            continue
        x = a[both].astype(np.float64)
        y = b[both].astype(np.float64)
        # A constant criterion has no correlation with anything; numpy would
        # return NaN through a zero division, which is the right answer but a
        # noisy way to get there.
        if x.std() < 1e-12 or y.std() < 1e-12:
            result[(names[i], names[j])] = (float("nan"), count)
            continue
        result[(names[i], names[j])] = (float(np.corrcoef(x, y)[0, 1]), count)
    return result


def double_counting(
    stack: CriterionStack,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    weights: dict[str, float] | None = None,
    groups: dict[str, str] | None = None,
) -> list[CorrelationFinding]:
    """Pairs correlated enough to be worth questioning.

    stack      the normalized criteria
    threshold  |r| above which a pair is reported
    weights    to say how much weight the pair carries between them
    groups     {criterion: group}; a pair already sharing a group is **not**
               reported — putting them in one is the documented remedy, and
               warning about it afterwards would be nagging about a fix

    returns  findings, strongest correlation first
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1]; got {threshold}")
    groups = groups or {}
    findings = []
    for (a, b), (coefficient, samples) in correlations(stack).items():
        if not np.isfinite(coefficient) or abs(coefficient) < threshold:
            continue
        if a in groups and groups.get(a) == groups.get(b):
            continue
        combined = None
        if weights and a in weights and b in weights:
            combined = float(weights[a] + weights[b])
        findings.append(CorrelationFinding(a, b, coefficient, samples, combined))
    return sorted(findings, key=lambda f: abs(f.coefficient), reverse=True)
