"""M5 — the decision flow, state by state.

The gate is a flow, so the storyboard is the flow:

    dados -> QA/QC -> harmonização -> membership -> AHP/pesos -> MCDA
          -> prospectividade

Each frame is one arrow. What is photographed is the screen a person would be
looking at when they take that step, with the numbers that step produced.
"""
from __future__ import annotations

from capture_sequence import Storyboard  # noqa: E402
from session import DATA  # noqa: E402

CANVAS = DATA / "synthetic" / "msp" / "canvas"
FIELD_A = CANVAS / "large_field.tif"
FIELD_B = CANVAS / "large_field_b.tif"

TARGET_CRS = "EPSG:26912"
PIXEL = 40.0

PROBES = {
    "workflow": (100, 500),
    "canvas": (700, 360),
    "inspector": (1300, 500),
    "statusbar": (700, 869),
}


def build() -> Storyboard:
    board = Storyboard("m5", "M5 — Geothermal Decision Engine")
    state: dict = {}

    def qc(session):
        """dados -> QA/QC."""
        report = session.validate(FIELD_A, {"unit": "mGal"})["report"]
        session.canvas.showArtifact(str(FIELD_A.resolve()), "mGal")
        session.describe(FIELD_A, {"unit": "mGal"})
        return {"usable": report["usable"], "severity": report["severity"]}

    def harmonize(session):
        """QA/QC -> harmonização."""
        finished, manifests = [], []
        session.controller._job_controller.jobFinished.connect(
            lambda _j, s: finished.append(s)
        )
        session.controller.supervisor.jobSucceeded.connect(
            lambda m: manifests.append(m["manifest"])
        )
        session.controller.submit("grid.harmonize", {
            "target_crs": TARGET_CRS, "pixel_size": PIXEL,
            "extent_policy": "intersection",
            "layers": [
                {"path": str(FIELD_A), "name": "heat_proxy", "unit": "mGal",
                 "resampling": "bilinear"},
                {"path": str(FIELD_B), "name": "structure_proxy", "unit": "mGal",
                 "resampling": "bilinear"},
            ],
        }, [])
        session.wait_for(lambda: bool(finished))
        manifest = manifests[-1] if manifests else {}
        state["layers"] = {l["name"]: l["artifact"] for l in manifest.get("layers", [])}
        grid = manifest.get("grid", {})
        if state["layers"]:
            session.canvas.showArtifact(state["layers"]["heat_proxy"], "mGal")
        return {"grid": f"{grid.get('width')}x{grid.get('height')}",
                "crs": grid.get("crs"), "layers": len(state["layers"])}

    def membership(session):
        """harmonização -> membership. The editor, with curve over histogram."""
        described = session.describe(
            state["layers"]["heat_proxy"], {"unit": "mGal"}
        )
        session.wizard  # keep the reference alive
        editor = session.window.findChild(type(session.window), "membershipEditor")
        editor = editor or _find(session, "membershipEditor")
        editor.setProperty("criterion", {
            "name": "heat_proxy", "path": state["layers"]["heat_proxy"],
            "unit": "mGal", "statistics": described.get("statistics", {}),
        })
        editor.setProperty("functionName", "linear_increasing")
        editor.open()
        return {"function": "linear_increasing",
                "sense": "more is more favourable"}

    def weights(session):
        """membership -> AHP/pesos. The decision model, with the CR stated."""
        _find(session, "membershipEditor").close()
        seen = []
        session.controller.supervisor.jobSucceeded.connect(
            lambda m: seen.append(m["manifest"])
        )
        session.controller.submit("decision.ahp_weights", {
            "matrix": [[1, 3], [1 / 3, 1]],
            "names": ["heat_proxy", "structure_proxy"],
        }, [])
        session.wait_for(lambda: bool(seen))
        ahp = seen[-1]["ahp"] if seen else {}
        state["ahp"] = ahp

        model = _find(session, "decisionModel")
        model.setProperty("criteria", [
            {"name": "heat_proxy", "path": state["layers"]["heat_proxy"],
             "unit": "mGal", "function": "linear_increasing", "group": "thermal"},
            {"name": "structure_proxy", "path": state["layers"]["structure_proxy"],
             "unit": "mGal", "function": "linear_decreasing", "group": "structural"},
        ])
        model.setProperty("ahp", ahp)
        model.open()
        return {"cr": round(ahp.get("cr", 0), 4),
                "consistent": ahp.get("consistent"),
                "w_heat": round(ahp.get("weights_by_name", {})
                                .get("heat_proxy", 0), 3)}

    def inconsistent(session):
        """The refusal, on screen: Run disabled until a justification exists."""
        model = _find(session, "decisionModel")
        model.setProperty("ahp", {
            "cr": 0.8623, "threshold": 0.10, "lambda_max": 4.1,
            "consistent": False,
            "weights_by_name": {"heat_proxy": 0.4, "structure_proxy": 0.6},
        })
        model.setProperty("correlations", [{
            "message": "'heat_proxy' and 'structure_proxy' correlate at "
                       "r = +0.91 over 640,000 shared pixels. They may be "
                       "measuring the same evidence, in which case independent "
                       "weights count it twice. Put them in one hierarchical "
                       "group, drop one, or record why both belong.",
        }])
        return {"cr": 0.8623, "run_enabled": False}

    def prospectivity(session):
        """MCDA -> prospectividade."""
        model = _find(session, "decisionModel")
        model.setProperty("ahp", state.get("ahp", {}))
        model.close()
        finished, manifests = [], []
        session.controller._job_controller.jobFinished.connect(
            lambda _j, s: finished.append(s)
        )
        session.controller.supervisor.jobSucceeded.connect(
            lambda m: manifests.append(m["manifest"])
        )
        session.controller.submit("decision.aggregate", {
            "method": "fuzzy_gamma", "gamma": 0.7,
            "result_name": "prospectivity",
            "criteria": [
                {"path": state["layers"]["heat_proxy"], "name": "heat_proxy",
                 "unit": "mGal", "function": "linear_increasing"},
                {"path": state["layers"]["structure_proxy"],
                 "name": "structure_proxy", "unit": "mGal",
                 "function": "linear_decreasing"},
            ],
        }, [])
        session.wait_for(lambda: bool(finished))
        manifest = manifests[-1] if manifests else {}
        runs = session.controller.store.runs()
        if runs:
            artifacts = session.controller.store.artifacts(runs[-1].id)
            if artifacts:
                session.canvas.showArtifact(artifacts[-1]["path"],
                                            "suitability [0-1]")
        result = manifest.get("result", {})
        return {"method": result.get("method"),
                "range": f"{result.get('min', 0):.3f}-{result.get('max', 0):.3f}",
                "valid": round(result.get("valid_fraction", 0) * 100, 1)}

    board.step("qc", "The layer, checked before anything is computed with it.",
               qc, probes=PROBES, must_change=False)
    board.step("harmonized", "Two layers brought onto one target grid in "
               "EPSG:26912 at 40 m — the step every later one assumes.",
               harmonize, probes=PROBES)
    def curve_is_drawn(frame, earlier):
        """MSP-07 asks for the curve and the histogram **at the same time**.

        Asserted by counting pixels of the curve's own colour, because "the
        curve is on screen" is exactly the kind of claim that reads as true
        from a thumbnail and is false. It was: the curve rendered as a flat
        line along the bottom for three iterations, because the anchors were
        empty, and nothing but this count would have said so.
        """
        from PIL import Image

        panel = Image.open(frame.path).convert("RGB").crop((330, 150, 1110, 330))
        warn = (224, 179, 65)  # Theme.warn
        drawn = sum(
            1 for pixel in panel.get_flattened_data()
            if abs(pixel[0] - warn[0]) < 40 and abs(pixel[1] - warn[1]) < 40
            and abs(pixel[2] - warn[2]) < 50
        )
        # The caption alone accounts for about 150 px; a drawn curve is several
        # hundred more.
        if drawn < 400:
            return (f"only {drawn} curve-coloured pixels in the distribution "
                    f"panel; the membership curve is not drawn over the "
                    f"histogram")
        return None

    board.step("membership_editor", "MSP-07's five things at once: histogram, "
               "curve, unit, physical sense and the range they act on.",
               membership, probes=PROBES, expect=curve_is_drawn)
    board.step("decision_model", "Weights from a comparison matrix, with the "
               "consistency ratio on screen beside them.", weights,
               probes=PROBES)
    board.step("inconsistent_refused", "CR above the threshold: Run is "
               "disabled, the reason is on the button, and the correlated pair "
               "is named.", inconsistent, probes=PROBES)
    board.step("prospectivity", "The suitability map: Fuzzy Gamma at 0.7 over "
               "the normalized stack, in [0,1], with a manifest that "
               "reproduces it.", prospectivity, probes=PROBES)

    return board


def _find(session, object_name: str):  # noqa: ANN001
    from PySide6.QtCore import QObject

    found = session.window.findChild(QObject, object_name)
    if found is None:
        raise RuntimeError(f"{object_name} is not in the shell")
    return found
