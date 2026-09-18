"""Entry point: `python -m geopotential_worker`.

  --self-test   run the operator registry's own checks and exit
  (no flag)     serve the JSON Lines protocol on stdin/stdout
"""
from __future__ import annotations

import sys

from .server import Worker


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--version" in argv:
        from ._version import VERSION
        print(VERSION)
        return 0
    if "--capabilities" in argv:
        import json
        from .operators import registry
        print(json.dumps(registry.describe_all(), indent=2))
        return 0
    return Worker().serve()


if __name__ == "__main__":
    raise SystemExit(main())
