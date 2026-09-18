import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The eight steps of the geospatial flow, down the left side.
//
// Every state shown here is derived by `viewmodels/workflow_model.py` from
// what the Project Store holds. This panel writes nothing and decides nothing:
// it draws the model and reports a click.
//
// The model publishes **catalogue keys**, never sentences; `txt` turns a key
// into the language the person chose. A literal typed here would be right in
// one language and wrong in the other.
//
// A blocked step is disabled **with its reason visible**, never enabled into a
// modal warning after the click.
Rectangle {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    // The step whose detail is expanded — **none, until someone asks**.
    //
    // It used to follow the flow's position, so one step was always open and
    // the panel was a column of paragraphs: state, purpose, reason, needs,
    // produces, leads to, for a step nobody had asked about. The eight rows
    // are now eight rows, the explanation is on the hover, and the facts are
    // one click away for the step being read.
    property string openKey: ""

    // One icon per step key, the same map the rail uses. By key and not by
    // position: reordering the flow must not reassign pictures.
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

    signal stepActivated(string key, string action)

    color: Theme.surface

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        width: 1
        color: Theme.border
    }

    function stateColor(state) {
        switch (state) {
        case "done":      return Theme.ok
        case "running":   return Theme.accent
        case "attention": return Theme.warn
        case "available": return Theme.text
        default:          return Theme.textMuted
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingXs

        Label {
            text: root.txt["workflow.caption"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.letterSpacing: 1
            Layout.bottomMargin: Theme.spacingXs
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2
            model: root.controller.workflow

            delegate: ItemDelegate {
                id: step
                required property string key
                required property int number
                required property string titleKey
                required property string purposeKey
                required property string stepState
                required property string reasonKey
                required property var inputs
                required property var outputs
                required property var nexts
                required property string stepAction

                readonly property bool blocked: stepState === "blocked"
                readonly property bool expanded: root.openKey === key
                readonly property bool current: root.controller.currentStep === key

                width: list.width
                implicitHeight: body.implicitHeight + Theme.spacingSm
                // A blocked step still takes a click: the click opens its
                // reason. What it never does is open the tool.
                onClicked: {
                    root.openKey = key
                    if (!blocked)
                        root.stepActivated(key, stepAction)
                }

                background: Rectangle {
                    color: step.current || step.hovered ? Theme.surfaceAlt : "transparent"
                    radius: Theme.radius

                    Rectangle {
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                        width: 2
                        radius: 1
                        visible: step.current
                        color: Theme.accent
                    }
                }

                contentItem: ColumnLayout {
                    id: body
                    spacing: Theme.spacingXs

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSm

                        // The number, in a ring that carries the state's
                        // colour. A filled ring is a finished step.
                        Rectangle {
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20
                            radius: 10
                            color: step.stepState === "done"
                                   ? root.stateColor(step.stepState) : "transparent"
                            border.color: root.stateColor(step.stepState)
                            border.width: 1

                            Label {
                                anchors.centerIn: parent
                                text: step.number
                                color: step.stepState === "done"
                                       ? Theme.background : root.stateColor(step.stepState)
                                font.pixelSize: Theme.fontSm
                                font.bold: step.current
                            }
                        }

                        ThemedIcon {
                            name: root.stepIcons[step.key] || "workflow/data"
                            size: 15
                            color: step.blocked ? Theme.textMuted
                                 : root.stateColor(step.stepState)
                        }

                        Label {
                            text: root.txt[step.titleKey]
                            color: step.blocked ? Theme.textMuted : Theme.text
                            font.pixelSize: Theme.fontMd
                            font.bold: step.current
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        // "Not yet", drawn rather than spelled with an emoji
                        // the font may not have. The reason is on the hover
                        // and, once opened, on the row.
                        ThemedIcon {
                            visible: step.blocked
                            name: "app/blocked"
                            size: 12
                            color: Theme.textMuted
                        }
                        Label {
                            visible: !step.blocked
                                     && (step.stepState === "running"
                                         || step.stepState === "attention")
                            text: step.stepState === "running" ? "▶" : "!"
                            color: root.stateColor(step.stepState)
                            font.pixelSize: Theme.fontSm
                        }
                    }

                    // ---- the detail, for the step being read --------------
                    ColumnLayout {
                        visible: step.expanded
                        Layout.fillWidth: true
                        Layout.leftMargin: 28
                        spacing: Theme.spacingXs

                        Label {
                            text: root.txt["workflow.state." + step.stepState]
                            color: root.stateColor(step.stepState)
                            font.pixelSize: Theme.fontSm
                        }
                        Label {
                            text: root.txt[step.purposeKey]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            visible: step.reasonKey.length > 0
                            text: step.reasonKey.length > 0 ? root.txt[step.reasonKey] : ""
                            color: step.blocked ? Theme.textMuted : Theme.warn
                            font.pixelSize: Theme.fontSm
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        component Facts: ColumnLayout {
                            property string caption: ""
                            property var items: []
                            visible: items.length > 0
                            Layout.fillWidth: true
                            spacing: 0
                            Label {
                                text: parent.caption
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSm
                                font.letterSpacing: 1
                            }
                            Repeater {
                                model: parent.items
                                delegate: Label {
                                    required property string modelData
                                    text: "· " + root.txt[modelData]
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSm
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        Facts { caption: root.txt["workflow.needs"];    items: step.inputs }
                        Facts { caption: root.txt["workflow.produces"]; items: step.outputs }
                        Facts { caption: root.txt["workflow.leadsTo"];  items: step.nexts }
                    }
                }

                // The row is a line; this is where the paragraph went. Name,
                // what the step is for, what state it is in, and — when it
                // cannot run — what is missing.
                ToolTip.text: {
                    var head = step.number + ". " + (root.txt[step.titleKey] || "")
                    var purpose = root.txt[step.purposeKey] || ""
                    var state = root.txt["workflow.state." + step.stepState] || ""
                    var why = (step.reasonKey.length > 0)
                              ? "\n⚠ " + (root.txt[step.reasonKey] || "") : ""
                    return head + "\n" + purpose + "\n· " + state + why
                }
                ToolTip.visible: hovered
                ToolTip.delay: 400
            }
        }
    }
}
