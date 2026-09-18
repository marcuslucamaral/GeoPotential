"""The operators that bring sparse data onto an analysis grid. MSP-06.

    grid.idw                 points  -> continuous field   (interpolates)
    grid.tin_linear          points  -> continuous field   (interpolates)
    grid.tin_cubic           points  -> continuous field   (interpolates)
    grid.euclidean_distance  features -> distance field     (measures)
    grid.rasterize           features -> burned field       (transfers)
    grid.cross_validate      points  -> a table of errors   (measures nothing
                                                             onto a grid)

Only the first three estimate a value where nothing was measured. Calling the
others interpolation would be wrong, and the difference matters to anyone
reading a manifest afterwards.

The three interpolators are the ones QGIS offers — IDW, and TIN with its two
methods — because a person who knows what those do in QGIS must get the same
thing here. Which of them fits a given survey is not a preference and is not
decided in code: `grid.cross_validate` holds samples out and measures, and the
gridding screen reports what it found (`ADR-MSP-007`).

Every gridding operator takes the same grid specification — CRS, pixel and an
optional area — because the grid is chosen, never inferred (`grid/spec.py`),
and every one consults the planner before allocating anything.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..domain.crs import CrsInfo
from ..grid import distance as distance_grid
from ..grid import idw as idw_grid
from ..grid import rasterize as rasterize_grid
from ..grid import spec as grid_spec
from ..grid import triangulated as tin_grid
from ..grid import crossval
from ..io.writers import write_geotiff
from .base import Context, Operator, Parameter, ParameterError

#: The grid parameters every gridding operator carries. Declared once so
#: they cannot drift into meaning different things by the same name.
GRID_PARAMETERS = (
    Parameter(
        name="target_crs", type="str", required=True,
        doc="CRS of the analysis grid. There is no default.",
    ),
    Parameter(
        name="pixel_size", type="float", required=True, minimum=1e-9,
        unit="CRS unit",
        doc="Square pixel of the analysis grid, in the target CRS unit.",
    ),
    Parameter(
        name="bounds", type="list", default=None,
        doc="(left, bottom, right, top) of the area to grid. Absent, the "
            "data's own extent is used; present, only that area is gridded — "
            "which is also the cheapest way to make a grid fit.",
    ),
    Parameter(
        name="bounds_crs", type="str", default=None,
        doc="CRS `bounds` is written in, when it is not the target CRS.",
    ),
    Parameter(
        name="result_name", type="str", required=True,
        doc="Name the result carries; also the output filename.",
    ),
)


def _read_points(path: Path, params: dict[str, Any]) -> tuple:
    """Coordinates and values out of a table or a point vector.

    Returns (x, y, values) in the file's own CRS. Which column is which is
    the caller's declaration, never a guess — the wizard asks for it and
    §16 forbids deciding it here.
    """
    suffix = path.suffix.lower()
    if suffix in (".csv", ".xyz", ".txt", ".dat"):
        import pandas as pd

        frame = pd.read_csv(path, sep=None, engine="python")
        for role in ("x_field", "y_field", "value_field"):
            name = params.get(role)
            if not name:
                raise ParameterError(
                    f"{role} was not declared. {path.name} has columns: "
                    f"{', '.join(map(str, frame.columns))}"
                )
            if name not in frame.columns:
                raise ParameterError(
                    f"{role}={name!r} is not a column of {path.name}. It has: "
                    f"{', '.join(map(str, frame.columns))}"
                )
        return (
            frame[params["x_field"]].to_numpy(dtype=np.float64),
            frame[params["y_field"]].to_numpy(dtype=np.float64),
            frame[params["value_field"]].to_numpy(dtype=np.float64),
        )

    import geopandas as gpd

    layer = params.get("layer")
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    field = params.get("value_field")
    if not field or field not in gdf.columns:
        raise ParameterError(
            f"value_field={field!r} is not a field of {path.name}. It has: "
            f"{', '.join(c for c in gdf.columns if c != gdf.geometry.name)}"
        )
    centroids = gdf.geometry.representative_point()
    return (
        centroids.x.to_numpy(dtype=np.float64),
        centroids.y.to_numpy(dtype=np.float64),
        gdf[field].to_numpy(dtype=np.float64),
    )


def _source_crs(path: Path, params: dict[str, Any]) -> CrsInfo:
    """The CRS the input is in — declared, or read from a vector that has one.

    A table has nowhere to write a CRS, so for a table the declaration is the
    only answer and its absence is refused by name (ADR-004).
    """
    declared = params.get("source_crs")
    if declared:
        return CrsInfo.from_user_input(declared, source="source_crs")
    if path.suffix.lower() in (".csv", ".xyz", ".txt", ".dat"):
        raise ParameterError(
            f"{path.name} is a table and carries no CRS. Declare source_crs; "
            f"there is no default."
        )
    import geopandas as gpd

    gdf = gpd.read_file(path, rows=1)
    if gdf.crs is None:
        raise ParameterError(
            f"{path.name} declares no CRS. Declare source_crs; there is no "
            f"default."
        )
    return CrsInfo.from_user_input(str(gdf.crs), source=path.name)


def _to_target(x, y, source: CrsInfo, target: CrsInfo):  # noqa: ANN001
    """Move coordinates into the grid's CRS, in one call for the whole array."""
    if source == target:
        return x, y
    import pyproj

    transformer = pyproj.Transformer.from_crs(
        source.crs, target.crs, always_xy=True)
    return transformer.transform(x, y)


