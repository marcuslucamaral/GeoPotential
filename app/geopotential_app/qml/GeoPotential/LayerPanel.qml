import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The layers open in the project, in the order they are drawn.
//
// Everything here is a display decision (ADR-MSP-002): visibility, order,
// opacity, colormap, style limits, which layer is active. None of it enters a
// manifest, none of it changes a value, and removing a layer removes it from
// the **view** and from nowhere else.
Rectangle {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings
    readonly property var stack: controller.layers

    signal zoomToRequested(string layerId)

    color: Theme.surface

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
        width: 1
        color: Theme.border
    }

    signal attributesRequested(string layerId)
    signal detailsRequested(string layerId)

    Menu {
        id: layerMenu
        property string layerId: ""
        MenuItem {
            text: root.txt["layers.zoomTo"]
            onTriggered: root.zoomToRequested(layerMenu.layerId)
        }
        MenuItem {
            text: root.txt["layers.attributes"]
            onTriggered: root.attributesRequested(layerMenu.layerId)
        }
        MenuItem {
            text: root.txt["layers.details"]
            onTriggered: root.detailsRequested(layerMenu.layerId)
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["layers.remove"]
            onTriggered: root.stack.remove(layerMenu.layerId)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingXs

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: root.txt["layers.caption"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1
            }
            Item { Layout.fillWidth: true }
            Label {
                text: root.stack.count
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
            }
        }

        Label {
            visible: root.stack.count === 0
            text: root.txt["layers.empty"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            // Room for the active layer's own controls: with less, the row
            // that names it is the first thing clipped, and a panel that hides
            // the name of the layer it is showing is worse than no panel.
            Layout.minimumHeight: 130
            clip: true
            spacing: 2
            // Top of the panel is the top of the draw order, which is the end
            // of the model: a person reads a layer list from the top down.
            verticalLayoutDirection: ListView.BottomToTop
            model: root.stack

            delegate: ItemDelegate {
                id: entry
                required property string layerId
                required property string name
                required property string layerRole
                required property bool layerVisible
                required property real layerOpacity
                required property string colormap
                required property bool isActive
                required property string unit

                width: list.width
                implicitHeight: column.implicitHeight + Theme.spacingSm
                onClicked: root.stack.setActive(layerId)

                // Right-click, where a layer list is expected to have one.
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: {
                        root.stack.setActive(entry.layerId)
                        layerMenu.layerId = entry.layerId
                        layerMenu.popup()
                    }
                }

                background: Rectangle {
                    color: entry.isActive || entry.hovered ? Theme.surfaceAlt
                                                           : "transparent"
                    radius: Theme.radius
                    Rectangle {
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                        width: 2
                        radius: 1
                        visible: entry.isActive
                        color: Theme.accent
                    }
                }

                contentItem: ColumnLayout {
                    id: column
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingXs

                        CheckBox {
                            checked: entry.layerVisible
                            onToggled: root.stack.setVisible(entry.layerId, checked)
                            implicitWidth: 22
                            implicitHeight: 22
                            ToolTip.text: root.txt["layers.visible"]
                            ToolTip.visible: hovered
                            ToolTip.delay: 400
                        }
                        Label {
                            text: entry.name
                            color: entry.layerVisible ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.fontMd
                            font.bold: entry.isActive
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                        }
                        Label {
                            text: root.txt["layers.role." + entry.layerRole]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        spacing: Theme.spacingXs
                        // A basemap is never the active layer — the Inspector
                        // and the identify tool read the active one, and a
                        // basemap has nothing to give them. Its own controls
                        // are still here.
                        visible: entry.isActive || entry.layerRole === "basemap"

                        Label {
                            text: root.txt["layers.opacity"]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                        }
                        Slider {
                            id: opacitySlider
                            from: 0.0; to: 1.0
                            value: entry.layerOpacity
                            Layout.fillWidth: true
                            implicitHeight: 20
                            onMoved: root.stack.setOpacity(entry.layerId, value)
                        }
                        Label {
                            text: Math.round(opacitySlider.value * 100) + " %"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                            Layout.preferredWidth: 34
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 24
                        spacing: Theme.spacingXs
                        visible: entry.isActive || entry.layerRole === "basemap"

                        component Action: ToolButton {
                            property string tip: ""
                            implicitHeight: 22
                            font.pixelSize: Theme.fontSm
                            ToolTip.text: tip
                            ToolTip.visible: hovered
                            ToolTip.delay: 400
                        }

                        // A basemap is always the ground: offering to move it
                        // or to frame it would be offering something that does
                        // not happen.
                        Action {
                            visible: entry.layerRole !== "basemap"
                            text: "▲"
                            tip: root.txt["layers.moveUp"]
                            onClicked: root.stack.move(entry.layerId, 1)
                        }
                        Action {
                            visible: entry.layerRole !== "basemap"
                            text: "▼"
                            tip: root.txt["layers.moveDown"]
                            onClicked: root.stack.move(entry.layerId, -1)
                        }
                        Action {
                            visible: entry.layerRole !== "basemap"
                            text: "⤢"
                            tip: root.txt["layers.zoomTo"]
                            onClicked: root.zoomToRequested(entry.layerId)
                        }
                        Label {
                            visible: entry.layerRole === "basemap"
                            text: root.txt["layers.basemap.note"]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Item { Layout.fillWidth: true }
                        Action {
                            text: "✕"
                            tip: root.txt["layers.remove.tip"]
                            onClicked: root.stack.remove(entry.layerId)
                        }
                    }
                }
            }
        }

        // ---- the active layer's colours ---------------------------------
        // The colormap belongs to the layer, not to the view: two layers can
        // carry two ramps at the same time, and changing one leaves the other
        // alone. It repaints and never rewrites a value.
        ColumnLayout {
            id: style
            visible: root.stack.count > 0
            Layout.fillWidth: true
            Layout.topMargin: Theme.spacingSm
            spacing: Theme.spacingXs

            // `revision` and `activeId` are notifiable; naming them here is
            // what makes this binding re-evaluate. `activeLayer()` alone is a
            // slot, and a slot is read once.
            readonly property var active: root.stack.revision >= 0
                                          && root.stack.activeId !== undefined
                                          ? root.stack.activeLayer() : ({})

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: Theme.border
            }
            Label {
                text: root.txt["colormap.caption"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingXs

                ComboBox {
                    id: ramp
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    model: root.stack.colormaps
                    currentIndex: Math.max(0, model.indexOf(
                        style.active && style.active.colormap
                        ? style.active.colormap : "viridis"))
                    onActivated: root.stack.setColormap(
                        root.stack.activeId, textAt(index))
                }
                ToolButton {
                    text: "⇄"
                    implicitHeight: Theme.controlHeight
                    checkable: true
                    checked: style.active && style.active.invert === true
                    onToggled: root.stack.setInvert(root.stack.activeId, checked)
                    ToolTip.text: root.txt["colormap.invert"]
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingXs

                TextField {
                    id: minField
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    placeholderText: root.txt["colormap.min"]
                    text: style.active && style.active.vmin !== null
                          && style.active.vmin !== undefined
                          ? String(style.active.vmin) : ""
                    onEditingFinished: root.stack.setLimits(
                        root.stack.activeId, text.length > 0 ? parseFloat(text) : null,
                        maxField.text.length > 0 ? parseFloat(maxField.text) : null)
                }
                TextField {
                    id: maxField
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    placeholderText: root.txt["colormap.max"]
                    text: style.active && style.active.vmax !== null
                          && style.active.vmax !== undefined
                          ? String(style.active.vmax) : ""
                    onEditingFinished: root.stack.setLimits(
                        root.stack.activeId,
                        minField.text.length > 0 ? parseFloat(minField.text) : null,
                        text.length > 0 ? parseFloat(text) : null)
                }
                ToolButton {
                    text: "↺"
                    implicitHeight: Theme.controlHeight
                    onClicked: root.stack.resetLimits(root.stack.activeId)
                    ToolTip.text: root.txt["colormap.auto"]
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                }
            }

            // ---- the symbol, for a point layer --------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingXs
                visible: style.active && style.active.kind === "points"

                ComboBox {
                    id: shape
                    Layout.preferredWidth: 96
                    implicitHeight: Theme.controlHeight
                    model: root.stack.symbols
                    textRole: ""
                    displayText: root.txt["symbol." + currentValue]
                    delegate: ItemDelegate {
                        required property string modelData
                        width: shape.width
                        text: root.txt["symbol." + modelData]
                    }
                    currentIndex: Math.max(0, root.stack.symbols.indexOf(
                        style.active && style.active.symbol
                        ? style.active.symbol : "circle"))
                    onActivated: root.stack.setSymbol(root.stack.activeId,
                                                      root.stack.symbols[index])
                    ToolTip.text: root.txt["layers.symbol.shape"]
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                }
                Label {
                    text: root.txt["layers.symbol.size"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                }
                Slider {
                    id: sizeSlider
                    from: 0; to: 8; stepSize: 1
                    value: style.active && style.active.pointSize !== undefined
                           ? style.active.pointSize : 2
                    Layout.fillWidth: true
                    implicitHeight: 20
                    onMoved: root.stack.setPointSize(root.stack.activeId, value)
                }
                ToolButton {
                    text: "◎"
                    implicitHeight: Theme.controlHeight
                    checkable: true
                    checked: style.active && style.active.outline === true
                    onToggled: root.stack.setOutline(root.stack.activeId, checked)
                    ToolTip.text: root.txt["layers.symbol.outline"]
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                }
            }

            Label {
                text: root.txt["colormap.displayOnly"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
