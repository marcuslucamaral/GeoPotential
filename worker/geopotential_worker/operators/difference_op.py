"""grid.difference — A minus B, on a shared grid.

The comparison half of gate M4 G5. Two rasters, one subtraction, and a great
deal of refusing:

  - **the two must be on the same grid.** Same CRS, same transform, same size.
    Resampling one onto the other to make the subtraction possible would hide
    the misalignment inside the result, and a difference map of two misaligned
    layers looks like structure. Harmonization is a separate, deliberate step
    (M5); it does not happen implicitly inside a comparison.
  - **the result is defined only where both are valid.** A difference against
    a null is not zero. Treating it as zero would paint "no change" over
    exactly the pixels where nothing is known.

The output is signed, so it gets a diverging colormap centred on zero — which
the renderer already does for a signed field.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..io.readers import read_raster
from ..io.writers import write_geotiff
from .base import Context, Operator, Parameter, ParameterError

CHUNK_ROWS = 256


class DifferenceOperator(Operator):
    name = "grid.difference"
    version = "1.0.0"
    summary = "Subtract one raster from another on a shared grid: A - B."
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md M4, MSP-05 difference map."

    parameters = (
        Parameter(
            name="result_name", type="str", required=True,
            doc="Name the difference carries; also the output filename.",
        ),
        Parameter(
            name="unit", type="str", required=True,
            doc="Unit of both inputs; the difference carries the same one.",
        ),
        Parameter(
            name="band", type="int", default=1, minimum=1,
            doc="1-based band of both inputs.",
        ),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        if len(inputs) != 2:
            raise ParameterError(
                f"{self.name}: expects exactly two rasters, A then B; "
                f"got {len(inputs)}"
            )

        ctx.progress("read", 0.0, f"reading {Path(inputs[0]).name}")
        ctx.check_cancel()
        a = read_raster(inputs[0], band=params["band"])
        ctx.progress("read", 0.5, f"reading {Path(inputs[1]).name}")
        ctx.check_cancel()
        b = read_raster(inputs[1], band=params["band"])
        ctx.progress("read", 1.0, "both read")

        ctx.progress("validate", 0.0, "checking the two grids agree")
        self._require_same_grid(a, b, inputs)
        ctx.progress("validate", 1.0, "grids agree")

        grid = a.grid
        out = np.empty(grid.shape, dtype=np.float32)
        rows = grid.height
        for start in range(0, rows, CHUNK_ROWS):
            ctx.check_cancel()
            stop = min(start + CHUNK_ROWS, rows)
            # NaN propagates through the subtraction on its own, which is
            # exactly the wanted rule: the difference is defined only where
            # both inputs are.
            out[start:stop] = a.values[start:stop] - b.values[start:stop]
            ctx.progress("difference", stop / rows, f"rows {stop}/{rows}")

        both_valid = np.isfinite(out)
        ctx.progress("commit", 0.0, "writing the artefact")
        ctx.check_cancel()
        artifact = write_geotiff(
            out, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "DIFFERENCE",
                "GEOPOTENTIAL_UNIT": params["unit"],
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_A": str(Path(inputs[0]).resolve()),
                "GEOPOTENTIAL_B": str(Path(inputs[1]).resolve()),
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        finite = out[both_valid]
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [
                {"role": "A", "path": str(Path(inputs[0]).resolve())},
                {"role": "B", "path": str(Path(inputs[1]).resolve())},
            ],
            "params": params,
            "grid": grid.describe(),
            "statistics": {
                "unit": params["unit"],
                "valid_fraction": float(both_valid.mean()),
                "min": float(finite.min()) if finite.size else None,
                "max": float(finite.max()) if finite.size else None,
                "mean": float(finite.mean(dtype=np.float64)) if finite.size else None,
                "rms": float(np.sqrt(np.mean(finite.astype(np.float64) ** 2)))
                if finite.size else None,
            },
        }

    @staticmethod
    def _require_same_grid(a, b, inputs: Sequence[str]) -> None:  # noqa: ANN001
        """Refuse two rasters that are not already on one grid.

        Naming the specific disagreement matters: "grids differ" sends someone
        looking at the wrong thing, and CRS, size and transform fail for
        completely different reasons.
        """
        name_a, name_b = Path(inputs[0]).name, Path(inputs[1]).name
        if a.grid.crs != b.grid.crs:
            raise ValueError(
                f"{name_a} is in {a.grid.crs.name} and {name_b} is in "
                f"{b.grid.crs.name}. A difference needs one CRS; reproject one "
                f"of them first."
            )
        if a.grid.shape != b.grid.shape:
            raise ValueError(
                f"{name_a} is {a.grid.width}x{a.grid.height} and {name_b} is "
                f"{b.grid.width}x{b.grid.height}. A difference needs one grid; "
                f"resample one of them first."
            )
        if tuple(a.grid.transform)[:6] != tuple(b.grid.transform)[:6]:
            raise ValueError(
                f"{name_a} and {name_b} are the same size but sit on different "
                f"origins or pixel sizes. Subtracting them would compare "
                f"pixels that are not in the same place; align them first."
            )
