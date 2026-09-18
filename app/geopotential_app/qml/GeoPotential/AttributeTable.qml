import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The rows behind a table layer, in a window of their own.
//
// It shows the **preview** the worker produced — bounded and decimated by
// ADR-MSP-004 — and it says so. It is not the file, and nothing computes from
// it: every number the project uses is read from the file itself.
Dialog {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    property string layerName: ""
    property var preview: ({})

    readonly property var columns: preview.columns || []
    readonly property var rows: preview.rows || []

    title: root.txt["layers.attributes"] + (layerName.length > 0
                                            ? " — " + layerName : "")
    modal: false
    width: 820
    height: 480
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.Close

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
        elide: Text.ElideMiddle
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingXs

        Label {
            visible: root.rows.length === 0
            text: root.txt["layers.attributes.empty"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontMd
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }

        RowLayout {
            visible: root.rows.length > 0
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Label {
                text: root.preview.source_rows !== undefined
                      ? root.txt["import.preview.rows"]
                            .replace("%1", root.preview.source_rows)
                            .replace("%2", root.rows.length)
                      : ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            Item { Layout.fillWidth: true }
            Label {
                visible: root.preview.truncated === true
                         || root.preview.decimated === true
                text: root.txt["import.preview.decimated"]
                color: Theme.warn
                font.pixelSize: Theme.fontSm
            }
        }

        // Header and rows scroll together horizontally, so a wide table stays
        // readable: a column heading that drifts off its column is worse than
        // no heading.
        Flickable {
            visible: root.rows.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: Math.max(width, root.columns.length * 130)
            contentHeight: header.height + body.contentHeight
            flickableDirection: Flickable.HorizontalAndVerticalFlick

            ColumnLayout {
                width: Math.max(root.width - 2 * Theme.spacingMd,
                                root.columns.length * 130)
                spacing: 0

                RowLayout {
                    id: header
                    Layout.fillWidth: true
                    spacing: 0
                    Repeater {
                        model: root.columns
                        delegate: Label {
                            required property string modelData
                            text: modelData
                            color: Theme.text
                            font.pixelSize: Theme.fontSm
                            font.bold: true
                            Layout.preferredWidth: 130
                            elide: Text.ElideRight
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.border
                }

                ListView {
                    id: body
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.height - 150
                    clip: true
                    model: root.rows
                    delegate: RowLayout {
                        required property var modelData
                        required property int index
                        spacing: 0
                        Repeater {
                            model: modelData
                            delegate: Label {
                                required property string modelData
                                text: modelData
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSm
                                font.family: Theme.fontMono
                                Layout.preferredWidth: 130
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }
    }
}
