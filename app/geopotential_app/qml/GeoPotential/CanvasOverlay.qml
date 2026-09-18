import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// What sits on top of the map: legend, scale bar, level-of-detail readout and
// the navigation controls.
//
// Every one of these states something the map cannot state by itself. The
// colour bar without its unit is decoration; the scale bar without its number
// is a line; and the LOD badge is what stops someone reading a decimated view
// as the data.
Item {
    id: root
    required property var canvas
    required property var txt

    signal aoiFinished()
    signal aoiCancelled()

    // ---- legend ---------------------------------------------------------
    //
    // The bar shows the **active layer's** ramp and its limits. It used to be
    // a fixed viridis gradient drawn twice, so it stayed the same while the
    // layer under it changed — a legend that does not follow its layer is
    // worse than none, because it is read as true.
    Rectangle {
        visible: root.canvas.hasLayer
        anchors { right: parent.right; bottom: parent.bottom; margins: Theme.spacingMd }
        width: 196
        height: 58
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.border

        readonly property var limits: root.canvas.displayLimits

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 2

            // Ten stops sampled from the layer's own ramp: the bar is the
            // colours the map is actually painted with.
            Row {
                Layout.alignment: Qt.AlignHCenter
                spacing: 0
                Repeater {
                    model: 40
                    delegate: Rectangle {
                        required property int index
                        width: 4
                        height: 10
                        color: Theme.ramp(root.canvas.colormapName, index / 39.0)
                    }
                }
            }
            RowLayout {
                Layout.preferredWidth: 160
                Label {
                    text: parent.parent.parent.limits.length === 2
                          ? Number(parent.parent.parent.limits[0]).toFixed(2) : ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: parent.parent.parent.limits.length === 2
                          ? Number(parent.parent.parent.limits[1]).toFixed(2) : ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                }
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: root.canvas.unit
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
        }
    }

    // ---- basemap attribution ---------------------------------------------
    //
    // ODbL and CC-BY both oblige it, and a map shown or printed without it
    // breaks the terms the tiles came under. It is not decoration and it is
    // not optional: when a basemap is on, this is on.
    Rectangle {
        visible: root.canvas.basemapAttribution.length > 0
        anchors { right: parent.right; top: parent.top; margins: Theme.spacingMd }
        width: attribution.implicitWidth + 2 * Theme.spacingSm
        height: 18
        radius: 2
        color: Theme.surface
        opacity: 0.9

        Label {
            id: attribution
            anchors.centerIn: parent
            text: root.canvas.basemapAttribution
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
    }

    // ---- scale bar ------------------------------------------------------
    // A bar with no number is a line. The number is a round distance in the
    // CRS's own unit, so it can be read against the coordinate readout.
    Item {
        visible: root.canvas.hasLayer && root.canvas.scalePixels > 8
        anchors { left: parent.left; bottom: parent.bottom; margins: Theme.spacingMd }
        width: Math.max(40, root.canvas.scalePixels)
        height: 26

        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 3
            color: Theme.text
        }
        Rectangle {
            anchors { left: parent.left; bottom: parent.bottom }
            width: 2; height: 9
            color: Theme.text
        }
        Rectangle {
            anchors { right: parent.right; bottom: parent.bottom }
            width: 2; height: 9
            color: Theme.text
        }
        Label {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 5 }
            text: root.canvas.scaleText
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }

    // ---- level of detail -------------------------------------------------
    // Named on screen because the alternative is someone measuring a feature
    // on a 32:1 view and believing the number. The readout under the cursor
    // is always full-resolution; this says what the *picture* is.
    Rectangle {
        visible: root.canvas.hasLayer && root.canvas.lodFactor > 1
        anchors { left: parent.left; top: parent.top; margins: Theme.spacingMd }
        width: lodLabel.implicitWidth + 2 * Theme.spacingSm
        height: 20
        radius: Theme.radius
        color: Theme.surfaceAlt
        border.color: Theme.border

        Label {
            id: lodLabel
            anchors.centerIn: parent
            text: root.txt["canvas.lod"].replace("%1", root.canvas.lodFactor)
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
    }

    // ---- split-view label ------------------------------------------------
    Row {
        visible: root.canvas.splitView
        anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: Theme.spacingMd }
        spacing: Theme.spacingLg

        Label {
            text: root.canvas.layerName
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
        Label {
            text: "│"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
        }
        Label {
            text: root.canvas.compareName
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }
    // ---- what the AOI tool is doing --------------------------------------
    //
    // The defect this replaces: a polygon drawn once stayed on the map for the
    // rest of the session, with nothing on screen saying what it was. Now the
    // mode says so, the vertex count says how far along it is, and finishing,
    // undoing and cancelling are all reachable while it happens.
    Rectangle {
        visible: root.canvas.toolMode === "aoi"
        anchors { horizontalCenter: parent.horizontalCenter; top: parent.top
                  topMargin: Theme.spacingMd }
        width: aoiRow.implicitWidth + 2 * Theme.spacingMd
        height: 34
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.warn

        RowLayout {
            id: aoiRow
            anchors.centerIn: parent
            spacing: Theme.spacingSm

            Rectangle {
                width: 8; height: 8; radius: 4
                color: Theme.warn
            }
            Label {
                text: root.txt["aoi.drawing"]
                color: Theme.text
                font.pixelSize: Theme.fontSm
                font.bold: true
            }
            Label {
                text: root.txt["aoi.vertices"].replace(
                          "%1", root.canvas.aoiPointCount)
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
            }
            Label {
                visible: root.canvas.aoiPointCount < 3
                text: root.txt["aoi.needMore"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ToolButton {
                text: root.txt["aoi.undo"]
                enabled: root.canvas.aoiPointCount > 0
                font.pixelSize: Theme.fontSm
                onClicked: root.canvas.undoAoiVertex()
            }
            ToolButton {
                text: root.txt["aoi.cancel"]
                font.pixelSize: Theme.fontSm
                onClicked: root.aoiCancelled()
            }
            Button {
                text: root.txt["aoi.finish"]
                enabled: root.canvas.aoiPointCount >= 3
                font.pixelSize: Theme.fontSm
                onClicked: root.aoiFinished()
            }
        }
    }

    // ---- what a measurement says -----------------------------------------
    Rectangle {
        visible: root.canvas.measurement.length > 0
        anchors { horizontalCenter: parent.horizontalCenter; top: parent.top
                  topMargin: Theme.spacingMd }
        width: measureLabel.implicitWidth + 2 * Theme.spacingMd
        height: 28
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.accent

        Label {
            id: measureLabel
            anchors.centerIn: parent
            text: root.canvas.measurement
            color: Theme.text
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }
}
