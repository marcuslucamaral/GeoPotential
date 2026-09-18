"""How much the answer moves when a choice changes. MSP-11, §17.3-17.6.

inputs   a CriterionStack of NORMALIZED criteria, and the aggregation that
         produced the map being questioned
output   per scenario: how far the map moved, and how far the *ranking* moved
unit     the score is dimensionless in [0,1]; Spearman rho is dimensionless
reference  Spearman, C. (1904), "The proof and measurement of association
           between two things", Am. J. Psychol. 15(1), 72-101; Saltelli et al.
           (2008), "Global Sensitivity Analysis: The Primer", ch. 1, for the
           one-at-a-time design and its limits.

**One at a time, and that is a stated limit.** Every sweep here moves one
choice and holds the rest. That answers "does this criterion matter" and does
not answer "do these two matter together": interactions between parameters are
invisible to a one-at-a-time design, which is exactly what Saltelli warns
about. Saying so here is cheaper than a reader assuming otherwise.

**Rankings are compared on the cells every scenario could answer.** Dropping a
criterion changes which cells are null — a score needs every criterion
(ADR-004) — so the baseline and the scenario have different valid masks.
Comparing rankings over different sets of cells is not comparing rankings, and
the intersection is what the comparison uses. Its size is reported next to
every number, because a correlation over 300 cells and one over 300 000 are
not the same evidence.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from ..domain.criterion import CriterionStack

#: Below this many cells in common, a rank correlation is noise dressed as a
#: number. The scenario still reports its other measures and says why rho is
#: absent, rather than printing a figure nobody should act on.
MIN_CELLS_FOR_RANK = 30


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    """Rank correlation between two score maps, over the cells both answered.

    inputs   two arrays of the same shape; NaN means "this cell has no score"
    output   rho in [-1, 1], or None when too few cells are shared
    reference  Spearman (1904)

    Ties are averaged, which is what makes this Spearman and not a correlation
    of `argsort`: a suitability map with a masked plateau has thousands of
    identical values, and ranking them arbitrarily invents an ordering the data
    does not have.
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    both = np.isfinite(a) & np.isfinite(b)
    if int(both.sum()) < MIN_CELLS_FOR_RANK:
        return None
    from scipy.stats import rankdata

    ra = rankdata(a[both])
    rb = rankdata(b[both])
    if ra.std() == 0 or rb.std() == 0:
        # A constant map has no ranking to correlate. That is a real answer.
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def compare(baseline: np.ndarray, scenario: np.ndarray,
            top_fraction: float = 0.1) -> dict[str, Any]:
    """How far one map moved from another.

    top_fraction  the head of the distribution that a prospector actually
                  visits. The default 0.1 is the top decile; it is a parameter
                  because "the best 10 %" is a choice, not a fact.
    returns  every number with the count it was measured over
    """
    baseline = np.asarray(baseline, dtype=np.float64)
    scenario = np.asarray(scenario, dtype=np.float64)
    if baseline.shape != scenario.shape:
        raise ValueError(
            f"the two maps are not the same shape: {baseline.shape} and "
            f"{scenario.shape}. They are not comparable cell by cell."
        )

    both = np.isfinite(baseline) & np.isfinite(scenario)
    shared = int(both.sum())
    if shared == 0:
        return {"cells_compared": 0, "mean_abs_change": None,
                "max_abs_change": None, "spearman": None,
                "top_agreement": None, "top_fraction": float(top_fraction),
                "note": "the two maps share no cell with a score in both"}

    difference = scenario[both] - baseline[both]
    result: dict[str, Any] = {
        "cells_compared": shared,
        "cells_baseline": int(np.isfinite(baseline).sum()),
        "cells_scenario": int(np.isfinite(scenario).sum()),
        "mean_abs_change": float(np.abs(difference).mean()),
        "max_abs_change": float(np.abs(difference).max()),
        "mean_change": float(difference.mean()),
        "spearman": spearman(baseline, scenario),
        "top_fraction": float(top_fraction),
    }

    # What a prospector would actually notice: whether the same places are
    # still in the head of the distribution. A rho of 0.98 with a completely
    # reshuffled top decile is a map that moved where it mattered.
    keep = max(1, int(round(shared * float(top_fraction))))
    base_top = set(np.argsort(baseline[both])[-keep:].tolist())
    scen_top = set(np.argsort(scenario[both])[-keep:].tolist())
    result["top_cells"] = keep
    result["top_agreement"] = float(len(base_top & scen_top) / keep)
    return result


