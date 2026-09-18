#!/usr/bin/env python3
"""Export `schemas/project/v1/` and `schemas/operators/v1/` from the code.

Same principle as the IPC schemas: the code is the single source, the published
schema is derived, and a change that forgot to re-export is caught rather than
trusted.

    tools/export_project_schema.py           write the schemas
    tools/export_project_schema.py --check   fail if they are out of date
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_app.project.store import SCHEMA, SCHEMA_VERSION  # noqa: E402
from geopotential_worker.operators import registry  # noqa: E402

PROJECT_OUT = ROOT / "schemas" / "project" / "v1"
OPERATOR_OUT = ROOT / "schemas" / "operators" / "v1"

PROJECT_HEADER = f"""\
-- GeoPotential project store, schema version {SCHEMA_VERSION}
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
"""


def build() -> dict[Path, str]:
    """Render every exported file. Returns {absolute path: content}."""
    files: dict[Path, str] = {
        PROJECT_OUT / "project.sql": PROJECT_HEADER + SCHEMA,
        OPERATOR_OUT / "registered.json": json.dumps(
            registry.describe_all(), indent=2
        ) + "\n",
        OPERATOR_OUT / "planned.json": json.dumps(registry.PLANNED, indent=2) + "\n",
    }

    rows = "".join(
        f"| `{name}` | {milestone} |\n"
        for name, milestone in sorted(registry.PLANNED.items())
    )
    files[OPERATOR_OUT / "README.md"] = (
        "# Operator contracts, version 1\n"
        "\n"
        "Generated from `worker/geopotential_worker/operators/registry.py` by\n"
        "`tools/export_project_schema.py`. Do not hand-edit.\n"
        "\n"
        "`registered.json` is what the worker announces in `hello.capabilities`\n"
        "and is therefore what the application may offer. Each entry carries its\n"
        "parameters with type, unit, documented default and range, plus the\n"
        "literature reference. Section 16: no default is silent.\n"
        "\n"
        "`planned.json` is what the milestones will add. The interface shows\n"
        "these disabled and names the milestone, rather than offering an\n"
        "operation that fails after the click.\n"
        "\n"
        f"## Registered ({len(registry.capabilities())})\n"
        "\n"
        + "".join(f"- `{name}`\n" for name in registry.capabilities())
        + "\n"
        f"## Planned ({len(registry.PLANNED)})\n"
        "\n"
        "| Operator | Milestone |\n"
        "|---|---|\n"
        f"{rows}"
    )
    return files


def main() -> int:
    files = build()
    if "--check" in sys.argv:
        stale = [
            path.relative_to(ROOT)
            for path, content in files.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print(f"project/operator schemas: FAIL — out of date: "
                  f"{', '.join(str(p) for p in sorted(stale))}")
            print("run tools/export_project_schema.py")
            return 1
        print(f"project/operator schemas: PASS — {len(files)} files match the code")
        return 0

    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"wrote {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
