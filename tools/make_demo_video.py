#!/usr/bin/env python3
"""Assemble the demo video from storyboard frames.

    tools/make_demo_video.py [--out FILE] [--fps N]

The frames are **not** captured here. They are produced by
`tools/capture_sequence.py`, where every one of them is asserted against
numbers before it is written — so this cannot show a screen the application
does not produce. What this adds is only timing: a hold on each frame, a
cross-fade between them, and a slow scale so the result reads as a recording
rather than a slideshow.

That distinction is the point. A screen recording of somebody driving the
application would be prettier and would prove less: nobody could re-run it,
and nothing would fail if the screen changed. These frames are regenerated and
re-checked by the gate on every round.

Encoded with the `imageio-ffmpeg` static binary, which lives inside the Python
environment. Nothing is installed on the machine.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "validation" / "images"

#: The sequence, and why it is this one.
#:
#: Two real datasets, one after the other: the Utah FORGE geothermal survey
#: and the Korean landslide-susceptibility layers. A demo on one dataset shows
#: a workflow; a demo on two shows that the workflow is not about the dataset.
SEQUENCE: tuple[tuple[str, str], ...] = (
    ("demo", "01_points"),
    ("demo", "02_basemap"),
    ("demo", "03_colormap"),
    ("demo", "04_measured"),
    ("demo", "05_cubic"),
    ("other_domain", "01_layers"),
    ("other_domain", "03_classes"),
    ("other_domain", "02_circular"),
    ("other_domain", "04_mixed"),
    ("other_domain", "05_sensitivity"),
)

HOLD_SECONDS = 2.6
FADE_SECONDS = 0.7
#: How far the slow scale travels across a hold. Small on purpose: a demo of a
#: measuring instrument should not look like a commercial.
ZOOM = 1.035


def _load(width: int) -> list[Image.Image]:
    frames = []
    for folder, stem in SEQUENCE:
        path = IMAGES / folder / f"{stem}.png"
        if not path.is_file():
            raise SystemExit(
                f"{path} is missing. Run tools/capture_sequence.py first — the "
                f"frames are gated evidence, not decoration."
            )
        image = Image.open(path).convert("RGB")
        height = int(image.height * width / image.width)
        frames.append(image.resize((width, height), Image.LANCZOS))
    return frames


def _scaled(image: Image.Image, factor: float) -> np.ndarray:
    """One frame at `factor`, cropped back to the original size."""
    if abs(factor - 1.0) < 1e-6:
        return np.asarray(image, dtype=np.float32)
    width, height = image.size
    big = image.resize((int(width * factor), int(height * factor)),
                       Image.LANCZOS)
    left = (big.width - width) // 2
    top = (big.height - height) // 2
    return np.asarray(big.crop((left, top, left + width, top + height)),
                      dtype=np.float32)


def build(out: Path, fps: int, width: int) -> Path:
    import imageio_ffmpeg

    frames = _load(width)
    hold = max(1, int(HOLD_SECONDS * fps))
    fade = max(1, int(FADE_SECONDS * fps))
    size = frames[0].size

    # Constant-rate factor rather than a quality knob: these frames are flat
    # interface panels between slow fades, which x264 compresses well, and a
    # README that carries thirty megabytes is a README nobody waits for.
    # `+faststart` puts the index first so it plays before it has downloaded.
    writer = imageio_ffmpeg.write_frames(
        str(out), size, fps=fps, macro_block_size=8,
        ffmpeg_log_level="error",
        output_params=[
            "-c:v", "libx264", "-crf", "30", "-preset", "slow",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ],
    )
    writer.send(None)

    for index, image in enumerate(frames):
        nxt = frames[(index + 1) % len(frames)]
        for step in range(hold):
            factor = 1.0 + (ZOOM - 1.0) * (step / max(1, hold - 1))
            writer.send(_scaled(image, factor).astype(np.uint8).tobytes())
        if index == len(frames) - 1:
            break
        end = _scaled(image, ZOOM)
        start = _scaled(nxt, 1.0)
        for step in range(fade):
            alpha = (step + 1) / fade
            blend = end * (1.0 - alpha) + start * alpha
            writer.send(blend.astype(np.uint8).tobytes())
    writer.close()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "validation" / "demo.mp4")
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out = build(args.out, args.fps, args.width)
    seconds = (len(SEQUENCE) * HOLD_SECONDS
               + (len(SEQUENCE) - 1) * FADE_SECONDS)
    print(f"wrote {out}")
    print(f"  {len(SEQUENCE)} frames · {seconds:.0f}s · {args.fps} fps · "
          f"{out.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
