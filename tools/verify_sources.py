#!/usr/bin/env python3
"""Fetch one tile from every basemap source and look at it.

A licence page says a style is CC-BY. It does not say whether the CDN serving
it answers an anonymous client. Carto's does not: it returns a 200 with a PNG
that reads `API KEY REQUIRED`, and that is what appeared on the map — a
perfectly valid HTTP response carrying a refusal.

So a source is verified the only way that means anything: fetch a tile of a
place that is definitely full of detail, decode it, and count what came back. A
real map tile has hundreds of distinct colours; a watermark has a dozen.

    tools/verify_sources.py            check every source
    tools/verify_sources.py --json     the same, machine-readable

`BLOCKED` without a network: a machine offline cannot answer this, and saying
`FAIL` there would be saying the wrong thing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

# Central London at zoom 14: dense in every basemap that has data at all.
DENSE = (-0.1276, 51.5074, 14)

# Below this, what came back is a watermark, an error card or an empty tile —
# not a map. A real tile of a dense city is in the hundreds.
MIN_COLOURS = 64
BLOCKED = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    from geopotential_app.basemap import sources as S
    from geopotential_app.basemap import tiles as T

    longitude, latitude, zoom = DENSE
    x, y = T.deg_to_tile(longitude, latitude, zoom)

    findings: list[dict] = []
    for key, source in S.SOURCES.items():
        request = urllib.request.Request(
            source.url(zoom, x, y), headers={"User-Agent": T.USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read()
                status = response.status
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            findings.append({"key": key, "ok": None, "why": f"unreachable: {exc}"})
            continue

        image = T.decode(payload)
        colours = (0 if image is None
                   else len(np.unique(image[..., :3].reshape(-1, 3), axis=0)))
        ok = status == 200 and colours >= MIN_COLOURS
        findings.append({
            "key": key, "name": source.name, "licence": source.licence,
            "status": status, "bytes": len(payload), "colours": colours,
            "ok": ok,
            "why": "" if ok else (
                f"only {colours} colours in a tile of central London — this "
                f"looks like a watermark or an error card, not a map"),
        })

    if all(f["ok"] is None for f in findings):
        print("BLOCKED: no source could be reached; is there a network?")
        return BLOCKED

    if options.json:
        print(json.dumps(findings, indent=2))
    else:
        for f in findings:
            mark = "ok  " if f["ok"] else ("?   " if f["ok"] is None else "BAD ")
            print(f"  {mark} {f['key']:14s} {f.get('colours', '—'):>4} colours  "
                  f"{f.get('bytes', 0):>6} bytes  {f.get('licence', '')}")
            if f["why"]:
                print(f"       {f['why']}")

    bad = [f for f in findings if f["ok"] is False]
    print(f"\n{len(findings) - len(bad)}/{len(findings)} sources serve a real tile")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
