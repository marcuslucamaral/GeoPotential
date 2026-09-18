import QtQuick
import QtQuick.Controls
import GeoPotential

// A button that is an icon, and says what it is when the pointer rests on it.
//
// **An icon without a tooltip is a rebus.** This component makes the tooltip
// impossible to forget: `tip` is required, and `tests/unit/test_icons.py`
// fails the gate on any use that leaves it empty. That is the whole contract
// of replacing words with pictures — the word does not disappear, it moves to
// the hover.
//
// `label` is the same text a menu would use. It is kept even where nothing
// draws it, because it is what the audit reads and what a screen reader would
// announce; a control identified only by a file path is not identified.
ToolButton {
    id: root

    required property string iconName
    required property string tip
    property string label: ""
    // Whether this is the mode or panel currently in force. Distinct from
    // `checked`, which Controls also uses for its own toggling.
    property bool active: false
    // How loudly `active` is drawn. A *selection* — the current tool, the step
    // the flow is on — is one of a set and gets the filled accent. A *toggle*
    // — a panel that is open — is one of several independent switches, and
    // four filled accents side by side stop reading as state and start reading
    // as decoration. A toggle gets the quiet treatment instead.
    property bool toggle: false
    // A destructive or interrupting action — cancel, remove. It is not red
    // until hovered: a toolbar of red icons stops meaning anything.
    property bool danger: false
    property int iconSize: 18
    property int side: 30

    implicitWidth: side
    implicitHeight: side
    hoverEnabled: true
    Accessible.name: label.length > 0 ? label : tip
    Accessible.description: tip

    background: Rectangle {
        radius: Theme.radius
        color: root.active && !root.toggle ? Theme.accent
             : root.active || (root.hovered && root.enabled) ? Theme.surfaceAlt
             : "transparent"
        border.width: (root.active && !root.toggle) ? 0 : 1
        border.color: root.active && root.toggle ? Theme.border
                    : root.hovered && root.enabled ? Theme.border
                    : "transparent"
    }

    contentItem: Item {
        ThemedIcon {
            anchors.centerIn: parent
            name: root.iconName
            size: root.iconSize
            color: !root.enabled ? Theme.textMuted
                 : root.active && !root.toggle ? Theme.background
                 : root.active ? Theme.accent
                 : root.danger && root.hovered ? Theme.error
                 : Theme.text
        }
    }

    // The delay is short enough to answer a deliberate hover and long enough
    // that crossing the bar does not trail tooltips behind the pointer.
    ToolTip.text: tip
    ToolTip.visible: hovered && tip.length > 0
    ToolTip.delay: 350
}
