"""decision.membership — turn one raw raster into a normalized criterion.

This is the smoke operator of the vertical slice, and it is real science rather
than a placeholder: it is the RAW -> NORMALIZED derivation that the whole MCDA
pipeline rests on, and it exercises every contract the slice has to prove.

  - the source is refused if it declares no CRS (ADR-004)
  - its declared nodata becomes NaN, the single in-memory null
  - the result is a `Criterion` at stage NORMALIZED, checked in [0, 1] at
    construction, carrying no unit
  - the raw values are not overwritten; the raw path stays in provenance
  - the GeoTIFF is written atomically with nodata declared, then validated,
    then hashed, then renamed (section 30)
  - progress is derived from rows actually processed, never simulated
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..decision import membership as mf
from ..domain.criterion import Criterion, Stage
from ..io.readers import read_raster
from ..io.writers import write_geotiff
from .base import Context, Operator, Parameter, ParameterError

# Rows per chunk. Large enough that the per-chunk Python overhead is
# negligible against the vectorized work, small enough that progress moves.
CHUNK_ROWS = 128


class MembershipOperator(Operator):
    name = "decision.membership"
    version = "1.0.0"
    summary = "Map a raw raster onto a dimensionless fuzzy membership in [0, 1]."
    reference = "Zadeh (1965), Information and Control 8(3), sec. 2."

    parameters = (
        Parameter(
            name="function",
            type="str",
            doc="Which membership function to apply.",
            required=True,
            # O mesmo vocabulário que `decision.aggregate` aceita. Duas
            # listas divergentes é como `categorical` e `circular` ficaram
            # utilizáveis na agregação e recusadas aqui: a mesma pertinência
            # existindo para um operador e não para o outro.
            choices=(
                "linear_increasing",
                "linear_decreasing",
                "sigmoidal",
                "gaussian",
                "small",
                "large",
                "circular",
                "categorical",
            ),
        ),
        Parameter(
            name="criterion_name",
            type="str",
            doc="Name the criterion carries into the stack; weights bind to it.",
            required=True,
        ),
        Parameter(
            name="unit",
            type="str",
            doc="Physical unit of the raw input, for provenance.",
            required=True,
        ),
        Parameter(
            name="x_min",
            type="float",
            doc="Low anchor, in the input unit. Taken from the data if absent.",
            unit="input unit",
        ),
        Parameter(
            name="x_max",
            type="float",
            doc="High anchor, in the input unit. Taken from the data if absent.",
            unit="input unit",
        ),
        Parameter(
            name="clamp_percentile_low",
            type="float",
            doc="Take the low anchor from this percentile instead of the minimum.",
            unit="percent",
            minimum=0.0,
            maximum=100.0,
        ),
        Parameter(
            name="clamp_percentile_high",
            type="float",
            doc="Take the high anchor from this percentile instead of the maximum.",
            unit="percent",
            minimum=0.0,
            maximum=100.0,
        ),
        Parameter(
            name="center",
            type="float",
            doc="Inflection point, sigmoidal only. The median if absent.",
            unit="input unit",
        ),
        Parameter(
            name="slope",
            type="float",
            doc="Steepness per input unit, sigmoidal only.",
            unit="1/input unit",
            default=1.0,
        ),
        Parameter(
            name="direction",
            type="str",
            doc="Sigmoidal sense.",
            default="increasing",
            choices=("increasing", "decreasing"),
        ),
        Parameter(
            name="mean",
            type="float",
            doc="Optimum, gaussian only. The sample mean if absent.",
            unit="input unit",
        ),
        Parameter(
            name="std",
            type="float",
            doc="Spread, gaussian only. The sample std if absent.",
            unit="input unit",
        ),
        Parameter(
            name="midpoint",
            type="float",
            doc="Value receiving membership 0.5; small/large only.",
            unit="input unit",
        ),
        Parameter(
            name="spread",
            type="float",
            doc="Shape exponent; small/large only.",
            unit="dimensionless",
            default=5.0,
            minimum=0.1,
        ),
        Parameter(
            name="preferred",
            type="float",
            doc="Azimuth receiving membership 1; circular only.",
            unit="degree",
        ),
        Parameter(
            name="angular_spread",
            type="float",
            doc="Angular distance receiving membership 0.5; circular only.",
            unit="degree",
            default=90.0,
        ),
        Parameter(
            name="mapping",
            type="dict",
            doc="{class code: membership in [0, 1]}; categorical only. Every "
                "code present in the data must be listed.",
        ),
        Parameter(
            name="band",
            type="int",
            doc="1-based band of the input raster.",
            default=1,
            minimum=1,
        ),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        if len(inputs) != 1:
            raise ParameterError(
                f"{self.name}: expects exactly one input raster, got {len(inputs)}"
            )

        ctx.progress("read", 0.0, f"reading {Path(inputs[0]).name}")
        ctx.check_cancel()
        source = read_raster(inputs[0], band=params["band"])
        grid = source.grid
        ctx.progress(
            "read",
            1.0,
            f"{grid.width}x{grid.height} on {grid.crs.name}, "
            f"pixel {grid.pixel_size[0]:g}x{grid.pixel_size[1]:g} {grid.crs.unit}",
        )

        ctx.progress("validate", 0.0, "checking the source")
        ctx.check_cancel()
        valid = np.isfinite(source.values)
        if not valid.any():
            raise ValueError(
                f"{Path(inputs[0]).name}: every pixel is null; nothing to map"
            )
        anchors = self._resolve_anchors(source.values[valid], params)
        ctx.progress(
            "validate",
            1.0,
            f"{valid.mean() * 100:.1f}% of pixels valid",
        )

        # The anchors are resolved once, over the whole valid population, and
        # then applied chunk by chunk. Resolving them per chunk would make each
        # chunk a different scientific transform.
        out = np.empty(grid.shape, dtype=np.float32)
        rows = grid.height
        for start in range(0, rows, CHUNK_ROWS):
            ctx.check_cancel()
            stop = min(start + CHUNK_ROWS, rows)
            out[start:stop] = self._apply(source.values[start:stop], params, anchors)
            ctx.progress(
                "membership",
                stop / rows,
                f"rows {stop}/{rows}",
            )

        criterion = Criterion(
            name=params["criterion_name"],
            values=out,
            grid=grid,
            stage=Stage.NORMALIZED,
            unit=None,
            higher_is_better=True,
            provenance={
                "operator": self.name,
                "operator_version": self.version,
                "source_path": str(Path(inputs[0]).resolve()),
                "source_unit": params["unit"],
                "source_nodata": source.nodata,
                "function": params["function"],
                "anchors": anchors,
                "reference": self.reference,
            },
        )

        ctx.progress("commit", 0.0, "writing the artefact")
        ctx.check_cancel()
        out_path = ctx.output_dir / f"{criterion.name}_membership.tif"
        artifact = write_geotiff(
            criterion.values,
            grid,
            out_path,
            tags={
                "GEOPOTENTIAL_STAGE": "NORMALIZED",
                "GEOPOTENTIAL_UNIT": "dimensionless [0-1]",
                "GEOPOTENTIAL_CRITERION": criterion.name,
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_SOURCE_UNIT": params["unit"],
            },
        )
        ctx.emit(f"{criterion.name}_membership", artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [
                {
                    "path": str(Path(inputs[0]).resolve()),
                    "crs": grid.crs.name,
                    "unit": params["unit"],
                    "nodata": source.nodata,
                }
            ],
            "params": params,
            "grid": grid.describe(),
            "criterion": criterion.describe(),
            "anchors": anchors,
        }

    def _resolve_anchors(
        self, valid_values: np.ndarray, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Fix the transform's anchors over the whole valid population.

        returns  the anchors actually used, for the manifest

        Percentile clamping changes the result, so which percentiles were used
        is recorded rather than implied.
        """
        fn = params["function"]
        # Direção e classe não têm âncora derivada da população: a primeira
        # tem um azimute declarado, a segunda uma tabela. Resolver percentil
        # sobre códigos de classe seria tratar `3` como se fosse uma
        # magnitude três vezes `1`.
        if fn == "circular":
            preferred = params.get("preferred")
            if preferred is None:
                raise ParameterError(
                    f"{self.name}: circular needs `preferred`, the azimuth "
                    f"that receives membership 1. There is no default: a "
                    f"preferred direction is the decision itself."
                )
            return {"preferred": float(preferred),
                    "angular_spread": float(params["angular_spread"])}
        if fn == "categorical":
            mapping = params.get("mapping")
            if not mapping:
                raise ParameterError(
                    f"{self.name}: categorical needs `mapping`, a score for "
                    f"every class code present. Scoring an unlisted class "
                    f"zero would turn a data gap into a claim."
                )
            return {"mapping": {float(c): float(v) for c, v in mapping.items()}}

        p_lo, p_hi = params["clamp_percentile_low"], params["clamp_percentile_high"]
        if (p_lo is None) != (p_hi is None):
            raise ParameterError(
                f"{self.name}: clamp_percentile_low and clamp_percentile_high "
                f"must be given together"
            )
        if fn in ("linear_increasing", "linear_decreasing"):
            clamp = (p_lo, p_hi) if p_lo is not None else None
            lo, hi = mf._bounds(
                valid_values, params["x_min"], params["x_max"], clamp, fn
            )
            return {"x_min": lo, "x_max": hi, "clamp_percentiles": list(clamp) if clamp else None}
        if fn == "sigmoidal":
            c = params["center"]
            c = float(np.median(valid_values)) if c is None else float(c)
            return {"center": c, "slope": params["slope"], "direction": params["direction"]}
        if fn == "gaussian":
            m = params["mean"]
            s = params["std"]
            m = float(valid_values.mean()) if m is None else float(m)
            s = float(valid_values.std()) if s is None else float(s)
            return {"mean": m, "std": s}
        if fn in ("small", "large"):
            mid = params["midpoint"]
            if mid is None:
                raise ParameterError(f"{self.name}: {fn} requires `midpoint`")
            return {"midpoint": float(mid), "spread": params["spread"]}
        raise ParameterError(f"{self.name}: unsupported function {fn!r}")

    @staticmethod
    def _apply(
        chunk: np.ndarray, params: dict[str, Any], anchors: dict[str, Any]
    ) -> np.ndarray:
        fn = params["function"]
        if fn == "linear_increasing":
            return mf.linear_increasing(chunk, anchors["x_min"], anchors["x_max"])
        if fn == "linear_decreasing":
            return mf.linear_decreasing(chunk, anchors["x_min"], anchors["x_max"])
        if fn == "sigmoidal":
            return mf.sigmoidal(
                chunk, anchors["center"], anchors["slope"], anchors["direction"]
            )
        if fn == "gaussian":
            return mf.gaussian(chunk, anchors["mean"], anchors["std"])
        if fn == "small":
            return mf.small(chunk, anchors["midpoint"], anchors["spread"])
        if fn == "circular":
            return mf.circular(chunk, anchors["preferred"],
                               anchors["angular_spread"])
        if fn == "categorical":
            return mf.categorical(chunk, anchors["mapping"])
        return mf.large(chunk, anchors["midpoint"], anchors["spread"])
