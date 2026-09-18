"""AppController — the one object QML is handed.

It publishes state as `Property` with a `NOTIFY` signal, never as a `Slot` that
returns a value: a slot is read once and QML has no way to know the answer
changed.

It does not compute anything. It opens a project, starts the worker, submits
jobs through the JobController, and republishes what comes back. Every
scientific decision is in the worker; every persistence decision is in the
store.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .._version import VERSION
from ..commands import (
    CancelJobCommand,
    CommandError,
    CommandStack,
    DiscardOrphansCommand,
    ImportDatasetCommand,
    RelinkDatasetCommand,
    RunOperatorCommand,
)
from ..i18n import Translator
from ..models.job_model import JobListModel
from ..models.layer_model import DisplayLayer, LayerStackModel
from ..preferences import Preferences
from ..project import recents
from ..project.logging import ProjectLogs
from ..project.recovery import RecoveryReport, recover
from ..project.store import ProjectStore
from ..utils.fromqml import to_dict, to_list
from ..utils.qtcore import QObject, Property, Signal, Slot
from ..viewmodels.workflow_model import Facts, WorkflowModel
from .job_controller import JobController


def _canonical_crs(name: str | None) -> str:
    """A CRS written the one way every consumer downstream reads."""
    if not name:
        return ""
    from ..geo import coordinates

    try:
        return coordinates.canonical(str(name))
    except Exception:                                # noqa: BLE001
        return str(name)
from .worker_supervisor import WorkerSupervisor


class AppController(QObject):
    """The application's observable state."""

    projectChanged = Signal()
    workerStateChanged = Signal()
    statusChanged = Signal()
    capabilitiesChanged = Signal()
    commandsChanged = Signal()
    # path, and the operator that produced it. The operator is what says what
    # the raster *is*: `artifact_type` in the protocol is a file format
    # ("GeoTIFF") and carries no meaning about the values, so a view that
    # labelled every artefact the same way called a harmonized mGal raster a
    # membership in [0,1] — the one thing this project forbids conflating.
    artifactReady = Signal(str, str)
    runCommitted = Signal(str, str)
    errorRaised = Signal(str, str)  # safe message, detail reference
    recoveryReported = Signal(str, dict)  # summary, full report
    datasetDescribed = Signal(dict)       # what the wizard shows
    datasetValidated = Signal(dict)       # the QA/QC report plus the plan
    methodsCompared = Signal(dict)        # which interpolator fits, measured
    policiesCompared = Signal(dict)       # what each extent policy would yield
    scenarioMeasured = Signal(str, dict)  # operator, what it measured
    recentsChanged = Signal()
    aoisChanged = Signal()
    workflowChanged = Signal()
    pointsReady = Signal(str, "QVariant")   # layer id, the bounded preview
    geometryReady = Signal(str, "QVariant")  # layer id, the bounded outline
    # A layer's own statistics arrived. The Inspector used to read the *last
    # dataset described*, which is a different thing entirely: it showed a
    # CSV's range and valid fraction under the name of the raster that had
    # been interpolated from it.
    layerDescribed = Signal(str, "QVariant")   # layer id, its description

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store: ProjectStore | None = None
        self._logs: ProjectLogs | None = None
        self._session_id: str | None = None
        self._recovery: RecoveryReport | None = None
        self._commands: CommandStack | None = None
        self._jobs = JobListModel(self)
        self._workflow = WorkflowModel(self)
        self._layers = LayerStackModel(self)
        self._translator = Translator(self)
        self._preferences = Preferences(self)
        self._supervisor = WorkerSupervisor(self)
        self._job_controller: JobController | None = None
        self._status = "no project"
        self._layer_serial = 1
        # Preview points per display layer. Display cache, never a
        # source: every computation reads the file itself.
        self._layer_points: dict[str, list] = {}
        self._layer_parts: dict[str, list] = {}
        self._layer_preview: dict[str, dict] = {}
        self._layer_crs_unit: dict[str, str] = {}
        # One description per layer, so the Inspector reads the layer it is
        # naming. Keyed by layer id; the probe that fills it is read-only and
        # commits no run.
        self._layer_description: dict[str, dict] = {}
        self._describing: dict[str, str] = {}      # job id -> layer id
        self._log: list[str] = []

        self._supervisor.stateChanged.connect(self._on_worker_state)
        self._supervisor.helloReceived.connect(self._on_hello)
        self._supervisor.logLine.connect(self._on_log)
        self._supervisor.protocolMismatch.connect(self._on_mismatch)

    # ---- properties -----------------------------------------------------

    def _get_jobs(self) -> JobListModel:
        return self._jobs

    def _get_workflow(self) -> WorkflowModel:
        return self._workflow

    def _get_translator(self) -> Translator:
        return self._translator

    def _get_preferences(self) -> Preferences:
        return self._preferences

    def _get_layers(self) -> LayerStackModel:
        return self._layers

    def _get_current_step(self) -> str:
        return self._workflow.currentKey()

    def _get_worker_state(self) -> str:
        return self._supervisor.state

    def _get_status(self) -> str:
        return self._status

    def _get_project_name(self) -> str:
        return self._store.project_info().get("name", "") if self._store else ""

    def _get_project_path(self) -> str:
        return str(self._store.root) if self._store else ""

    def _get_capabilities(self) -> list:
        return self._supervisor.capabilities

    def _get_version(self) -> str:
        return VERSION

    def _get_worker_version(self) -> str:
        return self._supervisor.worker_version

    def _get_can_undo(self) -> bool:
        return bool(self._commands and self._commands.canUndo)

    def _get_can_redo(self) -> bool:
        return bool(self._commands and self._commands.canRedo)

    def _get_undo_text(self) -> str:
        return self._commands.undoText if self._commands else "Nothing to undo"

    def _get_redo_text(self) -> str:
        return self._commands.redoText if self._commands else "Nothing to redo"

    def _get_recovery_summary(self) -> str:
        return self._recovery.summary() if self._recovery else ""

    def _get_needs_attention(self) -> bool:
        """Whether the recovery pass found something a person should look at."""
        return bool(self._recovery and not self._recovery.clean)

    jobs = Property(QObject, _get_jobs, constant=True)
    workflow = Property(QObject, _get_workflow, constant=True)
    tr = Property(QObject, _get_translator, constant=True)
    preferences = Property(QObject, _get_preferences, constant=True)
    layers = Property(QObject, _get_layers, constant=True)
    currentStep = Property(str, _get_current_step, notify=workflowChanged)
    canUndo = Property(bool, _get_can_undo, notify=commandsChanged)
    canRedo = Property(bool, _get_can_redo, notify=commandsChanged)
    undoText = Property(str, _get_undo_text, notify=commandsChanged)
    redoText = Property(str, _get_redo_text, notify=commandsChanged)
    recoverySummary = Property(str, _get_recovery_summary, notify=projectChanged)
    needsAttention = Property(bool, _get_needs_attention, notify=projectChanged)
    workerState = Property(str, _get_worker_state, notify=workerStateChanged)
    status = Property(str, _get_status, notify=statusChanged)
    projectName = Property(str, _get_project_name, notify=projectChanged)
    projectPath = Property(str, _get_project_path, notify=projectChanged)
    capabilities = Property(list, _get_capabilities, notify=capabilitiesChanged)
    appVersion = Property(str, _get_version, constant=True)
    workerVersion = Property(str, _get_worker_version, notify=capabilitiesChanged)

    # ---- project --------------------------------------------------------

    def _get_basemap_sources(self) -> list:
        """The basemap sources on offer, with their licences. ADR-MSP-006.

        Open sources only, each carrying the attribution its licence obliges.
        """
        from ..basemap import names

        return names()

    basemapSources = Property(list, _get_basemap_sources, constant=True)

    #: The display stack's id for the basemap. One entry, always: choosing
    #: another source replaces it rather than stacking a second one.
    BASEMAP_LAYER = "basemap"

    @Slot(str, result=str)
    def setBasemap(self, key: str) -> str:  # noqa: N802
        """Choose a basemap, and keep the layer panel telling the truth.

        The basemap appears as a layer because that is where a person looks for
        what is drawn — and it is display only (ADR-MSP-006): no operator takes
        it, it enters no manifest as an input, and it has no value under the
        cursor. Choosing `''` turns it off and removes the row.
        """
        from ..basemap import get

        source = get(key)
        if source is None:
            self._layers.remove(self.BASEMAP_LAYER)
            return ""
        existing = self._layers.layer(self.BASEMAP_LAYER)
        if existing is not None:
            existing.name = source.name
            self._layers.setVisible(self.BASEMAP_LAYER, True)
        else:
            self._layers.add(
                DisplayLayer(layer_id=self.BASEMAP_LAYER, name=source.name,
                             role="basemap", kind="basemap"),
                make_active=False,
            )
            # Under everything: a basemap is the ground the data sits on. It
            # was appended on top, so it moves down by exactly its own index —
            # `move` refuses a delta that would land outside the stack.
            self._layers.move(self.BASEMAP_LAYER, -(len(self._layers.layers) - 1))
        return source.key

    @Slot(result=str)
    def basemapCacheDir(self) -> str:  # noqa: N802
        """Where fetched tiles go: inside the project, or nowhere."""
        if self._store is None:
            return ""
        return str(self._store.root / "cache" / "basemap")

    @Slot(result=str)
    def defaultProjectFolder(self) -> str:  # noqa: N802
        """Where a project goes when nobody says otherwise.

        Creating a project must not depend on a system folder chooser: on this
        machine that dialog opens behind the modal that asked for it, so the
        button appeared to do nothing. The folder is shown, editable, and used
        as it is — never a hidden default.
        """
        return str(Path.home() / "GeoPotential")

    @Slot(str, str, result=bool)
    def createProject(self, path: str, name: str) -> bool:  # noqa: N802
        """Create a project at `path`. The parent folders are made if needed."""
        target = Path(path).expanduser()
        if target.suffix != ".gpot":
            target = target.with_name(target.name + ".gpot")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._store = ProjectStore.create(target, name)
        except FileExistsError:
            self._fail(f"{target} already holds a project. Open it, or choose "
                       f"another name.")
            return False
        except OSError as exc:
            self._fail(f"Could not create the project at {target}: {exc}")
            return False
        self._after_open()
        return True

    @Slot(str, result=bool)
    def openProject(self, path: str) -> bool:  # noqa: N802
        """Open a project by path. A typed or pasted path works as well as a
        picked one, and the refusal says which path failed."""
        target = Path(path.strip()).expanduser()
        try:
            self._store = ProjectStore.open(target)
        except (FileNotFoundError, ValueError) as exc:
            self._fail(f"Could not open {target}: {exc}")
            return False
        self._after_open()
        return True

    def _after_open(self) -> None:
        """Open the session, recover, then wire the controllers.

        The order matters. Recovery runs **before** the interface can submit
        anything, so a job cannot be launched into a project whose previous
        session left work in an unknown state.
        """
        assert self._store is not None
        self._logs = ProjectLogs(self._store.root, VERSION)
        self._session_id = self._store.open_session(VERSION)
        self._store.record_build(VERSION, None, None, self._package_versions())
        self._logs.application(
            "info", f"project opened: {self._store.root.name}",
            session=self._session_id, project=str(self._store.root),
        )

        self._recovery = recover(self._store)
        if not self._recovery.clean:
            self._logs.application(
                "warning", self._recovery.summary(), **self._recovery.as_dict()
            )
        self.recoveryReported.emit(self._recovery.summary(), self._recovery.as_dict())

        self._job_controller = JobController(
            self._supervisor, self._store, self._jobs, self._logs, self
        )
        self._job_controller.artifactReady.connect(
            lambda job_id, path: self.artifactReady.emit(
                path, str(self._jobs.detail(job_id).get("operator", "")))
        )
        self._job_controller.runCommitted.connect(self.runCommitted.emit)
        self._job_controller.jobFinished.connect(self._on_job_finished)
        self._job_controller.probeCompleted.connect(self._on_probe)

        self._restore_layers()

        self._commands = CommandStack(self._store, self._logs, self)
        self._commands.commandFailed.connect(lambda m: self._fail(m))
        self._commands.changed.connect(self.commandsChanged.emit)

        recents.remember(self._store.root, self._store.project_info().get("name", ""))
        self.recentsChanged.emit()

        self._set_status(
            self._recovery.summary() if not self._recovery.clean
            else f"project {self._store.root.name} open"
        )
        self.projectChanged.emit()
        self.commandsChanged.emit()
        self._refresh_workflow()

    @staticmethod
    def _package_versions() -> dict[str, str]:
        """Package versions recorded with every project. Section 18/22."""
        import importlib

        versions: dict[str, str] = {}
        for name in ("numpy", "rasterio", "geopandas", "pyproj", "shapely", "scipy",
                     "PySide6"):
            try:
                versions[name] = getattr(importlib.import_module(name), "__version__", "?")
            except ImportError:
                versions[name] = "absent"
        return versions

    def _get_recents(self) -> list:
        return recents.load()

    recentProjects = Property(list, _get_recents, notify=recentsChanged)

    @Slot(str, result=bool)
    def duplicateProject(self, destination: str) -> bool:  # noqa: N802
        """Copy the open project — catalogue, artefacts and lineage — elsewhere.

        The copy is a *new* project: it keeps every run and artefact, and it
        gets its own sessions from the moment it is opened. Cache is left
        behind, because cache is recreatable and copying gigabytes of it would
        make duplication feel broken.
        """
        import shutil

        if self._store is None:
            self._fail("Open a project before duplicating it.")
            return False
        target = Path(destination)
        if target.exists():
            self._fail(f"{target.name} already exists. Choose another name.")
            return False
        try:
            # WAL: commit and close so the copy is a consistent database rather
            # than one whose latest writes are still in a sidecar file.
            self._store.connect().commit()
            shutil.copytree(
                self._store.root, target,
                ignore=shutil.ignore_patterns("cache", "*.sqlite-wal",
                                              "*.sqlite-shm"),
            )
            (target / "cache").mkdir(exist_ok=True)
        except OSError as exc:
            self._fail(f"Could not duplicate the project: {exc}")
            return False
        self._store.record_event("project.duplicated", str(target), {})
        self._set_status(f"duplicated to {target.name}")
        return True

    # ---- areas of interest ----------------------------------------------

    @Slot(str, "QVariant", str, result="QVariant")
    def saveAoi(self, name: str, points: list, crs: str) -> dict:  # noqa: N802
        """Save an AOI as a new version, preserving the previous one (MSP-09)."""
        if self._store is None:
            self._fail("Open a project before saving an area of interest.")
            return {}
        try:
            saved = self._store.save_aoi(name, to_list(points), crs)
        except (ValueError, KeyError) as exc:
            self._fail(str(exc))
            return {}
        if self._logs is not None:
            self._logs.application(
                "info", f"AOI {name!r} saved as version {saved['version']}",
                aoi=name, version=saved["version"], crs=crs,
                vertices=len(saved["geometry"]),
            )
        self._set_status(
            f"AOI {name!r} saved as version {saved['version']} "
            f"({saved['area']:,.0f} {self._crs_area_unit(crs)})"
        )
        self.aoisChanged.emit()
        return saved

    @Slot(str, result="QVariant")
    def loadAoi(self, name: str) -> dict:  # noqa: N802
        if self._store is None:
            return {}
        return self._store.latest_aoi(name) or {}

    @Slot(result="QVariant")
    def listAois(self) -> list:  # noqa: N802
        return self._store.aois() if self._store else []

    @staticmethod
    def _crs_area_unit(crs: str) -> str:
        return "m²" if "26912" in crs or "31982" in crs or "5186" in crs else "units²"

    # ---- worker ---------------------------------------------------------

    @Slot()
    def startWorker(self) -> None:  # noqa: N802
        """Ensure a worker is running. Idempotent.

        QML asks on `Component.onCompleted` and a headless driver asks again;
        both are legitimate, and neither should get an exception for asking
        twice. Only the supervisor's own `start` refuses a double spawn, which
        is where refusing belongs.
        """
        if self._supervisor.state in (WorkerSupervisor.READY, WorkerSupervisor.STARTING):
            return
        self._supervisor.start()

    @Slot()
    def restartWorker(self) -> None:  # noqa: N802
        """Replace a crashed or wedged worker. The project survives (gate M2)."""
        self._supervisor.restart()

    @Slot()
    def shutdown(self) -> None:
        """Close the session cleanly. Idempotent — Qt calls it more than once.

        Gate M2, "fechar a janela encerra os filhos": the supervisor's `stop`
        enforces a deadline and kills, so a wedged worker cannot outlive the
        window. Only after the child is gone is the session marked clean, which
        is what tells the next open that nothing was interrupted.
        """
        if self._store is None:
            self._supervisor.stop()
            return
        if self._session_id is None:
            return  # already shut down

        self._supervisor.stop()
        if self._logs is not None:
            self._logs.application(
                "info", "project closed", session=self._session_id,
                store=self._store.summary(),
            )
        self._store.close_session(self._session_id)
        self._session_id = None
        self._store.close()

    @Slot(str, result=bool)
    def exportDiagnostic(self, path: str) -> bool:  # noqa: N802
        """Write the support archive. No scientific data goes into it."""
        if self._logs is None or self._store is None:
            self._fail("Open a project before exporting a diagnostic.")
            return False
        try:
            written = self._logs.export_diagnostic(Path(path), self._store.summary())
        except OSError as exc:
            self._fail(f"Could not write the diagnostic: {exc}")
            return False
        self._set_status(f"diagnostic written to {written.name}")
        return True

    @Slot(str, result="QVariant")
    def resolveDetail(self, ref: str) -> dict:  # noqa: N802
        """Turn a `detail_ref` shown in the interface into its log record."""
        if self._logs is None or not ref:
            return {}
        return self._logs.resolve(ref) or {}

    # ---- jobs -----------------------------------------------------------

    @Slot(str, "QVariant", "QVariant", result=str)
    @Slot(str, "QVariant", "QVariant", str, result=str)
    def submit(self, operator: str, params: dict, inputs: list,
               parent_run_id: str = "") -> str:
        """Submit a job through the command stack. Empty string on refusal.

        `parent_run_id` names the run this one derives from, when there is
        one. QML calls the three-argument form for anything that starts
        something new; `retry` calls the four-argument one.

        Everything that changes the domain goes through a Command, so the
        command log is the audit trail and nothing bypasses it (section 7.4).
        """
        if self._job_controller is None or self._commands is None:
            self._fail("Open a project before running anything.")
            return ""
        try:
            return self._commands.run(
                RunOperatorCommand(
                    self._job_controller, operator, to_dict(params),
                    to_list(inputs), parent_run_id or None,
                )
            ) or ""
        except (CommandError, RuntimeError, ValueError) as exc:
            self._fail(str(exc))
            return ""

    @Slot(str, result=str)
    def retry(self, job_id: str) -> str:
        """Run a job again with the same operator, inputs and parameters.

        It is a **new** job and, if it commits, a **child** run: the previous
        run is immutable and is preserved, and the new one records it as its
        parent (P-116). Repeating is submitting, not rewinding — and a child
        that did not record its parent is an orphan, which is what this used
        to produce while its own comment claimed lineage.
        """
        if self._store is None:
            self._fail("Open a project before repeating a job.")
            return ""
        row = next((job for job in self._store.jobs() if job["id"] == job_id), None)
        if row is None:
            self._fail(f"job {job_id} is not in this project")
            return ""
        parent = next(
            (run.id for run in self._store.runs() if run.job_id == job_id), "")
        return self.submit(
            row["operator"],
            json.loads(row["params_json"] or "{}"),
            json.loads(row["inputs_json"] or "[]"),
            parent,
        )

    @Slot(str)
    def cancel(self, job_id: str) -> None:
        if self._job_controller is None or self._commands is None:
            return
        try:
            self._commands.run(CancelJobCommand(self._job_controller, job_id))
        except (CommandError, RuntimeError) as exc:
            self._fail(str(exc))
            return
        self._set_status("cancel requested")

    # ---- the Import Wizard's two probes ---------------------------------

    @Slot(str, "QVariant", result=str)
    def describeDataset(self, path: str, declared: dict | None = None) -> str:  # noqa: N802
        """Read a dataset's metadata without importing it (section 9.2).

        `declared` carries what the operator stated in the wizard — a CRS for a
        file that has none, a unit, which columns are coordinates. Those are
        assertions by the operator, and they are recorded as such.
        """
        return self._probe("io.describe_dataset", path, to_dict(declared))

    @Slot(str, "QVariant", result=str)
    def validateDataset(self, path: str, declared: dict | None = None) -> str:  # noqa: N802
        """Run the MSP-04 checks. The wizard consults the verdict before import."""
        params = to_dict(declared)
        params.setdefault("context", self._layer_context())
        return self._probe("qc.validate_dataset", path, params)

    @Slot(str, "QVariant", result=str)
    def measureScenario(self, operator: str, params: dict | None = None) -> str:  # noqa: N802
        """Ask the worker what would change if a choice had been different.

        M6, MSP-11. Goes through `_probe`, not through the command stack: a
        scenario changes no domain state, so there is nothing to undo, and
        pushing it would bury the real commands under a pile of questions.

        `scenarios.leave_one_out` with `write_rasters` false, `explain` and
        `rank_targets` write nothing at all. The screen uses those.
        """
        if not str(operator).startswith("scenarios."):
            self._fail(f"{operator} is not a scenario operator")
            return ""
        if self._job_controller is None:
            self._fail("Open a project before measuring a scenario.")
            return ""
        try:
            job_id = self._job_controller.submit(operator, to_dict(params), [])
        except (RuntimeError, ValueError) as exc:
            self._fail(str(exc))
            return ""
        self._refresh_workflow()
        return job_id

    @Slot(str, "QVariant", result=str)
    def compareInterpolationMethods(self, path: str, params: dict | None = None) -> str:  # noqa: N802
        """Measure which interpolator fits these samples, before running one.

        Read-only (P-53): it holds samples out and scores each method, and it
        commits no run and registers no artefact. The gridding screen calls it
        so the choice between IDW and the two triangulated methods is made
        from this survey's own error, not from a default in the code —
        `ADR-MSP-007`.
        """
        return self._probe("grid.cross_validate", path, to_dict(params))

    def _probe(self, operator: str, path: str, params: dict) -> str:
        if self._job_controller is None:
            self._fail("Open a project before inspecting a dataset.")
            return ""
        try:
            # A probe does not go through the command stack: it changes no
            # domain state, so there is nothing to undo, and pushing it would
            # bury the real commands under a pile of inspections.
            job_id = self._job_controller.submit(operator, params, [str(path)])
        except (RuntimeError, ValueError) as exc:
            self._fail(str(exc))
            return ""
        self._refresh_workflow()
        return job_id

    def _layer_context(self) -> list:
        """The layers already in the project, for the overlap and resolution
        checks. Those two questions are only answerable across layers."""
        if self._store is None:
            return []
        context = []
        for row in self._store.datasets():
            try:
                metadata = json.loads(row.get("metadata") or "{}")
            except (TypeError, ValueError):
                metadata = {}
            if metadata.get("extent"):
                context.append({
                    "name": row["name"],
                    "extent": metadata["extent"],
                    "pixel_size": metadata.get("pixel_size"),
                    # ADR-MSP-005: without it, two extents from different CRSs
                    # get compared as if they were in the same one.
                    "crs": row.get("crs") or metadata.get("crs"),
                })
        return context

    def _on_probe(self, job_id: str, manifest: dict) -> None:
        operator = manifest.get("operator") or ""
        if operator.startswith("scenarios."):
            # M6. A scenario measures how far the answer would move; it never
            # moves it. What comes back is a table, and the screen shows it.
            payload = (manifest.get("leave_one_out")
                       or manifest.get("sensitivity")
                       or manifest.get("explanation")
                       or manifest.get("targets") or {})
            self.scenarioMeasured.emit(operator, payload)
            self._refresh_workflow()
            return
        if manifest.get("operator") == "grid.compare_policies":
            # The harmonize screen asks this before the person chooses, so the
            # choice stops being made blind. Read-only: nothing is registered.
            self.policiesCompared.emit(manifest)
            self._refresh_workflow()
            return
        if manifest.get("operator") == "grid.cross_validate":
            # Dispatched by name and before the fall-through: every probe that
            # was not a description used to be read as a QA/QC verdict, so a
            # third probe would have arrived at the wizard as an empty report.
            self.methodsCompared.emit(manifest.get("cross_validation") or {})
            self._refresh_workflow()
            return
        if manifest.get("operator") == "io.describe_dataset":
            description = manifest.get("description") or {}
            layer_id = self._describing.pop(job_id, "")
            if layer_id:
                # A description asked for on a layer's behalf answers that
                # layer, and does not touch the wizard's own last-described.
                self._layer_description[layer_id] = description
                self.layerDescribed.emit(layer_id, description)
                self._refresh_workflow()
                return
            self.datasetDescribed.emit(description)
        else:
            self.datasetValidated.emit({
                "report": manifest.get("report") or {},
                "plan": manifest.get("plan"),
                "declared": manifest.get("declared") or {},
            })
        self._refresh_workflow()

    @Slot(str, "QVariant", result=bool)
    def isDatasetUsable(self, path: str, _unused=None) -> bool:  # noqa: N802
        """Whether the last recorded verdict allows this dataset to be used.

        Gate M3 G4 goes through here, and so does the wizard. One function
        answering both means the import path and the job path cannot disagree
        about what a BLOCKER means.
        """
        if self._store is None:
            return False
        latest = self._store.latest_validation(str(Path(path).resolve()))
        if latest is None:
            latest = self._store.latest_validation(str(path))
        return bool(latest and latest["usable"])

    @Slot(str, str, result=str)
    def importDataset(self, path: str, kind: str) -> str:  # noqa: N802
        """Register an external input, with its size, timestamp and hash."""
        if self._store is None or self._commands is None:
            self._fail("Open a project before importing anything.")
            return ""
        resolved = str(Path(path).resolve())
        latest = self._store.latest_validation(resolved) or \
            self._store.latest_validation(str(path))
        if latest is not None and not latest["usable"]:
            # Section 9.2: no invalid data enters the project without its
            # diagnosis. The refusal quotes the verdict rather than restating
            # it, so the message the user sees here is the one QA/QC produced.
            self._fail(latest["summary"])
            return ""
        if latest is None:
            self._fail(
                f"{Path(path).name} has not been validated. Run the checks "
                f"before importing it."
            )
            return ""
        described = json.loads(latest["metadata_json"] or "{}")
        metadata = dict(json.loads(latest["declared_json"] or "{}"))
        metadata.setdefault("crs", described.get("crs"))
        metadata.setdefault("unit", described.get("unit"))
        metadata.setdefault("nodata", described.get("nodata"))
        metadata["extent"] = described.get("extent")
        # What the file's columns are, and which of them the reader took for
        # coordinates and for the measurement. Carried so that gridding a
        # table later does not have to describe the file a second time — and
        # `setdefault` because a column the operator *declared* in the wizard
        # is their statement and outranks the reader's guess.
        metadata["fields"] = described.get("fields")
        metadata["median_spacing"] = described.get("median_spacing")
        for role in ("x_field", "y_field", "value_field"):
            if described.get(role):
                metadata.setdefault(role, described[role])
        metadata["pixel_size"] = (
            [described.get("pixel_size_x"), described.get("pixel_size_y")]
            if described.get("pixel_size_x") is not None else None
        )
        metadata["validation_id"] = latest["id"]
        try:
            dataset_id = self._commands.run(
                ImportDatasetCommand(self._store, Path(path), kind, **metadata)
            ) or ""
        except (CommandError, OSError) as exc:
            self._fail(str(exc))
            return ""
        self._refresh_workflow()
        # A dataset that entered the project becomes a way of looking at it.
        # Display only: the stack derives from the registry, one way.
        if dataset_id:
            unit = str(metadata.get("unit") or "")
            preview = described.get("preview") or {}
            crs = str(described.get("crs") or metadata.get("crs") or "")
            crs_unit = str(described.get("crs_unit") or "")
            if preview.get("kind") == "points" and preview.get("points"):
                self.addPointLayer(str(path), Path(path).stem, unit, preview,
                                   crs, crs_unit)
            elif preview.get("kind") == "geometry" and preview.get("parts"):
                # A vector becomes visible. Until E4 it went to `addLayer`,
                # which opens files with rasterio: the layer appeared in the
                # panel and the canvas stayed empty, which is the gap M4 named
                # and carried forward.
                self.addGeometryLayer(str(path), Path(path).stem, preview,
                                      crs, crs_unit)
            else:
                self.addLayer(str(path), Path(path).stem, "original", unit)
        return dataset_id

    @Slot(str, str, result="QVariant")
    def relinkDataset(self, dataset_id: str, new_path: str) -> dict:  # noqa: N802
        """Point a registered input at a file that moved.

        The returned `hash_matches` is reported, not enforced: a file that moved
        *and* changed is a deliberate act or an accident, and only the operator
        knows which.
        """
        if self._store is None or self._commands is None:
            self._fail("Open a project before relinking anything.")
            return {}
        command = RelinkDatasetCommand(self._store, dataset_id, Path(new_path))
        try:
            result = self._commands.run(command)
        except (CommandError, KeyError, OSError) as exc:
            self._fail(str(exc))
            return {}
        if not result.get("hash_matches"):
            self._set_status(
                "relinked, but the file's contents differ from what was recorded"
            )
        return result

    @Slot("QVariant", result=int)
    def discardOrphans(self, paths: list) -> int:  # noqa: N802
        """Delete files the recovery pass found that belong to no run."""
        if self._store is None or self._commands is None:
            return 0
        try:
            removed = self._commands.run(
                DiscardOrphansCommand(self._store, [str(p) for p in to_list(paths)])
            )
        except (CommandError, OSError) as exc:
            self._fail(str(exc))
            return 0
        self._set_status(f"discarded {len(removed)} orphan file(s)")
        return len(removed)

    @Slot()
    def undo(self) -> None:
        if self._commands is not None:
            self._commands.undo()
            self._refresh_workflow()

    @Slot()
    def redo(self) -> None:
        if self._commands is not None:
            self._commands.redo()
            self._refresh_workflow()

    # ---- reactions ------------------------------------------------------

    def _on_worker_state(self, state: str) -> None:
        self.workerStateChanged.emit()
        self._set_status(f"worker {state}")
        if self._logs is None:
            return
        if state == WorkerSupervisor.CRASHED:
            self._logs.crash("worker crashed", worker_state=state)
        else:
            self._logs.application("info", f"worker {state}")

    def _on_hello(self, msg: dict[str, Any]) -> None:
        self.capabilitiesChanged.emit()
        if self._store is not None:
            self._store.record_build(
                VERSION, msg.get("worker"), msg.get("protocol"), self._package_versions()
            )
            self._store.record_event("worker.hello", str(msg.get("worker")), msg)

    def _on_mismatch(self, ours: str, theirs: str) -> None:
        self._fail(
            f"The scientific worker speaks protocol {theirs} and this build "
            f"speaks {ours}. The run was not started; reinstall so both halves "
            f"come from one build."
        )

    def _on_job_finished(self, job_id: str, state: str) -> None:
        """A job ended. Its outcome belongs to **that job**, not to a banner.

        `status` used to be written here with `job failed`, and it stayed on
        screen beside whatever job happened to be selected — including one that
        had succeeded. The outcome now lives on the job's own row, which the
        panel reads; `status` says what the *project* is doing and nothing else.
        """
        row = self._jobs.row(job_id)
        if state != "Succeeded" and row is not None:
            self.errorRaised.emit(row.message, row.detail_ref)
        self._refresh_workflow()

    def _on_log(self, line: str) -> None:
        self._log.append(line)

    # ---- the display stack ------------------------------------------------

    @Slot(str, str, str, "QVariant", str, str, result=str)
    def addPointLayer(self, path: str, name: str, unit: str,  # noqa: N802
                      preview, crs: str = "", crs_unit: str = "") -> str:  # noqa: ANN001
        """Put a table into the view, as the points the worker previewed.

        The stack carries no coordinates (ADR-MSP-002): the layer is registered
        here, and the points are handed to the canvas through `pointsReady`.
        The preview is bounded and declared, and it is display only — every
        computation reads the file.
        """
        target = Path(path)
        layer_id = f"L{self._layer_serial}"
        self._layer_serial += 1
        block = to_dict(preview) if isinstance(preview, dict) else {}
        points = to_list(block.get("points") if block else preview)
        self._layer_points[layer_id] = points
        # The rows behind the layer, for the attribute table. Bounded and
        # declared by ADR-MSP-004, and shown, never computed with.
        self._layer_preview[layer_id] = block
        self._layers.add(DisplayLayer(
            layer_id=layer_id,
            name=name or target.stem,
            path=str(target),
            role="original",
            kind="points",
            unit=unit,
            crs=crs,
        ))
        # The CRS's own unit travels with the layer: without it the scale bar
        # reads "10000 units" beside a UTM map that is in metres.
        self._layer_crs_unit[layer_id] = crs_unit
        self.pointsReady.emit(layer_id, points)
        return layer_id

    @Slot(str, str, "QVariant", str, str, result=str)
    def addGeometryLayer(self, path: str, name: str,  # noqa: N802
                         preview, crs: str = "", crs_unit: str = "") -> str:  # noqa: ANN001
        """Put a vector into the view, as the silhouette the worker previewed.

        The same shape as `addPointLayer`, and for the same reason: the display
        stack carries no coordinates (ADR-MSP-002), so the parts travel to the
        canvas on their own signal while the stack carries only the entry.

        A silhouette carries no values, so the layer has no unit. Giving it one
        would put a measurement beside a drawing that has none.
        """
        target = Path(path)
        layer_id = f"L{self._layer_serial}"
        self._layer_serial += 1
        block = to_dict(preview) if isinstance(preview, dict) else {}
        parts = to_list(block.get("parts") if block else preview)
        self._layer_parts[layer_id] = parts
        # The attribute rows behind it, for the attribute table — bounded and
        # declared by ADR-MSP-004, shown and never computed with.
        self._layer_preview[layer_id] = block
        self._layers.add(DisplayLayer(
            layer_id=layer_id,
            name=name or target.stem,
            path=str(target),
            role="original",
            kind="vector",
            unit="",
            crs=crs,
        ))
        self._layer_crs_unit[layer_id] = crs_unit
        self.geometryReady.emit(layer_id, parts)
        return layer_id

    @Slot(str, result="QVariant")
    def layerPoints(self, layer_id: str) -> list:  # noqa: N802
        """The preview points a table layer draws. Display only."""
        return self._layer_points.get(layer_id, [])

    #: What an operator's output *is*, for the restored stack. The same
    #: mapping the shell applies when an artefact arrives live — kept here so
    #: reopening a project shows the roles the session that made them showed.
    _ROLE_OF = {
        "decision.membership": ("membership", "membership [0-1]"),
        "decision.aggregate": ("result", "membership [0-1]"),
        "grid.harmonize": ("harmonized", ""),
    }

    def _restore_layers(self) -> None:
        """Put the project's data back on screen when it is opened.

        The `.gpot` stored everything all along — datasets, runs, artefacts,
        manifests — and opening it rebuilt none of it: the canvas came up empty
        and the work looked lost. It was not lost; it was simply never put
        back.

        Read in two passes so the stack comes up in the order a person built
        it: the imported data first, then what was computed from it.

        A file that has since been moved or deleted is skipped rather than
        added as a broken row: the registry still knows about it, and the
        recovery pass is what reports it.
        """
        assert self._store is not None
        for row in self._store.datasets():
            path = row.get("path") or ""
            if path and Path(path).exists():
                self.addLayer(path, row.get("name") or "", "original",
                              row.get("unit") or "")

        for run in self._store.runs():
            manifest = run.manifest or {}
            operator = str(manifest.get("operator", ""))
            role, unit = self._ROLE_OF.get(operator, ("result", ""))
            for artifact in self._store.artifacts(run.id):
                path = artifact.get("path") or ""
                if path and Path(path).exists():
                    self.addLayer(path, "", role, unit)

    @Slot(result="QVariant")
    def membershipCandidates(self) -> list:  # noqa: N802
        """The layers on the display stack a membership can be applied to.

        Read from the stack and not from the catalogue, because what the
        Membership Editor offers has to be what the person can see: a layer
        they removed from the view is not a layer they are about to shape.

        A basemap is excluded — it is display only and carries no value under
        the cursor (`ADR-MSP-006`) — and so is a result, because normalizing a
        suitability map would be a membership of a membership.
        """
        offered = []
        for row in self._layers.snapshot():
            if row.get("kind") == "basemap" or row.get("role") in (
                    "basemap", "result", "membership"):
                continue
            if not row.get("path"):
                continue
            offered.append({
                "layerId": row["layerId"],
                "name": row.get("name") or Path(row["path"]).stem,
                "path": row["path"],
                "role": row.get("role", ""),
            })
        return offered

    @Slot(result="QVariant")
    def harmonizableDatasets(self) -> list:  # noqa: N802
        """The registered rasters the analysis grid can be built from.

        Each entry carries what `grid.harmonize` needs to name a layer — path,
        name, unit — plus the CRS and pixel size the dialog offers as a
        starting point. They are **offered**, never applied: there is no
        default CRS (ADR-004), so the target grid is chosen and recorded.

        Vectors and tables are excluded: harmonization resamples a raster, and
        rasterizing a vector criterion is `grid.rasterize`, which M5 did not
        deliver.
        """
        if self._store is None:
            return []
        offered = []
        for row in self._store.datasets():
            if row["kind"] != "raster":
                # Harmonization reprojects and resamples a raster. Sparse data
                # reaches a grid another way — `grid.idw` for samples,
                # `grid.euclidean_distance` or `grid.rasterize` for features —
                # and `griddableDatasets` is what offers it.
                continue
            metadata = json.loads(row["metadata"] or "{}")
            pixel = metadata.get("pixel_size") or [None, None]
            offered.append({
                "id": row["id"],
                "name": row["name"],
                "path": row["path"],
                "unit": row["unit"] or "",
                "crs": row["crs"] or "",
                # Two numbers, never averaged: an anisotropic pixel is legal.
                "pixelX": pixel[0],
                "pixelY": pixel[1],
                "missing": not Path(row["path"]).exists(),
                "origin": "imported",
            })

        # And the rasters this project produced. A gridded survey is a raster
        # like any other, and leaving it out would mean a CSV could be turned
        # into a grid and then have nowhere to go.
        for row in self._store.all_artifacts():
            path = Path(row["path"])
            if path.suffix.lower() not in (".tif", ".tiff"):
                continue
            offered.append({
                "id": row["id"],
                "name": path.stem,
                "path": str(path),
                "unit": "",
                "crs": "",
                "pixelX": None,
                "pixelY": None,
                "missing": not path.exists(),
                "origin": "computed",
            })
        return offered

    @Slot(result="QVariant")
    def griddableDatasets(self) -> list:  # noqa: N802
        """The sparse datasets that can be turned into a raster criterion.

        A table of samples and a vector of features do not reach an analysis
        grid the way a raster does: one is interpolated (`grid.idw`), the
        others are measured or transferred (`grid.euclidean_distance`,
        `grid.rasterize`). Which methods apply depends on what the file is, so
        the answer carries them rather than leaving the screen to guess.
        """
        if self._store is None:
            return []
        offered = []
        for row in self._store.datasets():
            if row["kind"] == "raster":
                continue
            metadata = json.loads(row["metadata"] or "{}")
            if row["kind"] == "table":
                # A table is coordinates and a measurement. Interpolating it
                # is the only way to get a continuous field out of it; the
                # distance to the samples is a different, legitimate question.
                #
                # Three interpolators, which are the three QGIS offers, and
                # they are not interchangeable: IDW is a weighted mean and
                # flattens a gradient, the triangulated pair follow it. Which
                # one fits is measured by `grid.cross_validate`, because on
                # `vp_500_m.csv` IDW's held-out error is 1.9x Clough-
                # Tocher's, and on `density_modified_500m.csv` — also a
                # regular lattice — IDW is the one that wins.
                methods = ["grid.idw", "grid.tin_linear", "grid.tin_cubic",
                           "grid.euclidean_distance"]
            else:
                methods = ["grid.rasterize", "grid.euclidean_distance"]
            offered.append({
                "id": row["id"],
                "name": row["name"],
                "path": row["path"],
                "kind": row["kind"],
                # Normalised: `26912` is a CRS to pyproj and not to rasterio,
                # and a screen that offers one form while the panel shows the
                # other reads as two different CRSs.
                "crs": _canonical_crs(row["crs"]),
                "unit": row["unit"] or "",
                "fields": metadata.get("fields") or [],
                "xField": metadata.get("x_field") or "",
                "yField": metadata.get("y_field") or "",
                "valueField": metadata.get("value_field") or "",
                "extent": metadata.get("extent"),
                # The survey's own spacing, so the screen can propose a search
                # radius instead of leaving the person to guess one.
                "spacing": metadata.get("median_spacing"),
                "methods": methods,
                "missing": not Path(row["path"]).exists(),
            })
        return offered

    @Slot(str, result="QVariant")
    def layerDescription(self, layer_id: str) -> dict:  # noqa: N802
        """What the worker read about this layer's file. Empty until it has.

        The Inspector binds to this and not to the last dataset the wizard
        described: the two are different files whenever anything has been
        computed, and the panel names one while showing the other's numbers.
        """
        return self._layer_description.get(layer_id, {})

    @Slot(str, result=bool)
    def describeLayer(self, layer_id: str) -> bool:  # noqa: N802
        """Ask the worker for this layer's own statistics, once.

        Read-only: `io.describe_dataset` commits no run and registers no
        artefact (P-53), so this can follow the active layer around without
        putting an inspection into the project's lineage.
        """
        if layer_id in self._layer_description:
            return True
        # Já pedido e ainda sem resposta. `_layer_description` só é preenchido
        # **quando a resposta chega**, então dois pedidos feitos antes dela —
        # o painel seguindo a camada ativa, e a tela de pertinência abrindo —
        # submetiam dois jobs para o mesmo arquivo. Era isso que aparecia como
        # "described dem.tif" duas vezes na lista de jobs.
        if layer_id in self._describing.values():
            return True
        layer = self._layers.layer(layer_id)
        if layer is None or not layer.path or not Path(layer.path).exists():
            return False
        # Quietly, when the worker is not up yet. This follows the active
        # layer around, so it fires while a project is still opening — and a
        # panel detail that raised a modal error dialog because the worker had
        # not finished starting would interrupt the person over nothing. The
        # next time the layer becomes active, it asks again.
        if self._supervisor.state != WorkerSupervisor.READY:
            return False
        declared: dict[str, Any] = {}
        if layer.crs:
            declared["crs"] = layer.crs
        if layer.unit:
            declared["unit"] = layer.unit
        job_id = self._probe("io.describe_dataset", layer.path, declared)
        if job_id:
            self._describing[job_id] = layer_id
        return bool(job_id)

    @Slot(str, result="QVariant")
    def layerParts(self, layer_id: str) -> list:  # noqa: N802
        """The preview outline a vector layer draws. Display only."""
        return self._layer_parts.get(layer_id, [])

    @Slot(str, result=str)
    def layerCrsUnit(self, layer_id: str) -> str:  # noqa: N802
        """The linear unit of a layer's CRS, as the scale bar must label it."""
        return self._layer_crs_unit.get(layer_id, "")

    @Slot(str, result="QVariant")
    def layerPreview(self, layer_id: str) -> dict:  # noqa: N802
        """The rows and counts behind a layer, for the attribute table."""
        return self._layer_preview.get(layer_id, {})

    @Slot(str, str, str, str, result=str)
    def addLayer(self, path: str, name: str = "", role: str = "original",  # noqa: N802
                 unit: str = "") -> str:
        """Put something already registered into the view.

        The display stack derives from the registry one way (ADR-MSP-002): this
        adds a way of *looking* at a dataset or an artefact, and adds nothing to
        the project. Nothing here writes to the store.
        """
        target = Path(path)
        layer_id = f"L{self._layer_serial}"
        self._layer_serial += 1
        self._layers.add(DisplayLayer(
            layer_id=layer_id,
            name=name or target.stem,
            path=str(target),
            role=role if role in ("original", "harmonized", "membership",
                                  "result", "aoi") else "original",
            unit=unit,
        ))
        return layer_id

    def _get_layer_serial(self) -> int:
        return self._layer_serial

    # ---- the workflow ----------------------------------------------------

    # States a job is still in. Anything else is terminal, and a terminal job
    # is a fact about the past, not about what is running now.
    _IN_FLIGHT = ("Queued", "Validating", "Running", "Committing")

    def _facts(self) -> Facts:
        """The workflow's inputs, read from the store every time.

        Nothing is cached: the store is the one authoritative state, and a
        remembered copy is the second one. `committed_operators` comes from
        runs — a job that ran and did not commit produced nothing.
        """
        in_flight = tuple(
            row.operator for row in self._jobs.rows if row.state in self._IN_FLIGHT
        )
        failed = tuple(
            row.operator for row in self._jobs.rows
            if row.state in ("Failed", "Interrupted")
        )
        if self._store is None:
            return Facts(running_operators=in_flight, failed_operators=failed)

        operator_of = {job["id"]: job["operator"] for job in self._store.jobs()}
        committed = tuple({
            operator_of.get(run.job_id, "") for run in self._store.runs()
        } - {""})

        latest: dict[str, dict[str, Any]] = {}
        for record in self._store.validations():          # newest first
            latest.setdefault(record["dataset_path"], record)
        verdicts = tuple(
            {
                "dataset_path": record["dataset_path"],
                "usable": bool(record["usable"]),
                "warnings": record["severity"] in ("WARNING", "BLOCKER"),
            }
            for record in latest.values()
        )

        return Facts(
            project_open=True,
            datasets=tuple(self._store.datasets()),
            verdicts=verdicts,
            committed_operators=committed,
            running_operators=in_flight,
            failed_operators=failed,
        )

    def _refresh_workflow(self) -> None:
        self._workflow.update(self._facts())
        self.workflowChanged.emit()

    # ---- helpers --------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit()

    def _fail(self, message: str, detail_ref: str = "") -> None:
        """A failure with no job to belong to: opening a project, submitting.

        A failure that *does* belong to a job is recorded on the job's row and
        never here — see `_on_job_finished`.
        """
        self._set_status(message)
        self.errorRaised.emit(message, detail_ref)

    @property
    def store(self) -> ProjectStore | None:
        return self._store

    @property
    def logs(self) -> ProjectLogs | None:
        return self._logs

    @property
    def commands(self) -> CommandStack | None:
        return self._commands

    @property
    def recovery(self) -> RecoveryReport | None:
        return self._recovery

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def supervisor(self) -> WorkerSupervisor:
        return self._supervisor

    @property
    def job_model(self) -> JobListModel:
        return self._jobs

    @property
    def worker_log(self) -> list[str]:
        return list(self._log)
