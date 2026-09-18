"""Cenários, sensibilidade e explicabilidade. MSP-10, MSP-11, MSP-12, §17.

    scenarios.leave_one_out   drop each criterion; what does the map lose?
    scenarios.sensitivity     sweep one parameter; how far does the answer move?
    scenarios.explain         why did this cell score what it scored?
    scenarios.rank_targets    which places are the answer, in order?
    reporting.manifest        write the run's manifest out, as a file

**Every one of these re-runs the analysis with the same code the run used.**
The stack is built by `mcda_op.build_stack`, the weights by `weights_of`, the
aggregation by `aggregate_with` — the same three functions
`decision.aggregate` calls. A scenario computed by a second implementation is
a scenario that agrees with the run until it does not, and the disagreement
would surface as a sensitivity number nobody could explain.

**All four `scenarios.*` are read-only.** They answer questions *about* a
result that already exists and produce no science of their own, so they commit
no run and register no artefact (`P-53`).

`leave_one_out` used to offer to write a difference raster per criterion. It
does not, and that is the point: `grid.difference` has been the operator for
"the difference between two maps" since M4, and a second one that produces the
same artefact by a different route is two implementations of one thing. A
scenario says *how much* the map would move; asking for the picture of it is a
different request, with its own operator and its own run.

**None of them decides anything.** They measure how much the answer would move
if a choice changed. Choosing is the operator's, and it stays that way — the
screen shows the table and never rewrites a weight.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .._version import VERSION as WORKER_VERSION
from ..scenarios import explain as explain_core
from ..scenarios import sensitivity as sens
from .base import Context, Operator, Parameter, ParameterError
from .mcda_op import aggregate_with, build_stack, weights_of

#: The analysis a scenario questions, declared the same way `decision.aggregate`
#: declares it. Identical on purpose: a scenario is the run with one thing
#: changed, and a different spelling of the same analysis is a second analysis.
ANALYSIS_PARAMETERS = (
    Parameter(name="criteria", type="list", required=True,
              doc="[{path, name, unit, function, ...membership params}], the "
                  "same list the run was computed from, all on one grid."),
    Parameter(name="method", type="str", required=True,
              doc="The aggregation the run used. A scenario measured against a "
                  "different operator measures nothing."),
    Parameter(name="gamma", type="float", default=0.7, minimum=0.0, maximum=1.0,
              unit="dimensionless",
              doc="The run's gamma, for fuzzy_gamma."),
    Parameter(name="weights", type="list", default=None,
              doc="[{name, weight}], the run's weights."),
    Parameter(name="top_fraction", type="float", default=0.1,
              minimum=0.001, maximum=1.0, unit="dimensionless",
              doc="The head of the distribution the agreement is measured "
                  "over. 0.1 is the top decile; \"the best 10 %\" is a choice."),
)


def _analysis(params: dict[str, Any], ctx: Context):
    """The stack, the weights and the aggregation this run was made with."""
    specs = [dict(c) for c in params["criteria"]]
    if not specs:
        raise ParameterError("no criteria given; there is no analysis to question")
    ctx.progress("membership", 0.0, f"rebuilding {len(specs)} criteria")
    stack, provenance = build_stack(
        specs, progress=lambda f, name: ctx.progress("membership", f, name))
    weights = weights_of(params)
    return stack, weights, provenance


class LeaveOneOutOperator(Operator):
    """Drop each criterion in turn and measure what the map loses. §17.3."""

    name = "scenarios.leave_one_out"
    version = "1.0.0"
    summary = ("Remove each criterion in turn, re-aggregate, and report how "
               "far the map and its ranking moved.")
    reference = ("Saltelli et al. (2008), Global Sensitivity Analysis: The "
                 "Primer, ch. 1; IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-11, "
                 "section 17.3.")

    read_only = True
    parameters = ANALYSIS_PARAMETERS

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        stack, weights, provenance = _analysis(params, ctx)
        ctx.check_cancel()

        ctx.progress("scenarios", 0.0,
                     f"re-aggregating without each of {len(stack.names)}")
        report = sens.leave_one_out(
            stack,
            lambda s, w: aggregate_with(s, params, w),
            weights,
            top_fraction=float(params["top_fraction"]),
        )
        ctx.progress("scenarios", 1.0, f"{len(report['criteria'])} scenarios")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": stack.grid.describe(),
            "criteria": provenance,
            "leave_one_out": report,
        }


class SensitivityOperator(Operator):
    """Sweep one parameter and report how far the answer moved. §17.4-17.6."""

    name = "scenarios.sensitivity"
    version = "1.0.0"
    read_only = True
    summary = ("Vary gamma, one weight, or a membership anchor, and report the "
               "change in the map and in its ranking.")
    reference = ("Saltelli et al. (2008), ch. 1; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-11, section 17.")

    #: What can be swept, and what each one means. A parameter that is not here
    #: is refused by name rather than silently ignored.
    SWEEPS = ("gamma", "weight")

    parameters = ANALYSIS_PARAMETERS + (
        Parameter(name="parameter", type="str", required=True,
                  choices=SWEEPS,
                  doc="What to vary. `gamma` is the compensation; `weight` "
                      "moves one criterion's weight and renormalises the rest."),
        Parameter(name="values", type="list", required=True,
                  doc="The values to try. A list and not a range: an irregular "
                      "grid (0, 0.5, 0.7, 0.9, 1) is usually what is wanted."),
        Parameter(name="criterion", type="str", default=None,
                  doc="Which criterion's weight to sweep. Required for "
                      "`weight`, meaningless for `gamma`."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        stack, weights, provenance = _analysis(params, ctx)
        ctx.check_cancel()

        which = params["parameter"]
        values = [float(v) for v in (params["values"] or [])]
        baseline = aggregate_with(stack, params, weights)

        if which == "gamma":
            if params["method"] != "fuzzy_gamma":
                raise ParameterError(
                    f"gamma has no effect on {params['method']!r}; sweeping it "
                    f"would produce a table of zeros that looks like a result."
                )

            def build(value: float) -> np.ndarray:
                return aggregate_with(stack, {**params, "gamma": value}, weights)

        elif which == "weight":
            target = params.get("criterion")
            if not target:
                raise ParameterError(
                    "sweeping a weight needs `criterion`: which one. Available: "
                    + ", ".join(stack.names)
                )
            if target not in stack.names:
                raise ParameterError(
                    f"{target!r} is not a criterion of this analysis. "
                    f"Available: {', '.join(stack.names)}"
                )
            if not weights:
                raise ParameterError(
                    f"{params['method']!r} carries no weights, so there is "
                    f"none to sweep."
                )

            def build(value: float) -> np.ndarray:
                # The swept criterion takes `value`; the rest share what is
                # left, in their original proportion. Renormalising is the only
                # way to keep P-93 (weights sum to 1) while moving one of them,
                # and it is reported in the result.
                others = {n: w for n, w in weights.items() if n != target}
                rest = sum(others.values())
                scale = (1.0 - value) / rest if rest > 0 else 0.0
                moved = {n: w * scale for n, w in others.items()}
                moved[target] = value
                return aggregate_with(stack, params, moved)
        else:                                        # pragma: no cover - choices
            raise ParameterError(f"unknown parameter to sweep: {which!r}")

        ctx.progress("sweep", 0.0, f"{len(values)} value(s) of {which}")
        report = sens.sweep(values, build, baseline, parameter=which,
                            top_fraction=float(params["top_fraction"]))
        report["criterion"] = params.get("criterion")
        report["weights_renormalized"] = which == "weight"
        ctx.progress("sweep", 1.0, "measured")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": stack.grid.describe(),
            "criteria": provenance,
            "sensitivity": report,
        }


class ExplainOperator(Operator):
    """Why this cell scored what it scored. §17.1, §17.2. Read-only."""

    name = "scenarios.explain"
    version = "1.0.0"
    read_only = True
    summary = ("Decompose one cell's score into what each criterion "
               "contributed, with the decomposition named.")
    reference = ("Zimmermann and Zysno (1980) for the operators decomposed; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-12, section 17.1.")

    parameters = ANALYSIS_PARAMETERS + (
        Parameter(name="row", type="int", required=True, minimum=0,
                  doc="Row of the cell to explain."),
        Parameter(name="column", type="int", required=True, minimum=0,
                  doc="Column of the cell to explain."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        stack, weights, provenance = _analysis(params, ctx)
        ctx.check_cancel()

        try:
            answer = explain_core.contributions(
                stack, params["method"],
                (int(params["row"]), int(params["column"])),
                weights=weights, gamma=float(params["gamma"]),
            )
        except IndexError as outside:
            raise ParameterError(str(outside)) from outside

        score = aggregate_with(stack, params, weights)
        cell = float(score[int(params["row"]), int(params["column"])])
        answer["score"] = cell if np.isfinite(cell) else None
        # §17.2, for this cell rather than for the whole layer.
        answer["valid_fraction_here"] = (
            0.0 if not answer["scored"]
            else float(np.mean([np.isfinite(v)
                                for v in answer["memberships"].values()])))
        ctx.progress("explain", 1.0, answer.get("dominant") or "no score")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": stack.grid.describe(),
            "criteria": provenance,
            "explanation": answer,
        }


class RankTargetsOperator(Operator):
    """The best places, in order, as places. Read-only."""

    name = "scenarios.rank_targets"
    version = "1.0.0"
    read_only = True
    summary = ("Rank the highest-scoring places, separated so one anomaly is "
               "one target, each with what drove it.")
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-12, section 17."

    parameters = ANALYSIS_PARAMETERS + (
        Parameter(name="count", type="int", default=10, minimum=1,
                  doc="How many targets to return."),
        Parameter(name="min_separation", type="int", default=5, minimum=1,
                  unit="cells",
                  doc="Two targets closer than this are one anomaly seen "
                      "twice. Ten pixels from one hilltop are not ten targets."),
        Parameter(name="explain_each", type="bool", default=True,
                  doc="Decompose every target's score into its criteria."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        stack, weights, provenance = _analysis(params, ctx)
        ctx.check_cancel()

        score = aggregate_with(stack, params, weights)
        ctx.progress("rank", 0.5, "ranking")
        report = explain_core.rank_targets(
            score, count=int(params["count"]),
            min_separation=int(params["min_separation"]),
        )

        if params["explain_each"]:
            for target in report["targets"]:
                ctx.check_cancel()
                target["explanation"] = explain_core.contributions(
                    stack, params["method"], tuple(target["cell"]),
                    weights=weights, gamma=float(params["gamma"]),
                )
        ctx.progress("rank", 1.0, f"{report['count']} target(s)")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": params,
            "grid": stack.grid.describe(),
            "criteria": provenance,
            "targets": report,
        }


class ManifestOperator(Operator):
    """Write a run's manifest out as a file. §17.9, §17.10, §17.11.

    The manifest has existed inside the run record since M2. What did not
    exist was a way to **hand it to somebody**: a reviewer, a co-author, a
    regulator. A result whose provenance can only be read through the
    application that made it is a result nobody else can check.
    """

    name = "reporting.manifest"
    version = "1.0.0"
    summary = "Write the run's manifest to a JSON file that reproduces it."
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 17.9-17.11."

    parameters = (
        Parameter(name="manifest", type="dict", required=True,
                  doc="The run's manifest, as the store holds it."),
        Parameter(name="result_name", type="str", required=True,
                  doc="Filename the manifest is written under."),
        Parameter(name="run_id", type="str", default=None,
                  doc="The run this manifest belongs to (section 17.9)."),
        Parameter(name="app_version", type="str", default=None,
                  doc="The application version that produced it (17.10)."),
    )

    #: What a manifest has to carry to reproduce a run. Checked, because a
    #: manifest missing one of these is a file that looks like provenance.
    REQUIRED = ("operator", "operator_version", "params")

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        manifest = dict(params["manifest"] or {})
        missing = [key for key in self.REQUIRED if key not in manifest]
        if missing:
            raise ParameterError(
                f"this manifest cannot reproduce a run: it has no "
                f"{', '.join(missing)}. Writing it out would produce a file "
                f"that looks like provenance and is not."
            )

        document = {
            "geopotential_manifest_version": "1.0.0",
            "run_id": params.get("run_id"),
            "app_version": params.get("app_version"),
            "worker_version": WORKER_VERSION,
            "manifest": manifest,
        }
        path = ctx.output_dir / f"{params['result_name']}.json"
        ctx.progress("commit", 0.0, "writing the manifest")
        # Written through the same atomic path every artefact takes: tmp,
        # flush, rename. A half-written manifest is worse than none.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")
        temporary.replace(path)
        ctx.progress("commit", 1.0, path.name)

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "params": {"result_name": params["result_name"],
                       "run_id": params.get("run_id")},
            "manifest_path": str(path.resolve()),
            "bytes": path.stat().st_size,
        }
