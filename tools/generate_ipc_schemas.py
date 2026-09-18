#!/usr/bin/env python3
"""Generate `schemas/ipc/v1/` from the protocol module.

Hand-written schemas drift from the code they describe, and a schema that
disagrees with the wire is worse than none. `protocol.REQUIRED` is the single
source; these files are derived from it, so step 1 of section 29 — "alterar
schema" — is a one-line change in one place.

    tools/generate_ipc_schemas.py            write the schemas
    tools/generate_ipc_schemas.py --check    fail if they are out of date

`--check` is what a gate runs: it regenerates into memory and compares, so a
protocol change that forgot to regenerate is caught rather than discovered.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker import protocol as P  # noqa: E402

OUT = ROOT / "schemas" / "ipc" / "v1"

# JSON type per field name. Kept beside the generator rather than inside the
# protocol module: the protocol's job is the contract, not its JSON Schema
# spelling.
FIELD_TYPES = {
    "app": "string",
    "artifact_id": "string",
    "artifact_type": "string",
    "capabilities": "array",
    "code": "string",
    "deadline": "string",
    "detail_ref": "string",
    "fraction": "number",
    "hash": "string",
    "inputs": "array",
    "job_id": "string",
    "manifest": "object",
    "message": "string",
    "operator": "string",
    "output_dir": "string",
    "params": "object",
    "path": "string",
    "protocol": "string",
    "reason": "string",
    "safe_message": "string",
    "stage": "string",
    "worker": "string",
}

# The rules a JSON Schema cannot express, said in the description so they
# travel with the contract.
NOTES = {
    "hello": "A major-version mismatch blocks execution; it never degrades "
             "into a partial mode where some operators work.",
    "job_progress": "`fraction` is derived from work actually done and is "
                    "monotonic within a stage. Simulated progress is a defect.",
    "job_artifact": "Section 12.3 names the artefact's format field `type`. "
                    "The envelope owns `type` as the message kind, so the "
                    "artefact's is `artifact_type`. Emitted only after write, "
                    "flush, close, validation and hash.",
    "job_succeeded": "`Succeeded` is reachable only from `Committing`, so this "
                     "message never describes a partial output.",
    "job_failed": "`safe_message` reaches the user; `detail_ref` points at the "
                  "worker log line holding the traceback.",
    "cancel_job": "Cancellation is cooperative. A cancelled job commits no run "
                  "and registers no artefact.",
    "shutdown": "The worker completes the transaction in flight or records "
                "recovery before exiting.",
}


def build() -> dict[str, str]:
    """Render every schema. Returns {filename: content}."""
    files: dict[str, str] = {}
    index: list[tuple[str, str]] = []

    for kind, required in sorted(P.REQUIRED.items()):
        direction = "app -> worker" if kind in P.APP_TO_WORKER else "worker -> app"
        description = f"{direction}. Protocol {P.PROTOCOL_VERSION}."
        if kind in NOTES:
            description += " " + NOTES[kind]
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"geopotential/ipc/v1/{kind}.json",
            "title": kind,
            "description": description,
            "type": "object",
            "required": ["type", "protocol", *required],
            "properties": {
                "type": {"const": kind},
                "protocol": {"type": "string"},
                **{
                    field: {"type": FIELD_TYPES.get(field, "string")}
                    for field in required
                },
            },
        }
        files[f"{kind}.json"] = json.dumps(schema, indent=2) + "\n"
        index.append((kind, direction))

    rows = "".join(f"| `{kind}` | {direction} |\n" for kind, direction in index)
    files["README.md"] = (
        f"# IPC schemas, version {P.PROTOCOL_VERSION}\n"
        "\n"
        "Generated from `worker/geopotential_worker/protocol.py` by\n"
        "`tools/generate_ipc_schemas.py`. `REQUIRED` in that module is the\n"
        "single source; do not hand-edit these files.\n"
        "\n"
        "| Message | Direction |\n"
        "|---|---|\n"
        f"{rows}"
        "\n"
        "Changing any of them obliges the seven steps of\n"
        "`IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` section 29: alter the schema,\n"
        "version it, update the producer, update the consumer, update the\n"
        "compatibility test, update the documentation, and update the golden\n"
        "output where one exists.\n"
    )
    return files


def main() -> int:
    files = build()
    if "--check" in sys.argv:
        stale = [
            name
            for name, content in files.items()
            if not (OUT / name).exists()
            or (OUT / name).read_text(encoding="utf-8") != content
        ]
        if stale:
            print(f"schemas: FAIL — out of date: {', '.join(sorted(stale))}")
            print("run tools/generate_ipc_schemas.py")
            return 1
        print(f"schemas: PASS — {len(files)} files match the protocol module")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
