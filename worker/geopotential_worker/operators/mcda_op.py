"""The operators that turn criteria into a prospectivity map.

`grid.harmonize`   many layers on many grids  -> one TargetGrid
`decision.ahp_weights`  a comparison matrix   -> weights, or a refusal
`decision.aggregate`    normalized criteria   -> suitability, with provenance

The manifest each writes is the reproducibility contract: inputs and hashes,
CRS, grid, per-layer method and parameters, aggregation method and parameters,
weights and the criterion order they bind to. A result with no manifest is not
a result.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..decision import aggregate as agg
from ..decision import membership as mf
from ..decision.ahp import (
    DEFAULT_CR_THRESHOLD,
    InconsistentMatrixError,
    weights as ahp_weights,
)
from ..decision.correlation import DEFAULT_THRESHOLD as CORRELATION_THRESHOLD
from ..decision.correlation import double_counting
from ..domain.crs import CrsInfo
from ..domain.criterion import Criterion, CriterionStack, Stage
from ..grid.harmonize import (
    ExtentPolicy,
    LayerSpec,
    build_target_grid,
    harmonize,
)
from ..grid.planner import plan_operation
from ..io.readers import read_raster
from ..io.writers import sha256_file, write_geotiff
from .base import Context, Operator, Parameter, ParameterError


class HarmonizeOperator(Operator):
    """Bring every input onto one target grid. MSP-06."""

    name = "grid.harmonize"
    version = "1.0.0"
    summary = "Reproject, resample and clip every layer onto one target grid."
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06."

    parameters = (
        Parameter(name="target_crs", type="str", required=True,
                  doc="CRS of the analysis grid. There is no default."),
        Parameter(name="pixel_size", type="float", required=True, unit="CRS unit",
                  minimum=1e-9,
                  doc="Square pixel of the analysis grid, in the target CRS unit."),
        Parameter(name="layers", type="list", required=True,
                  doc="[{path, name, unit, resampling, categorical}], in the "
                      "order the criteria will carry."),
        Parameter(name="extent_policy", type="str", default="intersection",
                  choices=("intersection", "union"),
                  doc="Intersection keeps only where every layer has data; "
                      "union keeps where any does. They are different maps."),
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
            ctx.progress("read", index / len(specs), Path(spec.path).name)

        ctx.progress("plan", 0.0, "deriving the target grid")
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("harmonization to a metric grid")
        grid = build_target_grid(
            sources, target_crs,
            (params["pixel_size"], params["pixel_size"]),
            policy=ExtentPolicy(params["extent_policy"]),
        )
        plan = plan_operation(
            "harmonize", width=grid.width, height=grid.height,
            layers=len(specs), output_layers=len(specs),
            output_dir=ctx.output_dir,
        )
        if not plan.fits:
            raise ValueError(f"{self.name}: {plan.reason}")
        ctx.progress("plan", 1.0, plan.summary())

        layers = []
        provenance = []
        for index, spec in enumerate(specs, 1):
            ctx.check_cancel()
            values, record = harmonize(spec, grid)
            artifact = write_geotiff(
                values, grid, ctx.output_dir / f"{spec.name}_harmonized.tif",
                tags={
                    "GEOPOTENTIAL_STAGE": "RAW",
                    "GEOPOTENTIAL_UNIT": spec.unit,
                    "GEOPOTENTIAL_CRITERION": spec.name,
                    "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                },
            )
            ctx.emit(f"{spec.name}_harmonized", artifact)
            record["artifact"] = str(artifact.path)
            record["hash"] = artifact.hash
            record["source_hash"] = sha256_file(Path(spec.path))
            provenance.append(record)
            layers.append(values)
            ctx.progress("harmonize", index / len(specs), spec.name)

        common = np.isfinite(np.stack(layers)).all(axis=0)
        ctx.progress("commit", 1.0,
                     f"{len(specs)} layers on {grid.width}x{grid.height}")
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": grid.describe(),
            "extent_policy": params["extent_policy"],
            "plan": plan.as_dict(),
            "layers": provenance,
            "common_validity_fraction": float(common.mean()),
        }


class AhpWeightsOperator(Operator):
    """Saaty weights from a comparison matrix, refusing an inconsistent one."""

    name = "decision.ahp_weights"
    version = "1.0.0"
    read_only = True
    summary = ("Weights from a reciprocal comparison matrix, with the "
               "consistency ratio as a refusal.")
    reference = "Saaty (1980), The Analytic Hierarchy Process, ch. 3."

    parameters = (
        Parameter(name="matrix", type="list", required=True,
                  doc="Square, strictly positive, reciprocal comparison matrix."),
        Parameter(name="names", type="list", required=True,
                  doc="Criterion names in the stack's order; row i binds to "
                      "names[i]."),
        Parameter(name="cr_threshold", type="float",
                  default=DEFAULT_CR_THRESHOLD, minimum=0.0, maximum=1.0,
                  unit="dimensionless",
                  doc="Consistency ratio above which the matrix is refused."),
        Parameter(name="override_reason", type="str", default="",
                  doc="Written justification for proceeding above the "
                      "threshold. Recorded in the manifest."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        ctx.progress("validate", 0.0, "checking the comparison matrix")
        try:
            result = ahp_weights(
                params["matrix"], params["names"],
                threshold=params["cr_threshold"],
                override_reason=params["override_reason"],
            )
        except InconsistentMatrixError as exc:
            # Surfaced as a parameter error so the application shows the
            # message rather than an internal-error placeholder: the operator
            # did nothing wrong, the judgments did.
            raise ParameterError(str(exc)) from exc
        ctx.progress("validate", 1.0,
                     f"CR = {result.cr:.4f} against {result.threshold:.2f}")
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "ahp": result.as_dict(),
            # Shaped like a QA/QC report so the application records it the same
            # way, in the same table. A consistency ratio *is* a validation, and
            # an accepted override is the single most important thing in the
            # audit trail: it is a person overruling a numerical check, and six
            # months later someone will need to know who, when and why.
            "report": self._as_report(result),
        }

    @staticmethod
    def _as_report(result) -> dict[str, Any]:  # noqa: ANN001
        findings = []
        if not result.consistent:
            findings.append({
                "rule": "ahp.consistency",
                "severity": "WARNING" if result.override else "BLOCKER",
                "dataset": "comparison matrix",
                "what": f"the consistency ratio is {result.cr:.4f}, above the "
                        f"{result.threshold:.2f} threshold.",
                "why": "A CR this high means the judgments contradict each "
                       "other, so the weights do not represent a coherent "
                       "preference.",
                "fix": result.override or "Revise the judgments, or record a "
                                          "written justification.",
                "message": f"comparison matrix: CR = {result.cr:.4f} "
                           f"(threshold {result.threshold:.2f})"
                           + (f"; overridden: {result.override}"
                              if result.override else ""),
            })
        for warning in result.warnings:
            findings.append({
                "rule": "ahp.warning", "severity": "WARNING",
                "dataset": "comparison matrix", "what": warning,
                "why": "", "fix": "", "message": warning,
            })
        return {
            "dataset": "comparison matrix",
            "usable": True,  # reaching here means it was accepted
            "severity": "WARNING" if findings else "INFO",
            "summary": (
                f"AHP over {len(result.names)} criteria: CR = {result.cr:.4f} "
                f"against {result.threshold:.2f}"
                + (", accepted on a recorded override" if result.override
                   else ", consistent")
            ),
            "findings": findings,
            "metadata": result.as_dict(),
        }


class AggregateOperator(Operator):
    """Normalize each layer, then combine them into a suitability map."""

    name = "decision.aggregate"
    version = "1.0.0"
    summary = ("Apply memberships and aggregate by Fuzzy Gamma, Product, Sum "
               "or weighted linear combination.")
    reference = ("Zimmermann and Zysno (1980), Fuzzy Sets and Systems 4(1), "
                 "sec. 3; Saaty (1980) for the weights.")

    parameters = (
        Parameter(name="criteria", type="list", required=True,
                  doc="[{path, name, unit, function, ...membership params}], "
                      "all already on one grid."),
        Parameter(name="method", type="str", required=True,
                  choices=tuple(agg.OPERATORS),
                  doc="Aggregation operator."),
        Parameter(name="result_name", type="str", required=True,
                  doc="Name of the suitability map, and its filename."),
        Parameter(name="gamma", type="float", default=0.7, minimum=0.0,
                  maximum=1.0, unit="dimensionless",
                  doc="Compensation for fuzzy_gamma. 0 is the product, 1 the "
                      "sum. Recorded: 0.7 and 0.9 are different maps."),
        Parameter(name="weights", type="list", default=None,
                  doc="[{name, weight}] for weighted_linear_combination; must "
                      "sum to 1."),
        Parameter(name="mask_path", type="str", default=None,
                  doc="Raster mask — an AOI or a common validity mask. Outside "
                      "it the result is null, not zero."),
        Parameter(name="correlation_threshold", type="float",
                  default=CORRELATION_THRESHOLD, minimum=0.0, maximum=1.0,
                  unit="dimensionless",
                  doc="|r| above which a pair of criteria is reported as "
                      "possible double counting."),
        Parameter(name="groups", type="list", default=None,
                  doc="[{name, group}]; criteria sharing a group are not "
                      "reported as double counting."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        specs = [dict(c) for c in params["criteria"]]
        if not specs:
            raise ParameterError(f"{self.name}: no criteria given")

        ctx.progress("membership", 0.0, f"normalizing {len(specs)} criteria")
        criteria = []
        provenance = []
        grid = None
        for index, spec in enumerate(specs, 1):
            ctx.check_cancel()
            source = read_raster(spec["path"])
            grid = grid or source.grid
            if source.grid != grid:
                raise ValueError(
                    f"criterion {spec['name']!r} is on a different grid from "
                    f"{criteria[0].name!r}. Harmonize them first — comparing "
                    f"pixels that are not in the same place is not a comparison."
                )
            values, anchors = self._normalize(source.values, spec)
            criteria.append(Criterion(
                name=spec["name"], values=values, grid=grid,
                stage=Stage.NORMALIZED, unit=None,
                higher_is_better=bool(spec.get("higher_is_better", True)),
                provenance={"function": spec["function"], "anchors": anchors},
            ))
            provenance.append({
                "name": spec["name"],
                "source_path": str(Path(spec["path"]).resolve()),
                "source_hash": sha256_file(Path(spec["path"])),
                "source_unit": spec.get("unit"),
                "function": spec["function"],
                "anchors": anchors,
                "valid_fraction": float(np.isfinite(values).mean()),
            })
            ctx.progress("membership", index / len(specs), spec["name"])

        stack = CriterionStack(criteria)

        ctx.progress("check", 0.3, "looking for double counting")
        weights = self._weights(params, stack.names)
        groups = {g["name"]: g["group"] for g in (params.get("groups") or [])}
        findings = double_counting(
            stack, threshold=params["correlation_threshold"],
            weights=weights, groups=groups,
        )
        ctx.progress("check", 1.0,
                     f"{len(findings)} correlated pair(s) above "
                     f"{params['correlation_threshold']:.2f}")

        ctx.progress("aggregate", 0.0, params["method"])
        ctx.check_cancel()
        result = self._aggregate(stack, params, weights)

        mask_provenance = None
        if params.get("mask_path"):
            mask_source = read_raster(params["mask_path"])
            if mask_source.grid != grid:
                raise ValueError(
                    "the mask is on a different grid from the criteria; "
                    "harmonize it first"
                )
            result = agg.apply_mask(result, np.isfinite(mask_source.values))
            mask_provenance = {
                "path": str(Path(params["mask_path"]).resolve()),
                "hash": sha256_file(Path(params["mask_path"])),
            }
        ctx.progress("aggregate", 1.0, "combined")

        ctx.progress("commit", 0.0, "writing the suitability map")
        artifact = write_geotiff(
            result, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "NORMALIZED",
                "GEOPOTENTIAL_UNIT": "suitability [0-1]",
                "GEOPOTENTIAL_METHOD": params["method"],
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": grid.describe(),
            "criterion_order": stack.names,
            "criteria": provenance,
            "weights": weights,
            "mask": mask_provenance,
            "correlation_findings": [f.as_dict() for f in findings],
            "result": agg.describe_result(result, params["method"]),
        }

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _normalize(values: np.ndarray, spec: dict[str, Any]):
        """Apply one membership, and return the anchors it actually used."""
        function = spec["function"]
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            raise ValueError(f"criterion {spec['name']!r}: every pixel is null")

        if function in ("linear_increasing", "linear_decreasing"):
            clamp = spec.get("clamp_percentiles")
            low, high = mf._bounds(
                finite, spec.get("x_min"), spec.get("x_max"),
                tuple(clamp) if clamp else None, spec["name"],
            )
            out = getattr(mf, function)(values, low, high)
            return out, {"x_min": low, "x_max": high,
                         "clamp_percentiles": list(clamp) if clamp else None}
        if function == "sigmoidal":
            centre = spec.get("center")
            centre = float(np.median(finite)) if centre is None else float(centre)
            slope = float(spec.get("slope", 1.0))
            direction = spec.get("direction", "increasing")
            return (mf.sigmoidal(values, centre, slope, direction),
                    {"center": centre, "slope": slope, "direction": direction})
        if function == "gaussian":
            mean = spec.get("mean")
            std = spec.get("std")
            mean = float(finite.mean()) if mean is None else float(mean)
            std = float(finite.std()) if std is None else float(std)
            return mf.gaussian(values, mean, std), {"mean": mean, "std": std}
        if function in ("small", "large"):
            midpoint = spec.get("midpoint")
            if midpoint is None:
                raise ValueError(
                    f"criterion {spec['name']!r}: {function} needs `midpoint`, "
                    f"the value receiving membership 0.5"
                )
            spread = float(spec.get("spread", 5.0))
            return (getattr(mf, function)(values, float(midpoint), spread),
                    {"midpoint": float(midpoint), "spread": spread})
        if function == "categorical":
            # Declarado no módulo de pertinência desde o M5 e **não ligado
            # aqui**: pedir `categorical` dava "membership 'categorical' is
            # not known; use one of categorical, ..." — uma mensagem que se
            # contradiz na própria frase. Encontrado rodando o caminho MCDA
            # sobre um dataset de outro domínio, onde geologia, uso do solo e
            # solo são todos classes.
            mapping = spec.get("mapping")
            if not mapping:
                raise ValueError(
                    f"criterion {spec['name']!r}: categorical needs `mapping`, "
                    f"{{class code: membership}}. Uma classe sem nota não é "
                    f"zero — é uma decisão que ninguém tomou."
                )
            # As chaves chegam como texto quando o pedido veio por JSON.
            table = {float(code): float(score) for code, score in mapping.items()}
            return mf.categorical(values, table), {"mapping": table}
        if function == "circular":
            preferred = spec.get("preferred")
            if preferred is None:
                raise ValueError(
                    f"criterion {spec['name']!r}: circular needs `preferred`, "
                    f"o azimute que recebe pertinência 1."
                )
            spread = float(spec.get("spread", 90.0))
            return (mf.circular(values, float(preferred), spread),
                    {"preferred": float(preferred), "spread": spread})
        raise ValueError(
            f"criterion {spec['name']!r}: membership {function!r} is not known; "
            f"use one of {', '.join(sorted(mf.FAMILY))}"
        )

    @staticmethod
    def _weights(params: dict[str, Any], names: list[str]) -> dict[str, float] | None:
        return weights_of(params)

    @staticmethod
    def _aggregate(stack: CriterionStack, params: dict[str, Any],
                   weights: dict[str, float] | None) -> np.ndarray:
        return aggregate_with(stack, params, weights)


# ---------------------------------------------------------------------------
# Shared with the scenario operators
# ---------------------------------------------------------------------------
# A scenario re-runs the analysis with one thing changed, so it has to use the
# **same** weights and the **same** aggregation the run used. A second copy of
# either would be two implementations that agree until they do not, and the
# disagreement would show up as a sensitivity result nobody could explain.


def weights_of(params: dict[str, Any]) -> dict[str, float] | None:
    """The weights as a mapping, or None for an operator that carries none."""
    entries = params.get("weights")
    if not entries:
        return None
    return {e["name"]: float(e["weight"]) for e in entries}


def aggregate_with(stack: CriterionStack, params: dict[str, Any],
                   weights: dict[str, float] | None) -> np.ndarray:
    """Run the aggregation these parameters name."""
    method = params["method"]
    if method == "fuzzy_gamma":
        return agg.fuzzy_gamma(stack, params["gamma"])
    if method == "fuzzy_product":
        return agg.fuzzy_product(stack)
    if method == "fuzzy_sum":
        return agg.fuzzy_sum(stack)
    if weights is None:
        raise ParameterError(
            "weighted_linear_combination needs `weights`; without them "
            "there is no combination, only an average nobody chose"
        )
    return agg.weighted_linear_combination(stack, weights)


def build_stack(specs: Sequence[dict[str, Any]],
                progress=None) -> tuple[CriterionStack, list[dict[str, Any]]]:
    """Read each criterion, apply its membership, and stack them.

    specs     [{path, name, unit, function, ...membership params}]
    progress  optional f(fraction, message), for an operator that reports it
    returns   (stack, provenance) — the provenance is what the manifest records

    raises    ValueError naming the criterion that is on a different grid.
              Comparing pixels that are not in the same place is not a
              comparison.
    """
    criteria: list[Criterion] = []
    provenance: list[dict[str, Any]] = []
    grid = None
    for index, spec in enumerate(specs, 1):
        source = read_raster(spec["path"])
        grid = grid or source.grid
        if source.grid != grid:
            raise ValueError(
                f"criterion {spec['name']!r} is on a different grid from "
                f"{criteria[0].name!r}. Harmonize them first — comparing "
                f"pixels that are not in the same place is not a comparison."
            )
        values, anchors = AggregateOperator._normalize(source.values, spec)
        criteria.append(Criterion(
            name=spec["name"], values=values, grid=grid,
            stage=Stage.NORMALIZED, unit=None,
            higher_is_better=bool(spec.get("higher_is_better", True)),
            provenance={"function": spec["function"], "anchors": anchors},
        ))
        provenance.append({
            "name": spec["name"],
            "source_path": str(Path(spec["path"]).resolve()),
            "source_hash": sha256_file(Path(spec["path"])),
            "source_unit": spec.get("unit"),
            "function": spec["function"],
            "anchors": anchors,
            "valid_fraction": float(np.isfinite(values).mean()),
        })
        if progress is not None:
            progress(index / len(specs), spec["name"])
    return CriterionStack(criteria), provenance