def _grid_for(
    ctx: Context, params: dict[str, Any], data_bounds, operation: str,
    target_crs: CrsInfo,
):  # noqa: ANN001
    """Build the grid, or refuse before anything is allocated."""
    bounds = params.get("bounds")
    bounds_crs = (
        CrsInfo.from_user_input(params["bounds_crs"], source="bounds_crs")
        if params.get("bounds_crs") else None
    )
    px = float(params["pixel_size"])
    try:
        return grid_spec.build(
            target_crs=target_crs,
            pixel_size=(px, px),
            data_bounds=data_bounds,
            bounds=tuple(bounds) if bounds else None,
            bounds_crs=bounds_crs,
            operation=operation,
            output_dir=ctx.output_dir,
        )
    except grid_spec.GridRefused as refusal:
        raise ParameterError(str(refusal)) from refusal


def _one_input(name: str, inputs: Sequence[str]) -> Path:
    if len(inputs) != 1:
        raise ParameterError(
            f"{name}: expects exactly one input file; got {len(inputs)}")
    return Path(inputs[0])


class IdwOperator(Operator):
    """Shepard (1968) inverse distance weighting."""

    name = "grid.idw"
    version = "1.0.0"
    summary = "Interpolate scattered point samples onto a grid (Shepard 1968)."
    reference = ("Shepard, D. (1968), Proc. 23rd ACM National Conference; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06.")

    parameters = GRID_PARAMETERS + (
        Parameter(name="unit", type="str", required=True,
                  doc="Physical unit of the samples; the field carries it."),
        Parameter(name="source_crs", type="str", default=None,
                  doc="CRS the coordinates are in. Required for a table."),
        Parameter(name="x_field", type="str", default=None,
                  doc="Column holding the X coordinate."),
        Parameter(name="y_field", type="str", default=None,
                  doc="Column holding the Y coordinate."),
        Parameter(name="value_field", type="str", default=None,
                  doc="Column holding the measurement."),
        Parameter(name="layer", type="str", default=None,
                  doc="Layer of a multi-layer vector file."),
        Parameter(name="radius", type="float", required=True, minimum=1e-9,
                  unit="CRS unit",
                  doc="Search radius. Beyond it no sample is used, and a cell "
                      "with too few samples stays null rather than being "
                      "filled from far away."),
        Parameter(name="power", type="float", default=2.0, minimum=0.0,
                  doc="Shepard's p. Higher weights the nearest sample more; "
                      "2 is the documented default."),
        Parameter(name="min_points", type="int", default=1, minimum=1,
                  doc="Fewer neighbours than this leaves the cell null."),
        Parameter(name="max_points", type="int", default=16, minimum=1,
                  doc="Neighbours used, nearest first."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        path = _one_input(self.name, inputs)
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("inverse distance weighting")

        ctx.progress("read", 0.0, f"reading {path.name}")
        ctx.check_cancel()
        x, y, values = _read_points(path, params)
        source_crs = _source_crs(path, params)
        x, y = _to_target(x, y, source_crs, target_crs)
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
        if not finite.any():
            raise ValueError(
                f"{path.name}: no sample has a finite coordinate and value.")
        x, y, values = x[finite], y[finite], values[finite]
        ctx.progress("read", 1.0, f"{x.size} samples")

        data_bounds = (float(x.min()), float(y.min()),
                       float(x.max()), float(y.max()))
        grid, plan, provenance = _grid_for(
            ctx, params, data_bounds, "grid.idw", target_crs)
        ctx.progress("plan", 1.0, plan.summary())

        out = np.full(grid.shape, np.nan, dtype=np.float32)
        done = 0
        for start, stop in grid_spec.row_blocks(grid, plan):
            ctx.check_cancel()
            cell_x, cell_y = grid_spec.cell_centres(grid, start, stop)
            block = idw_grid.interpolate(
                x, y, values, cell_x, cell_y,
                radius=float(params["radius"]),
                power=float(params["power"]),
                min_points=int(params["min_points"]),
                max_points=int(params["max_points"]),
            )
            out[start:stop] = block.reshape(stop - start, grid.width)
            done = stop
            ctx.progress("interpolate", done / grid.height,
                         f"rows {done}/{grid.height}")

        ctx.progress("commit", 0.0, "writing the artefact")
        ctx.check_cancel()
        artifact = write_geotiff(
            out, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "RAW",
                "GEOPOTENTIAL_UNIT": params["unit"],
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_SOURCE": str(path.resolve()),
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "samples", "path": str(path.resolve()),
                        "crs": source_crs.name, "samples": int(x.size)}],
            "params": params,
            "grid": grid.describe(),
            "gridding": {"method": "idw", "interpolates": True, **provenance},
            "statistics": {"unit": params["unit"], **idw_grid.statistics(out)},
        }


