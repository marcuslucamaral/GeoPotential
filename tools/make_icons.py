#!/usr/bin/env python3
"""Draw the interface's icon set. One script, so 30-odd icons stay one family.

    python tools/make_icons.py            write every icon
    python tools/make_icons.py --check    fail if a file is missing or stale

The contract is `app/geopotential_app/qml/GeoPotential/icons/README.md`, and it
is enforced here rather than trusted: 24 x 24 area, the drawing inside 20 x 20,
1.5 px stroke, one colour. A set drawn by hand over months drifts — one icon at
1 px, another filled where its neighbour is stroked — and the drift is what
makes a toolbar look assembled instead of designed.

**The colour is not in the file.** Every path is `#000000`, and the QML recolours
it through `ThemedIcon.qml`, because an icon with its own colour does not follow
a theme and the light theme is one of the four this application promises.

Third-party icons would go in `CREDITS.md` with their licence. There are none:
these are drawn here, which is also why there is nothing to credit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "app" / "geopotential_app" / "qml" / "GeoPotential" / "icons"

#: Everything below is drawn in a 24 x 24 box with the ink inside 2..22.
STROKE = 1.5

_HEADER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="#000000" '
    f'stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">'
)


def svg(body: str) -> str:
    """One icon file. The body is paths; the header carries the whole style."""
    return _HEADER + body + "</svg>\n"


#: `d` attributes only, so the family shares every stroke setting above.
#: Grouped by the folder each belongs to, which the README defines by *who
#: draws it* and not by what it looks like.
TOOLS: dict[str, str] = {
    # Navigate: the pointer, tilted, as every map application draws it.
    "navigate": '<path d="M5 3l6 17 2.4-7.1L20.5 10z"/>',
    # Layers: three sheets seen edge-on.
    "layers": '<path d="M12 3l8.5 4.5L12 12 3.5 7.5z"/>'
              '<path d="M3.5 12L12 16.5 20.5 12"/>'
              '<path d="M3.5 16.5L12 21l8.5-4.5"/>',
    # Identify: what is under this point. A crosshair, not a magnifier —
    # it reads a value, it does not search.
    "identify": '<circle cx="12" cy="12" r="5.5"/>'
                '<path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4"/>',
    # AOI: a drawn polygon with its vertices showing.
    "aoi": '<path d="M12 3l8 6-3 10H7L4 9z"/>'
           '<circle cx="12" cy="3" r="1.4" fill="#000000"/>'
           '<circle cx="20" cy="9" r="1.4" fill="#000000"/>'
           '<circle cx="4" cy="9" r="1.4" fill="#000000"/>',
    # Distance: two points and the line between them, with end ticks.
    "measure-distance": '<path d="M4 18L20 6"/>'
                        '<path d="M2.5 15.5l3 3M18.5 3.5l3 3"/>'
                        '<circle cx="4" cy="18" r="1.6" fill="#000000"/>'
                        '<circle cx="20" cy="6" r="1.6" fill="#000000"/>',
    # Area: a closed figure with its interior hatched once.
    "measure-area": '<path d="M3.5 8.5L10 3.5l10.5 5-3 11.5H6.5z"/>'
                    '<path d="M7 14.5l8-6M9 18.5l8.5-6.5"/>',
    "zoom-in": '<circle cx="10.5" cy="10.5" r="6.5"/>'
               '<path d="M15.5 15.5L21 21M8 10.5h5M10.5 8v5"/>',
    "zoom-out": '<circle cx="10.5" cy="10.5" r="6.5"/>'
                '<path d="M15.5 15.5L21 21M8 10.5h5"/>',
    # Fit: the whole extent back inside the frame.
    "zoom-fit": '<path d="M3 8.5V3h5.5M15.5 3H21v5.5'
                'M21 15.5V21h-5.5M8.5 21H3v-5.5"/>'
                '<rect x="8" y="8" width="8" height="8" rx="1"/>',
    "fullscreen": '<path d="M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6"/>',
    # Export: the map leaves the application.
    "export": '<path d="M12 3v11"/><path d="M8 10.5l4 4 4-4"/>'
              '<path d="M3.5 17v2.5a1.5 1.5 0 001.5 1.5h14a1.5 1.5 0 '
              '001.5-1.5V17"/>',
}

WORKFLOW: dict[str, str] = {
    # The eight steps, in the order the flow runs them. Each says what the
    # step *does*, not what number it is: the number is already on the row.
    "project": '<path d="M3 7.5a1.5 1.5 0 011.5-1.5h4L11 8.5h8.5A1.5 1.5 0 '
               '0121 10v8.5a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18.5z"/>',
    # Data: a table of samples.
    "data": '<rect x="3" y="4.5" width="18" height="15" rx="1.5"/>'
            '<path d="M3 9.5h18M3 14.5h18M9 9.5v10M15 9.5v10"/>',
    # QA/QC: checked against a rule.
    "qc": '<path d="M12 3l7.5 3v6c0 4.5-3 7.8-7.5 9-4.5-1.2-7.5-4.5-7.5-9V6z"/>'
          '<path d="M8.5 12l2.5 2.5 4.5-5"/>',
    # Harmonize: everything brought onto one grid.
    "harmonize": '<rect x="3" y="3" width="8" height="8" rx="1"/>'
                 '<rect x="13" y="13" width="8" height="8" rx="1"/>'
                 '<path d="M13 7h5.5M21 7l-2.5-2M21 7l-2.5 2"/>'
                 '<path d="M11 17H5.5M3 17l2.5-2M3 17l2.5 2"/>',
    # Membership: the curve that maps a measurement to [0,1].
    "membership": '<path d="M3 20V4"/><path d="M3 20h18"/>'
                  '<path d="M4.5 17.5c4 0 4.5-10 8-10s4 6.5 7 6.5"/>',
    # Weights: the pairwise judgment, which is a balance.
    "weights": '<path d="M12 4v16M7 20h10"/><path d="M4 8h16"/>'
               '<path d="M4 8l-2.5 5.5h5zM20 8l-2.5 5.5h5z"/>',
    # Aggregate: several criteria become one score.
    "aggregate": '<path d="M4 5h6M4 10h6M4 15h6M4 20h6"/>'
                 '<path d="M11.5 12.5h6"/><path d="M20 12.5l-3-2.5M20 12.5l-3 2.5"/>',
    # Results: where on the map the answer is.
    "results": '<path d="M3 6.5l6-3 6 3 6-3v14l-6 3-6-3-6 3z"/>'
               '<path d="M9 3.5v14M15 6.5v14"/>'
               '<circle cx="12" cy="11" r="2" fill="#000000"/>',
}

APP: dict[str, str] = {
    "projects": '<rect x="3" y="3" width="7.5" height="7.5" rx="1.2"/>'
                '<rect x="13.5" y="3" width="7.5" height="7.5" rx="1.2"/>'
                '<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.2"/>'
                '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.2"/>',
    "undo": '<path d="M4 9h10a5.5 5.5 0 010 11h-6"/>'
            '<path d="M8 4.5L3.5 9 8 13.5"/>',
    "redo": '<path d="M20 9H10a5.5 5.5 0 000 11h6"/>'
            '<path d="M16 4.5L20.5 9 16 13.5"/>',
    # Run: the step the flow is on, executed.
    "run": '<path d="M6.5 4.5l13 7.5-13 7.5z" fill="#000000" stroke="none"/>',
    # Cancel: a job stops. A square, because it is a stop and not a refusal.
    "cancel": '<rect x="5.5" y="5.5" width="13" height="13" rx="2"/>'
              '<path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>',
    # Compare: two views of the same place, side by side.
    "compare": '<rect x="3" y="4.5" width="18" height="15" rx="1.5"/>'
               '<path d="M12 4.5v15"/><path d="M6 9.5h3M6 13h3M15 9.5h3M15 13h3"/>',
    "preferences": '<circle cx="12" cy="12" r="3"/>'
                   '<path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3'
                   'M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1'
                   'M18.7 18.7l-2.1-2.1M7.4 7.4L5.3 5.3"/>',
    # Import: a file arrives in the project.
    "import": '<path d="M14 3H6.5A1.5 1.5 0 005 4.5v15A1.5 1.5 0 006.5 21h11a1.5 '
              '1.5 0 001.5-1.5V8z"/><path d="M14 3v5h5"/>'
              '<path d="M12 11v6M9.5 14.5L12 17l2.5-2.5"/>',
    # Gridding: scattered samples become cells.
    "gridding": '<rect x="3" y="3" width="18" height="18" rx="1.5"/>'
                '<path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>'
                '<circle cx="6" cy="6" r="1.3" fill="#000000"/>'
                '<circle cx="12" cy="12" r="1.3" fill="#000000"/>'
                '<circle cx="18" cy="18" r="1.3" fill="#000000"/>'
                '<circle cx="18" cy="6" r="1.3" fill="#000000"/>',
    # The four panels, each drawn as the rectangle it occupies.
    "panel-workflow": '<rect x="3" y="4" width="18" height="16" rx="1.5"/>'
                      '<path d="M9 4v16"/>'
                      '<path d="M5.2 8h1.6M5.2 12h1.6M5.2 16h1.6"/>',
    "panel-layers": '<rect x="3" y="4" width="18" height="16" rx="1.5"/>'
                    '<path d="M9 4v16"/><path d="M4.5 9.5l2.2-1.2 2.3 1.2"/>'
                    '<path d="M4.5 13l2.2-1.2 2.3 1.2"/>',
    "panel-inspector": '<rect x="3" y="4" width="18" height="16" rx="1.5"/>'
                       '<path d="M15 4v16"/>'
                       '<path d="M17.2 8h1.6M17.2 12h1.6M17.2 16h1.6"/>',
    "panel-jobs": '<rect x="3" y="4" width="18" height="16" rx="1.5"/>'
                  '<path d="M3 14.5h18"/>'
                  '<path d="M6 17.5h6M6 19.5h9"/>',
    # The rail itself can be hidden, so it needs its own icon in the menu.
    "panel-rail": '<rect x="3" y="4" width="18" height="16" rx="1.5"/>'
                  '<path d="M7.5 4v16"/>'
                  '<circle cx="5.2" cy="8" r="1" fill="#000000"/>'
                  '<circle cx="5.2" cy="12" r="1" fill="#000000"/>'
                  '<circle cx="5.2" cy="16" r="1" fill="#000000"/>',
    # Theme: the light half and the dark half of the same disc.
    "theme": '<circle cx="12" cy="12" r="8"/>'
             '<path d="M12 4a8 8 0 000 16z" fill="#000000" stroke="none"/>',
    # A step that is blocked says so on the rail as well as in the panel.
    "blocked": '<circle cx="12" cy="12" r="8.5"/><path d="M6 18L18 6"/>',
}

FOLDERS: dict[str, dict[str, str]] = {
    "tools": TOOLS,
    "workflow": WORKFLOW,
    "app": APP,
}


def write(check: bool) -> int:
    """Write every icon, or report which ones are missing or stale."""
    stale: list[str] = []
    for folder, icons in FOLDERS.items():
        target = ICONS / folder
        target.mkdir(parents=True, exist_ok=True)
        for name, body in icons.items():
            path = target / f"{name}.svg"
            content = svg(body)
            if check:
                current = path.read_text(encoding="utf-8") if path.exists() else ""
                if current != content:
                    stale.append(f"{folder}/{name}.svg")
                continue
            path.write_text(content, encoding="utf-8")

    if check:
        if stale:
            print("icons out of date: " + ", ".join(stale), file=sys.stderr)
            print("regenerate with: python tools/make_icons.py", file=sys.stderr)
            return 1
        print(f"icons up to date: {sum(len(i) for i in FOLDERS.values())} files")
        return 0

    print(f"wrote {sum(len(i) for i in FOLDERS.values())} icons under {ICONS}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if any icon is missing or does not match")
    return write(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
