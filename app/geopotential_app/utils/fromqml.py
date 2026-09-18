"""Converting values that arrive from QML into plain Python.

A JavaScript object built in QML — `var d = {}; d["crs"] = "EPSG:26912"` —
reaches a `QVariant` slot as a **`QJSValue`**, not a `dict`. It behaves enough
like a mapping to pass casual inspection, and then fails at the first thing
that needs a real Python type. In this project that thing is `json.dumps` in
`protocol.encode`, which is the worst possible place to discover it: the job
has already been created and journalled, so the failure leaves a job stuck in
`Validating` and the rest of the QML function silently abandoned.

That happened. It is why this module exists, and why every slot taking a
`QVariant` from QML passes its arguments through `to_python` before doing
anything else.

An object literal written inline in QML often *is* converted automatically,
which is what makes this treacherous: the same code works from one call site
and breaks from another.
"""
from __future__ import annotations

from typing import Any


def to_python(value: Any) -> Any:
    """Recursively convert a QML value into plain Python containers.

    value    anything arriving from QML: QJSValue, QVariantMap, list, scalar
    returns  the same data in dict / list / str / float / int / bool / None

    The conversion is deep, because a QJSValue can nest: a dict of lists of
    dicts arrives with QJSValue at every level, and converting only the top
    one moves the failure inward rather than removing it.
    """
    # QJSValue is the JavaScript engine's own wrapper. `toVariant()` unwraps it
    # into Qt containers, which PySide then maps to Python ones — but only one
    # level reliably, so the result is walked again below.
    to_variant = getattr(value, "toVariant", None)
    if callable(to_variant):
        value = to_variant()

    if isinstance(value, dict):
        return {str(k): to_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_python(v) for v in value]
    return value


def to_dict(value: Any) -> dict[str, Any]:
    """Convert to a plain dict, treating None and non-mappings as empty."""
    converted = to_python(value)
    return converted if isinstance(converted, dict) else {}


def to_list(value: Any) -> list[Any]:
    """Convert to a plain list, treating None and non-sequences as empty."""
    converted = to_python(value)
    if isinstance(converted, list):
        return converted
    return [] if converted is None else [converted]