class EuclideanDistanceOperator(Operator):
    """Distance to the nearest feature. Measures; does not estimate."""

    name = "grid.euclidean_distance"
    version = "1.0.0"
    summary = "Distance from every cell to the nearest input feature."
    reference = ("Felzenszwalb & Huttenlocher (2012), exact distance "
                 "transform; IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06.")

    parameters = GRID_PARAMETERS + (
        Parameter(name="source_crs", type="str", default=None,
                  doc="CRS the features are in. Required for a table."),
        Parameter(name="x_field", type="str", default=None,
                  doc="Column holding the X coordinate, for a table."),
        Parameter(name="y_field", type="str", default=None,
                  doc="Column holding the Y coordinate, for a table."),
        Parameter(name="layer", type="str", default=None,
                  doc="Layer of a multi-layer vector file."),
        Parameter(name="max_distance", type="float", default=None,
                  minimum=1e-9, unit="CRS unit",
                  doc="Beyond this the result is null rather than a number "
                      "nobody asked for. Recorded in the manifest."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        path = _one_input(self.name, inputs)
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("a euclidean distance field")
        source_crs = _source_crs(path, params)

        ctx.progress("read", 0.0, f"reading {path.name}")
        ctx.check_cancel()
        geometries, x, y = self._features(path, params, source_crs, target_crs)
        if geometries is None:
            data_bounds = (float(x.min()), float(y.min()),
                           float(x.max()), float(y.max()))
            count = int(x.size)
        else:
            xs = np.concatenate([np.asarray(g.bounds)[[0, 2]] for g in geometries])
            ys = np.concatenate([np.asarray(g.bounds)[[1, 3]] for g in geometries])
            data_bounds = (float(xs.min()), float(ys.min()),
                           float(xs.max()), float(ys.max()))
            count = len(geometries)
        ctx.progress("read", 1.0, f"{count} features")

        grid, plan, provenance = _grid_for(
            ctx, params, data_bounds, self.name, target_crs)
        ctx.progress("plan", 1.0, plan.summary())

        ctx.check_cancel()
        occupied = (
            rasterize_grid.points_mask(x, y, grid) if geometries is None
            else rasterize_grid.mask(geometries, grid, all_touched=True)
        )
        ctx.progress("mask", 1.0, f"{int(occupied.sum())} cells hold a feature")

        cap = params.get("max_distance")
        out = distance_grid.to_features(
            occupied, grid.pixel_size,
            max_distance=float(cap) if cap else None)
        ctx.progress("distance", 1.0, "transform complete")

        ctx.check_cancel()
        artifact = write_geotiff(
            out, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "RAW",
                "GEOPOTENTIAL_UNIT": target_crs.unit or "CRS unit",
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_SOURCE": str(path.resolve()),
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "features", "path": str(path.resolve()),
                        "crs": source_crs.name, "features": count}],
            "params": params,
            "grid": grid.describe(),
            "gridding": {"method": "euclidean_distance", "interpolates": False,
                         "cells_on_feature": int(occupied.sum()), **provenance},
            "statistics": {"unit": target_crs.unit or "CRS unit",
                           **distance_grid.statistics(out)},
        }

    @staticmethod
    def _features(path: Path, params, source_crs, target_crs):  # noqa: ANN001
        """Geometries in the target CRS, or point coordinates for a table."""
        if path.suffix.lower() in (".csv", ".xyz", ".txt", ".dat"):
            params = dict(params)
            params.setdefault("value_field", params.get("x_field"))
            x, y, _ = _read_points(path, params)
            x, y = _to_target(x, y, source_crs, target_crs)
            return None, x, y

        import geopandas as gpd

        layer = params.get("layer")
        gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
        if gdf.crs is not None and source_crs != target_crs:
            gdf = gdf.to_crs(target_crs.crs)
        geometries = [g for g in gdf.geometry if g is not None and not g.is_empty]
        if not geometries:
            raise ValueError(f"{path.name}: holds no usable geometry.")
        return geometries, np.array([]), np.array([])


