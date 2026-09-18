-- GeoPotential project store, schema version 1.3.0
--
-- Generated from app/geopotential_app/project/store.py by
-- tools/export_project_schema.py. That module is the single source.
--
-- No scientific grid is ever a blob here: rasters live in artifacts/ and this
-- database holds the path and the hash.
--
-- The integrity rules of IMPLEMENTACAO_GEOPOTENTIAL_MSP.md section 14.4 are
-- constraints, not conventions: a committed run is immutable (triggers), an
-- output is never silently overwritten (artifact.path UNIQUE), and an artefact
-- cannot exist without a run (foreign key).

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
