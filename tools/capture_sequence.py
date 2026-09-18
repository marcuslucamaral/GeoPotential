#!/usr/bin/env python3
"""Drive the real application through a scripted sequence and photograph it.

Visual evidence has a cost problem. A 1440x880 screenshot is expensive to look
at, and a milestone needs several — so the honest thing (capture the running
application at every interesting state) collides with the cheap thing (capture
one and hope). This runner removes the collision:

  - it captures **every** step, at full size, to `docs/validation/images/<id>/`
  - it computes what can be checked **numerically** per frame — probe colours,
    how much of the frame changed since the previous one, whether the frame is
    blank — so most questions are answered by a text table, not by looking
  - it assembles **one** downscaled contact sheet, so when looking is genuinely
    needed it costs a single small image instead of N large ones

The rule that follows from it is in `docs/conventions/visual-evidence.md`:
read the contact sheet or the report; never the full-size frames.

    tools/capture_sequence.py m4              run one storyboard
    tools/capture_sequence.py --list          what storyboards exist
    tools/capture_sequence.py --all           every storyboard
    tools/capture_sequence.py m4 --check      run and fail on a broken frame
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Keep a storyboard out of the developer's real recents list.
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp(prefix="gp-storyboard-"))

IMAGES = ROOT / "docs" / "validation" / "images"
STORYBOARDS = ROOT / "tools" / "storyboards"

# Contact-sheet geometry. Three columns at 320 px is about 980 px wide, which
# is legible at a glance and cheap to read.
SHEET_COLUMNS = 3
SHEET_THUMB_WIDTH = 320


@dataclass
class Frame:
    """One captured state, and everything checkable about it without looking."""

    index: int
    name: str
    caption: str
    path: Path
    width: int = 0
    height: int = 0
    probes: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    changed_fraction: float = 0.0
    distinct_colours: int = 0
    blank: bool = False
    facts: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "caption": self.caption,
            "file": self.path.name,
            "size": [self.width, self.height],
            "probes": {k: list(v) for k, v in self.probes.items()},
            "changed_fraction": round(self.changed_fraction, 4),
            "distinct_colours": self.distinct_colours,
            "blank": self.blank,
            "facts": self.facts,
            "failures": self.failures,
        }


class Storyboard:
    """A named sequence of states to photograph.

    A storyboard is written per milestone and lives in `tools/storyboards/`.
    Each step drives the real application — no mockups, no stubs — and then
    declares what must be true of the frame it produced.
    """

    def __init__(self, identifier: str, title: str, *, size: tuple[int, int] = (1440, 880)) -> None:
        self.id = identifier
        self.title = title
        self.size = size
        self._steps: list[tuple[str, str, Callable, dict]] = []
        self.frames: list[Frame] = []

    def step(
        self,
        name: str,
        caption: str,
        action: Callable[[Any], dict[str, Any] | None],
        *,
        probes: dict[str, tuple[int, int]] | None = None,
        must_change: bool = True,
        settle_ms: int = 900,
        expect: Callable[[Frame, list[Frame]], str | None] | None = None,
    ) -> None:
        """Register one state.

        name       short slug; becomes the filename
        caption    one line saying what the frame shows and why it matters
        action     called with the `Session`; returns facts worth recording
        probes     {label: (x, y)} pixels to sample, for checks that would
                   otherwise need eyes
        must_change  whether this frame has to differ from the previous one.
                     A step that changes nothing visible is usually a step that
                     silently failed, and this is what catches it.
        expect       expect(frame, earlier) -> None when satisfied, else the
                     reason. This is where a claim about a *sequence* goes —
                     "the same colour after zooming out" cannot be asserted
                     from one frame, and it is exactly the kind of thing a
                     person would otherwise have to notice.
        """
        self._steps.append((name, caption, action, {
            "probes": probes or {},
            "must_change": must_change,
            "settle_ms": settle_ms,
            "expect": expect,
        }))

    # ---- running --------------------------------------------------------

    def run(self, *, strict: bool = False) -> list[Frame]:
        from session import Session  # local import: needs the Qt app first

        out = IMAGES / self.id
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)

        session = Session(self.size)
        previous = None
        try:
            for index, (name, caption, action, options) in enumerate(self._steps, 1):
                facts = action(session) or {}
                session.settle(options["settle_ms"])
                path = out / f"{index:02d}_{name}.png"
                session.grab(path)
                frame = self._measure(index, name, caption, path, previous,
                                      options, facts)
                if options.get("expect") is not None:
                    reason = options["expect"](frame, list(self.frames))
                    if reason:
                        frame.failures.append(reason)
                self.frames.append(frame)
                previous = path
        finally:
            session.close()

        self._contact_sheet(out)
        self._write_report(out)
        if strict and any(not f.ok for f in self.frames):
            return self.frames
        return self.frames

    def _measure(self, index, name, caption, path, previous, options, facts) -> Frame:  # noqa: ANN001
        from PIL import Image

        frame = Frame(index, name, caption, path, facts=dict(facts))
        image = Image.open(path).convert("RGB")
        frame.width, frame.height = image.size

        colours = image.getcolors(maxcolors=1 << 20)
        frame.distinct_colours = len(colours) if colours else 1 << 20
        # A frame with almost no colours is a frame of nothing — the usual
        # sign that the shell loaded but the state never arrived.
        frame.blank = frame.distinct_colours < 8
        if frame.blank:
            frame.failures.append("frame is effectively blank")

        for label, (x, y) in options["probes"].items():
            if 0 <= x < frame.width and 0 <= y < frame.height:
                frame.probes[label] = image.getpixel((x, y))

        if previous is not None:
            frame.changed_fraction = _changed_fraction(previous, path)
            if options["must_change"] and frame.changed_fraction < 0.001:
                frame.failures.append(
                    f"nothing changed since the previous frame "
                    f"({frame.changed_fraction:.4%}); the step probably did nothing"
                )
        return frame

    # ---- output ---------------------------------------------------------

    def _contact_sheet(self, out: Path) -> Path:
        """One downscaled grid of every frame. The only image worth reading."""
        from PIL import Image, ImageDraw

        if not self.frames:
            return out / "contact_sheet.png"
        thumbs = []
        for frame in self.frames:
            image = Image.open(frame.path).convert("RGB")
            ratio = SHEET_THUMB_WIDTH / image.width
            thumbs.append(image.resize(
                (SHEET_THUMB_WIDTH, max(1, int(image.height * ratio))),
                Image.LANCZOS,
            ))
        thumb_w, thumb_h = thumbs[0].size
        label_h = 16
        columns = min(SHEET_COLUMNS, len(thumbs))
        rows = (len(thumbs) + columns - 1) // columns
        sheet = Image.new(
            "RGB",
            (columns * thumb_w + (columns + 1) * 6,
             rows * (thumb_h + label_h) + (rows + 1) * 6),
            (16, 18, 24),
        )
        draw = ImageDraw.Draw(sheet)
        for i, (thumb, frame) in enumerate(zip(thumbs, self.frames)):
            col, row = i % columns, i // columns
            x = 6 + col * (thumb_w + 6)
            y = 6 + row * (thumb_h + label_h + 6)
            sheet.paste(thumb, (x, y))
            draw.text((x + 2, y + thumb_h + 2),
                      f"{frame.index:02d} {frame.name}",
                      fill=(200, 205, 215))
        path = out / "contact_sheet.png"
        sheet.save(path)
        return path

    def _write_report(self, out: Path) -> None:
        rows = "".join(
            f"| {f.index:02d} | `{f.name}` | {f.caption} | "
            f"{f.changed_fraction:.1%} | "
            f"{'ok' if f.ok else '**' + '; '.join(f.failures) + '**'} |\n"
            for f in self.frames
        )
        (out / "STORYBOARD.md").write_text(
            f"# {self.title}\n"
            f"\n"
            f"Captured from the running application at {self.size[0]} x "
            f"{self.size[1]}, offscreen. Regenerate with\n"
            f"`tools/capture_sequence.py {self.id}`.\n"
            f"\n"
            f"![contact sheet](contact_sheet.png)\n"
            f"\n"
            f"| # | Step | What it shows | Changed | Checks |\n"
            f"|---|---|---|---|---|\n"
            f"{rows}"
            f"\n"
            f"`Changed` is the fraction of pixels differing from the previous "
            f"frame. A step that changes nothing is a step that did nothing, "
            f"and the runner fails on it.\n",
            encoding="utf-8",
        )
        (out / "frames.json").write_text(
            json.dumps({
                "storyboard": self.id,
                "title": self.title,
                "size": list(self.size),
                "frames": [f.as_dict() for f in self.frames],
            }, indent=2),
            encoding="utf-8",
        )

    def report_text(self) -> str:
        """The compact table. This is what should be read, not the frames."""
        width = max((len(f.name) for f in self.frames), default=4)
        lines = [f"{self.title}  ->  docs/validation/images/{self.id}/"]
        for f in self.frames:
            status = "ok  " if f.ok else "FAIL"
            probes = " ".join(f"{k}={v}" for k, v in f.probes.items())
            facts = " ".join(f"{k}={v}" for k, v in f.facts.items())
            lines.append(
                f"  {status} {f.index:02d} {f.name.ljust(width)} "
                f"changed {f.changed_fraction:6.1%}  {facts}"
                + (f"  [{probes}]" if probes else "")
            )
            for failure in f.failures:
                lines.append(f"       ! {failure}")
        passed = sum(1 for f in self.frames if f.ok)
        lines.append(f"  {passed}/{len(self.frames)} frames ok; "
                     f"contact sheet: images/{self.id}/contact_sheet.png")
        return "\n".join(lines)


def _changed_fraction(a: Path, b: Path) -> float:
    """Fraction of pixels that differ, beyond a small tolerance.

    Downscaled first: a full-resolution comparison is slow and answers a
    question nobody asked — what matters is whether the frame is visibly
    different, not whether an antialiased edge moved.
    """
    from PIL import Image, ImageChops

    size = (360, 220)
    first = Image.open(a).convert("RGB").resize(size, Image.BILINEAR)
    second = Image.open(b).convert("RGB").resize(size, Image.BILINEAR)
    diff = ImageChops.difference(first, second).convert("L")
    changed = sum(1 for pixel in diff.getdata() if pixel > 12)
    return changed / (size[0] * size[1])


def available() -> list[str]:
    """Modules in `storyboards/` that actually define a storyboard.

    `session.py` lives there too — it is the harness every storyboard uses, not
    a storyboard itself — so membership is decided by whether the module
    defines `build()`, not by where the file sits.
    """
    sys.path.insert(0, str(STORYBOARDS))
    names = []
    for path in sorted(STORYBOARDS.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            module = importlib.import_module(path.stem)
        except Exception:  # noqa: BLE001 - a broken storyboard is reported below
            names.append(path.stem)
            continue
        if callable(getattr(module, "build", None)):
            names.append(path.stem)
    return names


def load(identifier: str) -> Storyboard:
    sys.path.insert(0, str(STORYBOARDS))
    module = importlib.import_module(identifier)
    return module.build()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storyboard", nargs="?", help="which sequence to run")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if any frame failed its checks")
    args = parser.parse_args()

    if args.list:
        for name in available():
            print(name)
        return 0

    names = available() if args.all else ([args.storyboard] if args.storyboard else [])
    if not names:
        parser.error("name a storyboard, or use --all / --list")

    failed = 0
    for name in names:
        board = load(name)
        board.run()
        print(board.report_text())
        failed += sum(1 for f in board.frames if not f.ok)
    if failed:
        print(f"\n{failed} frame(s) failed their checks")
    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