class RasterizeOperator(Operator):
    """Burn a feature's own value into the cells it covers."""

    name = "grid.rasterize"
    version = "1.0.0"
    summary = "Burn a vector attribute into the cells its feature covers."
    reference = "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06, rasterização."

    parameters = GRID_PARAMETERS + (
        Parameter(name="unit", type="str", required=True,
                  doc="Physical unit of the burned attribute."),
        Parameter(name="value_field", type="str", required=True,
                  doc="Attribute whose value each feature burns."),
        Parameter(name="source_crs", type="str", default=None,
                  doc="CRS of the features, when the file declares none."),
        Parameter(name="layer", type="str", default=None,
                  doc="Layer of a multi-layer vector file."),
        Parameter(name="all_touched", type="bool", default=False,
                  doc="True gives a cell to any feature touching it; False, "
                      "only to one covering its centre. They differ along "
                      "every boundary, and the choice is recorded."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        import geopandas as gpd

        path = _one_input(self.name, inputs)
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("a rasterized criterion grid")
        source_crs = _source_crs(path, params)

        ctx.progress("read", 0.0, f"reading {path.name}")
        ctx.check_cancel()
        layer = params.get("layer")
        gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
        field = params["value_field"]
        if field not in gdf.columns:
            raise ParameterError(
                f"value_field={field!r} is not a field of {path.name}. It has: "
                f"{', '.join(c for c in gdf.columns if c != gdf.geometry.name)}"
            )
        if gdf.crs is not None and source_crs != target_crs:
            gdf = gdf.to_crs(target_crs.crs)
        ctx.progress("read", 1.0, f"{len(gdf)} features")

        left, bottom, right, top = (float(v) for v in gdf.total_bounds)
        grid, plan, provenance = _grid_for(
            ctx, params, (left, bottom, right, top), self.name, target_crs)
        ctx.progress("plan", 1.0, plan.summary())

        ctx.check_cancel()
        pairs = list(zip(gdf.geometry,
                         gdf[field].to_numpy(dtype=np.float64, na_value=np.nan)))
        out = rasterize_grid.burn(
            pairs, grid, all_touched=bool(params["all_touched"]))
        ctx.progress("rasterize", 1.0, "burned")

        artifact = write_geotiff(
            out, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "RAW",
                "GEOPOTENTIAL_UNIT": params["unit"],
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_SOURCE": str(path.resolve()),
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "features", "path": str(path.resolve()),
                        "crs": source_crs.name, "features": int(len(gdf))}],
            "params": params,
            "grid": grid.describe(),
            "gridding": {"method": "rasterize", "interpolates": False,
                         "all_touched": bool(params["all_touched"]),
                         **provenance},
            "statistics": {"unit": params["unit"],
                           **rasterize_grid.statistics(out)},
        }


