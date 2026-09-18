#!/usr/bin/env python3
"""Record a live screen capture of the application working.

    tools/record_demo.py [--out FILE] [--fps N] [--display :77]

This is the other kind of demo, and the difference from `make_demo_video.py`
matters:

- `make_demo_video.py` assembles **gated storyboard frames**. Every frame was
  asserted against numbers before it was written, so the video cannot show a
  screen the product does not produce. It has no cursor and no motion of its
  own.
- This records a **real window on a real X server**, with the pointer moving
  and the interface repainting between states. It is more convincing and
  proves less: nothing here fails if the interface changes.

Keep both. The README's GIF is the checked one; this is the "watch it work".

**Your desktop is never filmed.** The application runs on a private Xvfb
display created for the recording and destroyed after it, so nothing of the
machine's own session can appear in the frame. Recording `:0` would have
needed no extra package and would have captured whatever happened to be open.

The interface is driven the same way the storyboards drive it — through the
shell's own objects, not by clicking at guessed coordinates — so a scene that
cannot happen does not get recorded as if it had. The pointer is moved
separately, over the canvas, so the capture shows motion a viewer can follow.

Needs: `Xvfb` (system package) and `pyautogui` (pip). The encoder is the
static ffmpeg inside `imageio-ffmpeg`; nothing is installed on the machine.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZE = (1440, 880)
#: Xvfb wants a size divisible by 8 for the capture to encode cleanly.
SCREEN = (1440, 880)


def _require(binary: str, how: str) -> str:
    found = shutil.which(binary)
    if not found:
        raise SystemExit(f"{binary} is not installed. {how}")
    return found


def start_xvfb(display: str) -> subprocess.Popen:
    """A private X server, so the machine's own screen is never in frame."""
    xvfb = _require("Xvfb", "Install it with: sudo apt install xvfb")
    proc = subprocess.Popen(
        [xvfb, display, "-screen", "0", f"{SCREEN[0]}x{SCREEN[1]}x24",
         "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(100):                       # up to 5 s for it to listen
        if Path(f"/tmp/.X11-unix/X{display.lstrip(':')}").exists():
            return proc
        time.sleep(0.05)
    proc.terminate()
    raise SystemExit(f"Xvfb did not come up on {display}")


def start_recorder(display: str, out: Path, fps: int) -> subprocess.Popen:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.Popen(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "x11grab", "-draw_mouse", "1",
         "-video_size", f"{SCREEN[0]}x{SCREEN[1]}",
         "-framerate", str(fps), "-i", f"{display}.0",
         # CRF over a bitrate: flat interface panels compress well, and a
         # README that carries thirty megabytes is one nobody waits for.
         "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "validation" / "demo-live.mp4")
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--display", default=":77")
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    xvfb = start_xvfb(args.display)
    recorder = None
    try:
        # Before Qt is imported: the platform plugin binds to whatever DISPLAY
        # said at load time, and an offscreen session renders no window to
        # capture.
        os.environ["DISPLAY"] = args.display
        os.environ.pop("QT_QPA_PLATFORM", None)
        os.environ.pop("WAYLAND_DISPLAY", None)
        # Xvfb has no GPU and no GL. Qt Quick's default scene graph asks for
        # one and the process dies in the render thread — a core dump with no
        # Python traceback, which is what the first run of this produced.
        # The software rasteriser draws the same frames, slower.
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["QSG_RENDER_LOOP"] = "basic"
        os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
        sys.path.insert(0, str(ROOT / "tools" / "storyboards"))
        sys.path.insert(0, str(ROOT / "app"))

        from scenes import run_scenes                       # noqa: E402
        from session import Session                         # noqa: E402

        session = Session(size=SIZE)
        session.window.show()
        session.settle(1500)

        recorder = start_recorder(args.display, args.out, args.fps)
        time.sleep(1.0)                          # let the first frames land

        run_scenes(session)

        session.settle(1200)
    finally:
        if recorder is not None:
            recorder.communicate(b"q", timeout=30)
        xvfb.terminate()
        xvfb.wait(timeout=10)

    size_mb = args.out.stat().st_size / 1024 / 1024 if args.out.exists() else 0
    print(f"wrote {args.out}")
    print(f"  {SCREEN[0]}x{SCREEN[1]} · {args.fps} fps · {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
