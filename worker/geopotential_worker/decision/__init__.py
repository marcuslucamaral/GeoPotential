"""Membership, AHP, fuzzy operators, weighted combination.

Pure numpy over `domain/`. No I/O, no Qt: a numerical gate here
needs neither a file nor a window.
"""
from . import ahp, aggregate, correlation, membership

__all__ = ["membership", "ahp", "aggregate", "correlation"]