#: What the two triangulated operators share. Declared once, for the same
#: reason `GRID_PARAMETERS` is: two operators that mean different things by
#: `max_distance` would be a defect nobody could see from either one.
_TIN_PARAMETERS = (
    Parameter(name="unit", type="str", required=True,
              doc="Physical unit of the samples; the field carries it."),
    Parameter(name="source_crs", type="str", default=None,
              doc="CRS the coordinates are in. Required for a table."),
    Parameter(name="x_field", type="str", default=None,
              doc="Column holding the X coordinate."),
    Parameter(name="y_field", type="str", default=None,
              doc="Column holding the Y coordinate."),
    Parameter(name="value_field", type="str", default=None,
              doc="Column holding the measurement."),
    Parameter(name="layer", type="str", default=None,
              doc="Layer of a multi-layer vector file."),
    Parameter(name="max_distance", type="float", default=None, minimum=1e-9,
              unit="CRS unit",
              doc="Cells farther than this from every sample stay null. "
                  "Absent, the convex hull of the samples is the only limit, "
                  "which is what QGIS does; present, it keeps one wide "
                  "triangle from filling a gap nobody surveyed."),
)


class _TriangulatedOperator(Operator):
    """Interpolation over a Delaunay triangulation of the samples.

    The subclass names the method. Everything else — reading the samples,
    moving them into the grid's CRS, the grid, the blocks, the artefact and
    the manifest — is identical, and identical here rather than in two files
    that drift.
    """

    method = ""
    parameters = GRID_PARAMETERS + _TIN_PARAMETERS

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        path = _one_input(self.name, inputs)
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric(f"{self.method} triangulated interpolation")

        ctx.progress("read", 0.0, f"reading {path.name}")
        ctx.check_cancel()
        x, y, values = _read_points(path, params)
        source_crs = _source_crs(path, params)
        x, y = _to_target(x, y, source_crs, target_crs)
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
        if not finite.any():
            raise ValueError(
                f"{path.name}: no sample has a finite coordinate and value.")
        x, y, values = x[finite], y[finite], values[finite]
        ctx.progress("read", 1.0, f"{x.size} samples")

        data_bounds = (float(x.min()), float(y.min()),
                       float(x.max()), float(y.max()))
        grid, plan, provenance = _grid_for(
            ctx, params, data_bounds, self.name, target_crs)
        ctx.progress("plan", 1.0, plan.summary())

        # Once, not per block: the triangulation is O(n log n) and every block
        # queries the same surface.
        ctx.check_cancel()
        try:
            surface = tin_grid.build(x, y, values, method=self.method)
        except tin_grid.TriangulationFailed as refusal:
            raise ParameterError(str(refusal)) from refusal
        ctx.progress("triangulate", 1.0, f"{x.size} samples triangulated")

        cap = params.get("max_distance")
        cap = float(cap) if cap else None
        out = np.full(grid.shape, np.nan, dtype=np.float32)
        done = 0
        for start, stop in grid_spec.row_blocks(grid, plan):
            ctx.check_cancel()
            cell_x, cell_y = grid_spec.cell_centres(grid, start, stop)
            block = surface(cell_x, cell_y)
            if cap is not None:
                block = np.where(
                    tin_grid.distance_to_nearest(x, y, cell_x, cell_y) <= cap,
                    block, np.nan)
            out[start:stop] = block.reshape(
                stop - start, grid.width).astype(np.float32)
            done = stop
            ctx.progress("interpolate", done / grid.height,
                         f"rows {done}/{grid.height}")

        statistics = tin_grid.statistics(
            out, sample_interval=(float(values.min()), float(values.max())))

        ctx.progress("commit", 0.0, "writing the artefact")
        ctx.check_cancel()
        artifact = write_geotiff(
            out, grid, ctx.output_dir / f"{params['result_name']}.tif",
            tags={
                "GEOPOTENTIAL_STAGE": "RAW",
                "GEOPOTENTIAL_UNIT": params["unit"],
                "GEOPOTENTIAL_OPERATOR": f"{self.name}@{self.version}",
                "GEOPOTENTIAL_SOURCE": str(path.resolve()),
            },
        )
        ctx.emit(params["result_name"], artifact)
        ctx.progress("commit", 1.0, f"{artifact.path.name} {artifact.hash[:19]}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "samples", "path": str(path.resolve()),
                        "crs": source_crs.name, "samples": int(x.size)}],
            "params": params,
            "grid": grid.describe(),
            "gridding": {
                "method": f"tin_{self.method}",
                "interpolates": True,
                "bounded_by": "convex hull of the samples",
                "max_distance": cap,
                "may_overshoot": self.method == "cubic",
                **provenance,
            },
            "statistics": {"unit": params["unit"], **statistics},
        }


