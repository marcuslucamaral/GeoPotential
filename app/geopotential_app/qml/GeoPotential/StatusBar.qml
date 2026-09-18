import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 8, status bar: CRS, scale, coordinate, value under cursor, memory,
// graphics backend.
//
// The CRS is shown wherever a coordinate is shown. A coordinate without its
// CRS is a pair of numbers.
Rectangle {
    id: root
    required property var controller
    property string crsName: ""
    property string coordinate: ""
    // What the coordinate above is expressed in. It is not always the layer's
    // CRS: a readout in degrees is in WGS 84 whatever the layer is.
    property string crsLabel: ""
    // What the basemap is, when one is on. The "offline" claim has to stop
    // being made the moment the application starts fetching tiles.
    property string basemap: ""
    property string valueUnderCursor: ""
    // The active map tool, named. A mode nobody can see is a mode nobody
    // knows they are in.
    property string toolLabel: ""

    readonly property var txt: controller.tr.strings

    implicitHeight: Theme.statusBarHeight
    color: Theme.surfaceAlt

    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 1
        color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingMd
        anchors.rightMargin: Theme.spacingMd
        spacing: Theme.spacingLg

        Label {
            text: root.crsName.length > 0
                  ? "CRS " + root.crsName : root.txt["status.noLayer"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
        Label {
            visible: root.coordinate.length > 0
            text: root.coordinate + "  ("
                  + (root.crsLabel.length > 0 ? root.crsLabel : root.crsName) + ")"
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
        Label {
            visible: root.valueUnderCursor.length > 0
            text: root.valueUnderCursor
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }

        Item { Layout.fillWidth: true }

        Label {
            visible: root.toolLabel.length > 0
            text: root.txt["status.mode"] + ": " + root.toolLabel
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }

        Label {
            text: root.basemap.length > 0
                  ? root.txt["status.online"].replace("%1", root.basemap)
                  : root.txt["status.offline"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
        Label {
            text: "v" + root.controller.appVersion
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
    }
}
