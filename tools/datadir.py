"""Where the datasets are. One answer, used by every gate and every tool.

Two layouts are legitimate and both have to work:

- **beside the tree** — `data/` a sibling of this project, which is how the
  workspace it was developed in is arranged;
- **inside the tree** — `data/` under the project root, which is what a clone
  of the published repository looks like.

Before this existed, twenty-one files each wrote `ROOT.parent / "data"`, and
the second layout worked in none of them: a fresh clone reported seventeen
gates `BLOCKED` for fixtures that were sitting right there. A repository that
only runs when its data lives one directory above it is not a repository
anybody can clone.

Inside wins when both exist. A checkout carries its own data, and that copy is
the one its gates were written against.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Override for a checkout that keeps its data somewhere else entirely.
ENV_VAR = "GEOPOTENTIAL_DATA"


def data_dir() -> Path:
    """The dataset directory, resolved once per call and never guessed.

    returns  the directory, whether or not it exists — callers report a
             missing fixture as `BLOCKED`, which is not the same as `FAIL`
    """
    declared = os.environ.get(ENV_VAR)
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    if inside.is_dir():
        return inside
    return (ROOT.parent / "data").resolve()


#: The resolved directory, for the many modules that want a constant.
DATA = data_dir()
