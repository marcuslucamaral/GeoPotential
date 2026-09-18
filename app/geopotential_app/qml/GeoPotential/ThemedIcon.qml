import QtQuick
import GeoPotential

// One icon, in the colour the theme is painting with.
//
// The file on disk is black; `icons.py` renders and tints it. That is the
// whole reason this wrapper exists: every icon site would otherwise repeat the
// URL construction, and one of them would forget the colour and ship a black
// icon into the dark theme.
//
// The colour is part of the request, so a theme change re-requests rather than
// re-filters — which is also why nothing here uses a shader effect. See
// `icons.py` for the measurement that ruled those out.
Image {
    id: root

    // "tools/identify", "workflow/qc", "app/run" — folder and name, no suffix.
    required property string name
    property color color: Theme.text
    property int size: 18

    // The `#` is dropped rather than percent-encoded: `urllib` is not
    // importable in the app outside the tile client, and the provider should
    // not need it to read a colour.
    source: "image://icon/" + name
            + "?color=" + String(root.color).replace("#", "")
    // Rendered at the device's pixel size, so the icon is not a scaled bitmap
    // on a high-density screen.
    sourceSize: Qt.size(root.size * Screen.devicePixelRatio,
                        root.size * Screen.devicePixelRatio)
    width: root.size
    height: root.size
    fillMode: Image.PreserveAspectFit
    smooth: true
    // Nothing here animates: an icon that fades on every theme change reads as
    // a redraw glitch, and P-123 requires a theme change to only repaint.
    cache: true
}
