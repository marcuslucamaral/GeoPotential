"""Two languages, one catalogue, and no string typed straight into the screen.

The two failures this suite exists to catch:

1. a key used in QML that the catalogue does not answer — it shows on screen as
   the key itself, and only in the language nobody tested;
2. a literal typed into a `.qml` file — it is right in one language and wrong
   in the other, for ever, and no test of the catalogue would ever see it.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from geopotential_app.i18n import LANGUAGES, fill, table  # noqa: E402
from geopotential_app.i18n.catalog import CATALOG  # noqa: E402

QML_DIR = (Path(__file__).resolve().parents[2]
           / "app" / "geopotential_app" / "qml")

# `txt["some.key"]` and `strings["some.key"]`, however the file spells the
# handle it put the catalogue behind.
USED = re.compile(r'(?:txt|strings)\[\s*"([a-zA-Z0-9._]+)"\s*\]')

# Screens still carrying their own literals. It is empty, and it stays empty:
# a screen added with a literal in it fails here, which is the point.
UNTRANSLATED: set[str] = set()

# Text that is not language: a symbol, a unit, a CRS, a glyph on a button.
NOT_A_SENTENCE = re.compile(
    r'^[\s\W\d]*$'                       # punctuation, arrows, digits only
    r'|^(CRS|AOI|AHP|WLC|IDW|QA/QC|EPSG:\d+|PNG|JSON|GeoTIFF|COG|CSV|XYZ)'
    r'|^v?\d'                            # a version, a number
    r'|^%\d'                             # a placeholder
    # The product's own name is the same in every language, and so is a key
    # sequence: `Ctrl+N` is what is printed on the keyboard.
    r'|^GeoPotential'
    r'|^(Ctrl|Alt|Shift|Meta|F\d)'
    r'|^v$'
)


def qml_files() -> list[Path]:
    return sorted(QML_DIR.rglob("*.qml"))


class TheCatalogue(unittest.TestCase):
    def test_every_key_has_both_languages(self) -> None:
        for key, values in CATALOG.items():
            self.assertEqual(len(values), len(LANGUAGES), f"{key} is malformed")
            for language, text in zip(LANGUAGES, values):
                self.assertTrue(str(text).strip(),
                                f"{key} has no {language} text")

    def test_a_placeholder_survives_translation(self) -> None:
        """A `%1` dropped in one language is a sentence missing its number."""
        for key, (pt, en) in CATALOG.items():
            self.assertEqual(
                sorted(re.findall(r"%\d", pt)),
                sorted(re.findall(r"%\d", en)),
                f"{key} has different placeholders in the two languages",
            )

    def test_every_language_resolves_the_whole_catalogue(self) -> None:
        for language in LANGUAGES:
            entries = table(language)
            self.assertEqual(set(entries), set(CATALOG))

    def test_filling_replaces_in_order(self) -> None:
        self.assertEqual(fill("%1 of %2", 3, 8), "3 of 8")
        self.assertEqual(fill("no placeholder", 1), "no placeholder")


class TheScreens(unittest.TestCase):
    def test_every_key_the_interface_asks_for_exists(self) -> None:
        missing: list[str] = []
        for path in qml_files():
            for key in USED.findall(path.read_text(encoding="utf-8")):
                if key not in CATALOG:
                    missing.append(f"{path.name}: {key}")
        self.assertEqual(missing, [], "keys used on screen with no translation")

    def test_a_translated_screen_carries_no_literal_text(self) -> None:
        """Any `text:`/`title:`/`ToolTip.text:` with a bare string, on a screen
        that has been translated, is a string that cannot be translated."""
        offenders: list[str] = []
        pattern = re.compile(
            r'(?:^|\s)(?:text|title|ToolTip\.text|placeholderText)\s*:\s*"([^"]*)"')
        for path in qml_files():
            if path.name in UNTRANSLATED:
                continue
            for literal in pattern.findall(path.read_text(encoding="utf-8")):
                if literal.strip() and not NOT_A_SENTENCE.match(literal.strip()):
                    offenders.append(f"{path.name}: {literal!r}")
        self.assertEqual(offenders, [], "literal text on a translated screen")

    def test_the_untranslated_list_names_only_files_that_exist(self) -> None:
        """A list of exceptions that outlives the files is a list nobody
        trusts. Renaming a screen has to fail here."""
        present = {path.name for path in qml_files()}
        self.assertEqual(UNTRANSLATED - present, set())


if __name__ == "__main__":
    unittest.main()
