"""What the person prefers, remembered between sessions. QtCore only.

A project is data. A theme, a coordinate format and which panels are open are
**not** data: they belong to the person, they follow them from project to
project, and putting them inside a `.gpot` would make two people opening the
same project fight over the layout — and would change a project's bytes when
nothing scientific changed.

So they live in `QSettings`, in the same file the language already uses, and
never inside a project. This object is the single place that knows that.

The system colour scheme is not read here: that needs QtGui, and this module is
on the QtCore-only side of the boundary. The entry point reads it and pushes it
in through `setSystemDark`, which also makes the behaviour testable without a
desktop that happens to be in the right mode.
"""
from __future__ import annotations

import os

from .utils.qtcore import Property, QObject, QSettings, Signal, Slot

#: The four the interface offers. `system` is a *choice to follow* the desktop,
#: not a palette: it resolves to `dark` or `light` at read time.
THEME_MODES = ("dark", "light", "highContrast", "system")
DEFAULT_THEME = "dark"

#: How a coordinate is written. Not a preference about the data — the CRS is
#: the data's — but about how it is read aloud.
COORDINATE_STYLES = ("native", "utm", "decimal", "dms")
DEFAULT_COORDINATE_STYLE = "native"

#: The map's ground. Black hides dark ramps, white hides pale ones, and which
#: is right depends on the layer and on the room.
CANVAS_GROUNDS = ("black", "charcoal", "grey", "white")
DEFAULT_GROUND = "black"

#: The panels whose open/closed state is remembered.
#: `rail` is the icon column on the far left. It is a panel like the others —
#: the person decides whether it is there, and the choice outlives the session.
PANELS = ("workflow", "layers", "inspector", "jobs", "rail")


class Preferences(QObject):
    """The person's settings, published as properties QML can bind to."""

    changed = Signal()

    ORGANISATION = "GeoPotential"
    APPLICATION = "GeoPotential Professional"

    #: A gate or a storyboard must not write the developer's own preferences.
    #: The same override the translator uses, so one environment variable
    #: redirects every preference this application has.
    OVERRIDE = "GEOPOTENTIAL_PREFERENCES"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        override = os.environ.get(self.OVERRIDE)
        self._settings = (
            QSettings(override, QSettings.IniFormat) if override
            else QSettings(self.ORGANISATION, self.APPLICATION)
        )
        self._system_dark = True
        self._theme = self._read("interface/theme", DEFAULT_THEME, THEME_MODES)
        self._coordinates = self._read(
            "interface/coordinates", DEFAULT_COORDINATE_STYLE, COORDINATE_STYLES)
        self._ground = self._read(
            "interface/canvasGround", DEFAULT_GROUND, CANVAS_GROUNDS)
        self._panels = {
            name: self._read_bool(f"interface/panel/{name}", True)
            for name in PANELS
        }

    # ---- reading --------------------------------------------------------

    def _read(self, key: str, default: str, allowed: tuple[str, ...]) -> str:
        """A stored value, or the default when it is absent or unknown.

        A settings file edited by hand, or written by an older build, must not
        put the interface into a state it has no palette for.
        """
        stored = str(self._settings.value(key, default))
        return stored if stored in allowed else default

    def _read_bool(self, key: str, default: bool) -> bool:
        stored = self._settings.value(key, default)
        if isinstance(stored, bool):
            return stored
        return str(stored).lower() in ("true", "1", "yes")

    def _write(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()

    # ---- theme ----------------------------------------------------------

    def _get_theme(self) -> str:
        return self._theme

    def _get_effective_theme(self) -> str:
        """The palette to paint with: `system` resolved to what it follows."""
        if self._theme != "system":
            return self._theme
        return "dark" if self._system_dark else "light"

    def _get_system_dark(self) -> bool:
        return self._system_dark

    themeMode = Property(str, _get_theme, notify=changed)
    effectiveTheme = Property(str, _get_effective_theme, notify=changed)
    systemDark = Property(bool, _get_system_dark, notify=changed)

    @Slot(str, result=bool)
    def setThemeMode(self, mode: str) -> bool:  # noqa: N802
        """Choose a theme. Returns False for a mode there is no palette for."""
        if mode not in THEME_MODES:
            return False
        if mode != self._theme:
            self._theme = mode
            self._write("interface/theme", mode)
            self.changed.emit()
        return True

    @Slot(bool)
    def setSystemDark(self, dark: bool) -> None:  # noqa: N802
        """What the desktop is currently set to, pushed in by the entry point.

        It only changes what is painted while the mode is `system`; the stored
        preference is untouched, because following the desktop *is* the
        preference.
        """
        if bool(dark) == self._system_dark:
            return
        self._system_dark = bool(dark)
        if self._theme == "system":
            self.changed.emit()

    # ---- coordinates and ground -----------------------------------------

    def _get_coordinates(self) -> str:
        return self._coordinates

    def _get_ground(self) -> str:
        return self._ground

    coordinateStyle = Property(str, _get_coordinates, notify=changed)
    canvasGround = Property(str, _get_ground, notify=changed)

    @Slot(str, result=bool)
    def setCoordinateStyle(self, style: str) -> bool:  # noqa: N802
        if style not in COORDINATE_STYLES:
            return False
        if style != self._coordinates:
            self._coordinates = style
            self._write("interface/coordinates", style)
            self.changed.emit()
        return True

    @Slot(str, result=bool)
    def setCanvasGround(self, ground: str) -> bool:  # noqa: N802
        if ground not in CANVAS_GROUNDS:
            return False
        if ground != self._ground:
            self._ground = ground
            self._write("interface/canvasGround", ground)
            self.changed.emit()
        return True

    # ---- panels ---------------------------------------------------------

    @Slot(str, result=bool)
    def panelVisible(self, name: str) -> bool:  # noqa: N802
        """Whether a panel was open when the application last closed."""
        return self._panels.get(name, True)

    @Slot(str, bool, result=bool)
    def setPanelVisible(self, name: str, visible: bool) -> bool:  # noqa: N802
        if name not in PANELS:
            return False
        if self._panels[name] != bool(visible):
            self._panels[name] = bool(visible)
            self._write(f"interface/panel/{name}", bool(visible))
            self.changed.emit()
        return True

    @Slot(result="QVariant")
    def panels(self) -> dict:
        """Every panel's remembered state, for the shell to apply on load."""
        return dict(self._panels)