class TinLinearOperator(_TriangulatedOperator):
    """Barycentric interpolation inside each Delaunay triangle.

    Continuous, never above the highest sample of its triangle nor below the
    lowest, and visibly faceted: the slope changes at every triangle edge.
    QGIS calls this TIN interpolation, method Linear.
    """

    name = "grid.tin_linear"
    version = "1.0.0"
    method = "linear"
    summary = ("Interpolate point samples over a Delaunay triangulation, "
               "linear inside each triangle (QGIS: TIN, Linear).")
    reference = ("Delaunay, B. (1934), Bull. Acad. Sci. URSS; "
                 "scipy.interpolate.LinearNDInterpolator; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06.")


class TinCubicOperator(_TriangulatedOperator):
    """Clough-Tocher: a cubic patch per triangle, C1 across every edge.

    Smooth where the linear method is faceted, and the best fit of the three
    on samples that sit on a lattice. **It can overshoot the samples'
    interval** — that is what a C1 cubic does at a sharp step, it is recorded
    in the manifest as `overshoot`, and it is not clamped (`ADR-MSP-007`).
    QGIS calls this TIN interpolation, method Clough-Toucher.
    """

    name = "grid.tin_cubic"
    version = "1.0.0"
    method = "cubic"
    summary = ("Interpolate point samples over a Delaunay triangulation, "
               "Clough-Tocher cubic (QGIS: TIN, Clough-Toucher).")
    reference = ("Clough, R. & Tocher, J. (1965), Proc. Conf. Matrix Methods "
                 "in Structural Mechanics; Alfeld, P. (1984), CAGD 1(2); "
                 "scipy.interpolate.CloughTocher2DInterpolator; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06.")


