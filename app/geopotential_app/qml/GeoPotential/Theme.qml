pragma Singleton
import QtQuick

// Design tokens. Every colour, spacing, radius, control height and font size
// in the shell resolves through here. Nothing outside this file names a colour.
//
// **A theme change may only repaint.** No metric token below depends on the
// mode — not one — so switching palettes cannot move anything by a pixel. That
// is not a promise in a comment: `--only theme` compares the four palettes
// token by token, and the storyboard compares captures.
QtObject {
    id: theme

    // dark | light | highContrast. `system` is resolved before it gets here:
    // it is a choice to follow the desktop, not a fourth palette.
    property string mode: "dark"

    readonly property bool dark: mode !== "light"
    readonly property bool contrast: mode === "highContrast"

    // ---- colour ----------------------------------------------------------
    //
    // High contrast is a third palette, not the dark one turned up. Its text
    // and its borders sit at or above **7:1** against the surface they are
    // drawn on — WCAG AAA for body text — and `--only theme` measures every
    // pair rather than trusting the numbers here.
    readonly property color background:
        contrast ? "#000000" : dark ? "#0f1115" : "#f6f7f9"
    readonly property color surface:
        contrast ? "#000000" : dark ? "#171a21" : "#ffffff"
    readonly property color surfaceAlt:
        contrast ? "#101010" : dark ? "#1e222b" : "#eef0f4"
    readonly property color border:
        contrast ? "#ffffff" : dark ? "#2a2f3a" : "#d3d7e0"
    readonly property color text:
        contrast ? "#ffffff" : dark ? "#e6e9ef" : "#141721"
    readonly property color textMuted:
        contrast ? "#e8e8e8" : dark ? "#98a0b3" : "#5b6377"
    readonly property color accent:
        contrast ? "#63d8ff" : dark ? "#4ea3ff" : "#0b6bcb"
    readonly property color ok:
        contrast ? "#5cf7a5" : dark ? "#3ecf8e" : "#127a52"
    readonly property color warn:
        contrast ? "#ffd95c" : dark ? "#e0b341" : "#8a6300"
    readonly property color error:
        contrast ? "#ff9d94" : dark ? "#f0776a" : "#b3261e"

    // The map's own ground. Black hides dark points and dark ramps; white
    // hides pale ones. It is a choice the person makes, and it is remembered.
    property string canvasGround: "black"
    readonly property var canvasGrounds: ({
        "black": "#000000",
        "charcoal": "#14161b",
        "grey": "#6e7480",
        "white": "#ffffff"
    })
    readonly property color canvas: canvasGrounds[canvasGround] || "#000000"

    // ---- metric — identical in every mode --------------------------------
    //
    // Nothing below may branch on `mode`, `dark` or `contrast`. A theme that
    // changes a spacing is a theme that moves the interface, and a person who
    // turns on high contrast to read the screen should not have to find it
    // again.
    readonly property int spacingXs: 4
    readonly property int spacingSm: 8
    readonly property int spacingMd: 12
    readonly property int spacingLg: 20
    readonly property int radius: 4
    readonly property int controlHeight: 28
    // The icon rail on the far left. Wide enough for a 32 px button with a
    // margin either side, and narrow enough that hiding it gains little —
    // which is the point: it costs almost no map area.
    readonly property int railWidth: 44
    readonly property int navigatorWidth: 210
    readonly property int workflowWidth: 240
    readonly property int inspectorWidth: 280
    readonly property int bottomPanelHeight: 170
    readonly property int topBarHeight: 40
    readonly property int statusBarHeight: 26

    readonly property int fontSm: 11
    readonly property int fontMd: 12
    readonly property int fontLg: 14
    readonly property string fontMono: "monospace"

    // ---- colour ramps, for the legend only -------------------------------
    //
    // The map's pixels are coloured in `render/colormap.py`; these are the
    // same control points, so the bar shows the ramp the map used. A legend
    // drawn from a different ramp is a legend that lies.
    //
    // They do not change with the theme: a ramp is the data's, not the room's.
    readonly property var ramps: ({
        "viridis": ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
        "magma":   ["#000004", "#51127c", "#b73779", "#fc8961", "#fcfdbf"],
        "plasma":  ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
        "inferno": ["#000004", "#57106e", "#bc3754", "#f98e09", "#fcffa4"],
        "cividis": ["#00204c", "#3d4c6b", "#7c7b78", "#bcaf6f", "#ffe945"],
        "turbo":   ["#30123b", "#4686fb", "#1be5b5", "#a4fc3c", "#7a0403"],
        "grey":    ["#000000", "#404040", "#808080", "#bfbfbf", "#ffffff"],
        "rdbu":    ["#053061", "#4393c3", "#f7f7f7", "#d6604d", "#67001f"]
    })

    function ramp(name, position) {
        var stops = ramps[name] || ramps["viridis"]
        var scaled = Math.max(0, Math.min(1, position)) * (stops.length - 1)
        var low = Math.floor(scaled)
        var high = Math.min(stops.length - 1, low + 1)
        return Qt.tint(stops[low],
                       Qt.rgba(Qt.color(stops[high]).r, Qt.color(stops[high]).g,
                               Qt.color(stops[high]).b, scaled - low))
    }
}
