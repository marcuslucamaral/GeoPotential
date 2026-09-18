import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 9.11 — Settings, for the settings that exist.
//
// Everything here belongs to the **person**, not to the project: it follows
// them from one `.gpot` to the next and is stored outside every one of them.
// Nothing on this screen changes a value, a unit, a CRS or an artefact, and
// the screen says so rather than leaving it to be assumed.
//
// It writes through `controller.preferences`, which is the only thing that
// knows where a preference is kept.
Dialog {
    id: root

    required property var controller
    property var txt: ({})

    readonly property var prefs: controller.preferences

    title: txt["prefs.title"] || ""
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 520
    standardButtons: Dialog.Close
    closePolicy: Popup.CloseOnEscape

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingMd

        Label {
            Layout.fillWidth: true
            text: root.txt["prefs.explain"] || ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            wrapMode: Text.WordWrap
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Theme.spacingMd
            rowSpacing: Theme.spacingSm

            Label {
                text: root.txt["prefs.language"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ComboBox {
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                model: ["Português", "English"]
                currentIndex: root.controller.tr.language === "en" ? 1 : 0
                onActivated: root.controller.tr.setLanguage(
                                 index === 1 ? "en" : "pt")
            }

            Label {
                text: root.txt["prefs.theme"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ComboBox {
                objectName: "prefsTheme"
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                // The order these are listed in is the order of `keys`; the
                // label is translated and the key is not, so a language change
                // cannot change which theme a click selects.
                property var keys: ["dark", "light", "highContrast", "system"]
                model: [root.txt["menu.view.theme.dark"],
                        root.txt["menu.view.theme.light"],
                        root.txt["menu.view.theme.contrast"],
                        root.txt["menu.view.theme.system"]]
                currentIndex: Math.max(0, keys.indexOf(root.prefs.themeMode))
                onActivated: root.prefs.setThemeMode(keys[index])
            }

            Label {
                text: root.txt["prefs.coordinates"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ComboBox {
                objectName: "prefsCoordinates"
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                property var keys: ["native", "utm", "decimal", "dms"]
                model: [root.txt["menu.view.coordinate.native"],
                        root.txt["menu.view.coordinate.utm"],
                        root.txt["menu.view.coordinate.decimal"],
                        root.txt["menu.view.coordinate.dms"]]
                currentIndex: Math.max(0, keys.indexOf(root.prefs.coordinateStyle))
                onActivated: root.prefs.setCoordinateStyle(keys[index])
            }

            Label {
                text: root.txt["prefs.ground"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ComboBox {
                objectName: "prefsGround"
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                property var keys: ["black", "charcoal", "grey", "white"]
                model: [root.txt["menu.view.background.black"],
                        root.txt["menu.view.background.charcoal"],
                        root.txt["menu.view.background.grey"],
                        root.txt["menu.view.background.white"]]
                currentIndex: Math.max(0, keys.indexOf(root.prefs.canvasGround))
                onActivated: root.prefs.setCanvasGround(keys[index])
            }
        }

        Label {
            Layout.fillWidth: true
            text: root.txt["prefs.scope"] || ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            wrapMode: Text.WordWrap
        }
    }
}
