import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 8, bottom panel: jobs, progress, stage, warnings, validations, logs.
//
// The progress shown is the fraction the worker computed from work actually
// done. Nothing here animates a bar on a timer.
//
// **Every outcome belongs to its own job.** The panel used to carry one global
// status line, written by whatever happened last, which is how `job failed`
// came to sit beside a job that had succeeded.
Rectangle {
    id: root
    required property var controller
    property string selectedJobId: ""
    // Collapsed, the panel is a title bar: the jobs are still there, and the
    // map gets the height back.
    property bool collapsed: false
    property bool activeOnly: false

    readonly property var txt: controller.tr.strings
    readonly property var detail: selectedJobId.length > 0
                                 ? controller.jobs.detail(selectedJobId) : ({})

    signal openArtifactRequested(string path)

    color: Theme.surface

    Rectangle {
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 1
        color: Theme.border
    }

    function stateColour(state) {
        switch (state) {
        case "Succeeded":   return Theme.ok
        case "Failed":      return Theme.error
        case "Interrupted": return Theme.error
        case "Cancelled":   return Theme.warn
        case "Warning":     return Theme.warn
        case "Queued":      return Theme.textMuted
        default:            return Theme.accent
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingXs

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ToolButton {
                text: root.collapsed ? "▲" : "▼"
                implicitHeight: 20
                onClicked: root.collapsed = !root.collapsed
                ToolTip.text: root.collapsed ? root.txt["jobs.expand"]
                                             : root.txt["jobs.collapse"]
                ToolTip.visible: hovered
                ToolTip.delay: 400
            }
            Label {
                text: root.txt["jobs.caption"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1

                // What the panel is for. It was not obvious, and a list of
                // technical operator names explains itself to nobody.
                HoverHandler { id: captionHover }
                ToolTip.text: root.txt["jobs.what"]
                ToolTip.visible: captionHover.hovered
                ToolTip.delay: 300
            }
            TabBar {
                id: filter
                Layout.preferredHeight: 22
                currentIndex: root.activeOnly ? 0 : 1
                onCurrentIndexChanged: root.activeOnly = currentIndex === 0
                TabButton {
                    text: root.txt["jobs.filter.active"]
                    font.pixelSize: Theme.fontSm
                    implicitHeight: 22
                }
                TabButton {
                    text: root.txt["jobs.filter.all"]
                    font.pixelSize: Theme.fontSm
                    implicitHeight: 22
                }
            }
            Item { Layout.fillWidth: true }
            // The project's own line. It says what the *project* is doing and
            // never what a job did.
            Label {
                text: root.controller.status
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                elide: Text.ElideLeft
                Layout.maximumWidth: 320
            }
        }

        RowLayout {
            visible: !root.collapsed
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spacingSm

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: root.controller.jobs
                spacing: 2

                Label {
                    anchors.centerIn: parent
                    visible: list.count === 0
                    text: root.txt["jobs.empty"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontMd
                }

                delegate: ItemDelegate {
                    id: delegate
                    required property string jobId
                    required property string operator
                    required property string state
                    required property string stage
                    required property real fraction
                    required property string message
                    required property string errorCode
                    required property int artifactCount
                    required property real elapsed
                    required property bool isActive

                    visible: !root.activeOnly || isActive
                    height: visible ? implicitHeight : 0
                    width: list.width
                    implicitHeight: 34
                    onClicked: root.selectedJobId = jobId
                    highlighted: root.selectedJobId === jobId

                    contentItem: RowLayout {
                        spacing: Theme.spacingSm

                        Rectangle {
                            Layout.preferredWidth: 6
                            Layout.preferredHeight: 6
                            radius: 3
                            color: root.stateColour(delegate.state)
                        }

                        // The friendly name is what a person recognises; the
                        // technical name is what a bug report needs. Both.
                        ColumnLayout {
                            spacing: 0
                            Layout.preferredWidth: 210
                            Label {
                                text: root.txt["operator." + delegate.operator]
                                      || delegate.operator
                                color: Theme.text
                                font.pixelSize: Theme.fontMd
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Label {
                                text: delegate.operator
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSm
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }

                        Label {
                            text: root.txt["jobs.state." + delegate.state]
                                  || delegate.state
                            color: root.stateColour(delegate.state)
                            font.pixelSize: Theme.fontSm
                            Layout.preferredWidth: 80
                        }

                        ProgressBar {
                            value: delegate.fraction
                            Layout.preferredWidth: 140
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Label {
                            text: delegate.stage
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            Layout.preferredWidth: 90
                            elide: Text.ElideRight
                        }

                        Label {
                            text: delegate.message
                            color: delegate.errorCode.length > 0 ? Theme.error
                                                                 : Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        Label {
                            visible: delegate.elapsed > 0
                            text: delegate.elapsed.toFixed(1) + " s"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                        }
                        Label {
                            visible: delegate.artifactCount > 0
                            text: root.txt["jobs.artifactCount"].replace(
                                      "%1", delegate.artifactCount)
                            color: Theme.ok
                            font.pixelSize: Theme.fontSm
                        }
                    }
                }
            }

            // ---- the selected job, in full --------------------------------
            Rectangle {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                color: Theme.surfaceAlt
                radius: Theme.radius

                Label {
                    anchors.centerIn: parent
                    visible: root.selectedJobId.length === 0
                    text: root.txt["jobs.selectOne"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                    width: parent.width - 2 * Theme.spacingMd
                    horizontalAlignment: Text.AlignHCenter
                }

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    clip: true
                    visible: root.selectedJobId.length > 0

                    ColumnLayout {
                        width: 300 - 2 * Theme.spacingSm
                        spacing: 2

                        Label {
                            text: (root.txt["operator." + (root.detail.operator || "")]
                                   || root.detail.operator || "")
                            color: Theme.text
                            font.pixelSize: Theme.fontMd
                            font.bold: true
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Label {
                            text: (root.txt["jobs.state." + (root.detail.state || "")]
                                   || root.detail.state || "")
                                  + (root.detail.stage ? " · " + root.detail.stage : "")
                            color: root.stateColour(root.detail.state || "")
                            font.pixelSize: Theme.fontSm
                        }
                        Label {
                            visible: (root.detail.message || "").length > 0
                            text: root.detail.message || ""
                            color: root.detail.errorCode ? Theme.error : Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        component Section: ColumnLayout {
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
                                Layout.topMargin: Theme.spacingXs
                            }
                            Repeater {
                                model: parent.items
                                delegate: Label {
                                    required property var modelData
                                    text: "· " + (modelData.path !== undefined
                                                  ? modelData.path : modelData)
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSm
                                    font.family: Theme.fontMono
                                    elide: Text.ElideMiddle
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        Section {
                            caption: root.txt["jobs.inputs"]
                            items: root.detail.inputs || []
                        }
                        Section {
                            caption: root.txt["jobs.artifacts"]
                            items: root.detail.artifacts || []
                        }

                        Label {
                            visible: (root.detail.elapsed || 0) > 0
                            text: root.txt["jobs.elapsed"] + ": "
                                  + (root.detail.elapsed || 0).toFixed(2) + " s"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            Layout.topMargin: Theme.spacingXs
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: Theme.spacingSm
                            spacing: Theme.spacingXs

                            Button {
                                text: root.txt["jobs.cancel"]
                                enabled: root.detail.active === true
                                font.pixelSize: Theme.fontSm
                                onClicked: root.controller.cancel(root.selectedJobId)
                            }
                            Button {
                                text: root.txt["jobs.retry"]
                                enabled: root.detail.active === false
                                font.pixelSize: Theme.fontSm
                                onClicked: root.controller.retry(root.selectedJobId)
                                ToolTip.text: root.txt["jobs.retry.tip"]
                                ToolTip.visible: hovered
                                ToolTip.delay: 400
                            }
                            Button {
                                text: root.txt["jobs.openResult"]
                                enabled: (root.detail.artifacts || []).length > 0
                                font.pixelSize: Theme.fontSm
                                onClicked: root.openArtifactRequested(
                                    root.detail.artifacts[0].path)
                            }
                        }

                        // Why a button here does nothing. A ToolTip never
                        // fires on a disabled control, so the reason has to
                        // be text: three greyed buttons and no explanation
                        // read as an interface that is broken.
                        Label {
                            Layout.fillWidth: true
                            Layout.topMargin: 2
                            visible: text.length > 0
                            text: {
                                var lines = []
                                if (root.detail.active === false)
                                    lines.push(root.txt["jobs.why.cancel"])
                                if ((root.detail.artifacts || []).length === 0
                                        && root.detail.active === false)
                                    lines.push(root.txt["jobs.why.noResult"])
                                return lines.join(" ")
                            }
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }
}
