"""Why this cell scored what it scored, and which cells are the targets.

inputs   a CriterionStack of NORMALIZED criteria and the aggregation used
output   per target: the score, the valid fraction, and what each criterion
         contributed to it
unit     memberships and scores are dimensionless in [0,1]; a share is a
         fraction of the score and sums to 1 over the criteria
reference  Zimmermann and Zysno (1980) for the fuzzy operators being
           decomposed; Saaty (1980) for the weights.

**A contribution means something different per operator, and the difference is
not cosmetic.**

`weighted_linear_combination` is a sum, so `w_i * m_i` is the criterion's
share of the score, exactly, and the shares add up to it. Nothing is being
approximated and the arithmetic can be checked by hand.

The fuzzy operators are products. There is no additive decomposition of a
product, so what is reported is the **share of the log** — for
`fuzzy_product`, `log m_i / sum_j log m_j`. That is a real and standard way to
read which factor pulled the product down, and it is **not** a share of the
score: multiplying the score by it gives a number with no meaning. The result
says which decomposition it used, in the payload, so nobody has to remember.

**A membership of exactly zero has no log.** One criterion at zero makes the
product zero regardless of the others, and that is the whole answer: the result
names that criterion as the veto rather than reporting shares of `-inf`.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..domain.criterion import CriterionStack

#: How a criterion's contribution was computed, per operator. Carried in every
#: result so a number is never read under the wrong meaning.
DECOMPOSITION = {
    "weighted_linear_combination": "additive: w_i * m_i, exact, shares sum to the score",
    "fuzzy_product": "log-share: log(m_i) / sum_j log(m_j); not a share of the score",
    "fuzzy_sum": "log-share of the complements: log(1-m_i) / sum_j log(1-m_j)",
    "fuzzy_gamma": ("log-share, weighted by gamma between the product and the "
                    "sum decompositions"),
}

#: A membership at or below this is a veto: it drives a product to zero and no
#: share of the remaining factors changes the answer.
VETO = 1e-12


def contributions(
    stack: CriterionStack,
    method: str,
    at: tuple[int, int],
    *,
    weights: dict[str, float] | None = None,
    gamma: float = 0.7,
) -> dict[str, Any]:
    """What each criterion contributed at one cell.

    at       (row, column) into the grid
    returns  {"cell", "memberships", "contributions", "decomposition", ...}
    raises   IndexError with the shape, when the cell is off the grid
    """
    row, column = int(at[0]), int(at[1])
    height, width = stack[0].values.shape
    if not (0 <= row < height and 0 <= column < width):
        raise IndexError(
            f"cell ({row}, {column}) is outside the grid, which is "
            f"{height} x {width}."
        )

    memberships = {c.name: float(c.values[row, column]) for c in stack}
    missing = [name for name, value in memberships.items()
               if not np.isfinite(value)]
    if missing:
        # A score needs every criterion (ADR-004), so a cell with a null is not
        # a low score — it is not a score.
        return {
            "cell": [row, column],
            "method": method,
            "memberships": memberships,
            "contributions": None,
            "decomposition": None,
            "scored": False,
            "reason": (f"no score here: {', '.join(missing)} "
                       f"{'has' if len(missing) == 1 else 'have'} no value at "
                       f"this cell, and a score needs every criterion"),
        }

    if method == "weighted_linear_combination":
        if not weights:
            raise ValueError(
                "weighted_linear_combination needs the weights that produced "
                "the map; without them a contribution is not defined."
            )
        parts = {name: float(weights[name]) * value
                 for name, value in memberships.items()}
        total = sum(parts.values())
    else:
        veto = [name for name, value in memberships.items()
                if (value <= VETO if method != "fuzzy_sum"
                    else (1.0 - value) <= VETO)]
        if veto:
            return {
                "cell": [row, column],
                "method": method,
                "memberships": memberships,
                "contributions": {name: (1.0 if name in veto else 0.0)
                                  for name in memberships},
                "decomposition": "veto",
                "scored": True,
                "veto": veto,
                "reason": (f"{', '.join(veto)} decides this cell on its own: a "
                           f"product is what it is regardless of the rest"),
            }
        parts = _log_parts(memberships, method, gamma)
        total = sum(parts.values())

    shares = ({name: value / total for name, value in parts.items()}
              if total not in (0.0,) else
              {name: 0.0 for name in parts})
    ranked = sorted(shares.items(), key=lambda kv: -kv[1])
    return {
        "cell": [row, column],
        "method": method,
        "memberships": memberships,
        "contributions": shares,
        "decomposition": DECOMPOSITION.get(method, "unknown"),
        "scored": True,
        "dominant": ranked[0][0] if ranked else None,
        "ranked": [name for name, _ in ranked],
    }


def _log_parts(memberships: dict[str, float], method: str,
               gamma: float) -> dict[str, float]:
    """The log magnitudes a fuzzy operator's factors carry at one cell."""
    if method == "fuzzy_sum":
        return {name: abs(float(np.log(1.0 - value)))
                for name, value in memberships.items()}
    product = {name: abs(float(np.log(value)))
               for name, value in memberships.items()}
    if method == "fuzzy_product":
        return product
    # fuzzy_gamma is product^(1-gamma) * sum^gamma, so the two decompositions
    # are mixed in exactly that proportion.
    complement = {name: abs(float(np.log(1.0 - value)))
                  if value < 1.0 else 0.0
                  for name, value in memberships.items()}
    return {name: (1.0 - gamma) * product[name] + gamma * complement[name]
            for name in memberships}


def rank_targets(
    score: np.ndarray,
    *,
    count: int = 10,
    min_separation: int = 5,
) -> dict[str, Any]:
    """The best places on the map, as places rather than as pixels.

    score            the suitability map; NaN where there is no score
    count            how many to return
    min_separation   cells. Two targets closer than this are the same
                     anomaly seen twice, and a list of ten pixels from one
                     hilltop is not a list of ten targets.

    returns  the targets, best first, each with its cell, score and rank

    **This ranks; it does not decide.** A high score is spatial favourability,
    not a resource, a reserve, thermal or electrical power, or economic
    viability, and the caller carries that sentence to the screen.
    """
    score = np.asarray(score, dtype=np.float64)
    valid = np.isfinite(score)
    if not valid.any():
        return {"targets": [], "count": 0, "valid_fraction": 0.0,
                "reason": "the map has no scored cell"}

    # NaN sorts to the *end* of an ascending argsort, so reversing puts the
    # null cells first and the very first candidate is never valid. Sorting a
    # copy with the nulls at negative infinity puts them where they belong:
    # after every cell that has a score.
    sortable = np.where(valid, score, -np.inf)
    order = np.argsort(sortable, axis=None)[::-1]
    height, width = score.shape
    chosen: list[dict[str, Any]] = []
    for flat in order:
        row, column = divmod(int(flat), width)
        if not valid[row, column]:
            break            # sorted descending: from here on it is all NaN
        if any(abs(row - t["cell"][0]) < min_separation
               and abs(column - t["cell"][1]) < min_separation
               for t in chosen):
            continue         # the same anomaly, one cell over
        chosen.append({
            "rank": len(chosen) + 1,
            "cell": [row, column],
            "score": float(score[row, column]),
        })
        if len(chosen) >= count:
            break

    return {
        "targets": chosen,
        "count": len(chosen),
        "requested": int(count),
        "min_separation_cells": int(min_separation),
        "valid_fraction": float(valid.mean()),
        "boundary": ("spatial favourability, not a resource, a reserve, "
                     "thermal or electrical power, or economic viability"),
    }
