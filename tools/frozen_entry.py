"""The bundle's entry point. One binary, two processes.

    geopotential              the Qt Quick application
    geopotential --worker     the scientific worker, speaking JSON Lines

In a checkout these are two commands run with two `-m` flags. In a bundle there
is no Python interpreter to give `-m` to: `sys.executable` is the binary
itself. So the binary has to be able to be either process, and the supervisor
starts the worker by re-launching the binary with `--worker`
(`controllers/worker_supervisor.py`).

**This file is not application code**, and that is the point. `P-02` says the
app imports no worker package — the boundary between them is the protocol and
nothing else — and the architecture gate enforces it over
`app/geopotential_app/`. A launcher that can start either process is neither of
them: it lives here, in `tools/`, it imports one or the other and never both in
the same process, and no module inside either package learns that the other
exists.

The two processes stay as separate as they were: different PIDs, different
memory, stdout as the protocol and stderr as the log. What is shared is one
file on disk, which is what `--onedir` gives either way.
"""
from __future__ import annotations

import sys

#: The switch the supervisor passes. Long-form and unabbreviated on purpose:
#: it is not a user-facing option, and anything shorter risks colliding with a
#: file the person dropped on the application.
WORKER_FLAG = "--worker"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == WORKER_FLAG:
        # The child. Its argv is the worker's own, minus the switch that got
        # it here.
        sys.argv = [sys.argv[0], *argv[1:]]
        from geopotential_worker.__main__ import main as worker_main

        return int(worker_main() or 0)

    from geopotential_app.app import main as app_main

    return int(app_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
