"""The operator registry.

An operator that is not registered cannot be run. The registry is also what the
worker announces in `hello.capabilities`, so the app never offers an operation
the worker on the other end of the pipe cannot perform.

Declared but not implemented is stated here rather than discovered at runtime:
`PLANNED` names what the milestones will add, so the interface can show it
disabled with the reason instead of failing after a click.
"""
from __future__ import annotations

from .base import Operator
from .difference_op import DifferenceOperator
from .extent_op import ComparePoliciesOperator
from .gridding_op import (
    CrossValidateOperator,
    EuclideanDistanceOperator,
    IdwOperator,
    RasterizeOperator,
    TinCubicOperator,
    TinLinearOperator,
)
from .inspect_op import DescribeDatasetOperator, ValidateDatasetOperator
from .mcda_op import (
    AggregateOperator,
    AhpWeightsOperator,
    HarmonizeOperator,
)
from .membership_op import MembershipOperator
from .potential_fields_op import (
    AnalyticSignalOperator,
    DerivativeOperator,
    RadialSpectrumOperator,
    ReductionToPoleOperator,
    RegionalResidualOperator,
    TiltOperator,
    TotalHorizontalGradientOperator,
    UpwardContinuationOperator,
)
from .scenarios_op import (
    ExplainOperator,
    LeaveOneOutOperator,
    ManifestOperator,
    RankTargetsOperator,
    SensitivityOperator,
)

_OPERATORS: dict[str, Operator] = {}


def register(operator: Operator) -> Operator:
    if operator.name in _OPERATORS:
        raise ValueError(f"operator {operator.name!r} is already registered")
    _OPERATORS[operator.name] = operator
    return operator


def get(name: str) -> Operator:
    """Look up an operator by name.

    raises  KeyError naming what is available, not a bare KeyError
    """
    try:
        return _OPERATORS[name]
    except KeyError:
        known = ", ".join(sorted(_OPERATORS)) or "none"
        planned = PLANNED.get(name)
        hint = f"; it is planned for milestone {planned}" if planned else ""
        raise KeyError(
            f"unknown operator {name!r}{hint}. Registered: {known}"
        ) from None


def capabilities() -> list[str]:
    """The operator names this worker announces in `hello`."""
    return sorted(_OPERATORS)


def describe_all() -> list[dict[str, object]]:
    return [op.describe() for op in _OPERATORS.values()]


register(DescribeDatasetOperator())
register(ValidateDatasetOperator())
register(MembershipOperator())
register(DifferenceOperator())
register(HarmonizeOperator())
register(ComparePoliciesOperator())
register(AhpWeightsOperator())
register(AggregateOperator())
register(IdwOperator())
register(TinLinearOperator())
register(TinCubicOperator())
register(EuclideanDistanceOperator())
register(RasterizeOperator())
register(CrossValidateOperator())
register(LeaveOneOutOperator())
register(SensitivityOperator())
register(ExplainOperator())
register(RankTargetsOperator())
register(ManifestOperator())
register(DerivativeOperator())
register(TotalHorizontalGradientOperator())
register(AnalyticSignalOperator())
register(TiltOperator())
register(UpwardContinuationOperator())
register(RegionalResidualOperator())
register(ReductionToPoleOperator())
register(RadialSpectrumOperator())

#: Operators the milestones will add, with the milestone that adds each.
#:
#: A name here must always point at a milestone that has **not** closed. Three
#: of them pointed at M5 after M5 shipped, so the application answered "it is
#: planned for milestone M5" to someone standing in M5.5 — and importing was
#: listed as a future operator while it had been a command since M3.
#: The interface shows these disabled and says which milestone owns them,
#: rather than offering an operation that fails after the click.
PLANNED: dict[str, str] = {
    "reporting.report": "M8",
}
