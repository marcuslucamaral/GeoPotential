import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import GeoPotential

// Section 9.1 — the Project Hub: create, open, recover, duplicate, relink,
// list recents.
//
// Carried from M2 and M3 and delivered here, because M4 is where the shell's
// surfaces get built and a project chooser without a workspace to open into
// would have been built twice.
//
// "Recover" is not a separate action: every open runs the recovery pass, and
// what it found is reported. A button that only sometimes recovers would let
// someone open a damaged project without it.
Dialog {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    title: root.txt["hub.title"]
    modal: true
    width: 720
    height: 520
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton

    property string selectedPath: ""

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
        radius: Theme.radius
    }
    header: Label {
        text: root.title
        color: Theme.text
        font.pixelSize: Theme.fontLg
        font.bold: true
        padding: Theme.spacingMd
    }

    FolderDialog {
        id: openPicker
        title: root.txt["hub.pickOpen"]
        onAccepted: {
            var path = selectedFolder.toString().replace("file://", "")
            if (root.controller.openProject(path)) {
                root.selectedPath = path
                root.close()
            }
        }
    }

    FolderDialog {
        id: createPicker
        title: root.txt["hub.pickCreate"]
        onAccepted: {
            // It fills the field; creating stays one explicit click away, so
            // the two paths cannot disagree about where the project went.
            folderField.text = selectedFolder.toString().replace("file://", "")
        }
    }

    FolderDialog {
        id: duplicatePicker
        title: root.txt["hub.pickCopy"]
        onAccepted: {
            var parent = selectedFolder.toString().replace("file://", "")
            root.controller.duplicateProject(parent + "/"
                + root.controller.projectName + " copy.gpot")
        }
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingMd

        // ---- current project ------------------------------------------
        GroupBox {
            title: root.txt["hub.open"]
            Layout.fillWidth: true
            background: Rectangle {
                color: Theme.surfaceAlt
                border.color: Theme.border
                radius: Theme.radius
            }
            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.spacingXs

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: root.controller.projectName.length > 0
                              ? root.controller.projectName
                              : root.txt["hub.noProject"]
                        color: Theme.text
                        font.pixelSize: Theme.fontMd
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: root.txt["hub.duplicate"]
                        enabled: root.controller.projectName.length > 0
                        onClicked: duplicatePicker.open()
                        ToolTip.text: root.txt["hub.duplicate.tip"]
                        ToolTip.visible: hovered
                        ToolTip.delay: 400
                    }
                }
                Label {
                    text: root.controller.projectPath
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                    Layout.fillWidth: true
                    elide: Text.ElideMiddle
                }
                Label {
                    visible: root.controller.needsAttention
                    text: root.controller.recoverySummary
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }

        // ---- recents ---------------------------------------------------
        Label {
            text: root.txt["hub.recent"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.letterSpacing: 1
        }

        ListView {
            id: recents
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.controller.recentProjects
            spacing: 2

            Label {
                anchors.centerIn: parent
                visible: recents.count === 0
                text: root.txt["hub.noRecent"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontMd
            }

            delegate: ItemDelegate {
                required property var modelData
                width: recents.width
                implicitHeight: 40
                enabled: modelData.exists
                // One click. It used to take two, and the second one is not
                // discoverable: the row looked like a dead list.
                onClicked: {
                    if (root.controller.openProject(modelData.path))
                        root.close()
                }
                ToolTip.text: modelData.exists ? root.txt["hub.clickToOpen"]
                                               : root.txt["hub.missing"]
                ToolTip.visible: hovered
                ToolTip.delay: 400

                contentItem: RowLayout {
                    spacing: Theme.spacingSm
                    ColumnLayout {
                        spacing: 0
                        Layout.fillWidth: true
                        Label {
                            text: modelData.name
                            color: modelData.exists ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.fontMd
                        }
                        Label {
                            text: modelData.exists
                                  ? modelData.path
                                  : modelData.path + "  " + root.txt["hub.missing"]
                            color: modelData.exists ? Theme.textMuted : Theme.error
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                        }
                    }
                    Label {
                        text: modelData.opened_at
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                }
            }
        }

        // ---- create ------------------------------------------------------
        //
        // The folder is a field, not a dialog. The system folder chooser opens
        // *behind* this modal on at least one desktop, so a Create button that
        // needed it did nothing at all. The picker is still here, as the
        // second way; the first way is typing.
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            Label {
                text: root.txt["hub.where"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            TextField {
                id: folderField
                Layout.fillWidth: true
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
                text: root.controller.defaultProjectFolder()
                ToolTip.text: root.txt["hub.where.tip"]
                ToolTip.visible: hovered
                ToolTip.delay: 400
            }
            Button {
                text: root.txt["hub.browse"]
                font.pixelSize: Theme.fontSm
                onClicked: createPicker.open()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            TextField {
                id: nameField
                placeholderText: root.txt["hub.newName"]
                Layout.preferredWidth: 220
                font.pixelSize: Theme.fontSm
                onAccepted: createButton.clicked()
            }
            Button {
                id: createButton
                text: root.txt["hub.create"]
                enabled: nameField.text.length > 0 && folderField.text.length > 0
                onClicked: {
                    if (root.controller.createProject(
                            folderField.text + "/" + nameField.text + ".gpot",
                            nameField.text))
                        root.close()
                }
            }
            Item { Layout.fillWidth: true }
            Button {
                text: root.txt["hub.close"]
                onClicked: root.close()
            }
        }

        // ---- open by path --------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            TextField {
                id: openField
                Layout.fillWidth: true
                placeholderText: root.txt["hub.openPath"]
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
                onAccepted: openButton.clicked()
            }
            Button {
                id: openButton
                text: root.txt["hub.openHere"]
                enabled: openField.text.length > 0
                onClicked: {
                    if (root.controller.openProject(openField.text))
                        root.close()
                }
            }
            Button {
                text: root.txt["hub.openDots"]
                onClicked: openPicker.open()
                ToolTip.text: root.txt["hub.recovery.tip"]
                ToolTip.visible: hovered
                ToolTip.delay: 400
            }
        }
    }
}
