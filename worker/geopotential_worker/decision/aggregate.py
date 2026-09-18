"""Combining normalized criteria into a suitability map.

Four operators, one null rule, and a great deal of refusing.

The null rule, stated once and applied identically by all four: **a score is
defined only where every contributing criterion is valid.** Where one is
unknown there is no defensible score, and the two ways of inventing one —
treating the null as zero, or renormalizing the weights over whatever happens
to be present — both state a confidence nobody has. Two operators in one
program disagreeing about nulls is the defect this paragraph exists to prevent.

References:
  Zimmermann and Zysno (1980), Fuzzy Sets and Systems 4(1), sec. 3 — gamma.
  Saaty (1980) — the weights WLC consumes.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from ..domain.criterion import CriterionStack

EPS = 1e-12


def _stacked(stack: CriterionStack) -> np.ndarray:
    """The stack as (n, h, w), after refusing anything not NORMALIZED."""
    stack.require_normalized()
    if len(stack) == 0:
        raise ValueError("no criteria to aggregate")
    return stack.stacked()


def _valid_everywhere(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values).all(axis=0)


def fuzzy_product(stack: CriterionStack) -> np.ndarray:
    """Algebraic product: mu = prod(mu_i).

    stack    every criterion NORMALIZED, on one grid
    returns  (h, w) float32 in [0, 1], NaN where any criterion is null

    Strictly AND-like and unforgiving: one low membership drags the result
    down however good the rest are. Use it where a single unfavourable
    criterion genuinely disqualifies a location.
    """
    values = _stacked(stack)
    valid = _valid_everywhere(values)
    out = np.full(values.shape[1:], np.nan, dtype=np.float32)
    out[valid] = np.prod(values[:, valid], axis=0)
    return out


def fuzzy_sum(stack: CriterionStack) -> np.ndarray:
    """Algebraic sum: mu = 1 - prod(1 - mu_i).

    stack    every criterion NORMALIZED, on one grid
    returns  (h, w) float32 in [0, 1], NaN where any criterion is null

    OR-like and generous: any one high membership pulls the result up. The
    result is never lower than the largest input, which is what makes it the
    opposite pole from the product.
    """
    values = _stacked(stack)
    valid = _valid_everywhere(values)
    out = np.full(values.shape[1:], np.nan, dtype=np.float32)
    out[valid] = 1.0 - np.prod(1.0 - values[:, valid], axis=0)
    return out


def fuzzy_gamma(stack: CriterionStack, gamma: float) -> np.ndarray:
    """Gamma operator: mu = (1 - prod(1 - mu_i))^gamma * (prod mu_i)^(1 - gamma).

    stack    every criterion NORMALIZED, on one grid
    gamma    in [0, 1]; 0 is the algebraic product, 1 the algebraic sum
    returns  (h, w) float32 in [0, 1], NaN where any criterion is null

    Zimmermann and Zysno (1980), Fuzzy Sets and Systems 4(1), sec. 3.

    Gamma is a compensation parameter, not a tuning knob: it says how much a
    strong criterion is allowed to make up for a weak one. It belongs in the
    manifest, and a map made at 0.7 is not the map made at 0.9.
    """
    if not 0.0 <= gamma <= 1.0:
        raise ValueError(
            f"gamma must be in [0, 1]; got {gamma}. Outside that range the "
            f"operator is no longer a weighted compromise between the "
            f"algebraic product and the algebraic sum, and Zimmermann and "
            f"Zysno's interpretation does not hold."
        )
    values = _stacked(stack)
    valid = _valid_everywhere(values)
    out = np.full(values.shape[1:], np.nan, dtype=np.float32)
    subset = values[:, valid]
    algebraic_sum = 1.0 - np.prod(1.0 - subset, axis=0)
    algebraic_product = np.prod(subset, axis=0)
    out[valid] = (algebraic_sum ** gamma) * (algebraic_product ** (1.0 - gamma))
    return np.clip(out, 0.0, 1.0, out=out)


def weighted_linear_combination(
    stack: CriterionStack,
    weights: dict[str, float],
    *,
    constraints: Sequence[np.ndarray] = (),
) -> np.ndarray:
    """WLC: S = (sum w_i * v_i) * prod(c_j).

    stack        every criterion NORMALIZED, on one grid
    weights      {criterion name: weight}, summing to 1
    constraints  boolean masks; a location excluded by any is excluded
    returns      (h, w) float32 in [0, 1], NaN where any criterion is null

    A factor is continuous and weighted; a constraint is boolean and
    multiplies. Letting one become the other through a configuration field is
    how a soft preference silently becomes a veto.

    The weights are looked up **by criterion name**, not by position in a dict:
    the stack's order is authoritative, and a missing or extra name is refused
    rather than quietly zero.
    """
    values = _stacked(stack)
    names = stack.names

    missing = [n for n in names if n not in weights]
    extra = [n for n in weights if n not in names]
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"no weight for {', '.join(repr(n) for n in missing)}")
        if extra:
            parts.append(
                f"weight given for {', '.join(repr(n) for n in extra)}, which "
                f"is not in the stack"
            )
        raise ValueError(
            "; ".join(parts)
            + f". The stack is: {', '.join(names)}."
        )

    ordered = np.array([weights[n] for n in names], dtype=np.float64)
    total = ordered.sum()
    if not np.isclose(total, 1.0, atol=1e-6):
        raise ValueError(
            f"the weights sum to {total:.6f}, not 1. Renormalizing them here "
            f"would silently change the result's scale, so it is refused: "
            f"normalize them deliberately and record that you did."
        )
    if np.any(ordered < 0):
        raise ValueError("a negative weight is not a preference; refuse it")

    valid = _valid_everywhere(values)
    out = np.full(values.shape[1:], np.nan, dtype=np.float32)
    out[valid] = np.tensordot(ordered, values[:, valid], axes=(0, 0))

    for index, constraint in enumerate(constraints):
        mask = np.asarray(constraint)
        if mask.shape != out.shape:
            raise ValueError(
                f"constraint {index} is {mask.shape}, the grid is {out.shape}"
            )
        if mask.dtype != bool:
            unique = np.unique(mask[np.isfinite(mask)])
            if not np.all(np.isin(unique, (0, 1))):
                raise ValueError(
                    f"constraint {index} holds values other than 0 and 1 "
                    f"({unique[:5]}). A constraint is boolean and multiplies; a "
                    f"continuous layer is a factor and is weighted."
                )
            mask = mask.astype(bool)
        out[~mask] = 0.0

    return np.clip(out, 0.0, 1.0, out=out)


def apply_mask(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Restrict a result to a mask — an AOI, or a common validity mask.

    Outside the mask the result becomes NaN, not zero: outside an area of
    interest a score was not computed, and zero would read as "computed, and
    unfavourable".
    """
    if mask.shape != values.shape:
        raise ValueError(f"mask is {mask.shape}, values are {values.shape}")
    out = values.copy()
    out[~mask.astype(bool)] = np.nan
    return out


#: The operators, by the name the registry exposes.
OPERATORS = {
    "fuzzy_gamma": fuzzy_gamma,
    "fuzzy_product": fuzzy_product,
    "fuzzy_sum": fuzzy_sum,
    "weighted_linear_combination": weighted_linear_combination,
}


def describe_result(values: np.ndarray, method: str) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    return {
        "method": method,
        "unit": "suitability [0-1], dimensionless",
        "valid_fraction": float(np.isfinite(values).mean()),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean(dtype=np.float64)) if finite.size else None,
    }
