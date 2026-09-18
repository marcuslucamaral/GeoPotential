"""A criterion of one MCDA analysis, and the stack of them.

A raw criterion and a normalized criterion are not the same value. Raw carries
a physical unit; normalized carries a dimensionless membership in [0, 1].
Never under the same name, never aggregated unless NORMALIZED.

This is the guard that makes the legacy defect D-01 impossible before any
method is written: `normalize_subroutine` wrote the membership over the raw
physical values under the key `array`, and nothing in the data marked which
stage a dictionary was in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator, Sequence

import numpy as np

from .grid import TargetGrid


class Stage(str, Enum):
    """What a criterion's values mean. Never absent, never both."""

    RAW = "RAW"                # a physical quantity, with `unit`
    NORMALIZED = "NORMALIZED"  # a dimensionless membership in [0, 1]


class StageError(TypeError):
    """A raw criterion reached an operation defined only on normalized ones."""


@dataclass
class Criterion:
    """One layer of one analysis, on the run's target grid.

    name    the criterion's name; weights bind to it by position in the stack
    values  (grid.height, grid.width) float32, NaN for null
    grid    the run's target grid; every criterion shares it
    stage   RAW or NORMALIZED
    unit    physical unit when RAW ('mGal', 'g/cm3', 'm', 'degC', 'mW/m2');
            must be None when NORMALIZED
    higher_is_better  part of the scientific claim, not a display preference
    provenance        how these values were produced; goes into the manifest
    """

    name: str
    values: np.ndarray
    grid: TargetGrid
    stage: Stage
    unit: str | None = None
    higher_is_better: bool = True
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.values.shape != self.grid.shape:
            raise ValueError(
                f"criterion {self.name!r}: values are {self.values.shape}, "
                f"grid is {self.grid.shape}"
            )
        if self.values.dtype != np.float32:
            raise TypeError(
                f"criterion {self.name!r}: values must be float32, "
                f"got {self.values.dtype}"
            )
        if self.stage is Stage.NORMALIZED:
            if self.unit is not None:
                raise ValueError(
                    f"criterion {self.name!r}: NORMALIZED is dimensionless; "
                    f"it cannot carry unit {self.unit!r}"
                )
            valid = np.isfinite(self.values)
            if valid.any():
                lo = float(np.nanmin(self.values[valid]))
                hi = float(np.nanmax(self.values[valid]))
                if lo < -1e-6 or hi > 1 + 1e-6:
                    raise ValueError(
                        f"criterion {self.name!r}: NORMALIZED must be in [0, 1]; "
                        f"got [{lo:.6g}, {hi:.6g}]"
                    )
        elif self.unit is None:
            raise ValueError(
                f"criterion {self.name!r}: a RAW criterion must declare its unit"
            )

    @property
    def valid_mask(self) -> np.ndarray:
        """True where the pixel carries data. NaN is the single in-memory null."""
        return np.isfinite(self.values)

    @property
    def valid_fraction(self) -> float:
        return float(self.valid_mask.mean())

    def describe(self) -> dict[str, Any]:
        valid = self.valid_mask
        stats: dict[str, Any] = {
            "name": self.name,
            "stage": self.stage.value,
            "unit": self.unit or "dimensionless [0-1]",
            "higher_is_better": self.higher_is_better,
            "valid_fraction": self.valid_fraction,
        }
        if valid.any():
            v = self.values[valid]
            stats |= {
                "min": float(v.min()),
                "max": float(v.max()),
                "mean": float(v.mean()),
            }
        return stats


class CriterionStack:
    """The criteria of one run, in the order weights bind to.

    `names` is the canonical criterion order. An AHP matrix row `i` binds to
    `names[i]`, and that binding is explicit. Deriving the order from
    `list(some_dict.keys())` at two call sites is how weights end up on the
    wrong layers with no error anywhere — defect D-06.
    """

    def __init__(self, criteria: Sequence[Criterion] = ()) -> None:
        self._criteria: list[Criterion] = list(criteria)
        self._check_common_grid()

    def _check_common_grid(self) -> None:
        if not self._criteria:
            return
        grid = self._criteria[0].grid
        for c in self._criteria[1:]:
            if c.grid != grid:
                raise ValueError(
                    f"criterion {c.name!r} is on a different grid from "
                    f"{self._criteria[0].name!r}; harmonize before stacking"
                )

    def add(self, criterion: Criterion) -> None:
        if any(c.name == criterion.name for c in self._criteria):
            raise ValueError(f"criterion {criterion.name!r} is already in the stack")
        self._criteria.append(criterion)
        self._check_common_grid()

    def __len__(self) -> int:
        return len(self._criteria)

    def __iter__(self) -> Iterator[Criterion]:
        return iter(self._criteria)

    def __getitem__(self, index: int) -> Criterion:
        return self._criteria[index]

    @property
    def names(self) -> list[str]:
        """The canonical criterion order. Weights bind to this, by position."""
        return [c.name for c in self._criteria]

    @property
    def grid(self) -> TargetGrid:
        if not self._criteria:
            raise ValueError("an empty stack has no grid")
        return self._criteria[0].grid

    def require_normalized(self) -> None:
        """Refuse the stack if any criterion is still RAW, naming it.

        raises  StageError listing every raw criterion

        Aggregation is defined only on memberships. Passing a raw layer to a
        Gamma Fuzzy or WLC operator is a programming error and must raise, not
        clamp.
        """
        raw = [c.name for c in self._criteria if c.stage is not Stage.NORMALIZED]
        if raw:
            raise StageError(
                "aggregation accepts NORMALIZED criteria only; still RAW: "
                + ", ".join(repr(n) for n in raw)
            )

    def stacked(self) -> np.ndarray:
        """(n_criteria, height, width) float32, in `names` order."""
        if not self._criteria:
            raise ValueError("an empty stack cannot be stacked")
        return np.stack([c.values for c in self._criteria])
