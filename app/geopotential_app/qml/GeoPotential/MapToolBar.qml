import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The map's own tools, in one compact column over the canvas.
//
// **The active tool is visible**, and it is the canvas's mode, not a copy of
// it: `active` reads `canvas.toolMode`, so a mode changed anywhere shows here
// and the two can never disagree.
//
// The groups are meaning, not decoration: navigate; what a click reads or
// draws; what the view does; what leaves the application.
//
// The buttons were text glyphs, guarded by a test that rendered each one and
// failed if the font lacked it. They are SVG now, which is the change the
// icons README anticipated, and that test became the stronger one: every
// `icon:` has to name a file that exists.
Rectangle {
    id: root
    required property var canvas
    required property var txt

    signal layersRequested()
    signal fullScreenRequested()
    signal exportRequested()

    implicitWidth: 34
    implicitHeight: column.implicitHeight + 2 * Theme.spacingXs
    radius: Theme.radius
    color: Theme.surface
    border.color: Theme.border
    opacity: 0.96

    component Tool: IconButton {
        side: 28
        iconSize: 17
    }

    component Divider: Rectangle {
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 18
        Layout.preferredHeight: 1
        color: Theme.border
    }

    ColumnLayout {
        id: column
        anchors.centerIn: parent
        spacing: 2

        Tool {
            iconName: "tools/navigate"
            label: root.txt["tool.navigate"]
            tip: root.txt["tool.navigate"] + " — " + root.txt["tool.navigate.tip"]
            active: root.canvas.toolMode === "navigate"
            onClicked: root.canvas.toolMode = "navigate"
        }
        Tool {
            iconName: "tools/layers"
            label: root.txt["tool.layers"]
            tip: root.txt["tool.layers"]
            onClicked: root.layersRequested()
        }

        Divider {}

        Tool {
            iconName: "tools/identify"
            label: root.txt["tool.identify"]
            tip: root.txt["tool.identify"] + " — " + root.txt["tool.identify.tip"]
            enabled: root.canvas.hasLayer
            active: root.canvas.toolMode === "identify"
            onClicked: root.canvas.toolMode = "identify"
        }
        Tool {
            iconName: "tools/aoi"
            label: root.txt["tool.aoi"]
            tip: root.txt["tool.aoi"] + " — " + root.txt["tool.aoi.tip"]
            enabled: root.canvas.hasLayer
            active: root.canvas.toolMode === "aoi"
            onClicked: root.canvas.toolMode = "aoi"
        }
        Tool {
            iconName: "tools/measure-distance"
            label: root.txt["tool.measureDistance"]
            tip: root.txt["tool.measureDistance"] + " — " + root.txt["tool.measure.tip"]
            enabled: root.canvas.hasLayer
            active: root.canvas.toolMode === "measure-distance"
            onClicked: root.canvas.toolMode = "measure-distance"
        }
        Tool {
            iconName: "tools/measure-area"
            label: root.txt["tool.measureArea"]
            tip: root.txt["tool.measureArea"] + " — " + root.txt["tool.measure.tip"]
            enabled: root.canvas.hasLayer
            active: root.canvas.toolMode === "measure-area"
            onClicked: root.canvas.toolMode = "measure-area"
        }

        Divider {}

        Tool {
            iconName: "tools/zoom-in"
            label: root.txt["tool.zoomIn"]
            tip: root.txt["tool.zoomIn"]
            enabled: root.canvas.hasLayer
            onClicked: root.canvas.zoomBy(0.8)
        }
        Tool {
            iconName: "tools/zoom-out"
            label: root.txt["tool.zoomOut"]
            tip: root.txt["tool.zoomOut"]
            enabled: root.canvas.hasLayer
            onClicked: root.canvas.zoomBy(1.25)
        }
        Tool {
            iconName: "tools/zoom-fit"
            label: root.txt["tool.zoomFull"]
            tip: root.txt["tool.zoomFull"]
            enabled: root.canvas.hasLayer
            onClicked: root.canvas.zoomToFit()
        }
        Tool {
            iconName: "tools/fullscreen"
            label: root.txt["tool.fullScreen"]
            tip: root.txt["tool.fullScreen"]
            onClicked: root.fullScreenRequested()
        }

        Divider {}

        Tool {
            iconName: "tools/export"
            label: root.txt["tool.exportMap"]
            tip: root.txt["tool.exportMap"]
            enabled: root.canvas.hasLayer
            onClicked: root.exportRequested()
        }
    }
}