class CrossValidateOperator(Operator):
    """Which interpolator fits these samples. Measured, and read-only.

    Holds samples out, predicts them with each method, and reports the error
    in the samples' own unit. It writes nothing and registers nothing: it is a
    decision aid taken *before* a run, and an inspection that half-committed a
    run would be the defect P-53 exists to prevent.
    """

    name = "grid.cross_validate"
    version = "1.0.0"
    read_only = True
    summary = ("Hold samples out and measure each interpolation method's "
               "error, in the samples' own unit.")
    reference = ("Stone, M. (1974), J. R. Stat. Soc. B 36(2), 111-147; "
                 "IMPLEMENTACAO_GEOPOTENTIAL_MSP.md MSP-06.")

    parameters = (
        Parameter(name="target_crs", type="str", required=True,
                  doc="CRS the comparison is made in. There is no default: a "
                      "distance decides every method, so it must be metric."),
        Parameter(name="source_crs", type="str", default=None,
                  doc="CRS the coordinates are in. Required for a table."),
        Parameter(name="x_field", type="str", default=None,
                  doc="Column holding the X coordinate."),
        Parameter(name="y_field", type="str", default=None,
                  doc="Column holding the Y coordinate."),
        Parameter(name="value_field", type="str", default=None,
                  doc="Column holding the measurement."),
        Parameter(name="layer", type="str", default=None,
                  doc="Layer of a multi-layer vector file."),
        Parameter(name="radius", type="float", required=True, minimum=1e-9,
                  unit="CRS unit",
                  doc="The search radius grid.idw would run with, so the "
                      "comparison scores the run about to be made."),
        Parameter(name="power", type="float", default=2.0, minimum=0.0,
                  doc="Shepard's p, as grid.idw would run with it."),
        Parameter(name="min_points", type="int", default=1, minimum=1,
                  doc="As grid.idw would run with it."),
        Parameter(name="max_points", type="int", default=16, minimum=1,
                  doc="As grid.idw would run with it."),
        Parameter(name="max_distance", type="float", default=None,
                  minimum=1e-9, unit="CRS unit",
                  doc="As a triangulated method would run with it."),
        Parameter(name="folds", type="int", default=5, minimum=2,
                  doc="k in k-fold. 5 holds out a fifth at a time."),
    )

    def run(
        self, inputs: Sequence[str], params: dict[str, Any], ctx: Context
    ) -> dict[str, Any]:
        path = _one_input(self.name, inputs)
        target_crs = CrsInfo.from_user_input(params["target_crs"],
                                             source="target_crs")
        target_crs.require_metric("comparing interpolation methods")

        ctx.progress("read", 0.0, f"reading {path.name}")
        ctx.check_cancel()
        x, y, values = _read_points(path, params)
        source_crs = _source_crs(path, params)
        x, y = _to_target(x, y, source_crs, target_crs)
        ctx.progress("read", 1.0, f"{np.size(x)} samples")

        ctx.check_cancel()
        cap = params.get("max_distance")
        comparison = crossval.compare(
            x, y, values,
            radius=float(params["radius"]),
            power=float(params["power"]),
            min_points=int(params["min_points"]),
            max_points=int(params["max_points"]),
            max_distance=float(cap) if cap else None,
            folds=int(params["folds"]),
        )
        ctx.progress("compare", 1.0,
                     f"recommended: {comparison.get('recommended') or 'none'}")

        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "samples", "path": str(path.resolve()),
                        "crs": source_crs.name}],
            "params": params,
            "cross_validation": comparison,
        }
