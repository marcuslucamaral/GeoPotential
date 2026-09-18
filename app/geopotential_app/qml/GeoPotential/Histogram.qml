import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The histogram of §9.3, drawn from the counts the worker computed.
//
// Drawn here rather than fetched as an image: the same 32 bins feed the
// Membership Editor at M5, where the curve has to sit on top of the
// distribution it is shaping. An image could not carry that.
//
// A log count axis, because a raster's histogram is almost always dominated by
// one mode: on a linear axis every other bin is a flat line, and the tails —
// which are what a membership's anchors sit in — become invisible.
Item {
    id: root
    // No controller here; the caller hands the strings in, the same way
    // the canvas overlay is handed them.
    property var txt: ({})

    property var counts: []
    property var edges: []
    property string unit: ""
    property color barColor: Theme.accent

    readonly property real maxCount: {
        var m = 0
        for (var i = 0; i < counts.length; ++i) m = Math.max(m, counts[i])
        return m
    }
    readonly property bool ready: counts.length > 0 && edges.length === counts.length + 1

    implicitHeight: 96

    Label {
        anchors.centerIn: parent
        visible: !root.ready
        text: root.txt["histogram.empty"] || ""
        color: Theme.textMuted
        font.pixelSize: Theme.fontSm
    }

    Row {
        id: bars
        visible: root.ready
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: parent.height - 16
        spacing: 1

        Repeater {
            model: root.counts
            delegate: Rectangle {
                required property int index
                required property var modelData

                width: Math.max(1, (bars.width - root.counts.length) / root.counts.length)
                // log1p keeps an empty bin at zero height while stopping the
                // modal bin from flattening everything else.
                height: root.maxCount > 0
                        ? Math.max(modelData > 0 ? 1 : 0,
                                   bars.height * Math.log(1 + modelData)
                                   / Math.log(1 + root.maxCount))
                        : 0
                anchors.bottom: parent.bottom
                color: root.barColor
                opacity: 0.85
            }
        }
    }

    RowLayout {
        visible: root.ready
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        Label {
            text: root.edges.length ? Number(root.edges[0]).toPrecision(4) : ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
        Item { Layout.fillWidth: true }
        Label {
            text: root.unit
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
        Item { Layout.fillWidth: true }
        Label {
            text: root.edges.length
                  ? Number(root.edges[root.edges.length - 1]).toPrecision(4) : ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }
}
