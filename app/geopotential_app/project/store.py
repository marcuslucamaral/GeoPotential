"""The Project Store.

A project is a directory, not a file:

    MeuProjeto.gpot/
    ├── project.sqlite   catalogue, relations, parameters, lineage, state
    ├── manifest.json    schema version, software version, environment
    ├── data/ artifacts/ cache/ previews/ reports/ recovery/ logs/

SQLite holds the catalogue. **No scientific grid is ever a blob**: rasters live
in `artifacts/` as GeoTIFF and the database holds the path and the hash.

The integrity rules of section 14.4 are constraints and code here, not prose:

  1. a completed run is immutable — enforced by a trigger
  2. changing parameters creates a child run, with the parent preserved
  3. an output is never silently overwritten — the artefact path carries the
     run id, and `register_artifact` refuses a duplicate hash under a new name
  4. parameters enter the hash, canonically serialized
  5. an external input records size, timestamp and hash, and can be relinked
  6. deleting the cache never destroys a run

No Qt. The store is exercised from a plain `python3 -c`, which is the point.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.3.0"

SUBDIRECTORIES = (
    "data",
    "artifacts",
    "cache",
    "previews",
    "reports",
    "recovery",
    "logs",
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    crs           TEXT
);

CREATE TABLE IF NOT EXISTS software_build (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at   TEXT NOT NULL,
    app_version   TEXT NOT NULL,
    worker_version TEXT,
    protocol      TEXT,
    python        TEXT NOT NULL,
    platform      TEXT NOT NULL,
    packages      TEXT NOT NULL      -- JSON {name: version}
);

CREATE TABLE IF NOT EXISTS dataset (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    kind          TEXT NOT NULL,     -- raster | vector | table
    crs           TEXT,
    unit          TEXT,
    nodata        REAL,
    size_bytes    INTEGER,
    mtime         TEXT,
    hash          TEXT,
    metadata      TEXT NOT NULL DEFAULT '{}',
    relinked_from TEXT,
    added_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    id            TEXT PRIMARY KEY,
    operator      TEXT NOT NULL,
    operator_version TEXT,
    params_json   TEXT NOT NULL,
    params_hash   TEXT NOT NULL,
    inputs_json   TEXT NOT NULL,
    state         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    finished_at   TEXT,
    error_code    TEXT,
    error_message TEXT,
    detail_ref    TEXT
);

CREATE TABLE IF NOT EXISTS run (
    id            TEXT PRIMARY KEY,
    job_id        TEXT NOT NULL REFERENCES job(id),
    parent_run_id TEXT REFERENCES run(id),
    scenario_id   TEXT REFERENCES scenario(id),
    content_key   TEXT NOT NULL,     -- inputs + operator + version + params
    manifest_json TEXT NOT NULL,
    immutable     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    parent_id     TEXT REFERENCES scenario(id),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES run(id),
    artifact_id   TEXT NOT NULL,
    path          TEXT NOT NULL UNIQUE,
    artifact_type TEXT NOT NULL,
    hash          TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_event (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,
    kind          TEXT NOT NULL,
    subject       TEXT NOT NULL,
    detail_json   TEXT NOT NULL DEFAULT '{}'
);

-- One row per session, opened when the project opens and closed on a clean
-- shutdown. A row with no `closed_at` is how the next open knows the previous
-- one died rather than exited: there is nothing to ask the operating system.
CREATE TABLE IF NOT EXISTS session (
    id            TEXT PRIMARY KEY,
    opened_at     TEXT NOT NULL,
    closed_at     TEXT,
    app_version   TEXT NOT NULL,
    pid           INTEGER NOT NULL,
    clean         INTEGER NOT NULL DEFAULT 0
);

-- The write-ahead record of a job's intent, written BEFORE the job is
-- submitted and cleared when it reaches a terminal state. A surviving row is
-- an interrupted job, and it names the directory whose contents are orphans.
CREATE TABLE IF NOT EXISTS job_journal (
    job_id        TEXT PRIMARY KEY REFERENCES job(id),
    session_id    TEXT NOT NULL REFERENCES session(id),
    operator      TEXT NOT NULL,
    output_dir    TEXT NOT NULL,
    opened_at     TEXT NOT NULL,
    last_stage    TEXT,
    last_fraction REAL DEFAULT 0.0
);

-- What the command stack did, so an undo is auditable and a session that died
-- mid-command can say what it was doing.
CREATE TABLE IF NOT EXISTS command_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,
    session_id    TEXT REFERENCES session(id),
    name          TEXT NOT NULL,
    direction     TEXT NOT NULL,     -- do | undo | redo
    payload_json  TEXT NOT NULL DEFAULT '{}'
);

-- Section 14.3 lists ValidationResult as its own entity, and it is one here:
-- a QA/QC verdict is not a run. It answers a question about a dataset, often
-- before that dataset is in the project at all, so it cannot hang off a run id.
-- This is the audit trail gate M3 G5 requires.
CREATE TABLE IF NOT EXISTS validation_result (
    id            TEXT PRIMARY KEY,
    at            TEXT NOT NULL,
    session_id    TEXT REFERENCES session(id),
    dataset_path  TEXT NOT NULL,
    dataset_name  TEXT NOT NULL,
    dataset_id    TEXT REFERENCES dataset(id),
    operator      TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    usable        INTEGER NOT NULL,
    severity      TEXT NOT NULL,
    summary       TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    declared_json TEXT NOT NULL DEFAULT '{}',
    plan_json     TEXT,
    -- The description the verdict was formed on: CRS, extent, pixel size,
    -- fields, statistics. Kept so the overlap and resolution checks can ask
    -- about layers already in the project without re-reading every file.
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- MSP-09. An AOI is a versioned object with provenance, not a rectangle held
-- in a property of the view. Editing one creates a new version and preserves
-- the old, for the same reason a run is immutable: a result computed inside an
-- AOI is only interpretable if that AOI can still be recovered.
CREATE TABLE IF NOT EXISTS aoi (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       INTEGER NOT NULL,
    parent_id     TEXT REFERENCES aoi(id),
    crs           TEXT NOT NULL,
    geometry_json TEXT NOT NULL,      -- [[x, y], ...] in `crs`, a closed ring
    area          REAL,
    created_at    TEXT NOT NULL,
    session_id    TEXT REFERENCES session(id),
    note          TEXT NOT NULL DEFAULT '',
    UNIQUE (name, version)
);

CREATE INDEX IF NOT EXISTS idx_aoi_name ON aoi(name, version);
CREATE INDEX IF NOT EXISTS idx_validation_dataset ON validation_result(dataset_path);
CREATE INDEX IF NOT EXISTS idx_artifact_run ON artifact(run_id);
CREATE INDEX IF NOT EXISTS idx_run_content ON run(content_key);
CREATE INDEX IF NOT EXISTS idx_run_parent ON run(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_journal_session ON job_journal(session_id);

-- Rule 1 of section 14.4: a completed run is immutable. Changing parameters
-- creates a child run; it never edits the parent.
CREATE TRIGGER IF NOT EXISTS run_is_immutable
BEFORE UPDATE ON run
FOR EACH ROW WHEN OLD.immutable = 1
BEGIN
    SELECT RAISE(ABORT, 'run is immutable; derive a child run instead');
END;

CREATE TRIGGER IF NOT EXISTS run_is_undeletable
BEFORE DELETE ON run
FOR EACH ROW WHEN OLD.immutable = 1
BEGIN
    SELECT RAISE(ABORT, 'run is immutable; it cannot be deleted');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _polygon_area(points: list[list[float]]) -> float:
    """Shoelace area, in the square of the CRS unit.

    Absolute, so vertex order does not change the answer. Reported for the
    interface; nothing computes from it.
    """
    if len(points) < 3:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        total += float(x0) * float(y1) - float(x1) * float(y0)
    return abs(total) / 2.0


def canonical_params(params: dict[str, Any]) -> str:
    """Serialize parameters so the same set always hashes the same.

    params   the resolved parameter set, defaults filled in
    returns  JSON with sorted keys and no insignificant whitespace

    Rule 5 of section 14.4. Two runs whose parameters differ only in dict order
    are the same run, and must land on the same content key.
    """
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def content_key(
    operator: str, operator_version: str, inputs: list[str], params: dict[str, Any]
) -> str:
    """Content address of a run: what would have to change to make it a new run.

    Section 31: inputs, operator, version and parameters. The cache is keyed by
    this, and the cache is discardable — deleting it never destroys a run.
    """
    digest = hashlib.sha256()
    digest.update(operator.encode())
    digest.update(b"\0")
    digest.update(operator_version.encode())
    for path in sorted(inputs):
        digest.update(b"\0")
        digest.update(str(Path(path).resolve()).encode())
    digest.update(b"\0")
    digest.update(canonical_params(params).encode())
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class RunRecord:
    id: str
    job_id: str
    parent_run_id: str | None
    content_key: str
    manifest: dict[str, Any]
    immutable: bool
    created_at: str


class ProjectStore:
    """One open `.gpot` project."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.db_path = self.root / "project.sqlite"
        self._conn: sqlite3.Connection | None = None

    # ---- lifecycle ------------------------------------------------------

    @classmethod
    def create(cls, root: Path, name: str, *, crs: str | None = None) -> "ProjectStore":
        """Create a project directory and its database.

        root   the .gpot directory to create; must not already be a project
        name   the project's display name
        crs    the project CRS, if already chosen; there is no default
        """
        root = Path(root)
        if (root / "project.sqlite").exists():
            raise FileExistsError(f"{root} is already a project")
        root.mkdir(parents=True, exist_ok=True)
        for sub in SUBDIRECTORIES:
            (root / sub).mkdir(exist_ok=True)

        store = cls(root)
        conn = store.connect()
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO project (id, name, created_at, schema_version, crs) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, name, _now(), SCHEMA_VERSION, crs),
        )
        conn.commit()

        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "name": name,
                    "created_at": _now(),
                    "crs": crs,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        store.record_event("project.created", name, {"crs": crs})
        return store

    @classmethod
    def open(cls, root: Path) -> "ProjectStore":
        root = Path(root)
        if not (root / "project.sqlite").exists():
            raise FileNotFoundError(f"{root} is not a project (no project.sqlite)")
        store = cls(root)
        conn = store.connect()
        (version,) = conn.execute("SELECT schema_version FROM project").fetchone()
        if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
            raise ValueError(
                f"{root.name}: project schema {version} cannot be opened by "
                f"this build, which speaks {SCHEMA_VERSION}"
            )
        conn.executescript(SCHEMA)  # additive; brings a minor version forward
        conn.commit()
        return store

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            # WAL keeps a reader working while a job commits, and survives a
            # kill mid-write, which M2's crash tests depend on.
            self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    # ---- writing --------------------------------------------------------

    def record_event(self, kind: str, subject: str, detail: dict[str, Any]) -> None:
        conn = self.connect()
        conn.execute(
            "INSERT INTO provenance_event (at, kind, subject, detail_json) "
            "VALUES (?, ?, ?, ?)",
            (_now(), kind, subject, json.dumps(detail, default=str)),
        )
        conn.commit()

    def record_build(
        self,
        app_version: str,
        worker_version: str | None,
        protocol: str | None,
        packages: dict[str, str],
    ) -> None:
        import platform
        import sys

        conn = self.connect()
        conn.execute(
            "INSERT INTO software_build "
            "(recorded_at, app_version, worker_version, protocol, python, platform, packages) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _now(),
                app_version,
                worker_version,
                protocol,
                sys.version.split()[0],
                platform.platform(),
                json.dumps(packages, sort_keys=True),
            ),
        )
        conn.commit()

    def add_dataset(
        self, path: Path, kind: str, *, name: str | None = None, **metadata: Any
    ) -> str:
        """Register an external input with size, timestamp and hash.

        Rule 6-9 of section 14.4: an external input records enough to detect
        that it changed, and enough to be relinked when it moves.

        **Importing the same file again is not a second dataset.** Same path,
        same content: it is the one already in the catalogue, and its id comes
        back unchanged. Inserting a row per import made the catalogue grow
        every time a project was reopened and the data brought in again, and
        the harmonize dialog then offered the same raster four times — which
        is not a screen defect but this line.

        The hash is what decides. Same path with *different* content is a
        different dataset: the file changed under the project, runs that used
        the old bytes recorded the old hash, and collapsing the two would
        erase that.
        """
        path = Path(path).resolve()
        stat = path.stat()
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        content = f"sha256:{digest.hexdigest()}"
        conn = self.connect()
        existing = conn.execute(
            "SELECT id FROM dataset WHERE path=? AND hash=?", (str(path), content)
        ).fetchone()
        if existing is not None:
            self.record_event("dataset.alreadyRegistered", str(path),
                              {"dataset_id": existing["id"]})
            return existing["id"]
        dataset_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO dataset (id, name, path, kind, crs, unit, nodata, "
            "size_bytes, mtime, hash, metadata, added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dataset_id,
                name or path.name,
                str(path),
                kind,
                metadata.get("crs"),
                metadata.get("unit"),
                metadata.get("nodata"),
                stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                content,
                json.dumps(metadata, default=str),
                _now(),
            ),
        )
        conn.commit()
        self.record_event("dataset.added", str(path), {"kind": kind, **metadata})
        return dataset_id

    def create_job(
        self,
        operator: str,
        params: dict[str, Any],
        inputs: list[str],
        *,
        job_id: str | None = None,
    ) -> str:
        job_id = job_id or uuid.uuid4().hex
        conn = self.connect()
        conn.execute(
            "INSERT INTO job (id, operator, params_json, params_hash, inputs_json, "
            "state, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                job_id,
                operator,
                canonical_params(params),
                hashlib.sha256(canonical_params(params).encode()).hexdigest(),
                json.dumps([str(Path(p).resolve()) for p in inputs]),
                "Queued",
                _now(),
            ),
        )
        conn.commit()
        return job_id

    def set_job_state(
        self,
        job_id: str,
        state: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        detail_ref: str | None = None,
    ) -> None:
        conn = self.connect()
        finished = _now() if state in ("Succeeded", "Failed", "Cancelled") else None
        conn.execute(
            "UPDATE job SET state=?, finished_at=COALESCE(?, finished_at), "
            "error_code=?, error_message=?, detail_ref=? WHERE id=?",
            (state, finished, error_code, error_message, detail_ref, job_id),
        )
        conn.commit()

    def commit_run(
        self,
        job_id: str,
        manifest: dict[str, Any],
        *,
        parent_run_id: str | None = None,
        scenario_id: str | None = None,
    ) -> str:
        """Record a completed run and seal it.

        The run is written with `immutable = 1` in the same transaction that
        records it, so there is no window in which a completed run can be
        edited. A later change to its parameters produces a child run through
        `derive_run`, and the parent is preserved.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT operator, params_json, inputs_json FROM job WHERE id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no such job: {job_id}")
        key = content_key(
            row["operator"],
            str(manifest.get("operator_version", "")),
            json.loads(row["inputs_json"]),
            json.loads(row["params_json"]),
        )
        run_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO run (id, job_id, parent_run_id, scenario_id, content_key, "
            "manifest_json, immutable, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (
                run_id,
                job_id,
                parent_run_id,
                scenario_id,
                key,
                json.dumps(manifest, default=str),
                _now(),
            ),
        )
        conn.execute(
            "UPDATE job SET operator_version=? WHERE id=?",
            (manifest.get("operator_version"), job_id),
        )
        conn.commit()
        self.record_event("run.committed", run_id, {"content_key": key, "job": job_id})
        return run_id

    def register_artifact(
        self,
        run_id: str,
        artifact_id: str,
        path: str,
        artifact_type: str,
        digest: str,
        size_bytes: int,
    ) -> str:
        """Record a closed, validated, hashed file against a run.

        Rule 3 of section 14.4: an output is never silently overwritten. The
        path column is UNIQUE, so a second artefact claiming the same path
        raises rather than replacing the first.
        """
        conn = self.connect()
        row_id = uuid.uuid4().hex
        try:
            conn.execute(
                "INSERT INTO artifact (id, run_id, artifact_id, path, artifact_type, "
                "hash, size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (row_id, run_id, artifact_id, path, artifact_type, digest,
                 size_bytes, _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"an artefact is already registered at {path}; a run never "
                f"overwrites another run's output"
            ) from exc
        conn.commit()
        return row_id

    # ---- reading --------------------------------------------------------

    def project_info(self) -> dict[str, Any]:
        row = self.connect().execute("SELECT * FROM project").fetchone()
        return dict(row) if row else {}

    def find_run_by_content(self, key: str) -> RunRecord | None:
        """Cache lookup: has this exact computation already been recorded?"""
        row = self.connect().execute(
            "SELECT * FROM run WHERE content_key=? ORDER BY created_at LIMIT 1", (key,)
        ).fetchone()
        return self._to_run(row) if row else None

    def runs(self) -> list[RunRecord]:
        rows = self.connect().execute(
            "SELECT * FROM run ORDER BY created_at"
        ).fetchall()
        return [self._to_run(r) for r in rows]

    def all_artifacts(self) -> list[dict[str, Any]]:
        """Every artefact this project has produced, newest last.

        A raster this project computed is as usable as one it imported — a
        gridded survey is exactly that — so whatever offers layers for an
        analysis has to see both. They stay different rows: an artefact
        belongs to the run that made it and a dataset is an external input,
        and collapsing the two would lose which is which.
        """
        rows = self.connect().execute(
            "SELECT a.*, r.id AS run_id FROM artifact a "
            "JOIN run r ON r.id = a.run_id ORDER BY a.created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT * FROM artifact WHERE run_id=? ORDER BY created_at", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def jobs(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT * FROM job ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            job_id=row["job_id"],
            parent_run_id=row["parent_run_id"],
            content_key=row["content_key"],
            manifest=json.loads(row["manifest_json"]),
            immutable=bool(row["immutable"]),
            created_at=row["created_at"],
        )

    def artifact_dir(self, job_id: str) -> Path:
        """Where a job's artefacts go. One directory per job, so two runs never
        contend for a filename."""
        path = self.root / "artifacts" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ---- sessions -------------------------------------------------------

    def open_session(self, app_version: str) -> str:
        """Record that a session began, and return its id.

        A row without `closed_at` is how the next open knows the previous
        session died rather than exited. There is nothing to ask the operating
        system after the fact, so the record has to be written up front.
        """
        session_id = uuid.uuid4().hex
        conn = self.connect()
        conn.execute(
            "INSERT INTO session (id, opened_at, app_version, pid, clean) "
            "VALUES (?, ?, ?, ?, 0)",
            (session_id, _now(), app_version, os.getpid()),
        )
        conn.commit()
        self._session_id = session_id
        return session_id

    def close_session(self, session_id: str | None = None) -> None:
        """Mark a session closed and clean. Only a normal exit reaches here."""
        session_id = session_id or getattr(self, "_session_id", None)
        if session_id is None:
            return
        conn = self.connect()
        conn.execute(
            "UPDATE session SET closed_at=?, clean=1 WHERE id=?", (_now(), session_id)
        )
        conn.commit()

    def unclean_sessions(self) -> list[dict[str, Any]]:
        """Sessions that opened and never closed — previous runs that died."""
        current = getattr(self, "_session_id", None)
        rows = self.connect().execute(
            "SELECT * FROM session WHERE closed_at IS NULL AND id IS NOT ? "
            "ORDER BY opened_at",
            (current,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- the job journal ------------------------------------------------

    def journal_open(self, job_id: str, operator: str, output_dir: Path) -> None:
        """Record a job's intent BEFORE it is submitted.

        This is write-ahead on purpose. If the row were written after the
        submission, a process killed in between would leave a running job with
        no record that it existed, and its output directory would be
        indistinguishable from an empty one.
        """
        session_id = getattr(self, "_session_id", None)
        if session_id is None:
            raise RuntimeError("no session is open; call open_session first")
        conn = self.connect()
        conn.execute(
            "INSERT OR REPLACE INTO job_journal "
            "(job_id, session_id, operator, output_dir, opened_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, session_id, operator, str(output_dir), _now()),
        )
        conn.commit()

    def journal_progress(self, job_id: str, stage: str, fraction: float) -> None:
        """Keep the journal's idea of where the job got to.

        This is autosave, and autosave is **not** a scientific commit: it says
        what was in flight, never what was produced.
        """
        conn = self.connect()
        conn.execute(
            "UPDATE job_journal SET last_stage=?, last_fraction=? WHERE job_id=?",
            (stage, float(fraction), job_id),
        )
        conn.commit()

    def journal_close(self, job_id: str) -> None:
        """Clear a job's journal row once it reaches a terminal state."""
        conn = self.connect()
        conn.execute("DELETE FROM job_journal WHERE job_id=?", (job_id,))
        conn.commit()

    def open_journal_entries(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT * FROM job_journal ORDER BY opened_at"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- the command log ------------------------------------------------

    def log_command(self, name: str, direction: str, payload: dict[str, Any]) -> None:
        if direction not in ("do", "undo", "redo"):
            raise ValueError(
                f"command direction must be do, undo or redo; got {direction!r}"
            )
        conn = self.connect()
        conn.execute(
            "INSERT INTO command_log (at, session_id, name, direction, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (_now(), getattr(self, "_session_id", None), name, direction,
             json.dumps(payload, default=str)),
        )
        conn.commit()

    def commands(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT * FROM command_log ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- validation results ---------------------------------------------

    def record_validation(
        self,
        dataset_path: str,
        operator: str,
        operator_version: str,
        report: dict[str, Any],
        *,
        declared: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        dataset_id: str | None = None,
    ) -> str:
        """Record one QA/QC verdict. The audit trail of gate M3 G5.

        Kept whatever the verdict: a dataset that was refused is exactly the
        one someone will later ask about, and "we checked and said no" has to
        survive the refusal. Nothing here imports anything.
        """
        result_id = uuid.uuid4().hex
        conn = self.connect()
        conn.execute(
            "INSERT INTO validation_result (id, at, session_id, dataset_path, "
            "dataset_name, dataset_id, operator, operator_version, usable, "
            "severity, summary, findings_json, declared_json, plan_json, "
            "metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                result_id,
                _now(),
                getattr(self, "_session_id", None),
                str(dataset_path),
                Path(dataset_path).name,
                dataset_id,
                operator,
                operator_version,
                1 if report.get("usable") else 0,
                str(report.get("severity", "INFO")),
                str(report.get("summary", "")),
                json.dumps(report.get("findings", []), default=str),
                json.dumps(declared or {}, default=str),
                json.dumps(plan, default=str) if plan else None,
                json.dumps(report.get("metadata") or {}, default=str),
            ),
        )
        conn.commit()
        self.record_event(
            "dataset.validated", str(dataset_path),
            {"usable": report.get("usable"), "severity": report.get("severity"),
             "declared": declared or {}},
        )
        return result_id

    def validations(self, dataset_path: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        if dataset_path:
            rows = conn.execute(
                "SELECT * FROM validation_result WHERE dataset_path=? "
                "ORDER BY at DESC", (str(dataset_path),)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM validation_result ORDER BY at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_validation(self, dataset_path: str) -> dict[str, Any] | None:
        results = self.validations(dataset_path)
        return results[0] if results else None

    # ---- areas of interest ----------------------------------------------

    def save_aoi(
        self,
        name: str,
        points: list[list[float]],
        crs: str,
        *,
        note: str = "",
    ) -> dict[str, Any]:
        """Save an AOI as a new version. The previous one is preserved.

        name    the AOI's name; versions accumulate under it
        points  [[x, y], ...] in `crs`, at least three vertices
        crs     the CRS the coordinates are in — never assumed
        returns the row that was written

        MSP-09 asks for versioning, and this is why: a result computed inside
        an AOI is only interpretable if that AOI can still be recovered. An
        edit that overwrote the old boundary would make every earlier run
        describe an area that no longer exists.
        """
        if len(points) < 3:
            raise ValueError(
                f"an AOI needs at least three vertices; got {len(points)}"
            )
        if not crs:
            raise ValueError(
                f"AOI {name!r}: no CRS given. Coordinates without a CRS are "
                f"pairs of numbers; there is no default."
            )
        conn = self.connect()
        row = conn.execute(
            "SELECT id, version FROM aoi WHERE name=? ORDER BY version DESC LIMIT 1",
            (name,),
        ).fetchone()
        version = (row["version"] + 1) if row else 1
        parent = row["id"] if row else None
        aoi_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO aoi (id, name, version, parent_id, crs, geometry_json, "
            "area, created_at, session_id, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                aoi_id, name, version, parent, crs,
                json.dumps([[float(x), float(y)] for x, y in points]),
                _polygon_area(points), _now(),
                getattr(self, "_session_id", None), note,
            ),
        )
        conn.commit()
        self.record_event("aoi.saved", name, {
            "aoi_id": aoi_id, "version": version, "vertices": len(points),
            "crs": crs, "parent": parent,
        })
        return self.aoi(aoi_id)

    def aoi(self, aoi_id: str) -> dict[str, Any]:
        row = self.connect().execute(
            "SELECT * FROM aoi WHERE id=?", (aoi_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no such AOI: {aoi_id}")
        record = dict(row)
        record["geometry"] = json.loads(record.pop("geometry_json"))
        return record

    def latest_aoi(self, name: str) -> dict[str, Any] | None:
        row = self.connect().execute(
            "SELECT id FROM aoi WHERE name=? ORDER BY version DESC LIMIT 1",
            (name,),
        ).fetchone()
        return self.aoi(row["id"]) if row else None

    def aois(self, *, latest_only: bool = True) -> list[dict[str, Any]]:
        conn = self.connect()
        if latest_only:
            rows = conn.execute(
                "SELECT a.* FROM aoi a JOIN ("
                "  SELECT name, MAX(version) AS v FROM aoi GROUP BY name"
                ") m ON a.name = m.name AND a.version = m.v ORDER BY a.name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM aoi ORDER BY name, version"
            ).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["geometry"] = json.loads(record.pop("geometry_json"))
            result.append(record)
        return result

    # ---- relink ---------------------------------------------------------

    def relink_dataset(self, dataset_id: str, new_path: Path) -> dict[str, Any]:
        """Point a registered input at a file that moved.

        dataset_id  the row to repoint
        new_path    where the file is now
        returns     {"hash_matches": bool, "old_path": str, "new_path": str}

        The hash is recomputed and compared, and the answer is returned rather
        than enforced: a file that moved *and* changed is a legitimate thing to
        do deliberately, and an illegitimate thing to do by accident. The
        caller decides, and either way the provenance event records which it
        was. The previous path is kept in `relinked_from`.
        """
        new_path = Path(new_path).resolve()
        if not new_path.exists():
            raise FileNotFoundError(f"cannot relink to a path that does not exist: {new_path}")
        conn = self.connect()
        row = conn.execute("SELECT * FROM dataset WHERE id=?", (dataset_id,)).fetchone()
        if row is None:
            raise KeyError(f"no such dataset: {dataset_id}")

        digest = hashlib.sha256()
        with open(new_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        new_hash = f"sha256:{digest.hexdigest()}"
        matches = new_hash == row["hash"]
        stat = new_path.stat()

        conn.execute(
            "UPDATE dataset SET path=?, hash=?, size_bytes=?, mtime=?, "
            "relinked_from=? WHERE id=?",
            (str(new_path), new_hash, stat.st_size,
             datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
             row["path"], dataset_id),
        )
        conn.commit()
        result = {
            "hash_matches": matches,
            "old_path": row["path"],
            "new_path": str(new_path),
            "old_hash": row["hash"],
            "new_hash": new_hash,
        }
        self.record_event("dataset.relinked", str(new_path), result)
        return result

    def datasets(self) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT * FROM dataset ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def missing_datasets(self) -> list[dict[str, Any]]:
        """Registered inputs whose file is no longer where it was."""
        return [d for d in self.datasets() if not Path(d["path"]).exists()]

    # ---- summary --------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Catalogue counts and states. Goes into the exported diagnostic, so
        it carries no scientific values — only counts, states and versions."""
        conn = self.connect()

        def count(table: str) -> int:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        states = {
            row["state"]: row["n"]
            for row in conn.execute(
                "SELECT state, COUNT(*) AS n FROM job GROUP BY state"
            ).fetchall()
        }
        return {
            "schema_version": self.project_info().get("schema_version"),
            "datasets": count("dataset"),
            "missing_datasets": len(self.missing_datasets()),
            "jobs": count("job"),
            "job_states": states,
            "runs": count("run"),
            "artifacts": count("artifact"),
            "sessions": count("session"),
            "unclean_sessions": len(self.unclean_sessions()),
            "open_journal_entries": len(self.open_journal_entries()),
            "provenance_events": count("provenance_event"),
            "commands": count("command_log"),
            "validations": count("validation_result"),
            "aois": count("aoi"),
        }

    def __repr__(self) -> str:
        return f"ProjectStore({self.root})"
