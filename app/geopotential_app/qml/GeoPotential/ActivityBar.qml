import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The rail down the far left: the flow, the two ways data enters, and what the
// window is showing. Every one of them one click from anywhere.
//
// It exists because the things a person reaches for most — load a file, build a
// grid, open the step the flow is on — were each two or three levels inside a
// menu. A rail is the shortest path to them that does not spend map area, and
// the map is the evidence (`docs/conventions/frontend.md`).
//
// **Nothing here decides anything.** The step states are the workflow model's,
// derived from the Project Store; the panel states are the preferences'. This
// file draws them and emits a token, exactly as the menu bar does — which is
// why a step blocked in the panel is blocked here, with the same reason, and
// the two can never disagree.
//
// The rail itself can be hidden (View › Rail), because a person who knows the
// menus should not have to keep a bar they do not use.
Rectangle {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    // Which panels are showing, so the toggles read the truth rather than
    // remembering their own copy.
    property bool workflowVisible: true
    property bool layersVisible: true
    property bool inspectorVisible: true
    property bool jobsVisible: true

    signal actionRequested(string token)
    signal stepRequested(string key, string action)

    implicitWidth: Theme.railWidth
    color: Theme.surface

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        width: 1
        color: Theme.border
    }

    // One icon per step key. The key is the model's, not a position: reordering
    // the flow must not silently reassign pictures.
    readonly property var stepIcons: ({
        "project": "workflow/project",
        "data": "workflow/data",
        "qc": "workflow/qc",
        "harmonize": "workflow/harmonize",
        "membership": "workflow/membership",
        "weights": "workflow/weights",
        "aggregate": "workflow/aggregate",
        "results": "workflow/results"
    })

    function stateColor(state) {
        switch (state) {
        case "done":      return Theme.ok
        case "running":   return Theme.accent
        case "attention": return Theme.warn
        case "available": return Theme.text
        default:          return Theme.textMuted
        }
    }

    component Divider: Rectangle {
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 20
        Layout.preferredHeight: 1
        Layout.topMargin: 3
        Layout.bottomMargin: 3
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Theme.spacingSm
        anchors.bottomMargin: Theme.spacingSm
        spacing: 2

        // ---- the flow ----------------------------------------------------
        Repeater {
            model: root.controller.workflow

            delegate: IconButton {
                required property string key
                required property int number
                required property string titleKey
                required property string purposeKey
                required property string stepState
                required property string reasonKey
                required property string stepAction

                Layout.alignment: Qt.AlignHCenter
                objectName: "rail_" + key
                iconName: root.stepIcons[key] || "workflow/data"
                label: number + ". " + (root.txt[titleKey] || titleKey)
                // The number, the name, what the step is for, and — when it
                // cannot run — why. The panel says the same thing in the same
                // words; this is the short way to the same fact.
                tip: {
                    var head = number + ". " + (root.txt[titleKey] || titleKey)
                    var body = root.txt[purposeKey] || ""
                    var why = stepState === "blocked"
                              ? "\n⚠ " + (root.txt[reasonKey] || reasonKey) : ""
                      return body.length > 0 ? head + "\n" + body + why : head + why
                }
                iconSize: 19
                side: 32
                // A blocked step still takes the click: it opens its reason,
                // exactly as it does in the panel. What it never does is open
                // a tool whose inputs are missing.
                active: root.controller.currentStep === key
                onClicked: root.stepRequested(key, stepAction)

                // The state is on the icon's colour, and repeated as a dot, so
                // "done" is not carried by hue alone.
                ThemedIcon {
                    visible: parent.stepState === "blocked"
                    anchors { right: parent.right; bottom: parent.bottom
                              rightMargin: 1; bottomMargin: 1 }
                    name: "app/blocked"
                    size: 9
                    color: Theme.textMuted
                }
                Rectangle {
                    visible: parent.stepState === "done"
                             || parent.stepState === "running"
                             || parent.stepState === "attention"
                    anchors { right: parent.right; bottom: parent.bottom
                              rightMargin: 3; bottomMargin: 3 }
                    width: 5; height: 5; radius: 2.5
                    color: root.stateColor(parent.stepState)
                }
            }
        }

        Divider {}

        // ---- how data gets in --------------------------------------------
        // The two the report asked for by name. Both are also in Arquivo and
        // in Processamento; this is the short way, not a second route.
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railImport"
            iconName: "app/import"
            label: root.txt["menu.file.import"]
            tip: root.txt["rail.import.tip"]
            iconSize: 19
            side: 32
            enabled: root.controller.projectName.length > 0
            onClicked: root.actionRequested("data.import")
        }
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railGridding"
            iconName: "app/gridding"
            label: root.txt["menu.file.gridding"]
            tip: root.txt["rail.gridding.tip"]
            iconSize: 19
            side: 32
            enabled: root.controller.projectName.length > 0
            onClicked: root.actionRequested("data.gridding")
        }

        Item { Layout.fillHeight: true }

        Divider {}

        // ---- what the window shows ---------------------------------------
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railPanelWorkflow"
            iconName: "app/panel-workflow"
            label: root.txt["menu.view.workflow"]
            tip: root.txt["rail.panel.workflow.tip"]
            iconSize: 18
            side: 30
            active: root.workflowVisible
            toggle: true
            onClicked: root.actionRequested("view.workflow")
        }
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railPanelLayers"
            iconName: "app/panel-layers"
            label: root.txt["menu.view.layers"]
            tip: root.txt["rail.panel.layers.tip"]
            iconSize: 18
            side: 30
            active: root.layersVisible
            toggle: true
            onClicked: root.actionRequested("view.layers")
        }
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railPanelInspector"
            iconName: "app/panel-inspector"
            label: root.txt["menu.view.inspector"]
            tip: root.txt["rail.panel.inspector.tip"]
            iconSize: 18
            side: 30
            active: root.inspectorVisible
            toggle: true
            onClicked: root.actionRequested("view.inspector")
        }
        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railPanelJobs"
            iconName: "app/panel-jobs"
            label: root.txt["menu.view.jobs"]
            tip: root.txt["rail.panel.jobs.tip"]
            iconSize: 18
            side: 30
            active: root.jobsVisible
            toggle: true
            onClicked: root.actionRequested("view.jobs")
        }

        Divider {}

        IconButton {
            Layout.alignment: Qt.AlignHCenter
            objectName: "railPreferences"
            iconName: "app/preferences"
            label: root.txt["menu.edit.preferences"]
            tip: root.txt["rail.preferences.tip"]
            iconSize: 18
            side: 30
            onClicked: root.actionRequested("edit.preferences")
        }
    }
}
