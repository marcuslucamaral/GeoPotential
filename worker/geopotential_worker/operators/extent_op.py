"""`grid.compare_policies` — what each extent policy would actually produce.

Intersection and union are **different maps**, not two spellings of one: an
intersection answers "where do we know everything" and a union answers "where
do we know anything". Measured on the Utah FORGE chain the difference is the
whole result — 100 % of cells carry a score under intersection and 27,7 % under
union — and until this operator existed the choice was made on the harmonize
screen before either number could be seen.

It is **read-only**: it registers no run and writes no artefact. The estimate
is produced by calling `harmonize` itself on a decimated grid, so it cannot
drift from the operator whose result it predicts. What it costs is one coarse
reprojection per layer per policy; what it buys is the choice stopping being
blind.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from affine import Affine

from ..domain.crs import CrsInfo
from ..domain.grid import TargetGrid
from ..grid.harmonize import (
    ExtentPolicy,
    LayerSpec,
    build_target_grid,
    harmonize,
)
from ..io.readers import read_raster
from .base import Context, Operator, Parameter, ParameterError

#: Cells the estimate may use per policy. A fraction converges long before
#: the grid is full resolution; 512x512 keeps the probe under a second per
#: layer on the datasets this project ships.
#:
#: Named `estimate`, never `preview`: in this project a **preview** is the
#: bounded, decimated array that crosses the IPC for drawing (ADR-MSP-004),
#: and `P-117` forbids any operator taking one as input. This is a different
#: quantity, so it gets a different name.
DEFAULT_ESTIMATE_CELLS = 262_144


def _decimated(grid: TargetGrid, max_cells: int) -> tuple[TargetGrid, int]:
    """The same extent at a coarser pixel, and the factor used.

    grid       the real analysis grid the policy would produce
    max_cells  the budget for the estimate
    returns    (coarse grid, decimation factor >= 1)

    The extent is preserved exactly; only the pixel grows. Shrinking the
    extent instead would answer a question about a different map.
    """
    if grid.pixel_count <= max_cells:
        return grid, 1
    factor = int(math.ceil(math.sqrt(grid.pixel_count / max_cells)))
    px, py = grid.pixel_size
    left, _, _, top = grid.bounds
    width = max(1, grid.width // factor)
    height = max(1, grid.height // factor)
    transform = Affine(px * factor, 0.0, left, 0.0, -py * factor, top)
    return TargetGrid(transform=transform, crs=grid.crs,
                      width=width, height=height), factor


def _scored_fraction(
    specs: Sequence[LayerSpec], grid: TargetGrid, ctx: Context,
    progress: tuple[float, float],
) -> tuple[float, list[float]]:
    """The fraction of cells where **every** layer has a value, and each alone.

    returns  (fraction with all layers present, per-layer valid fractions)

    A score needs all its criteria (ADR-004), so the cells that will carry one
    are the intersection of the layers' masks — never their union, however the
    grid's own extent was chosen.
    """
    together: np.ndarray | None = None
    per_layer: list[float] = []
    start, span = progress
    for index, spec in enumerate(specs, 1):
        ctx.check_cancel()
        values, _ = harmonize(spec, grid)
        mask = np.isfinite(values)
        per_layer.append(float(mask.mean()))
        together = mask if together is None else (together & mask)
        ctx.progress("measure", start + span * index / len(specs),
                     f"{Path(spec.path).name} on {grid.width}x{grid.height}")
    return (float(together.mean()) if together is not None else 0.0), per_layer


class ComparePoliciesOperator(Operator):
    """Measure both extent policies before either is chosen. Write nothing."""

    name = "grid.compare_policies"
    version = "1.0.0"
    read_only = True
    summary = ("Report the grid and the share of cells that would carry a "
               "score under each extent policy, without harmonizing.")
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06, ADR-MSP-004."

    parameters = (
        Parameter(name="target_crs", type="str", required=True,
                  doc="CRS of the analysis grid. There is no default."),
        Parameter(name="pixel_size", type="float", required=True,
                  unit="CRS unit", minimum=1e-9,
                  doc="Square pixel of the analysis grid, in the target CRS unit."),
        Parameter(name="layers", type="list", required=True,
                  doc="[{path, name, unit, resampling, categorical}], the same "
                      "shape `grid.harmonize` takes."),
        Parameter(name="estimate_cells", type="int",
                  default=DEFAULT_ESTIMATE_CELLS, minimum=256,
                  unit="cells",
                  doc="Budget for the decimated grid the estimate runs on."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        specs = [LayerSpec(**dict(layer)) for layer in params["layers"]]
        if not specs:
            raise ParameterError(f"{self.name}: no layers given")

        ctx.progress("read", 0.0, f"reading {len(specs)} layers")
        sources = []
        for index, spec in enumerate(specs, 1):
            ctx.check_cancel()
            sources.append(read_raster(spec.path))
            ctx.progress("read", 0.2 * index / len(specs), Path(spec.path).name)

        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("harmonization to a metric grid")
        pixel = (params["pixel_size"], params["pixel_size"])
        budget = int(params["estimate_cells"])

        policies: list[dict[str, Any]] = []
        for slot, policy in enumerate(ExtentPolicy):
            ctx.check_cancel()
            try:
                grid = build_target_grid(sources, target_crs, pixel,
                                         policy=policy)
            except ValueError as exc:
                # An empty intersection is an answer, not a failure: it is
                # precisely what the person needs to know before choosing it.
                policies.append({
                    "policy": policy.value,
                    "available": False,
                    "reason": str(exc),
                })
                continue

            coarse, factor = _decimated(grid, budget)
            fraction, per_layer = _scored_fraction(
                specs, coarse, ctx, (0.2 + 0.4 * slot, 0.4))
            left, bottom, right, top = grid.bounds
            policies.append({
                "policy": policy.value,
                "available": True,
                "width": grid.width,
                "height": grid.height,
                "cells": grid.pixel_count,
                "bounds": [left, bottom, right, top],
                # The number the choice turns on: cells that would carry a
                # score, which needs every criterion present (ADR-004).
                "scored_fraction": fraction,
                "scored_cells": int(round(fraction * grid.pixel_count)),
                "per_layer_fraction": [
                    {"name": spec.name, "fraction": value}
                    for spec, value in zip(specs, per_layer)
                ],
                # Stated, never implied: this is an estimate, and this is the
                # grid it was estimated on.
                "estimated": factor > 1,
                "estimate_width": coarse.width,
                "estimate_height": coarse.height,
                "decimation": factor,
            })

        ctx.progress("measure", 1.0, "both policies measured")
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "target_crs": target_crs.name,
            "pixel_size": params["pixel_size"],
            "layers": [spec.name for spec in specs],
            "policies": policies,
        }
