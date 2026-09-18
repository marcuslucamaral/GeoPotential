# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for GeoPotential Professional.

Run it through `tools/build_app.sh`, never directly: that script gates the tree
first and exercises the artefact afterwards, and a build that has not been
exercised is not evidence that it works.

**This application is two processes in one file.** The app and the worker are
separate packages that never import each other (`P-02`); in a bundle they are
also two PIDs, started by the binary re-launching itself with `--worker`
(`tools/frozen_entry.py`). Both packages are collected, and the entry script is
the launcher rather than either one.

Five things do not survive a default PyInstaller run, and each is handled
explicitly below:

1. **QML is data, not code.** PyInstaller follows imports; it has no idea that
   `Main.qml` names `ActivityBar`, or that `ActivityBar` names
   `icons/app/import.svg`. The shell — the `.qml` files, the `qmldir` and the
   35 icons — is listed as data at the same position relative to the package
   that it occupies in a checkout, so `utils/paths.qml_dir()` resolves in both
   modes without a branch.

2. **The worker package is not reachable by static analysis from the app**,
   because the app deliberately does not import it. It is collected by name.

3. **PROJ and GDAL carry their own data directories.** `proj.db` is what turns
   `EPSG:26912` into a projection; without it the binary starts, opens a
   window, and dies on the first CRS operation with an error that looks like a
   data problem. They live in the environment's `share/`, not inside the Python
   packages, and a runtime hook points at them.

4. **rasterio, pyogrio and fiona import their extensions dynamically**, so
   static analysis misses them. They are named as hidden imports.

5. **The fixtures are what make `--self-test` mean anything** on a machine with
   no checkout. All of them are bundled: the smoke raster, the 14 defective
   datasets the QA/QC checks need, and the two 4096x4096 rasters the canvas
   checks need. Without the last pair, seven of the 59 checks skip themselves
   and the verification that gates this build gets quietly weaker.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
MSP = SPEC_DIR.parent
APP = MSP / "app"
WORKER = MSP / "worker"
# `../data/` is the only dataset directory, and it is outside this tree.
DATA = MSP.parent / "data"

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
datas = []

# 1. The Qt Quick shell, at the same relative position as in the source tree,
#    so `qml_dir()` is `resource_root() / "qml"` in both modes. The icons come
#    with it: they are inside `qml/GeoPotential/icons/`, and the image provider
#    reads them from there.
qml_src = APP / "geopotential_app" / "qml"
if not (qml_src / "Main.qml").is_file():
    raise SystemExit(f"the QML shell is not at {qml_src}; this build would "
                     f"produce a binary with no window")
datas.append((str(qml_src), "geopotential_app/qml"))

# 2. PROJ and GDAL data, found from the live environment rather than hardcoded:
#    a hardcoded conda path builds on this machine and on no other.
def _proj_data() -> Path | None:
    try:
        import pyproj

        path = Path(pyproj.datadir.get_data_dir())
        return path if (path / "proj.db").exists() else None
    except Exception:
        return None


def _gdal_data() -> Path | None:
    try:
        import rasterio._env

        found = rasterio._env.GDALDataFinder().search()
        return Path(found) if found else None
    except Exception:
        return None


proj_dir = _proj_data()
if proj_dir is None:
    raise SystemExit(
        "PROJ data not found. Without proj.db every CRS operation fails at "
        "runtime, so this build would produce a broken binary."
    )
datas.append((str(proj_dir), "share/proj"))

gdal_dir = _gdal_data()
if gdal_dir is not None:
    datas.append((str(gdal_dir), "share/gdal"))

# 3. The fixtures the shipped binary gates itself with. `repository_root()`
#    returns the bundle root when frozen, so these land where `--self-test`
#    already looks for them.
smoke = DATA / "utah_forge" / "Distance_to_fault.tif"
if smoke.is_file():
    datas.append((str(smoke), "data/utah_forge"))
else:
    print(f"WARNING: {smoke} is missing; the shipped binary will have no "
          f"default input and --screenshot verification will be skipped")

for fixture in ("broken", "canvas"):
    folder = DATA / "synthetic" / "msp" / fixture
    if folder.is_dir():
        datas.append((str(folder), f"data/synthetic/msp/{fixture}"))
    else:
        print(f"WARNING: {folder} is missing; the checks that need it will "
              f"skip themselves in the shipped binary's own gate")

