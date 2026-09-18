"""The list of projects this machine has opened.

Section 9.1 asks the Project Hub to list recents. That list is **not** project
state — it belongs to the person at the keyboard, not to any one project — so
it lives beside the application's own settings rather than inside a `.gpot`.

A project that has been moved or deleted stays in the list and is marked as
gone. Silently dropping it would hide the one fact the user needs: that the
path they remember no longer holds a project.

No Qt, so it can be exercised without an event loop.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_RECENTS = 12


def settings_dir() -> Path:
    """Where per-user application state goes.

    XDG on Linux, with the environment variable honoured so a test — or a
    sandboxed run — can point it somewhere harmless. No user path is baked
    into source.
    """
    base = os.environ.get("XDG_STATE_HOME") or os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "geopotential"


def recents_file() -> Path:
    return settings_dir() / "recent_projects.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> list[dict[str, Any]]:
    """The recents, most recent first, each marked with whether it still exists."""
    path = recents_file()
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt recents file is a nuisance, never a failure: the list is a
        # convenience and losing it costs nothing but a re-open.
        return []
    if not isinstance(entries, list):
        return []
    return [
        {
            "path": str(entry.get("path", "")),
            "name": str(entry.get("name", "")),
            "opened_at": str(entry.get("opened_at", "")),
            "exists": (Path(entry.get("path", "")) / "project.sqlite").exists(),
        }
        for entry in entries
        if entry.get("path")
    ]


def remember(root: Path, name: str) -> list[dict[str, Any]]:
    """Move a project to the top of the list and write it back."""
    root = Path(root).resolve()
    entries = [e for e in load() if Path(e["path"]) != root]
    entries.insert(0, {
        "path": str(root),
        "name": name,
        "opened_at": _now(),
        "exists": True,
    })
    entries = entries[:MAX_RECENTS]
    _write(entries)
    return entries


def forget(root: Path) -> list[dict[str, Any]]:
    entries = [e for e in load() if Path(e["path"]) != Path(root).resolve()]
    _write(entries)
    return entries


def _write(entries: list[dict[str, Any]]) -> None:
    path = recents_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic, like every other write in this project: a half-written recents
    # file would be read back as no recents at all.
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            [{k: v for k, v in e.items() if k != "exists"} for e in entries],
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)
