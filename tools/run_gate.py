#!/usr/bin/env python3
"""Regression gate for geopotencial_msp.

Classifies each suite as PASS, FAIL or BLOCKED. BLOCKED means the gate could
not be evaluated — a missing dependency, an absent fixture — and is never
reported as PASS and never as FAIL. A missing `rasterio` is not a red gate.

    tools/run_gate.py                      everything
    tools/run_gate.py --only membership    one suite
    tools/run_gate.py --list               what there is to run

Exit codes:  0 PASS   1 FAIL   2 BLOCKED
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_PATH = ROOT / "app"
WORKER_PATH = ROOT / "worker"
def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
# The smoke dataset. Real, and in the repository: EPSG:26912, 10 m, a
# distance-to-fault field over the Utah FORGE geothermal site. `../data/` is
# the project's only dataset directory; nothing here creates another.
SMOKE_RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"

GEO_STACK = ["numpy", "rasterio", "pyproj", "affine"]
QT = ["PySide6"]

# name -> (test module, dependencies, required fixture)
SUITES: dict[str, tuple[str, list[str], Path | None]] = {
    "membership": ("tests.unit.test_membership", ["numpy"], None),
    "domain":     ("tests.unit.test_domain", ["numpy", "pyproj", "affine"], None),
    "protocol":   ("tests.contract.test_protocol", [], None),
    "store":      ("tests.integration.test_store", [], None),
    "io-render":  ("tests.integration.test_io_and_render", GEO_STACK, None),
    "commands":   ("tests.unit.test_commands", QT, None),
    "recovery":   ("tests.integration.test_recovery", QT, None),
    "describe":   ("tests.unit.test_describe_and_plan", GEO_STACK + ["geopandas"], None),
    "qc":         ("tests.synthetic.test_qc_fixtures", GEO_STACK,
                   DATA / "synthetic" / "msp" / "broken" / "MANIFEST.json"),
    "import":     ("tests.integration.test_import_flow", GEO_STACK + QT,
                   DATA / "synthetic" / "msp" / "broken" / "MANIFEST.json"),
    "gridding":   ("tests.unit.test_gridding",
                   GEO_STACK + ["scipy", "pandas", "geopandas", "shapely"],
                   DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"),
    # The lattice file is a fixture of this suite, not a nicety: the finding
    # that justifies the triangulated methods is measured on it.
    "interpolation": ("tests.unit.test_interpolation",
                      GEO_STACK + ["scipy", "pandas"],
                      DATA / "utah_forge" / "vp_500_m.csv"),
    "decision":   ("tests.unit.test_decision", ["numpy", "pyproj", "affine"], None),
    # O caminho MCDA num domínio que não é o geotérmico. Fecha a lacuna de
    # evidência que todo gate anterior tinha: todos rodavam sobre Utah.
    # A corrente que o produto existe para percorrer: .csv e .tif na mesma
    # análise. As peças eram gateadas; a corrente que as liga, não.
    "mixed-sources": ("tests.integration.test_mixed_sources",
                      GEO_STACK + ["pandas", "scipy"], SMOKE_RASTER),
    "other-domain": ("tests.integration.test_other_domain",
                     GEO_STACK, DATA / "conditioning_factors" / "slope.tif"),
    # Todo arquivo de `../data/` é lido, e nenhum apodrece em silêncio. Anda
    # no diretório em vez de nomear arquivos: acrescentar um fixture já o põe
    # neste gate. Antes dele, 26 dos 56 arquivos não eram citados por teste
    # nem storyboard nenhum da árvore.
    "data-coverage": ("tests.integration.test_data_coverage",
                      GEO_STACK + ["pandas"], DATA),
    "scenarios":  ("tests.unit.test_scenarios",
                   ["numpy", "pyproj", "affine", "scipy"], None),
    # A suíte sintética do M7: o caso conhecido decide a convenção de sinal,
    # e nenhum filtro é comparado consigo mesmo (FIS-01, FIS-04).
    "potential-fields": ("tests.unit.test_potential_fields",
                         ["numpy"], None),
    "pipeline":   ("tests.integration.test_pipeline", GEO_STACK + QT,
                   DATA / "synthetic" / "msp" / "canvas" / "MANIFEST.json"),
    "canvas":     ("tests.unit.test_canvas", GEO_STACK,
                   DATA / "synthetic" / "msp" / "canvas" / "MANIFEST.json"),
    "aoi-diff":   ("tests.integration.test_aoi_and_difference", GEO_STACK + QT,
                   DATA / "synthetic" / "msp" / "canvas" / "MANIFEST.json"),
    "workflow":   ("tests.unit.test_workflow", [], None),
    "menus":      ("tests.ui.test_shell", GEO_STACK + QT, None),
    "layers":     ("tests.unit.test_layers", GEO_STACK + QT, SMOKE_RASTER),
    "tools":      ("tests.unit.test_map_tools", GEO_STACK + QT, SMOKE_RASTER),
    "i18n":       ("tests.unit.test_i18n", [], None),
    "theme":      ("tests.unit.test_theme", QT, None),
    "coordinates": ("tests.unit.test_coordinates", GEO_STACK + QT, SMOKE_RASTER),
    "basemap":    ("tests.unit.test_basemap", QT, None),
    # Qt is a real dependency here: the preview is drawn on the canvas, and a
    # missing PySide6 must report BLOCKED rather than quietly skipping the
    # half of this suite that proves a vector reaches the screen.
    "preview":    ("tests.unit.test_preview",
                   GEO_STACK + QT + ["pandas", "geopandas"],
                   DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"),
}

# The interface gate drives the real application headless and asserts on the
# authoritative state. A UI claim without this is a screenshot somebody took
# once.
INTERFACE = {
    "vertical-slice": (["--self-test", str(SMOKE_RASTER)], GEO_STACK + QT, SMOKE_RASTER),
}

RESET, RED, GREEN, YELLOW = "\033[0m", "\033[31m", "\033[32m", "\033[33m"


def colour(status: str) -> str:
    if not sys.stdout.isatty():
        return status
    return {"PASS": GREEN, "FAIL": RED, "BLOCKED": YELLOW}[status] + status + RESET


def missing(modules: list[str]) -> list[str]:
    return [m for m in modules if importlib.util.find_spec(m) is None]


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(APP_PATH), str(WORKER_PATH), str(ROOT)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, *args], cwd=ROOT, env=child_env(),
        capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def run_architecture() -> tuple[str, str]:
    code, output = run([str(ROOT / "tools" / "architecture_check.py")])
    headline = output.splitlines()[0] if output else "no output"
    return ("PASS" if code == 0 else "FAIL"), headline


def run_fixtures() -> tuple[str, str]:
    """The generated datasets the gates need. Derived, never shipped.

    Generate first, then check. Checking alone passes on the machine that has
    run the generators once before and blocks six checks on every machine that
    has not — which is what a fresh clone is. Each generator is a no-op when
    its output is already there, so this costs nothing on the second run.
    """
    for script in ("make_synthetic_data.py", "make_broken_fixtures.py",
                   "make_canvas_fixtures.py"):
        code, output = run([str(ROOT / "tools" / script)])
        if code != 0:
            head = output.splitlines()[0] if output else "no output"
            return "BLOCKED", f"{script}: {head}"
    lines = []
    for script in ("make_broken_fixtures.py", "make_canvas_fixtures.py"):
        code, output = run([str(ROOT / "tools" / script), "--check"])
        line = output.splitlines()[0] if output else script
        if code != 0:
            return "BLOCKED", line
        lines.append(line.split("— ")[-1])
    return "PASS", "; ".join(lines)


def run_interaction() -> tuple[str, str]:
    """Drive the real window and survive it.

    Every other check renders offscreen, on Qt's basic render loop. The
    application a person opens may render on its own thread, and two
    segmentation faults lived exactly in that difference. BLOCKED without a
    display: a machine that has none cannot answer this.
    """
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "BLOCKED", "no display; the real-window check needs one"
    missing_modules = missing(GEO_STACK + QT)
    if missing_modules:
        return "BLOCKED", f"missing: {', '.join(missing_modules)}"
    code, output = run([str(ROOT / "tools" / "interaction_check.py")])
    if code == 2:
        return "BLOCKED", output.strip().splitlines()[-1] if output else "blocked"
    summary = [line for line in output.splitlines() if "interactions survived" in line]
    return ("PASS" if code == 0 else "FAIL",
            summary[-1] if summary else output.strip().splitlines()[-1])


def run_storyboards() -> tuple[str, str]:
    """Every interface storyboard, re-captured and checked.

    A frame that came out blank, or a step that changed nothing, is a broken
    interface — and it fails here rather than being noticed in a screenshot
    three milestones later.
    """
    code, output = run([str(ROOT / "tools" / "capture_sequence.py"),
                        "--all", "--check"])
    lines = [l.strip() for l in output.splitlines() if "frames ok" in l]
    return ("PASS" if code == 0 else "FAIL"), (
        "; ".join(l.split(";")[0] for l in lines) if lines else "no storyboard ran"
    )


def run_schemas() -> tuple[str, str]:
    """The published schemas must still describe the protocol module.

    A protocol change that forgot to regenerate is caught here rather than
    discovered by whoever trusted the schema.
    """
    for script in ("generate_ipc_schemas.py", "export_project_schema.py"):
        code, output = run([str(ROOT / "tools" / script), "--check"])
        if code != 0:
            return "FAIL", (output.splitlines()[0] if output else script)
    return "PASS", "IPC, project and operator schemas match the code"


def run_architecture_negative() -> tuple[str, str]:
    """The gate has to be able to fail, or it is decoration."""
    code, output = run([str(ROOT / "tools" / "architecture_check.py"), "--self-check"])
    tail = [l for l in output.splitlines() if "proved able to fail" in l or "not gates" in l]
    return ("PASS" if code == 0 else "FAIL"), (tail[-1] if tail else "no output")


def run_suite(name: str) -> tuple[str, str]:
    module, deps, fixture = SUITES[name]
    absent = missing(deps)
    if absent:
        return "BLOCKED", f"not installed: {', '.join(absent)}"
    if fixture is not None and not fixture.exists():
        return "BLOCKED", f"fixture absent: {fixture}"
    code, output = run(["-m", "unittest", module, "-v"])
    last = [l for l in output.splitlines() if l.startswith(("OK", "FAILED", "Ran "))]
    summary = " ".join(last[-2:]) if last else output.splitlines()[-1:] or ["no output"]
    return ("PASS" if code == 0 else "FAIL"), (summary if isinstance(summary, str) else str(summary))


def run_interface(name: str) -> tuple[str, str]:
    args, deps, fixture = INTERFACE[name]
    absent = missing(deps)
    if absent:
        return "BLOCKED", f"not installed: {', '.join(absent)}"
    if fixture is not None and not fixture.exists():
        return "BLOCKED", f"fixture absent: {fixture.relative_to(ROOT.parent)}"
    code, output = run(["-m", "geopotential_app", *args])
    tail = [l for l in output.splitlines() if "checks passed" in l]
    return ("PASS" if code == 0 else "FAIL"), (tail[-1] if tail else "no summary line")


def main() -> int:
    names = ["architecture", "architecture-negative", "schemas", "fixtures",
             *SUITES, *INTERFACE, "interaction", "storyboards"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=names, help="run a single check")
    parser.add_argument("--list", action="store_true", help="list the checks")
    args = parser.parse_args()

    if args.list:
        for name in names:
            print(name)
        return 0

    selected = [args.only] if args.only else names
    results: list[tuple[str, str, str]] = []
    for name in selected:
        if name == "architecture":
            status, detail = run_architecture()
        elif name == "architecture-negative":
            status, detail = run_architecture_negative()
        elif name == "schemas":
            status, detail = run_schemas()
        elif name == "fixtures":
            status, detail = run_fixtures()
        elif name == "interaction":
            status, detail = run_interaction()
        elif name == "storyboards":
            status, detail = run_storyboards()
        elif name in SUITES:
            status, detail = run_suite(name)
        elif name in INTERFACE:
            status, detail = run_interface(name)
        else:
            status, detail = run_storyboards()
        results.append((name, status, detail))
        width = max(len(n) for n in names)
        print(f"{colour(status):<18} {name.ljust(width)}  {detail}")

    failed = sum(1 for _, s, _ in results if s == "FAIL")
    blocked = sum(1 for _, s, _ in results if s == "BLOCKED")
    passed = len(results) - failed - blocked
    print(f"\n{passed} passed, {failed} failed, {blocked} blocked, of {len(results)}")
    if failed:
        return 1
    if blocked:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
