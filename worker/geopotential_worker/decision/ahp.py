"""Analytic Hierarchy Process.

Saaty (1980), *The Analytic Hierarchy Process*, ch. 1-3: weights are the
normalized principal eigenvector of a positive reciprocal matrix, and the
consistency ratio measures how far the judgments are from transitive.

The arithmetic is the legacy tree's `core/ahp.py`, which is correct. What is
new is that **the consistency check refuses**. MSP-08:

    "Não aceite AHP inconsistente de forma silenciosa. Quando o consistency
     ratio ultrapassar o limite configurado: bloqueie a execução; ou exija
     justificativa registrada."

Reporting `CR` and continuing is the same as not computing it. So `weights()`
raises above the threshold, and the only way past is an explicit override that
is written into the manifest with its reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

# Saaty's Random Index: the mean CI of random reciprocal matrices, by order.
# Valid to n = 10. Beyond that there is no published value, and reusing 1.49
# would manufacture consistency for a matrix nobody can fill in reliably
# anyway — 11 criteria is 55 pairwise judgments.
RANDOM_INDEX = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
}
MAX_CRITERIA = max(RANDOM_INDEX)

#: Saaty's threshold. A parameter, not a constant: section 16 forbids silent
#: values, and a project may justify a different one — in writing.
DEFAULT_CR_THRESHOLD = 0.10

# The fundamental scale. A judgment outside it is not on Saaty's scale and the
# RI table does not describe it.
SCALE_MIN, SCALE_MAX = 1.0 / 9.0, 9.0


class InconsistentMatrixError(ValueError):
    """CR is above the threshold and no override was recorded."""


@dataclass
class AhpResult:
    """Weights and everything needed to defend them."""

    names: list[str]
    weights: np.ndarray
    lambda_max: float
    ci: float
    ri: float
    cr: float
    threshold: float
    consistent: bool
    override: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def weights_by_name(self) -> dict[str, float]:
        """Weights bound to criterion names **by position**.

        Row `i` of the matrix is criterion `i` of the stack. That binding is
        explicit here and nowhere else; deriving it from a dict's key order at
        two call sites is how a weight lands on the wrong layer with no error
        anywhere (defect D-06).
        """
        return {name: float(w) for name, w in zip(self.names, self.weights)}

    def as_dict(self) -> dict[str, Any]:
        return {
            "names": self.names,
            "weights": [float(w) for w in self.weights],
            "weights_by_name": self.weights_by_name,
            "lambda_max": self.lambda_max,
            "ci": self.ci,
            "ri": self.ri,
            "cr": self.cr,
            "threshold": self.threshold,
            "consistent": self.consistent,
            "override": self.override,
            "warnings": self.warnings,
            "reference": "Saaty (1980), The Analytic Hierarchy Process, ch. 3.",
        }


def reciprocal_matrix(
    n: int, judgments: dict[tuple[int, int], float] | None = None
) -> np.ndarray:
    """Build a reciprocal matrix from the upper-triangle judgments.

    n          number of criteria
    judgments  {(i, j): a_ij} for i < j, on Saaty's scale
    returns    (n, n) with A[i,i] = 1 and A[j,i] = 1 / A[i,j]

    Building it this way makes reciprocity structural: a caller cannot supply
    a matrix where A[i,j] * A[j,i] != 1, which is a judgment that means nothing.
    """
    matrix = np.ones((n, n), dtype=np.float64)
    for (i, j), value in (judgments or {}).items():
        if not 0 <= i < n or not 0 <= j < n:
            raise ValueError(f"judgment ({i}, {j}) is outside a {n}x{n} matrix")
        if i == j:
            raise ValueError("a criterion cannot be compared with itself")
        if not SCALE_MIN - 1e-9 <= value <= SCALE_MAX + 1e-9:
            raise ValueError(
                f"judgment ({i}, {j}) = {value} is off Saaty's fundamental "
                f"scale [1/9, 9]. The random index table does not describe "
                f"matrices built from other scales."
            )
        matrix[i, j] = float(value)
        matrix[j, i] = 1.0 / float(value)
    return matrix


def weights(
    matrix: Sequence[Sequence[float]],
    names: Sequence[str],
    *,
    threshold: float = DEFAULT_CR_THRESHOLD,
    override_reason: str = "",
) -> AhpResult:
    """Saaty weights, with the consistency check as a refusal.

    matrix           square, strictly positive, reciprocal
    names            criterion names, in the stack's order; row i is names[i]
    threshold        CR above which the matrix is refused
    override_reason  a recorded justification for proceeding anyway. Empty
                     means no override, and an inconsistent matrix then raises.

    returns  AhpResult
    raises   ValueError on a malformed matrix; InconsistentMatrixError when
             CR >= threshold and no reason was given

    Saaty (1980) ch. 3: w is the principal eigenvector normalized to sum 1;
    CI = (lambda_max - n) / (n - 1); CR = CI / RI(n).
    """
    A = np.asarray(matrix, dtype=np.float64)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(
            f"the comparison matrix must be square; got shape {A.shape}"
        )
    n = A.shape[0]
    if n != len(names):
        raise ValueError(
            f"the matrix is {n}x{n} but {len(names)} criteria were named. Row i "
            f"binds to criterion i, so the two must agree."
        )
    if n == 0:
        raise ValueError("no criteria")
    if np.any(A <= 0):
        raise ValueError(
            "every judgment must be strictly positive; a zero or negative "
            "entry is not a ratio"
        )
    if not np.allclose(A * A.T, 1.0, atol=1e-6):
        bad = np.argwhere(~np.isclose(A * A.T, 1.0, atol=1e-6))
        i, j = bad[0]
        raise ValueError(
            f"the matrix is not reciprocal: A[{i},{j}] * A[{j},{i}] = "
            f"{A[i, j] * A[j, i]:.4f}, not 1. Build it with "
            f"`reciprocal_matrix`, which makes that structural."
        )
    if n > MAX_CRITERIA:
        raise ValueError(
            f"{n} criteria: Saaty's random index table is published to "
            f"{MAX_CRITERIA}. Reusing RI({MAX_CRITERIA}) beyond it would "
            f"manufacture a consistency ratio the literature does not support. "
            f"Group the criteria hierarchically instead — {n} criteria is "
            f"{n * (n - 1) // 2} pairwise judgments."
        )

    # Principal eigenvector. The eigen decomposition is exact for a consistent
    # matrix and the standard estimate otherwise; the column-normalization
    # average is an approximation that disagrees with lambda_max.
    values, vectors = np.linalg.eig(A)
    principal = int(np.argmax(values.real))
    vector = np.abs(vectors[:, principal].real)
    w = vector / vector.sum()
    lambda_max = float(values.real[principal])

    if n <= 2:
        # Any 2x2 reciprocal matrix is consistent by construction: there is
        # only one judgment and nothing for it to contradict.
        ci = cr = 0.0
        ri = 0.0
        consistent = True
    else:
        ci = (lambda_max - n) / (n - 1)
        ri = RANDOM_INDEX[n]
        cr = ci / ri if ri > 0 else 0.0
        consistent = cr < threshold

    warnings: list[str] = []
    smallest = float(w.min())
    if n >= 4 and smallest < 0.02:
        warnings.append(
            f"criterion {names[int(np.argmin(w))]!r} carries weight "
            f"{smallest:.3f}; below about 0.02 a criterion cannot change the "
            f"map and is better dropped than kept for appearance"
        )

    if not consistent and not override_reason:
        raise InconsistentMatrixError(
            f"the comparison matrix is inconsistent: CR = {cr:.4f}, above the "
            f"{threshold:.2f} threshold (lambda_max = {lambda_max:.4f}, "
            f"CI = {ci:.4f}, RI = {ri:.2f}). Revise the judgments — a CR this "
            f"high means at least one triple contradicts another — or record a "
            f"written justification to proceed."
        )
    if not consistent:
        warnings.append(
            f"proceeding with CR = {cr:.4f} above the {threshold:.2f} "
            f"threshold, on a recorded override"
        )

    return AhpResult(
        names=list(names), weights=w, lambda_max=lambda_max, ci=float(ci),
        ri=float(ri), cr=float(cr), threshold=float(threshold),
        consistent=bool(consistent), override=override_reason, warnings=warnings,
    )


def group_weights(
    group_result: AhpResult, within: dict[str, AhpResult]
) -> dict[str, float]:
    """Combine a group-level AHP with a per-group one.

    group_result  weights over the groups themselves
    within        {group name: AHP over that group's criteria}
    returns       {criterion name: global weight}, summing to 1

    Section 15.1's remedy for double counting. Three criteria derived from one
    piece of evidence — heat flow, gradient, temperature — share a group and so
    share its weight, instead of each drawing an independent one and giving
    that evidence three times its due.
    """
    global_weights: dict[str, float] = {}
    for group, weight in group_result.weights_by_name.items():
        inner = within.get(group)
        if inner is None:
            raise KeyError(
                f"group {group!r} has a weight but no criteria beneath it"
            )
        for name, share in inner.weights_by_name.items():
            global_weights[name] = weight * share
    total = sum(global_weights.values())
    if not np.isclose(total, 1.0, atol=1e-9):
        raise ValueError(f"global weights sum to {total}, not 1")
    return global_weights
