"""The four themes, and the two promises they make.

P-123 — a theme change only repaints: no metric token depends on the mode, so
        nothing can move. Checked here by reading `Theme.qml`; checked again
        by the `themes` storyboard, which compares captures.
A36   — high contrast reaches a **declared** ratio, measured rather than
        estimated. The number is WCAG AAA for body text, 7:1, and it is fixed
        here before anything is measured against it.

Preferences are checked in the same suite because a theme nobody can keep is
not a theme: the mode, the coordinate format, the map's ground and the panel
layout belong to the person and are stored outside every project.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

THEME_QML = ROOT / "app" / "geopotential_app" / "qml" / "GeoPotential" / "Theme.qml"

#: WCAG AAA for body text. Declared here, before any measurement, and not
#: adjusted afterwards: a tolerance moved to fit a result measures nothing.
AAA = 7.0
#: WCAG AA, which the ordinary dark and light palettes are held to.
AA = 4.5

MODES = ("dark", "light", "highContrast")


def _channel(value: int) -> float:
    """One sRGB channel, linearised. WCAG 2.1, relative luminance."""
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    """Relative luminance of `#rrggbb`."""
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return (0.2126 * _channel(r) + 0.7152 * _channel(g)
            + 0.0722 * _channel(b))


def contrast(first: str, second: str) -> float:
    """The WCAG contrast ratio between two colours, 1:1 to 21:1."""
    a, b = luminance(first), luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def palette(mode: str) -> dict[str, str]:
    """The colour tokens of one mode, read out of `Theme.qml`.

    Read from the file rather than restated here: a palette copied into a test
    is a second palette, and the day they disagree the test passes.
    """
    source = THEME_QML.read_text(encoding="utf-8")
    # `readonly property color name: contrast ? "#a" : dark ? "#b" : "#c"`
    pattern = re.compile(
        r"readonly property color (\w+):\s*"
        r'contrast \? "(#[0-9a-fA-F]{6})"\s*'
        r': dark \? "(#[0-9a-fA-F]{6})"\s*'
        r': "(#[0-9a-fA-F]{6})"',
        re.MULTILINE,
    )
    column = {"highContrast": 0, "dark": 1, "light": 2}[mode]
    found = {m.group(1): m.group(2 + column) for m in pattern.finditer(source)}
    if not found:
        raise AssertionError(
            "no colour tokens parsed from Theme.qml; the shape of the palette "
            "changed and this test is now measuring nothing")
    return found


class ThemeTokens(unittest.TestCase):
    """P-123, at its source: geometry cannot depend on the palette."""

    #: Every token that decides a position or a size.
    METRIC = ("spacingXs", "spacingSm", "spacingMd", "spacingLg", "radius",
              "controlHeight", "navigatorWidth", "workflowWidth",
              "inspectorWidth", "bottomPanelHeight", "topBarHeight",
              "statusBarHeight", "fontSm", "fontMd", "fontLg")

    def setUp(self) -> None:
        self.source = THEME_QML.read_text(encoding="utf-8")

    def test_every_metric_token_exists(self) -> None:
        for token in self.METRIC:
            with self.subTest(token=token):
                self.assertRegex(self.source, rf"property \w+ {token}:")

    def test_no_metric_token_depends_on_the_mode(self) -> None:
        """A theme that changes a spacing is a theme that moves the interface,
        and someone who turned on high contrast to read the screen should not
        have to find it again."""
        for token in self.METRIC:
            match = re.search(rf"property \w+ {token}:(.*)", self.source)
            self.assertIsNotNone(match, token)
            expression = match.group(1)
            for forbidden in ("mode", "dark", "contrast"):
                self.assertNotIn(
                    forbidden, expression,
                    f"the metric token {token} reads {forbidden!r}: "
                    f"{expression.strip()}")

    def test_the_three_palettes_define_the_same_tokens(self) -> None:
        first = set(palette("dark"))
        for mode in MODES:
            self.assertEqual(set(palette(mode)), first,
                             f"the {mode} palette defines a different set")

    def test_the_ramps_do_not_change_with_the_theme(self) -> None:
        """A colour ramp belongs to the data, not to the room. A ramp that
        changed with the theme would make two screenshots of one map
        incomparable."""
        ramps = self.source.split("readonly property var ramps:", 1)[1]
        ramps = ramps.split("function ramp", 1)[0]
        for forbidden in ("contrast ?", "dark ?", "mode ="):
            self.assertNotIn(forbidden, ramps)


class Contrast(unittest.TestCase):
    """A36 — measured, not estimated."""

    #: Which token is read against which ground. Text and borders only: an
    #: accent used as a fill is not text and is not held to a text ratio.
    PAIRS = (("text", "background"), ("text", "surface"),
             ("text", "surfaceAlt"), ("textMuted", "background"),
             ("textMuted", "surface"), ("textMuted", "surfaceAlt"),
             ("border", "background"), ("border", "surface"),
             ("accent", "background"), ("ok", "background"),
             ("warn", "background"), ("error", "background"))

    def test_the_ratio_formula_agrees_with_the_known_extremes(self) -> None:
        """White on black is 21:1 and a colour on itself is 1:1. Without this,
        a broken formula would report every palette as compliant."""
        self.assertAlmostEqual(contrast("#ffffff", "#000000"), 21.0, places=2)
        self.assertAlmostEqual(contrast("#4ea3ff", "#4ea3ff"), 1.0, places=6)

    def test_high_contrast_reaches_the_declared_ratio(self) -> None:
        colours = palette("highContrast")
        for token, ground in self.PAIRS:
            with self.subTest(token=token, ground=ground):
                ratio = contrast(colours[token], colours[ground])
                self.assertGreaterEqual(
                    ratio, AAA,
                    f"high contrast: {token} on {ground} is {ratio:.2f}:1, "
                    f"below the declared {AAA}:1")

    def test_the_ordinary_themes_reach_AA_for_text(self) -> None:  # noqa: N802
        for mode in ("dark", "light"):
            colours = palette(mode)
            for token, ground in (("text", "background"), ("text", "surface"),
                                  ("text", "surfaceAlt"),
                                  ("textMuted", "background"),
                                  ("textMuted", "surface")):
                with self.subTest(mode=mode, token=token, ground=ground):
                    ratio = contrast(colours[token], colours[ground])
                    self.assertGreaterEqual(
                        ratio, AA,
                        f"{mode}: {token} on {ground} is {ratio:.2f}:1")

    def test_high_contrast_is_not_merely_the_dark_theme(self) -> None:
        """It is a third palette. If it were the dark one it would already
        have failed the ratio above, but saying so here names the intent."""
        self.assertNotEqual(palette("highContrast"), palette("dark"))


class PreferencesAreTheirOwn(unittest.TestCase):
    """The mode, the format, the ground and the layout outlive the project."""

    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(prefix="geopotential-prefs-"))
        self.ini = self.workdir / "prefs.ini"
        os.environ["GEOPOTENTIAL_PREFERENCES"] = str(self.ini)

    def _fresh(self):
        """A Preferences reading the same file, as a new session would."""
        from geopotential_app.preferences import Preferences
        return Preferences()

    def test_the_default_is_dark(self) -> None:
        self.assertEqual(self._fresh().themeMode, "dark")

    def test_a_chosen_theme_survives_the_session(self) -> None:
        first = self._fresh()
        self.assertTrue(first.setThemeMode("highContrast"))
        self.assertEqual(self._fresh().themeMode, "highContrast")

    def test_an_unknown_mode_is_refused(self) -> None:
        prefs = self._fresh()
        self.assertFalse(prefs.setThemeMode("neon"))
        self.assertEqual(prefs.themeMode, "dark")

    def test_a_settings_file_naming_an_unknown_mode_falls_back(self) -> None:
        """A file edited by hand, or written by a later build, must not put
        the interface into a state it has no palette for."""
        self.ini.write_text("[interface]\ntheme=neon\n", encoding="utf-8")
        self.assertEqual(self._fresh().themeMode, "dark")

    def test_system_resolves_to_what_the_desktop_says(self) -> None:
        prefs = self._fresh()
        prefs.setThemeMode("system")
        prefs.setSystemDark(True)
        self.assertEqual(prefs.effectiveTheme, "dark")
        prefs.setSystemDark(False)
        self.assertEqual(prefs.effectiveTheme, "light")

    def test_the_desktop_does_not_override_an_explicit_choice(self) -> None:
        """Choosing `light` on a dark desktop means light."""
        prefs = self._fresh()
        prefs.setThemeMode("light")
        prefs.setSystemDark(True)
        self.assertEqual(prefs.effectiveTheme, "light")

    def test_the_coordinate_format_and_ground_persist(self) -> None:
        prefs = self._fresh()
        prefs.setCoordinateStyle("dms")
        prefs.setCanvasGround("white")
        later = self._fresh()
        self.assertEqual(later.coordinateStyle, "dms")
        self.assertEqual(later.canvasGround, "white")

    def test_a_closed_panel_stays_closed(self) -> None:
        prefs = self._fresh()
        self.assertTrue(prefs.panelVisible("jobs"))
        prefs.setPanelVisible("jobs", False)
        self.assertFalse(self._fresh().panelVisible("jobs"))

    def test_an_unknown_panel_is_refused(self) -> None:
        self.assertFalse(self._fresh().setPanelVisible("nowhere", False))

    def test_nothing_is_written_into_a_project(self) -> None:
        """The whole point: preferences go to the settings file, and the file
        is the one the environment names."""
        prefs = self._fresh()
        prefs.setThemeMode("light")
        self.assertTrue(self.ini.exists(),
                        "the preference went somewhere else")
        self.assertIn("theme", self.ini.read_text(encoding="utf-8"))

    def test_preferences_import_no_gui_module(self) -> None:
        """QtCore only. The module says why in prose, so the check reads the
        **imports** and not the text: a rule spelled out in a docstring must
        not make the docstring fail the rule."""
        import ast

        source = (ROOT / "app" / "geopotential_app"
                  / "preferences.py").read_text(encoding="utf-8")
        imported: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        for name in imported:
            # `utils.qtcore` is the allowed shim and `utils.qt` is the full
            # one, so this compares the module's tail rather than searching
            # for a substring that is a prefix of the legitimate name.
            tail = name.rsplit(".", 1)[-1]
            self.assertNotIn(
                tail, ("QtGui", "QtQuick", "QtQml", "qt"),
                f"preferences.py imports {name}, which is not QtCore")


class TheCatalogueHasNoDuplicates(unittest.TestCase):
    """A key written twice silently keeps the last value.

    Python builds the dictionary without complaining, so the first entry — and
    whatever it said — disappears with nothing to show for it.
    """

    def test_every_key_appears_once(self) -> None:
        source = (ROOT / "app" / "geopotential_app" / "i18n"
                  / "catalog.py").read_text(encoding="utf-8")
        keys = re.findall(r'^\s{4}"([^"]+)":', source, re.MULTILINE)
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(duplicates, [], f"duplicate keys: {duplicates}")


if __name__ == "__main__":
    unittest.main()
