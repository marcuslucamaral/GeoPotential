import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 8, top bar. Two things at once, and they are separated on purpose:
//
//   **what is loaded** — the project, its CRS, how many layers. Facts, read
//   from the controller, drawn as chips so they scan without being read.
//   **what can be done to it** — undo, redo, run, cancel, compare. Icons, each
//   with the word on its hover.
//
// The words did not disappear when the buttons became icons: `tip` is required
// by `IconButton`, and the gate fails a button that leaves it empty. What
// changed is that the row now fits the facts as well as the actions.
//
// An action whose preconditions are not met is disabled with the reason in its
// tooltip, never enabled into a modal warning after the click.
Rectangle {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    // What the map is drawing in. Passed in rather than read from the active
    // layer: the layer row carries a CRS only when one was declared with it,
    // and the canvas is the authority the status bar already trusts.
    property string viewCrs: ""

    signal runRequested()
    signal cancelRequested()
    signal projectsRequested()
    signal splitRequested()
    signal aoiRequested()
    signal decisionRequested()
    signal themeToggleRequested()

    implicitHeight: Theme.topBarHeight
    color: Theme.surface

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 1
        color: Theme.border
    }

    // A fact about what is loaded: a quiet caption and the value beside it.
    // Reads at a glance and never competes with the actions for attention.
    component Chip: Rectangle {
        property string caption: ""
        property string value: ""
        visible: value.length > 0
        Layout.preferredWidth: chipRow.implicitWidth + 2 * Theme.spacingSm
        Layout.preferredHeight: 22
        radius: Theme.radius
        color: Theme.surfaceAlt
        border.color: Theme.border

        RowLayout {
            id: chipRow
            anchors.centerIn: parent
            spacing: 5
            Label {
                text: parent.parent.caption
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            Label {
                text: parent.parent.value
                color: Theme.text
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingMd
        anchors.rightMargin: Theme.spacingMd
        spacing: Theme.spacingSm

        Label {
            text: "GeoPotential"
            color: Theme.text
            font.pixelSize: Theme.fontLg
            font.bold: true
        }
        Label {
            text: root.txt["top.subtitle"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            Layout.leftMargin: -2
        }

        Rectangle { width: 1; Layout.preferredHeight: 18; color: Theme.border }

        IconButton {
            objectName: "topProjects"
            iconName: "app/projects"
            label: root.txt["top.projects"]
            tip: root.txt["top.projects.tip"]
            onClicked: root.projectsRequested()
        }

        Rectangle { width: 1; Layout.preferredHeight: 18; color: Theme.border }

        // Undo reverts project state, never science. A committed run is
        // immutable, so the stack stops at one and the tooltip says so rather
        // than the button silently refusing.
        IconButton {
            objectName: "topUndo"
            iconName: "app/undo"
            label: root.txt["top.undo"]
            tip: root.controller.undoText
            enabled: root.controller.canUndo
            onClicked: root.controller.undo()
        }
        IconButton {
            objectName: "topRedo"
            iconName: "app/redo"
            label: root.txt["top.redo"]
            tip: root.controller.redoText
            enabled: root.controller.canRedo
            onClicked: root.controller.redo()
        }

        Rectangle { width: 1; Layout.preferredHeight: 18; color: Theme.border }

        IconButton {
            objectName: "topRun"
            iconName: "app/run"
            label: root.txt["top.run"]
            tip: enabled
                 ? root.txt["top.run.tip"]
                 : root.txt["top.run.blocked"].replace("%1", root.controller.workerState)
            enabled: root.controller.workerState === "ready"
            onClicked: root.runRequested()
        }
        IconButton {
            objectName: "topCancel"
            iconName: "app/cancel"
            label: root.txt["top.cancel"]
            tip: root.txt["top.cancel.tip"]
            danger: true
            enabled: root.controller.workerState === "ready"
            onClicked: root.cancelRequested()
        }
        IconButton {
            objectName: "topCompare"
            iconName: "app/compare"
            label: root.txt["top.compare"]
            tip: root.txt["top.compare.tip"]
            onClicked: root.splitRequested()
        }

        Rectangle {
            width: 1
            Layout.preferredHeight: 18
            color: Theme.border
            visible: root.controller.projectName.length > 0
        }

        // ---- what is loaded ----------------------------------------------
        Label {
            text: root.controller.projectName
            visible: text.length > 0
            color: Theme.text
            font.pixelSize: Theme.fontMd
            elide: Text.ElideRight
            Layout.maximumWidth: 220
        }
        Chip {
            caption: root.txt["top.chip.crs"]
            value: root.viewCrs
        }
        Chip {
            caption: root.txt["top.chip.layers"]
            value: root.controller.layers.count > 0
                   ? String(root.controller.layers.count) : ""
        }

        Item { Layout.fillWidth: true }

        // ---- what the application is doing -------------------------------
        Rectangle {
            Layout.preferredWidth: workerLabel.implicitWidth + 2 * Theme.spacingSm
            Layout.preferredHeight: 20
            radius: Theme.radius
            color: Theme.surfaceAlt
            border.color: root.controller.workerState === "ready" ? Theme.ok
                        : root.controller.workerState === "crashed" ? Theme.error
                        : Theme.border

            Label {
                id: workerLabel
                anchors.centerIn: parent
                text: root.txt["top.worker"].replace("%1", root.controller.workerState)
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
        }

        Button {
            text: root.txt["top.worker.restart"]
            visible: root.controller.workerState === "crashed"
            onClicked: root.controller.restartWorker()
        }

        IconButton {
            objectName: "topTheme"
            iconName: "app/theme"
            label: root.txt["menu.view.theme"]
            tip: root.txt["top.theme.tip"]
            onClicked: root.themeToggleRequested()
        }
    }
}
