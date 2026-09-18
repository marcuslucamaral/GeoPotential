"""The translator the interface binds to.

Two languages, one catalogue, and a **property** rather than a slot: QML has no
way to know that the answer to `t("menu.file")` changed, so the strings are
published as a dictionary that changes wholesale when the language does. Every
binding through `tr.strings[...]` then re-evaluates by itself.

The chosen language is a preference of the person, not of the project, so it is
stored with `QSettings` and never inside a `.gpot`.

QtCore only.
"""
from __future__ import annotations

import os

from ..utils.qtcore import Property, QObject, QSettings, Signal, Slot
from .catalog import CATALOG

LANGUAGES = ("pt", "en")
DEFAULT = "pt"

_COLUMN = {"pt": 0, "en": 1}


def table(language: str) -> dict[str, str]:
    """Every key in one language.

    inputs   language, `'pt'` or `'en'`
    output   key -> text; a key missing its column falls back to the other,
             which is visible on screen and therefore reported by the gate
             rather than hidden.
    """
    column = _COLUMN.get(language, _COLUMN[DEFAULT])
    return {
        key: (values[column] or values[1 - column])
        for key, values in CATALOG.items()
    }


def fill(text: str, *args: object) -> str:
    """`%1`, `%2`, … replaced in order, the way QML's `arg` does it.

    One substitution rule for both halves of the application: a message built
    in Python and the same message built in QML cannot then disagree.
    """
    result = text
    for position, value in enumerate(args, start=1):
        result = result.replace(f"%{position}", str(value))
    return result


class Translator(QObject):
    """The current language, and every string in it."""

    languageChanged = Signal()

    ORGANISATION = "GeoPotential"
    APPLICATION = "GeoPotential Professional"

    # A gate or a storyboard must not write the developer's own preference.
    # Point this at a file and the preference goes there instead; the run is
    # then reproducible and leaves nothing behind.
    OVERRIDE = "GEOPOTENTIAL_PREFERENCES"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        override = os.environ.get(self.OVERRIDE)
        self._settings = (
            QSettings(override, QSettings.IniFormat) if override
            else QSettings(self.ORGANISATION, self.APPLICATION)
        )
        stored = str(self._settings.value("interface/language", DEFAULT))
        self._language = stored if stored in LANGUAGES else DEFAULT
        self._table = table(self._language)

    def _get_language(self) -> str:
        return self._language

    def _get_strings(self) -> dict:
        return self._table

    language = Property(str, _get_language, notify=languageChanged)
    strings = Property("QVariant", _get_strings, notify=languageChanged)

    @Slot(str)
    def setLanguage(self, language: str) -> None:  # noqa: N802
        """Switch language. Idempotent, and it repaints nothing by itself:
        every binding that reads `strings` re-evaluates on the signal."""
        if language not in LANGUAGES or language == self._language:
            return
        self._language = language
        self._table = table(language)
        self._settings.setValue("interface/language", language)
        self._settings.sync()
        self.languageChanged.emit()

    @Slot(str, result=str)
    def t(self, key: str) -> str:
        """One string. For Python; QML binds to `strings` instead, because a
        slot is read once and never re-read."""
        return self._table.get(key, key)

    @Slot(str, "QVariant", result=str)
    def fmt(self, key: str, args) -> str:  # noqa: ANN001
        """A string with `%1`-style placeholders filled."""
        values = args if isinstance(args, (list, tuple)) else [args]
        return fill(self._table.get(key, key), *values)
