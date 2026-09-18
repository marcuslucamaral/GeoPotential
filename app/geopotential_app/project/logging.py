"""The four log channels, and the diagnostic the user can send to support.

Section 32 separates application, scientific, worker and crash logs, and asks
each record to carry timestamp, version, `job_id`, `run_id`, operator, stage,
error, duration and resources. They are separate files because they answer
different questions and are read by different people: the worker log is where a
`detail_ref` resolves, the scientific log is what a reviewer reads to see what
was computed, and the crash log is what survives when nothing else does.

Two rules that shape everything here:

  - **A raw stack trace never reaches the user by default.** It goes to a log
    line with a reference; the interface shows the safe message and the
    reference.
  - **The exportable diagnostic carries no scientific data.** Paths, versions,
    hashes, states, durations and errors — never pixel values. Someone sends
    this to support; it must not leak the survey.

No Qt. The store and its logs are exercised without an event loop.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPLICATION = "application"
SCIENTIFIC = "scientific"
WORKER = "worker"
CRASH = "crash"

CHANNELS = (APPLICATION, SCIENTIFIC, WORKER, CRASH)

# Rotate at 8 MiB. A log that grew without bound would be the reason a project
# directory became unmanageable, and truncating on open would throw away the
# record of the crash that is being investigated.
MAX_BYTES = 8 << 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def resource_snapshot() -> dict[str, Any]:
    """Peak RSS and CPU time for this process, when the platform offers them.

    Section 32 asks for resources on a record. `resource` is POSIX-only, and
    where it is absent the fields are simply missing rather than zero — a zero
    would read as a measurement.
    """
    try:
        import resource  # POSIX only

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "peak_rss_mb": round(usage.ru_maxrss / 1024, 1),
            "cpu_user_s": round(usage.ru_utime, 3),
            "cpu_system_s": round(usage.ru_stime, 3),
        }
    except (ImportError, OSError):
        return {}


@dataclass
class LogChannel:
    """One append-only JSON Lines file."""

    path: Path
    name: str
    version: str

    def write(self, level: str, message: str, **fields: Any) -> str:
        """Append one record and return its reference.

        level     'debug' | 'info' | 'warning' | 'error'
        message   one line, safe to show a user
        fields    job_id, run_id, operator, stage, duration_s, error, resources
        returns   a 12-character reference, which is what `detail_ref` carries
        """
        ref = uuid.uuid4().hex[:12]
        record = {
            "ts": _now(),
            "ref": ref,
            "level": level,
            "channel": self.name,
            "version": self.version,
            "msg": message,
            **{k: v for k, v in fields.items() if v is not None},
        }
        self._rotate_if_needed()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return ref

    def _rotate_if_needed(self) -> None:
        if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
            previous = self.path.with_suffix(self.path.suffix + ".1")
            previous.unlink(missing_ok=True)
            self.path.rename(previous)

    def tail(self, lines: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-lines:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"raw": line})
        return records

    def find(self, ref: str) -> dict[str, Any] | None:
        """Resolve a `detail_ref` to the record that carries the traceback."""
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("ref") == ref:
                return record
        return None


class ProjectLogs:
    """The four channels of one open project, plus the diagnostic export."""

    def __init__(self, root: Path, version: str) -> None:
        self.root = Path(root)
        self.dir = self.root / "logs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.version = version
        self._channels = {
            name: LogChannel(self.dir / f"{name}.jsonl", name, version)
            for name in CHANNELS
        }

    def __getitem__(self, channel: str) -> LogChannel:
        try:
            return self._channels[channel]
        except KeyError:
            raise KeyError(
                f"unknown log channel {channel!r}; the four are: "
                + ", ".join(CHANNELS)
            ) from None

    # ---- the channels ---------------------------------------------------

    def application(self, level: str, message: str, **fields: Any) -> str:
        """What the application did: opened, closed, started a worker, saved."""
        return self[APPLICATION].write(level, message, **fields)

    def scientific(self, message: str, **fields: Any) -> str:
        """What was computed: operator, parameters, grid, run, artefact, hash.

        This is the channel a reviewer reads. It records decisions, not
        progress: one record per run, not one per chunk.
        """
        return self[SCIENTIFIC].write("info", message, **fields)

    def worker(self, level: str, message: str, **fields: Any) -> str:
        """Verbatim from the worker's stderr, plus what the supervisor saw.

        This is where a `detail_ref` resolves, and where a traceback lives.
        """
        return self[WORKER].write(level, message, **fields)

    def crash(self, message: str, **fields: Any) -> str:
        """What survived. Written on an unexpected exit, before anything else."""
        return self[CRASH].write("error", message, resources=resource_snapshot(),
                                 **fields)

    def resolve(self, ref: str) -> dict[str, Any] | None:
        """Find a record by its reference, in whichever channel holds it."""
        for channel in self._channels.values():
            record = channel.find(ref)
            if record is not None:
                return record
        return None

    # ---- diagnostic export ----------------------------------------------

    def export_diagnostic(self, out: Path, store_summary: dict[str, Any]) -> Path:
        """Write a zip a user can send to support.

        out            destination .zip
        store_summary  catalogue counts and states from the Project Store
        returns        the path written

        **No scientific data goes in.** Paths, versions, hashes, states,
        durations and errors — never pixel values, never an artefact. A user
        sending this must not be sending their survey.
        """
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        environment = {
            "generated_at": _now(),
            "app_version": self.version,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": sys.executable,
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "resources": resource_snapshot(),
            "packages": _package_versions(),
            "project_root": str(self.root),
            "store": store_summary,
        }
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("environment.json", json.dumps(environment, indent=2,
                                                            default=str))
            for name, channel in self._channels.items():
                if channel.path.exists():
                    archive.write(channel.path, f"logs/{name}.jsonl")
            archive.writestr(
                "README.txt",
                "GeoPotential Professional — exported diagnostic\n"
                "\n"
                "Contents: the four log channels of one project, plus the\n"
                "environment that produced them.\n"
                "\n"
                "This archive deliberately contains NO scientific data. There\n"
                "are no rasters, no pixel values and no artefacts in it — only\n"
                "paths, versions, hashes, states, durations and error records.\n",
            )
        return out


def _package_versions() -> dict[str, str]:
    import importlib

    versions: dict[str, str] = {}
    for name in ("numpy", "rasterio", "geopandas", "pyproj", "shapely", "scipy",
                 "PySide6", "affine"):
        try:
            versions[name] = getattr(importlib.import_module(name), "__version__", "?")
        except ImportError:
            versions[name] = "absent"
    return versions
