import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// What one point on the map says, layer by layer.
//
// A person clicks a place to compare what the layers report there — that is
// the whole reason a stack exists — so this shows **every visible layer**, not
// just the active one. Each value was read from that layer's own source at
// full resolution and in its own CRS; the number on screen is a number that is
// in the dataset, never an average of the tile that was drawn.
//
// A layer that holds samples rather than a field reports no value: asking what
// a point cloud "is" at a coordinate it does not occupy has no answer, and a
// blank is the honest one.
Rectangle {
    id: root

    property var txt: ({})
    property var readings: []
    property string coordinate: ""
    property string crsLabel: ""

    readonly property bool hasReadings: readings.length > 0

    visible: hasReadings
    color: Theme.surface
    border.color: Theme.border
    radius: Theme.radius
    implicitWidth: 300
    implicitHeight: body.implicitHeight + 2 * Theme.spacingSm

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingXs

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: root.txt["identify.title"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                Layout.fillWidth: true
            }
            ToolButton {
                objectName: "identifyClose"
                text: "×"
                implicitWidth: 22
                implicitHeight: 22
                onClicked: root.readings = []
            }
        }

        // The place, with the CRS it is written in. A pair of numbers without
        // one is not a location.
        Label {
            Layout.fillWidth: true
            text: root.coordinate + (root.crsLabel.length > 0
                                     ? "   " + root.crsLabel : "")
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
            elide: Text.ElideRight
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

        Repeater {
            model: root.readings
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 0

                Label {
                    Layout.fillWidth: true
                    text: modelData.name
                    color: Theme.text
                    font.pixelSize: Theme.fontSm
                    font.bold: true
                    elide: Text.ElideRight
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    Label {
                        text: {
                            if (modelData.kind !== "raster")
                                return root.txt["identify.notAField"] || ""
                            if (modelData.value === null
                                    || modelData.value === undefined)
                                return modelData.onGrid
                                       ? (root.txt["identify.noData"] || "")
                                       : (root.txt["identify.outside"] || "")
                            return Number(modelData.value).toPrecision(6)
                                   + (modelData.unit ? " " + modelData.unit : "")
                        }
                        color: (modelData.kind === "raster"
                                && modelData.value !== null
                                && modelData.value !== undefined)
                               ? Theme.accent : Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    // Which cell the value came from. It is what turns "the
                    // value here" into something a person can find again in
                    // the file itself.
                    Label {
                        visible: modelData.row !== null
                                 && modelData.row !== undefined
                        text: (root.txt["identify.cell"] || "")
                                  .replace("%1", modelData.column)
                                  .replace("%2", modelData.row)
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                    }
                }
            }
        }
    }
}
