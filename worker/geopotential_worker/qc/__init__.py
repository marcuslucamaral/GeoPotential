"""Spatial QA/QC. MSP-04, milestone M3.

`validate()` is the one entry point, so that "impede operação inválida" is
decided in one place: the Import Wizard and job submission both consult
`Report.usable`, and two callers of one function cannot disagree.
"""
from .findings import Finding, Report, Severity
from .rules import UNIT_RANGES
from .validate import validate

__all__ = ["Finding", "Report", "Severity", "validate", "UNIT_RANGES"]