def leave_one_out(
    stack: CriterionStack,
    aggregate: Callable[[CriterionStack, dict[str, float] | None], np.ndarray],
    weights: dict[str, float] | None = None,
    *,
    top_fraction: float = 0.1,
) -> dict[str, Any]:
    """Drop each criterion in turn and measure what the map loses. §17.3.

    stack      the criteria the baseline was built from, NORMALIZED
    aggregate  f(stack, weights) -> score map. Passed in rather than chosen
               here: the scenario has to use the *same* operator the run used,
               and this module does not get to decide which.
    weights    the baseline's weights, or None for an unweighted operator
    returns    {"baseline": ..., "criteria": [per-criterion comparison]}

    raises     ValueError when the stack has fewer than two criteria — there is
               no "without one" of a single criterion, and returning zeros
               would be an answer to a question nobody asked.
    """
    names = list(stack.names)
    if len(names) < 2:
        raise ValueError(
            f"leave-one-out needs at least two criteria; this analysis has "
            f"{len(names)}. With one criterion the map *is* the criterion."
        )

    baseline = aggregate(stack, weights)
    rows = []
    for dropped in names:
        kept = [c for c in stack if c.name != dropped]
        kept_weights = _renormalized(weights, [c.name for c in kept])
        scenario = aggregate(CriterionStack(kept), kept_weights)
        row = {
            "dropped": dropped,
            "weight": None if not weights else float(weights.get(dropped, 0.0)),
            **compare(baseline, scenario, top_fraction=top_fraction),
        }
        # Renormalising is the only honest way to keep an operator that
        # requires weights summing to 1 (P-93), and it is *said* rather than
        # done quietly: the remaining criteria are not carrying their original
        # weights any more.
        row["weights_renormalized"] = kept_weights is not None
        rows.append(row)

    # The criterion whose removal moves the map most is the one the answer
    # leans on. Ordered so the reader does not have to sort a table.
    rows.sort(key=lambda r: (r["mean_abs_change"] is None,
                             -(r["mean_abs_change"] or 0.0)))
    return {
        "design": "leave-one-criterion-out, one at a time",
        "limitation": ("a one-at-a-time design cannot see interactions between "
                       "criteria; Saltelli et al. (2008), ch. 1"),
        "criterion_order": names,
        "baseline_cells": int(np.isfinite(baseline).sum()),
        "criteria": rows,
    }


def sweep(
    values: list[float],
    build: Callable[[float], np.ndarray],
    baseline: np.ndarray,
    *,
    parameter: str,
    top_fraction: float = 0.1,
) -> dict[str, Any]:
    """Vary one parameter across a list of values and measure each map.

    values     what to try. A list and not a range: the caller decides the
               grid, and an irregular one (0.0, 0.5, 0.7, 0.9, 1.0) is often
               what a person actually wants to see.
    build      f(value) -> score map
    baseline   the map the run produced, to compare each against
    parameter  its name, for the result to be readable on its own

    returns    one row per value, plus the span of the whole sweep
    """
    if not values:
        raise ValueError(f"a sweep over {parameter!r} needs at least one value")

    rows = []
    for value in values:
        rows.append({"value": float(value),
                     **compare(baseline, build(float(value)),
                               top_fraction=top_fraction)})

    moves = [r["mean_abs_change"] for r in rows
             if r["mean_abs_change"] is not None]
    agreements = [r["top_agreement"] for r in rows
                  if r["top_agreement"] is not None]
    return {
        "parameter": parameter,
        "values": [float(v) for v in values],
        "rows": rows,
        # The two numbers that say whether this parameter matters at all.
        "worst_mean_abs_change": max(moves) if moves else None,
        "worst_top_agreement": min(agreements) if agreements else None,
    }


def _renormalized(weights: dict[str, float] | None,
                  keep: list[str]) -> dict[str, float] | None:
    """The weights of the criteria that stayed, summing to 1 again.

    Returns None when the operator carries no weights. Raises when every
    remaining weight is zero: renormalising that is a division by zero wearing
    a helpful expression.
    """
    if not weights:
        return None
    remaining = {name: float(weights.get(name, 0.0)) for name in keep}
    total = sum(remaining.values())
    if total <= 0:
        raise ValueError(
            "dropping this criterion leaves every remaining weight at zero; "
            "there is no analysis left to compare against."
        )
    return {name: value / total for name, value in remaining.items()}
