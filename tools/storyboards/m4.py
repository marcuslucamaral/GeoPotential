"""M4 — the GeoCanvas, state by state.

Photographs the sequence a person actually walks through: open a large layer,
navigate it, watch the level of detail change, draw an area, compare two
layers. Each step declares what must be true of its frame, so the sequence is
checked by the runner rather than by looking at it.
"""
from __future__ import annotations

from pathlib import Path

sys_path_marker = None  # the runner puts this directory on sys.path

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

CANVAS = DATA / "synthetic" / "msp" / "canvas"
LARGE = CANVAS / "large_field.tif"
OTHER = CANVAS / "large_field_b.tif"

# Points worth sampling, in window coordinates at 1440 x 880. Each answers a
# question that would otherwise need eyes.
PROBES = {
    "workflow": (100, 500),   # panel background: the theme is applied
    "canvas": (700, 360),      # the map itself: something is drawn
    "inspector": (1300, 500),  # right panel background
    "statusbar": (700, 869),   # the status bar
}


def build() -> Storyboard:
    board = Storyboard("m4", "M4 — GeoCanvas nativo")

    def empty(session):
        return {"layer": "none"}

    def open_large(session):
        session.canvas.showArtifact(str(LARGE.resolve()), "mGal")
        described = session.describe(LARGE, {"unit": "mGal"})
        state = session.canvas_state
        return {
            "lod": state.get("lod"),
            "read": state.get("pixels_read"),
            "valid": round(described.get("statistics", {})
                           .get("valid_fraction", 0) * 100, 1),
        }

    def zoom_in(session):
        session.canvas.zoomBy(0.12)
        session.settle(400)
        state = session.canvas_state
        return {"lod": state.get("lod"), "read": state.get("pixels_read")}

    def zoom_further(session):
        session.canvas.zoomBy(0.12)
        session.settle(400)
        state = session.canvas_state
        return {"lod": state.get("lod"), "read": state.get("pixels_read")}

    def back_to_fit(session):
        session.canvas.zoomToFit()
        session.settle(400)
        return {"lod": session.canvas_state.get("lod")}

    def draw_aoi(session):
        left, bottom, right, top = _bounds(session)
        polygon = [
            [left + 4000, top - 3000], [left + 14000, top - 4000],
            [left + 15000, top - 14000], [left + 3000, top - 13000],
        ]
        session.canvas.setAoiPolygon(polygon)
        saved = session.controller.saveAoi(
            "survey", session.canvas.aoiPolygon(), session.canvas.property("crsName")
        )
        return {"aoi_version": saved.get("version"),
                "area_km2": round(saved.get("area", 0) / 1e6, 1)}

    def split(session):
        session.canvas.showComparison(str(OTHER.resolve()))
        return {"left": session.canvas.property("layerName"),
                "right": session.canvas.property("compareName")}

    def difference(session):
        session.canvas.clearComparison()
        state = session.run_job(
            "grid.difference",
            {"result_name": "field_delta", "unit": "mGal"},
            [str(LARGE.resolve()), str(OTHER.resolve())],
        )
        runs = session.controller.store.runs()
        if runs:
            artifacts = session.controller.store.artifacts(runs[-1].id)
            if artifacts:
                session.canvas.showArtifact(artifacts[-1]["path"], "mGal difference")
        return {"job": state, "runs": len(runs)}

    board.step("empty_canvas", "The shell with no layer: every section that has "
               "not landed names its milestone.", empty,
               probes=PROBES, must_change=False)
    board.step("large_layer_fit", "16.8 Mpx fitted to the window. The badge "
               "states the view is decimated and that values are read at full "
               "resolution.", open_large, probes=PROBES)
    board.step("zoomed_once", "Zoomed in: a finer level is chosen and more "
               "detail appears, but the pixel count read stays screen-sized.",
               zoom_in, probes=PROBES)
    board.step("zoomed_full_res", "Zoomed to full resolution — the level "
               "reaches 1:1 and the scale bar shrinks with it.", zoom_further,
               probes=PROBES)
    def colour_is_stable(frame, earlier):
        """The same map point must have the same colour as before the zoom.

        A stretch derived from whatever tile is on screen makes a colour mean a
        different value at every zoom, so navigating appears to change the
        data. That happened, and this is what catches it coming back.
        """
        first = next((f for f in earlier if f.name == "large_layer_fit"), None)
        if first is None:
            return None
        before, after = first.probes.get("canvas"), frame.probes.get("canvas")
        if before != after:
            return (f"the canvas colour changed across a zoom round-trip: "
                    f"{before} -> {after}; the stretch is not held per layer")
        return None

    board.step("back_to_fit", "Back to the whole layer, at the coarse level "
               "again — and the same colour as before the zoom, because the "
               "stretch belongs to the layer, not to the view.", back_to_fit,
               probes=PROBES, expect=colour_is_stable)
    board.step("aoi_drawn", "An area of interest, saved as version 1 with its "
               "CRS, its vertices and its area.", draw_aoi, probes=PROBES)
    board.step("split_view", "Two layers on one viewport, at the same extent "
               "and the same scale, each named above its half.", split,
               probes=PROBES)
    board.step("difference_map", "A - B computed by the worker on the shared "
               "grid, drawn with a diverging ramp centred on zero.", difference,
               probes=PROBES)

    return board


def _bounds(session) -> tuple[float, float, float, float]:  # noqa: ANN001
    info = session.canvas.viewportInfo() or {}
    extent = info.get("extent")
    if extent:
        return tuple(extent)
    return (330_000.0, 4_229_040.0, 370_960.0, 4_270_000.0)