# ---------------------------------------------------------------------------
# Imports static analysis cannot see
# ---------------------------------------------------------------------------
hiddenimports = [
    # The worker package. The app does not import it — that is P-02 — so
    # nothing in the graph leads here and it has to be named.
    "geopotential_worker",
    "geopotential_app",
    # rasterio loads these by name at runtime.
    "rasterio._shim", "rasterio.control", "rasterio.crs", "rasterio.sample",
    "rasterio.vrt", "rasterio._features", "rasterio._warp", "rasterio.rpc",
    # the vector stack. `io/describe.py` imports fiona inside a function.
    "pyogrio._geometry", "pyogrio._io", "pyogrio._ogr", "pyogrio._vsi",
    "fiona._shim", "fiona.schema", "fiona.crs",
    # shapely 2 dispatches through these
    "shapely._geometry_helpers", "shapely._geos",
    # pandas/geopandas engines
    "geopandas._compat", "geopandas.io.file",
    # scipy: cKDTree for IDW and the euclidean distance, Qhull for the two
    # triangulated interpolators, ndimage for the distance transform. All of
    # them reached through `from scipy... import` inside a function.
    "scipy.spatial", "scipy.spatial._qhull", "scipy.spatial.transform",
    "scipy.interpolate", "scipy.ndimage", "scipy._lib.messagestream",
    # SVG is what every interface icon is.
    "PySide6.QtSvg",
]
hiddenimports += collect_submodules("rasterio")
hiddenimports += collect_submodules("pyproj")
hiddenimports += collect_submodules("geopotential_worker")
hiddenimports += collect_submodules("geopotential_app")

binaries = collect_dynamic_libs("rasterio") + collect_dynamic_libs("pyogrio")

# ---------------------------------------------------------------------------
# Libraries that must come from the environment, not from the host
# ---------------------------------------------------------------------------
# PyInstaller resolves a shared library by asking the dynamic loader, and the
# loader answers with the *system* copy when one exists. On the sibling build
# that mixed a conda `libcurl` with a `/usr/lib` `libssl` and produced a binary
# that built cleanly and died at first import:
#
#   ImportError: libssl.so.3: version `OPENSSL_3.2.0' not found
#                (required by libcurl.so.4)
#
# Naming the environment's copies explicitly keeps the pair consistent. Listed
# first so they win the destination-name collision.
import sys as _sys

_env_lib = Path(_sys.prefix) / "lib"
_pinned_binaries = []
for _name in ("libssl.so.3", "libcrypto.so.3", "libcurl.so.4"):
    _candidate = _env_lib / _name
    if _candidate.exists():
        _pinned_binaries.append((str(_candidate.resolve()), "."))

if not _pinned_binaries:
    print("WARNING: no pinned crypto libraries found in", _env_lib)

binaries = _pinned_binaries + binaries

# ---------------------------------------------------------------------------
# Excluded: weight that is never imported
# ---------------------------------------------------------------------------
# Checked, not assumed: `grep -rn <name> app/ worker/` for each. The one
# mention of matplotlib in this tree is a comment in `render/colormap.py`
# saying the ramps are defined by hand *because* `render/` may not import a
# plotting library.
excludes = [
    "matplotlib", "plotly", "seaborn", "bokeh",
    # Never a dependency; pulled in transitively.
    "sklearn",
    "tkinter", "IPython", "jupyter", "notebook", "pytest", "PyInstaller",
    # P-07 and ADR-MSP-006: no web framework, no WebView. The basemap client is
    # the standard library, and there is nothing here for QtWebEngine to do.
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtTest",
    "PySide6.QtDesigner",
]

block_cipher = None

a = Analysis(
    # The launcher, not either package: the binary has to be able to be both.
    [str(SPEC_DIR / "frozen_entry.py")],
    pathex=[str(APP), str(WORKER)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "runtime_hook_geodata.py")],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="geopotential",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX corrupts Qt plugin loading often enough to avoid
    console=True,        # a GUI that fails silently cannot be diagnosed remotely
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# One directory, not one file. One-file unpacks the whole bundle to /tmp on
# every launch — slow, and it fails where /tmp is small or mounted noexec. It
# would also unpack it *twice* here, once per process.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="geopotential",
)
