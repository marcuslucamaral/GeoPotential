"""io.describe_dataset and qc.validate_dataset — the Import Wizard's two probes.

Both are **read-only**. They create nothing, register nothing and copy
nothing: section 9.2 requires the diagnosis to happen *before* the dataset
enters the project, so describing cannot be a step that half-imports it.

They emit no artefact. Their result travels in the manifest of a job that
succeeded, which is how the application receives it without the protocol
having to grow a second result channel — and without a raster ever being
serialized into JSON.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..grid.planner import plan_operation
from ..io.describe import UnsupportedFormat, describe
from ..qc.validate import validate
from .base import Context, Operator, Parameter, ParameterError

# Overrides the wizard may declare. Each is the operator asserting something
# the file does not say for itself, and each is recorded as such.
_OVERRIDE_PARAMETERS = (
    Parameter(name="crs", type="str",
              doc="CRS the operator declares for a file that carries none."),
    Parameter(name="unit", type="str",
              doc="Physical unit of the values: mGal, g/cm3, m, degC, mW/m2, nT."),
    Parameter(name="nodata", type="float",
              doc="Nodata sentinel to honour, for a file that declares none."),
    Parameter(name="band", type="int", default=1, minimum=1,
              doc="1-based band of a raster."),
    Parameter(name="x_field", type="str", doc="Column holding the X coordinate."),
    Parameter(name="y_field", type="str", doc="Column holding the Y coordinate."),
    Parameter(name="value_field", type="str", doc="Column holding the value."),
    Parameter(name="layer", type="str",
              doc="Layer name, for a GeoPackage holding several."),
    Parameter(name="separator", type="str",
              doc="Column separator, when a table's is not detected."),
)


def _overrides(params: dict[str, Any]) -> dict[str, Any]:
    """The declared values only. A None override is not a declaration."""
    keys = ("crs", "unit", "nodata", "band", "x_field", "y_field", "value_field",
            "layer", "separator")
    return {k: params[k] for k in keys if params.get(k) is not None}


class DescribeDatasetOperator(Operator):
    """Read a dataset's metadata, statistics and histogram. Import nothing."""

    name = "io.describe_dataset"
    version = "1.0.0"
    read_only = True
    summary = ("Read format, CRS, unit, fields, NoData, extent and statistics "
               "without importing.")
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 9.2, MSP-03."
    parameters = _OVERRIDE_PARAMETERS

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        if len(inputs) != 1:
            raise ParameterError(
                f"{self.name}: expects exactly one dataset, got {len(inputs)}"
            )
        ctx.progress("read", 0.0, f"reading {Path(inputs[0]).name}")
        ctx.check_cancel()
        try:
            description = describe(inputs[0], overrides=_overrides(params))
        except UnsupportedFormat as exc:
            raise ParameterError(str(exc)) from exc
        ctx.progress("read", 1.0, f"{description.kind}, {description.driver}")

        payload = description.as_dict()
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "description": payload,
            "declared": _overrides(params),
        }


class ValidateDatasetOperator(Operator):
    """Run the MSP-04 checks and return findings with severities."""

    name = "qc.validate_dataset"
    version = "1.0.0"
    read_only = True
    summary = "Validate CRS, unit, NoData, coverage, overlap, resolution, " \
              "duplicates, gaps and finiteness, with actionable messages."
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-04, section 33."
    parameters = (
        *_OVERRIDE_PARAMETERS,
        Parameter(
            name="require_metric", type="bool", default=False,
            doc="True when the intended operation measures in metres; a "
                "geographic CRS then blocks.",
        ),
        Parameter(
            name="context", type="list", default=None,
            doc="Layers already in the project, each {name, extent, "
                "pixel_size}, for the overlap and resolution checks.",
        ),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        if len(inputs) != 1:
            raise ParameterError(
                f"{self.name}: expects exactly one dataset, got {len(inputs)}"
            )
        ctx.progress("read", 0.0, f"reading {Path(inputs[0]).name}")
        ctx.check_cancel()
        try:
            description = describe(inputs[0], overrides=_overrides(params))
        except UnsupportedFormat as exc:
            raise ParameterError(str(exc)) from exc

        ctx.progress("validate", 0.3, "running the QA/QC rules")
        ctx.check_cancel()
        report = validate(
            description,
            context=params.get("context") or (),
            require_metric=bool(params.get("require_metric")),
        )
        ctx.progress("validate", 1.0, report.summary())

        plan = None
        if description.kind == "raster":
            plan = plan_operation(
                "harmonize to the target grid",
                width=int(description.detail.get("width", 0)) or 1,
                height=int(description.detail.get("height", 0)) or 1,
                layers=max(1, len(params.get("context") or ()) + 1),
                output_dir=ctx.output_dir,
            ).as_dict()

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "report": report.as_dict(),
            "plan": plan,
            "declared": _overrides(params),
        }
