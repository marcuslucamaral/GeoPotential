import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// The application's menu bar: File, Edit, View, Processing, Help.
//
// One rule governs every entry, and the gate checks it: **an enabled item has
// an action, and a disabled item says why it is disabled** — in its own label,
// not in a tooltip nobody can reach on a disabled control.
//
// Every item names a `token`; the shell routes tokens to slots. The menu bar
// decides nothing and calls no controller method directly, which is also what
// makes it auditable: `auditTable` is the same list the gate walks.
MenuBar {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    // What the shell is currently showing. Bound by Main.qml so the View menu
    // reflects reality instead of remembering its own copy.
    property bool workflowVisible: true
    property bool inspectorVisible: true
    property bool jobsVisible: true
    property bool layersVisible: true
    property bool railVisible: true
    property bool fullScreen: false
    property bool hasLayer: false
    property string coordinateStyle: "native"
    property string viewCrsChosen: ""
    // The theme the person chose, which is not always the one being painted.
    readonly property string themeMode: controller.preferences.themeMode
    property string basemapSource: ""
    property var basemapSources: []
    // The active layer's ramp, so the colormap submenu can tick the one in
    // use. Read from the model, which is the authority on it.
    readonly property string activeColormap: {
        var active = controller.layers.activeLayer()
        return (active && active.colormap) ? active.colormap : ""
    }

    signal actionRequested(string token)

    // Filled at completion by walking the real items. The gate reads it, so it
    // cannot drift from what is on screen.
    property var auditTable: []

    function _arrives(milestone) {
        return root.txt["reason.arrivesIn"].replace("%1", milestone)
    }

    Menu {
        title: root.txt["menu.file"]
        MenuItem {
            text: root.txt["menu.file.new"]
            property string token: "project.new"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.file.open"]
            property string token: "project.open"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        Menu {
            title: root.txt["menu.file.recent"]
            enabled: root.controller.recentProjects.length > 0
            Repeater {
                model: root.controller.recentProjects
                delegate: MenuItem {
                    required property var modelData
                    text: modelData.name && modelData.name.length > 0
                          ? modelData.name : modelData.path
                    property string token: "project.openRecent:" + modelData.path
                    property string reason: ""
                    onTriggered: root.actionRequested(token)
                }
            }
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.file.import"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.import"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.file.gridding"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.gridding"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.file.exportResult"] + reason
            enabled: false
            property string token: ""
            property string reason: root._arrives("M6")
        }
        MenuItem {
            text: root.txt["menu.file.exportMap"] + reason
            enabled: root.hasLayer
            property string token: "map.export"
            property string reason: enabled ? "" : root.txt["reason.noLayer"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.file.exportDiagnostic"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "diagnostic.export"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.file.quit"]
            property string token: "app.quit"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
    }

    Menu {
        title: root.txt["menu.edit"]
        // The reason a disabled entry gives has to be *on the label*: a
        // tooltip never fires on a disabled control, so a reason parked there
        // is a reason nobody can read.
        MenuItem {
            text: root.txt["menu.edit.undo"] + " — " + root.controller.undoText
            enabled: root.controller.canUndo
            property string token: "edit.undo"
            property string reason: enabled ? "" : root.controller.undoText
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.edit.redo"] + " — " + root.controller.redoText
            enabled: root.controller.canRedo
            property string token: "edit.redo"
            property string reason: enabled ? "" : root.controller.redoText
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        // These three act on the active layer, so each is disabled when there
        // is none — and says that, rather than naming a milestone that has
        // already shipped. The panel grew the controls in E2 and the menu was
        // left behind pointing at E2.
        MenuItem {
            text: root.txt["menu.edit.layerProperties"] + reason
            enabled: root.controller.layers.count > 0
            property string token: "layer.properties"
            property string reason: enabled ? "" : root.txt["reason.noLayer"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.edit.rename"] + reason
            enabled: root.controller.layers.activeId.length > 0
            property string token: "layer.rename"
            property string reason: enabled ? "" : root.txt["reason.noLayer"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.edit.removeLayer"] + reason
            enabled: root.controller.layers.activeId.length > 0
            property string token: "layer.remove"
            property string reason: enabled ? "" : root.txt["reason.noLayer"]
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.edit.preferences"]
            property string token: "edit.preferences"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
    }

    Menu {
        title: root.txt["menu.view"]
        MenuItem {
            text: root.txt["menu.view.layers"]
            checkable: true
            checked: root.layersVisible
            property string token: "view.layers"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.view.workflow"]
            checkable: true
            checked: root.workflowVisible
            property string token: "view.workflow"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.view.inspector"]
            checkable: true
            checked: root.inspectorVisible
            property string token: "view.inspector"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.view.rail"]
            checkable: true
            checked: root.railVisible
            property string token: "view.rail"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.view.jobs"]
            checkable: true
            checked: root.jobsVisible
            property string token: "view.jobs"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.view.fullScreen"]
            checkable: true
            checked: root.fullScreen
            property string token: "view.fullScreen"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuSeparator {}
        Menu {
            title: root.txt["menu.view.coordinateFormat"]
            MenuItem {
                text: root.txt["menu.view.coordinate.native"]
                checkable: true; checked: root.coordinateStyle === "native"
                property string token: "coord.native"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.coordinate.utm"]
                checkable: true; checked: root.coordinateStyle === "utm"
                property string token: "coord.utm"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.coordinate.decimal"]
                checkable: true; checked: root.coordinateStyle === "decimal"
                property string token: "coord.decimal"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.coordinate.dms"]
                checkable: true; checked: root.coordinateStyle === "dms"
                property string token: "coord.dms"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
        }
        Menu {
            title: root.txt["menu.view.basemap"]
            MenuItem {
                text: root.txt["menu.view.basemap.none"]
                checkable: true; checked: root.basemapSource.length === 0
                property string token: "basemap.none"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuSeparator {}
            Repeater {
                model: root.basemapSources
                delegate: MenuItem {
                    required property var modelData
                    text: modelData.name + "  ·  " + modelData.licence
                    checkable: true
                    checked: root.basemapSource === modelData.key
                    property string token: "basemap:" + modelData.key
                    property string reason: ""
                    onTriggered: root.actionRequested(token)
                }
            }
        }
        Menu {
            title: root.txt["menu.view.crs"]
            MenuItem {
                text: root.txt["menu.view.crs.layer"]
                checkable: true; checked: root.viewCrsChosen.length === 0
                property string token: "viewcrs.layer"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.crs.wgs84"]
                checkable: true; checked: root.viewCrsChosen === "EPSG:4326"
                property string token: "viewcrs.4326"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.crs.mercator"]
                checkable: true; checked: root.viewCrsChosen === "EPSG:3857"
                property string token: "viewcrs.3857"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
        }
        // The colormap belongs to the layer (P-111), so this acts on the
        // active one and is disabled when there is none. The panel has had
        // the same control since E2; the menu was still deferring to E2.
        Menu {
            title: root.txt["menu.view.colormap"]
                   + (enabled ? "" : root.txt["reason.noLayer"])
            enabled: root.controller.layers.activeId.length > 0
            Repeater {
                model: root.controller.layers.colormaps
                delegate: MenuItem {
                    required property string modelData
                    text: modelData
                    checkable: true
                    checked: root.activeColormap === modelData
                    property string token: "colormap:" + modelData
                    property string reason: ""
                    onTriggered: root.actionRequested(token)
                }
            }
        }
        Menu {
            title: root.txt["menu.view.background"]
            MenuItem {
                text: root.txt["menu.view.background.black"]
                checkable: true; checked: Theme.canvasGround === "black"
                property string token: "canvas.black"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.background.charcoal"]
                checkable: true; checked: Theme.canvasGround === "charcoal"
                property string token: "canvas.charcoal"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.background.grey"]
                checkable: true; checked: Theme.canvasGround === "grey"
                property string token: "canvas.grey"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.background.white"]
                checkable: true; checked: Theme.canvasGround === "white"
                property string token: "canvas.white"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
        }
        Menu {
            title: root.txt["menu.view.theme"]
            // The tick follows the *chosen* mode, not the painted one: with
            // `system` chosen and a dark desktop, `dark` is what is painted
            // and `system` is what was asked for, and the menu has to say so.
            MenuItem {
                text: root.txt["menu.view.theme.dark"]
                checkable: true
                checked: root.themeMode === "dark"
                property string token: "theme.dark"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.theme.light"]
                checkable: true
                checked: root.themeMode === "light"
                property string token: "theme.light"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.theme.contrast"]
                checkable: true
                checked: root.themeMode === "highContrast"
                property string token: "theme.contrast"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.theme.system"]
                checkable: true
                checked: root.themeMode === "system"
                property string token: "theme.system"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
        }
        Menu {
            title: root.txt["menu.view.language"]
            MenuItem {
                text: root.txt["menu.view.language.pt"]
                checkable: true
                checked: root.controller.tr.language === "pt"
                property string token: "language.pt"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
            MenuItem {
                text: root.txt["menu.view.language.en"]
                checkable: true
                checked: root.controller.tr.language === "en"
                property string token: "language.en"
                property string reason: ""
                onTriggered: root.actionRequested(token)
            }
        }
    }

    // Processing: the flow, and the operations that feed it.
    //
    // The eight steps are here as well as on the rail and in the panel, and
    // that is deliberate — they are the application's spine, and a person who
    // navigates by menu should not have to find them in a panel. All three
    // read the same model and route the same token, so a step blocked in one
    // is blocked in all of them, with the same reason on the label.
    Menu {
        title: root.txt["menu.processing"]

        Repeater {
            model: root.controller.workflow

            delegate: MenuItem {
                required property string key
                required property int number
                required property string titleKey
                required property string stepState
                required property string reasonKey
                required property string stepAction

                text: number + ". " + (root.txt[titleKey] || titleKey) + reason
                enabled: stepState !== "blocked"
                property string token: "step:" + key
                // The reason is on the label, not in a tooltip: a disabled
                // menu item does not receive hover, so a tooltip there is a
                // reason nobody can reach.
                property string reason: enabled
                    ? "" : "  —  " + (root.txt[reasonKey] || reasonKey)
                onTriggered: root.actionRequested(token)
            }
        }

        MenuSeparator {}

        MenuItem {
            text: root.txt["menu.file.import"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.import"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.file.gridding"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.gridding"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.processing.harmonize"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.harmonize"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.processing.membership"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.membership"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.processing.decision"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.decision"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.processing.potentialFields"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.potentialFields"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.processing.scenarios"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "data.scenarios"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
    }

    Menu {
        title: root.txt["menu.help"]
        MenuItem {
            text: root.txt["menu.help.workflow"]
            property string token: "help.workflow"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.help.shortcuts"]
            property string token: "help.shortcuts"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.help.documentation"] + reason
            enabled: false
            property string token: ""
            property string reason: root._arrives("M8")
        }
        MenuSeparator {}
        MenuItem {
            text: root.txt["menu.help.diagnostic"] + reason
            enabled: root.controller.projectName.length > 0
            property string token: "diagnostic.export"
            property string reason: enabled ? "" : root.txt["reason.noProject"]
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.help.versions"]
            property string token: "help.versions"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
        MenuItem {
            text: root.txt["menu.help.about"]
            property string token: "help.about"
            property string reason: ""
            onTriggered: root.actionRequested(token)
        }
    }

    // ---- audit ----------------------------------------------------------
    //
    // Built from the items themselves, not from a second list. A menu that
    // gained an entry and forgot its token or its reason fails the gate here.
    function collect(menu, path, table) {
        for (let i = 0; i < menu.count; ++i) {
            const item = menu.itemAt(i)
            if (!item)
                continue
            // A submenu's own item opens the submenu and does nothing else;
            // what has to be audited is what is inside it.
            //
            // Unless the submenu is disabled. Then nothing inside it can be
            // reached, and the entry a person meets is the submenu itself —
            // which carries the reason on its title, where it can be read.
            // Descending into it would report every ramp inside a greyed-out
            // "Colormap" as a silent dead entry, which is the opposite of
            // what P-105 is asking.
            if (item.subMenu) {
                if (item.subMenu.enabled === false) {
                    table.push({
                        "menu": path,
                        "label": String(item.subMenu.title),
                        "token": "",
                        "enabled": false,
                        "reason": String(item.subMenu.reason === undefined
                                         ? root.txt["reason.noLayer"]
                                         : item.subMenu.reason)
                    })
                    continue
                }
                collect(item.subMenu, path + " › " + String(item.subMenu.title), table)
                continue
            }
            if (item.token === undefined)
                continue        // a separator
            table.push({
                "menu": path,
                "label": String(item.text),
                "token": String(item.token),
                "enabled": item.enabled === true,
                "reason": String(item.reason)
            })
        }
    }

    function buildAudit() {
        let table = []
        for (let m = 0; m < count; ++m) {
            const menu = menuAt(m)
            if (menu)
                collect(menu, String(menu.title), table)
        }
        auditTable = table
    }

    Component.onCompleted: buildAudit()
    // The labels change with the language, and the audit is a snapshot of the
    // labels. Rebuilding keeps the gate reading what is actually on screen.
    Connections {
        target: root.controller.tr
        function onLanguageChanged() { root.buildAudit() }
    }
    // And the layer entries change with the stack: three of them and the
    // colormap submenu are disabled while no layer is active. An audit taken
    // once, at startup, would describe an empty project forever — and the
    // entries it never saw are exactly the ones that were dead for a
    // milestone without anything noticing.
    Connections {
        target: root.controller.layers
        function onChanged() { root.buildAudit() }
        function onActiveChanged() { root.buildAudit() }
    }
}
