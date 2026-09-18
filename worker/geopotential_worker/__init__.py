"""GeoPotential scientific worker.

Runs as a child process of the GUI and speaks JSON Lines over stdin/stdout.
Imports no Qt, in any form: the architecture gate fails on it.
"""
from ._version import PEP440_VERSION, VERSION

__all__ = ["VERSION", "PEP440_VERSION"]
