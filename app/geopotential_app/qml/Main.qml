import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import GeoPotential
import GeoPotential.Canvas

// The workspace of section 8: top bar, left navigator, central canvas, right
// inspector, bottom panel, status bar.
//
// QML composes and binds. It holds no scientific rule, touches no file, and
// calls nothing but the properties and slots `controller` publishes.
//
// The root is `appWindow`, never `window`: QML has a `window` attached
// property that wins the lookup inside a Loader.
ApplicationWindow {
    id: appWindow
    required property var controller

    width: 1440
    height: 880
    visible: true
    title: controller.projectName.length > 0
           ? "GeoPotential Professional — " + controller.projectName
           : "GeoPotential Professional"
    color: Theme.background

    // Qt Quick Controls paint from the palette, not from our tokens. Without
    // this, a GroupBox or a TextField draws its own light background and
    // near-white themed text becomes invisible on it — which is exactly what
    // happened to the Import Wizard's "Detected" panel. Every role below
    // still resolves through Theme.qml, so there is still one source.
    palette.window: Theme.background
    palette.windowText: Theme.text
    palette.base: Theme.surfaceAlt
    palette.alternateBase: Theme.surface
    palette.text: Theme.text
    palette.button: Theme.surfaceAlt
    palette.buttonText: Theme.text
    palette.mid: Theme.border
    palette.midlight: Theme.border
    palette.dark: Theme.border
    palette.light: Theme.surface
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.background
    palette.placeholderText: Theme.textMuted
    palette.toolTipBase: Theme.surfaceAlt
    palette.toolTipText: Theme.text

    // ---- what the shell is showing ---------------------------------------
    // Panel visibility lives here, on the root, because the View menu and the
    // panels themselves must read one value. A menu with its own copy is a
    // menu that lies after the first toggle from elsewhere.
    // Which panels are open. Read back from the preferences on load, so a
    // layout a person arranged is the layout they get next time.
    property bool workflowVisible: true
    property bool layersVisible: true
    property bool inspectorVisible: true
    property bool jobsVisible: true
    // The rail is a panel like the others: the person's choice, remembered.
    property bool railVisible: true

    function togglePanel(name) {
        var now = !appWindow.controller.preferences.panelVisible(name)
        appWindow.controller.preferences.setPanelVisible(name, now)
        appWindow.applyPanels()
    }

    function applyPanels() {
        var prefs = appWindow.controller.preferences
        appWindow.workflowVisible = prefs.panelVisible("workflow")
        appWindow.layersVisible = prefs.panelVisible("layers")
        appWindow.inspectorVisible = prefs.panelVisible("inspector")
        appWindow.jobsVisible = prefs.panelVisible("jobs")
        appWindow.railVisible = prefs.panelVisible("rail")
    }

    function setTheme(mode) {
        appWindow.controller.preferences.setThemeMode(mode)
    }

    // The three things the theme decides, applied from the preference and
    // re-applied whenever it changes. `system` is resolved on the Python side
    // — reading the desktop needs QtGui, and this file only paints.
    Binding {
        target: Theme
        property: "mode"
        value: appWindow.controller.preferences.effectiveTheme
    }
    Binding {
        target: Theme
        property: "canvasGround"
        value: appWindow.controller.preferences.canvasGround
    }
    Binding {
        target: canvas
        property: "coordinateStyle"
        value: appWindow.controller.preferences.coordinateStyle
    }


    // Every visible string resolves through the catalogue. `txt` re-evaluates
    // by itself when the language changes, because `strings` is a property
    // with a NOTIFY signal and not a slot read once.
    readonly property var txt: controller.tr.strings

    // Every menu entry and every shortcut arrives here as a token. One place
    // routes them, so an entry with no route is a gate failure and not a
    // silent no-op.
    function dispatch(token) {
        if (token.indexOf("basemap:") === 0) {
            var chosen = token.substring("basemap:".length)
            canvas.basemapSource = chosen
            // The panel is where a person looks for what is drawn, so the
            // basemap appears there too — as display, and nothing else.
            appWindow.controller.setBasemap(chosen)
            return
        }
        if (token.indexOf("project.openRecent:") === 0) {
            appWindow.controller.openProject(token.substring("project.openRecent:".length))
            return
        }
        if (token.indexOf("step:") === 0) {
            // The Processing menu and the rail both address a step by key.
            // They route through `openStep` like the panel does, so the three
            // surfaces cannot come to open different things.
            var stepKey = token.substring("step:".length)
            var chosen = appWindow.controller.workflow.step(stepKey)
            if (chosen && chosen.stepAction !== undefined)
                appWindow.openStep(stepKey, chosen.stepAction)
            return
        }
        if (token.indexOf("colormap:") === 0) {
            // The ramp belongs to the layer, not to the view (P-111): it is
            // set on the active layer and repaints nothing else.
            appWindow.controller.layers.setColormap(
                appWindow.controller.layers.activeId,
                token.substring("colormap:".length))
            return
        }
        switch (token) {
        case "project.new":
        case "project.open":       projectHub.open(); break
        case "data.import":        appWindow.openImport(""); break
        case "data.gridding":      griddingDialog.open(); break
        case "data.harmonize":     harmonizeDialog.open(); break
        case "data.membership":    appWindow.openMembership(); break
        case "data.decision":      decisionModel.open(); break
        case "data.scenarios":     appWindow.openScenarios(); break
        case "data.potentialFields": potentialFieldsDialog.open(); break
        case "diagnostic.export":  diagnosticPicker.open(); break
        case "map.export":         mapExportPicker.open(); break
        case "app.quit":           appWindow.close(); break
        case "edit.undo":          appWindow.controller.undo(); break
        case "edit.redo":          appWindow.controller.redo(); break
        case "layer.properties":
            // The layer panel *is* the properties: visibility, order, opacity,
            // ramp, limits, symbol. Opening a second surface with the same
            // controls would be two states of one thing.
            appWindow.layersVisible = true
            break
        case "layer.rename":       renameDialog.open(); break
        case "edit.preferences":   preferencesDialog.open(); break
        case "layer.remove":
            // Out of the view only. Nothing on disk and nothing in the
            // catalogue is touched (P-108).
            appWindow.controller.layers.remove(appWindow.controller.layers.activeId)
            break
        // Panel visibility is the person's, so it is remembered between
        // sessions and the shell reads it back on load.
        case "view.workflow":      appWindow.togglePanel("workflow"); break
        case "view.layers":        appWindow.togglePanel("layers"); break
        case "view.inspector":     appWindow.togglePanel("inspector"); break
        case "view.jobs":          appWindow.togglePanel("jobs"); break
        case "view.rail":          appWindow.togglePanel("rail"); break
        case "view.fullScreen":
            appWindow.visibility = appWindow.visibility === Window.FullScreen
                                 ? Window.Windowed : Window.FullScreen
            break
        case "basemap.none":
            canvas.basemapSource = ""
            appWindow.controller.setBasemap("")
            break
        case "coord.native":
        case "coord.utm":
        case "coord.decimal":
        case "coord.dms":
            // Through the preference, and the canvas follows it: the format a
            // person reads coordinates in outlives the project they opened.
            appWindow.controller.preferences.setCoordinateStyle(
                token.substring("coord.".length))
            break
        case "viewcrs.layer":      canvas.viewCrs = ""; break
        case "viewcrs.4326":       canvas.viewCrs = "EPSG:4326"; break
        case "viewcrs.3857":       canvas.viewCrs = "EPSG:3857"; break
        case "canvas.black":
        case "canvas.charcoal":
        case "canvas.grey":
        case "canvas.white":
            appWindow.controller.preferences.setCanvasGround(
                token.substring("canvas.".length))
            break
        case "theme.dark":         appWindow.setTheme("dark"); break
        case "theme.light":        appWindow.setTheme("light"); break
        case "theme.contrast":     appWindow.setTheme("highContrast"); break
        case "theme.system":       appWindow.setTheme("system"); break
        case "language.pt":        appWindow.controller.tr.setLanguage("pt"); break
        case "language.en":        appWindow.controller.tr.setLanguage("en"); break
        case "help.workflow":      workflowGuide.open(); break
        case "help.shortcuts":     shortcutsDialog.open(); break
        case "help.versions":      versionsDialog.open(); break
        case "help.about":         aboutDialog.open(); break
        default:
            appWindow.controller.errorRaised("no action is bound to " + token, "")
        }
    }

    // Clicking a step opens the tool that step is about. A blocked step never
    // gets here: the panel refuses it with its reason already on screen.
    // Opening the wizard on a file. The drop, the menu and the workflow step
    // all come through here, so they cannot behave differently.
    function openImport(path) {
        importWizard.clearWizard()
        if (path && path.length > 0) {
            importWizard.path = path
            importWizard.inspect()
        }
        importWizard.open()
    }

    function openStep(key, action) {
        switch (action) {
        case "projectHub":       projectHub.open(); break
        case "importWizard":     appWindow.openImport(""); break
        case "membershipEditor": appWindow.openMembership(); break
        case "decisionModel":    decisionModel.open(); break
        case "harmonize":        harmonizeDialog.open(); break
        case "results":
            // The result is the map, and the map is already on screen. This
            // brings the view back to it rather than opening a screen that
            // would only repeat what the canvas shows.
            canvas.zoomToFit()
            break
        }
    }

    // The Run button. It does what the step the workflow is on says to do —
    // there is no operator of its own here and no injected input (E6, A33).
    //
    // The workflow's state is derived from the Project Store, so this always
    // acts on what the project actually holds. A step that cannot run says so
    // through `runReason` and the button is disabled with that on it.
    function runCurrentStep() {
        var key = appWindow.controller.currentStep
        var step = appWindow.controller.workflow.step(key)
        if (!step || step.key === undefined)
            return
        if (step.state === "blocked") {
            // The step names what is missing. Saying it here is the whole
            // point: a disabled Run that explains nothing is the defect this
            // milestone exists to remove.
            appWindow.controller.errorRaised(
                appWindow.txt[step.reasonKey] || step.reasonKey || "", "")
            return
        }
        appWindow.openStep(key, step.stepAction)
    }

    // What the Run button would do next, for its label and its tooltip.
    readonly property var currentStepDetail:
        controller.workflow.step(controller.currentStep)

    menuBar: AppMenuBar {
        id: appMenu
        objectName: "appMenuBar"
        controller: appWindow.controller
        workflowVisible: appWindow.workflowVisible
        layersVisible: appWindow.layersVisible
        inspectorVisible: appWindow.inspectorVisible
        jobsVisible: appWindow.jobsVisible
        railVisible: appWindow.railVisible
        fullScreen: appWindow.visibility === Window.FullScreen
        hasLayer: canvas.hasLayer
        coordinateStyle: canvas.coordinateStyle
        basemapSource: canvas.basemapSource
        basemapSources: appWindow.controller.basemapSources
        viewCrsChosen: canvas.viewCrs
        onActionRequested: function (token) { appWindow.dispatch(token) }
    }

    // The shortcuts of the Help › Atalhos list. They call `dispatch`, so a
    // shortcut and its menu entry can never do different things.
    Shortcut { sequence: "Ctrl+N";       onActivated: appWindow.dispatch("project.new") }
    Shortcut { sequence: "Ctrl+O";       onActivated: appWindow.dispatch("project.open") }
    Shortcut { sequence: "Ctrl+I";       onActivated: appWindow.dispatch("data.import") }
    Shortcut { sequence: "Ctrl+Z";       onActivated: appWindow.dispatch("edit.undo") }
    Shortcut { sequence: "Ctrl+Shift+Z"; onActivated: appWindow.dispatch("edit.redo") }
    Shortcut { sequence: "F11";          onActivated: appWindow.dispatch("view.fullScreen") }
    Shortcut { sequence: "F1";           onActivated: appWindow.dispatch("help.workflow") }

    // ---- top bar ---------------------------------------------------------
    header: TopBar {
        controller: appWindow.controller
        viewCrs: canvas.crsName
        onRunRequested: appWindow.runCurrentStep()
        onProjectsRequested: projectHub.open()
        onSplitRequested: canvas.splitView = !canvas.splitView
        onDecisionRequested: decisionModel.open()
        onAoiRequested: {
            if (canvas.aoiPointCount >= 3) {
                canvas.endAoi()
                appWindow.controller.saveAoi("survey", canvas.aoiPolygon(), canvas.crsName)
            } else {
                canvas.beginAoi()
            }
        }
        onCancelRequested: {
            if (jobsPanel.selectedJobId.length > 0)
                appWindow.controller.cancel(jobsPanel.selectedJobId)
        }
        // One click walks dark -> light -> high contrast -> system, which is
        // the same set the View menu lists. The menu stays the way to pick one
        // directly; this is the way to try them.
        onThemeToggleRequested: {
            var order = ["dark", "light", "highContrast", "system"]
            var at = order.indexOf(appWindow.controller.preferences.themeMode)
            appWindow.setTheme(order[(at + 1) % order.length])
        }
    }

    // The last histogram the worker computed, for the inspector.
    property var lastDescription: ({})
    // The active layer's own statistics, asked for once per layer. The
    // Inspector reads this and not `lastDescription`: that one is whatever
    // the wizard looked at last, and after any computation the two are
    // different files — a CSV's range under the name of the raster
    // interpolated from it.
    property var activeDescription: ({})
    // The decision model's working state. It lives here, on the root, because
    // two screens read it — the editor adds criteria, the model combines them
    // — and a copy in each would be two states that drift.
    property var criteria: []
    property var lastAhp: ({})
    property var lastCorrelations: []

    // M6. The scenarios screen questions the analysis the Decision Model
    // holds — the same criteria, the same operator, the same weights. A
    // scenario measured against a different analysis measures nothing.
    function openScenarios() {
        scenariosDialog.criteria = decisionModel.criteria
        scenariosDialog.method = decisionModel.method
        scenariosDialog.gamma = decisionModel.gamma
        scenariosDialog.weights = appWindow.decisionWeights()
        scenariosDialog.clearMeasurements()
        scenariosDialog.open()
    }

    // The AHP weights as the operators want them, or an empty list when the
    // chosen operator carries none.
    function decisionWeights() {
        var byName = decisionModel.ahp ? decisionModel.ahp.weights_by_name : null
        if (!byName)
            return []
        var out = []
        for (var name in byName)
            out.push({"name": name, "weight": byName[name]})
        return out
    }

    // Abre a pertinência sobre a camada ativa, pedindo a descrição ao worker
    // quando ela ainda não chegou. Sem camada, diz o que falta em vez de abrir
    // um diálogo vazio que não explica nada.
    function openMembership() {
        var active = appWindow.controller.layers.activeLayer()
        // `activeLayer()` devolve `layerId`, não `id`. Ler a chave errada dá
        // `undefined`, que é falso, e o diálogo nunca abria — trocando um
        // editor vazio por uma recusa, que é outro defeito.
        if (!active || !active.layerId || !active.path) {
            appWindow.controller.errorRaised(
                appWindow.txt["membership.noLayer"], "")
            return
        }
        var described = appWindow.controller.layerDescription(active.layerId)
        membershipEditor.choosable = appWindow.controller.membershipCandidates()
        membershipEditor.criterion = appWindow.buildCriterion(described, active)
        // Ainda não descrita: o pedido é read-only e a resposta chega pelo
        // sinal acima, que preenche o editor já aberto.
        if (!described || described.statistics === undefined)
            appWindow.controller.describeLayer(active.layerId)
        membershipEditor.open()
    }

    // O que o editor precisa saber sobre a camada: onde ela está, como se
    // chama, em que unidade, e a distribuição que a curva vai atravessar.
    function buildCriterion(described, active) {
        var layer = active || appWindow.controller.layers.activeLayer() || ({})
        var d = described || ({})
        return {
            "path": d.path || layer.path || "",
            "name": layer.name || d.name || "",
            "unit": layer.unit || d.unit || "",
            "statistics": d.statistics
        }
    }

    // O funil entre a tela de decisão e o operador. Uma chave que a tela
    // monta e este deixa cair é uma decisão perdida em silêncio — foi assim
    // que `weights` sumiu e a combinação ponderada nunca produziu mapa.
    // Um critério por camada. A chave é o caminho do raster, não o nome:
    // dois arquivos podem receber o mesmo nome e continuar sendo dois dados.
    function setCriterion(spec) {
        var out = []
        var replaced = false
        for (var i = 0; i < appWindow.criteria.length; ++i) {
            if (appWindow.criteria[i].path === spec.path) {
                out.push(spec)
                replaced = true
            } else {
                out.push(appWindow.criteria[i])
            }
        }
        if (!replaced)
            out.push(spec)
        appWindow.criteria = out
    }

    // O mapa normalizado da etapa 5, como camada visível.
    //
    // O operador existia e ninguém o chamava — a agregação recalculava a
    // pertinência por dentro e nada aparecia na tela. O nome diz o que foi
    // feito: `<camada>_<função>`, e não um rótulo genérico.
    // O nome que a camada de pertinência desta curva terá. Reaplicar tem de
    // **substituir** a anterior: três tentativas de curva deixavam três
    // rasters na pilha, todos chamados quase igual, e nada dizia qual era o
    // da vez.
    function dropPreviousMembership(spec) {
        var wanted = appWindow.criterionName(spec)
        var rows = controller.layers.snapshot()
        for (var i = 0; i < rows.length; ++i) {
            if (rows[i].role !== "membership")
                continue
            var name = String(rows[i].name || "")
            // A pertinência anterior **desta mesma camada**, qualquer que
            // tenha sido a curva: o prefixo é o nome da camada de origem.
            if (name === wanted || name.indexOf(
                    appWindow.sourceStem(spec) + "_") === 0)
                controller.layers.remove(rows[i].layerId)
        }
    }

    function sourceStem(spec) {
        return (spec.name || "criterion").replace(/_harmonized$/, "")
    }

    function runMembership(spec) {
        appWindow.dropPreviousMembership(spec)
        // `criterion_name` **é** o nome do resultado aqui: o operador não
        // declara `result_name`, e mandá-lo fazia o job ser recusado por
        // parâmetro desconhecido — o mapa nunca aparecia e nada dizia por quê.
        var params = {
            "function": spec["function"],
            "criterion_name": appWindow.criterionName(spec),
            "unit": spec.unit || ""
        }
        var carry = ["x_min", "x_max", "midpoint", "center", "spread",
                     "mapping", "preferred", "angular_spread"]
        for (var i = 0; i < carry.length; ++i)
            if (spec[carry[i]] !== undefined)
                params[carry[i]] = spec[carry[i]]
        controller.submit("decision.membership", params, [spec.path])
    }

    // O nome do resultado diz o operador, o gamma quando ele importa, e
    // quantos critérios entraram. `short` seria o nome óbvio da variável
    // abaixo e é palavra reservada em QML — o shell inteiro deixa de carregar.
    function resultName(request) {
        var tag = request.method === "fuzzy_gamma"
                  ? "gamma" + String(Math.round(request.gamma * 100))
                  : (request.method === "weighted_linear_combination"
                     ? "wlc" : String(request.method))
        return "suitability_" + tag + "_"
               + String((request.criteria || []).length) + "crit"
    }

    // O nome de um critério diz a camada **e** a transformação: duas curvas
    // diferentes sobre o mesmo raster são dois critérios diferentes, e
    // chamá-los pelo nome do arquivo esconde exatamente a diferença.
    function criterionName(spec) {
        return appWindow.sourceStem(spec) + "_"
               + (spec["function"] || "membership") + "_membership"
    }

    function runDecision(request) {
        var params = {
            "method": request.method,
            "gamma": request.gamma,
            // Não mais "prospectivity" para tudo: o nome diz o operador, o
            // gamma quando ele importa, e quantos critérios entraram. Três
            // execuções diferentes deixavam três arquivos com o mesmo nome e
            // nada na tela os distinguia.
            "result_name": request.result_name && request.result_name.length > 0
                           ? request.result_name
                           : appWindow.resultName(request),
            "criteria": request.criteria
        }
        // Só o que o operador declara. `weights` acompanha o método que os
        // usa; o gamma não os toma, e mandá-los registraria na procedência
        // uma escolha que não afetou o resultado.
        if (request.weights !== undefined)
            params["weights"] = request.weights
        controller.submit("decision.aggregate", params, [])
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // What the recovery pass found on open. Shown as a persistent banner
        // rather than a modal: the previous session's damage is context for
        // the work, not an interruption to dismiss before starting.
        Rectangle {
            id: recoveryBanner
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 34 : 0
            visible: appWindow.controller.needsAttention && !dismissed
            property bool dismissed: false
            color: Theme.surfaceAlt

            Rectangle {
                anchors { left: parent.left; bottom: parent.bottom; right: parent.right }
                height: 1
                color: Theme.border
            }
            Rectangle {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                width: 3
                color: Theme.warn
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingMd
                anchors.rightMargin: Theme.spacingMd
                spacing: Theme.spacingSm

                Label {
                    text: appWindow.controller.recoverySummary
                    color: Theme.text
                    font.pixelSize: Theme.fontSm
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Label {
                    text: appWindow.txt["recovery.nothingRecorded"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                }
                ToolButton {
                    text: appWindow.txt["recovery.dismiss"]
                    onClicked: recoveryBanner.dismissed = true
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // The rail: the flow, the two ways data enters, and what the
            // window shows. Against the window edge, ahead of the panels,
            // because it is the one column that is always the same.
            ActivityBar {
                id: activityBar
                objectName: "activityBar"
                visible: appWindow.railVisible
                Layout.fillHeight: true
                controller: appWindow.controller
                workflowVisible: appWindow.workflowVisible
                layersVisible: appWindow.layersVisible
                inspectorVisible: appWindow.inspectorVisible
                jobsVisible: appWindow.jobsVisible
                onActionRequested: function (token) { appWindow.dispatch(token) }
                onStepRequested: function (key, action) {
                    appWindow.openStep(key, action)
                }
            }

            // The left column: the flow on top, the layers under it. Both are
            // about "what am I working on", and splitting them across the
            // screen would make the map the smaller thing.
            SplitView {
                visible: appWindow.workflowVisible || appWindow.layersVisible
                orientation: Qt.Vertical
                Layout.preferredWidth: Theme.workflowWidth
                Layout.fillHeight: true

                WorkflowPanel {
                    id: workflowPanel
                    objectName: "workflowPanel"
                    visible: appWindow.workflowVisible
                    SplitView.preferredHeight: 320
                    SplitView.minimumHeight: 140
                    controller: appWindow.controller
                    onStepActivated: function (key, action) { appWindow.openStep(key, action) }
                }

                LayerPanel {
                    id: layerPanel
                    objectName: "layerPanel"
                    visible: appWindow.layersVisible
                    SplitView.fillHeight: true
                    SplitView.minimumHeight: 160
                    controller: appWindow.controller
                    onZoomToRequested: function (layerId) { canvas.zoomToLayer(layerId) }
                    onAttributesRequested: function (layerId) {
                        appWindow.controller.layers.setActive(layerId)
                        attributeTable.layerName =
                            appWindow.controller.layers.activeLayer().name || ""
                        attributeTable.preview =
                            appWindow.controller.layerPreview(layerId)
                        attributeTable.open()
                    }
                    onDetailsRequested: function (layerId) {
                        appWindow.controller.layers.setActive(layerId)
                        appWindow.inspectorVisible = true
                    }
                }
            }

            // ---- central canvas ------------------------------------------
            Rectangle {
                id: mapContainer
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.canvas

                MapItem {
                    id: canvas
                    // Named, because it is no longer the only MapItem in the
                    // scene: the Import Wizard's PreviewMap holds one too, and
                    // anything that found "the canvas" by type would find
                    // whichever the tree happened to reach first.
                    objectName: "mapCanvas"
                    anchors.fill: parent
                    ground: Theme.canvas
                    onCursorMoved: function (x, y, text) {
                        statusBar.coordinate = canvas.formatPosition(x, y)
                        statusBar.crsLabel = canvas.positionLabel()
                        statusBar.valueUnderCursor = text
                    }
                }

                Label {
                    anchors.centerIn: parent
                    visible: !canvas.hasLayer
                    text: appWindow.txt["canvas.empty"]
                    horizontalAlignment: Text.AlignHCenter
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontLg
                }

                IdentifyPanel {
                    objectName: "identifyPanel"
                    id: identifyPanel
                    txt: appWindow.txt
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.margins: Theme.spacingMd
                    z: 5
                }

                CanvasOverlay {
                    anchors.fill: parent
                    canvas: canvas
                    txt: appWindow.txt
                    onAoiFinished: {
                        canvas.endAoi()
                        var saved = appWindow.controller.saveAoi(
                            "survey", canvas.aoiPolygon(), canvas.crsName)
                        if (saved && saved.version !== undefined)
                            statusBar.valueUnderCursor =
                                appWindow.txt["aoi.saved"].replace("%1", saved.version)
                    }
                    onAoiCancelled: {
                        canvas.cancelAoi()
                        statusBar.valueUnderCursor = appWindow.txt["aoi.cancelled"]
                    }
                }

                MapToolBar {
                    objectName: "mapToolBar"
                    anchors { left: parent.left; top: parent.top; margins: Theme.spacingMd }
                    canvas: canvas
                    txt: appWindow.txt
                    onLayersRequested: appWindow.layersVisible = !appWindow.layersVisible
                    onFullScreenRequested: appWindow.dispatch("view.fullScreen")
                    onExportRequested: mapExportPicker.open()
                }
            }

            Inspector {
                id: inspector
                visible: appWindow.inspectorVisible
                Layout.preferredWidth: Theme.inspectorWidth
                Layout.fillHeight: true
                controller: appWindow.controller
                description: appWindow.activeDescription
                view: canvas.displayState
                // Re-read when the stack changes: `activeLayer()` is a slot,
                // and `revision` is the notifiable property that makes this
                // binding follow it.
                activeLayer: appWindow.controller.layers.revision >= 0
                             ? appWindow.controller.layers.activeLayer() : ({})
            }
        }

        JobsPanel {
            id: jobsPanel
            objectName: "jobsPanel"
            visible: appWindow.jobsVisible
            Layout.fillWidth: true
            Layout.preferredHeight: collapsed ? 34 : Theme.bottomPanelHeight
            controller: appWindow.controller
            onOpenArtifactRequested: function (path) {
                // Adding it is not enough: the result may sit far from the
                // current view, and a layer you cannot see reads as a layer
                // that was not added.
                var added = appWindow.controller.addLayer(
                    path, "", "result", appWindow.txt["canvas.membershipUnit"])
                if (added.length > 0)
                    canvas.zoomToLayer(added)
            }
        }
    }

    footer: StatusBar {
        id: statusBar
        controller: appWindow.controller
        crsName: canvas.viewCrs
        basemap: canvas.basemapSource
        toolLabel: appWindow.txt["tool." + ({
            "navigate": "navigate", "identify": "identify", "aoi": "aoi",
            "measure-distance": "measureDistance",
            "measure-area": "measureArea"
        }[canvas.toolMode] || "navigate")]
    }

    // What the canvas refuses, said where the person is looking. A measurement
    // in degrees is refused, never approximated (P-14).
    Connections {
        target: canvas
        function onRefused(message) {
            errorDialog.text = message
            errorDialog.detail = ""
            errorDialog.open()
        }
        function onIdentified(x, y, text) {
            statusBar.coordinate = canvas.formatPosition(x, y)
            statusBar.crsLabel = canvas.positionLabel()
            statusBar.valueUnderCursor = text
            // And the panel, which answers for every visible layer rather
            // than only the active one: a person clicks a place to compare
            // what the layers say there.
            identifyPanel.coordinate = canvas.formatPosition(x, y)
            identifyPanel.crsLabel = canvas.positionLabel()
            identifyPanel.readings = canvas.identifyAt(x, y)
        }
    }

    // An artefact reaches the canvas only after the worker closed, validated
    // and hashed it, and the controller registered it against a run.
    Connections {
        target: appWindow.controller
        function onProjectChanged() {
            // Tiles are cached inside the project, so the map that supported a
            // decision reopens with it — and without a network.
            canvas.setBasemapCache(appWindow.controller.basemapCacheDir())
        }
        function onArtifactReady(path, operator) {
            // The artefact becomes a layer in the display stack; the stack is
            // what the canvas draws. Painting it directly would leave the
            // panel and the map with two opinions about what is on screen.
            //
            // What it *is* comes from the operator that made it. Labelling
            // every artefact a membership put "membership [0-1]" beside a
            // harmonized raster still carrying mGal — a raw value under a
            // normalized layer's name, which is the conflation this project
            // forbids outright.
            var role = "result"
            var unit = ""
            if (operator === "decision.membership") {
                role = "membership"
                unit = appWindow.txt["canvas.membershipUnit"]
            } else if (operator === "decision.aggregate") {
                role = "result"
                unit = appWindow.txt["canvas.membershipUnit"]
            } else if (operator === "grid.harmonize") {
                // Harmonization reprojects and resamples; it does not
                // normalize. The values keep the unit they came in with, and
                // this view does not know which layer of the batch this file
                // is, so it claims no unit rather than the wrong one.
                role = "harmonized"
            }
            appWindow.controller.addLayer(path, "", role, unit)
        }
        function onDatasetDescribed(d) {
            appWindow.lastDescription = d
        }
        function onErrorRaised(message, detailRef) {
            errorDialog.text = message
            errorDialog.detail = detailRef
            errorDialog.open()
        }
    }

    // The display stack is the authority on what is drawn. One reconciliation
    // call, every time it changes: no incremental bookkeeping on two sides.
    Connections {
        target: appWindow.controller
        // A table's points reach the canvas here, not through the stack: the
        // display stack carries no coordinates (ADR-MSP-002).
        function onPointsReady(layerId, points) {
            var layer = appWindow.controller.layers.activeLayer()
            canvas.addPointLayer(layerId, points, layer.name || "",
                                 layer.unit || "", layer.crs || "",
                                 appWindow.controller.layerCrsUnit(layerId))
        }
        // A vector's silhouette, for the same reason and by the same route.
        function onLayerDescribed(layerId, description) {
            if (layerId === appWindow.controller.layers.activeId)
                appWindow.activeDescription = description
        }
        function onGeometryReady(layerId, parts) {
            var layer = appWindow.controller.layers.activeLayer()
            canvas.addGeometryLayer(layerId, parts, layer.name || "",
                                    layer.crs || "",
                                    appWindow.controller.layerCrsUnit(layerId))
        }
    }

    Connections {
        target: appWindow.controller.layers
        function onChanged() {
            canvas.applyStack(appWindow.controller.layers.snapshot())
        }
        function onActiveChanged() {
            canvas.setActiveLayer(appWindow.controller.layers.activeId)
            // The panel follows the layer. Cached after the first ask, and
            // the ask is a read-only probe that commits no run.
            var active = appWindow.controller.layers.activeId
            appWindow.activeDescription =
                appWindow.controller.layerDescription(active)
            appWindow.controller.describeLayer(active)
        }
    }

    // Dropping a file on the window is the shortest way in: it opens the
    // wizard on that file, already described and checked. It is a shortcut to
    // the same path, never a way around QA/QC.
    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]
        onEntered: function (drag) { dropHint.visible = true }
        onExited: dropHint.visible = false
        onDropped: function (drop) {
            dropHint.visible = false
            if (!drop.hasUrls || drop.urls.length === 0)
                return
            var first = drop.urls[0].toString().replace("file://", "")
            appWindow.openImport(decodeURIComponent(first))
            drop.accept()
        }
    }

    Rectangle {
        id: dropHint
        visible: false
        anchors.centerIn: parent
        width: hintLabel.implicitWidth + 4 * Theme.spacingLg
        height: 64
        radius: Theme.radius
        color: Theme.surface
        border.color: Theme.accent
        border.width: 2
        z: 1000

        Label {
            id: hintLabel
            anchors.centerIn: parent
            text: appWindow.txt["import.drop"]
            color: Theme.text
            font.pixelSize: Theme.fontLg
        }
    }

    AttributeTable {
        id: attributeTable
        objectName: "attributeTable"
        controller: appWindow.controller
    }

    ProjectHub {
        id: projectHub
        objectName: "projectHub"
        controller: appWindow.controller
    }

    MembershipEditor {
        id: membershipEditor
        objectName: "membershipEditor"
        controller: appWindow.controller
        // Substitui, nunca acumula: aplicar a pertinência duas vezes na
        // mesma camada é **corrigir** a curva, não criar um segundo critério
        // sobre o mesmo raster. Antes disso a lista mostrava a mesma camada
        // duas vezes e a agregação a contava duas vezes.
        // Preenchida em `openMembership`, não aqui: uma chamada de função
        // numa ligação de propriedade é avaliada **uma vez**, na carga do
        // shell, quando ainda não há camada nenhuma — o combo ficava vazio
        // para sempre.
        onLayerChosen: function (layerId) {
            appWindow.controller.layers.setActive(layerId)
            appWindow.openMembership()
        }
        onMembershipChosen: function (spec) {
            appWindow.setCriterion(spec)
            // E produz o mapa normalizado, que é o que a etapa 5 promete
            // entregar. Sem isso o critério existia só como linha numa lista:
            // ninguém via a pertinência antes de combiná-la, que é justamente
            // onde uma curva mal escolhida se reconhece.
            appWindow.runMembership(spec)
        }
    }

    // O editor de pertinência precisa da camada, e ele **não a recebia**: era
    // instanciado só com o controller, e `criterion` ficava `{}`. O resultado
    // é o que apareceu na tela de quem usou — "sem distribuição", âncoras
    // vazias e nenhuma curva, com o Inspector logo ao lado mostrando a faixa
    // e o histograma da mesma camada.
    //
    // A descrição vem de `layerDescription`, que é a mesma fonte que o
    // Inspector lê — e não da última coisa que o wizard descreveu, que é uma
    // camada diferente sempre que algo foi calculado.
    Connections {
        target: appWindow.controller
        function onLayerDescribed(layerId, description) {
            if (membershipEditor.visible
                && layerId === appWindow.controller.layers.activeId)
                membershipEditor.criterion = appWindow.buildCriterion(description)
        }
    }

    PreferencesDialog {
        id: preferencesDialog
        objectName: "preferencesDialog"
        controller: appWindow.controller
        txt: appWindow.txt
    }

    GriddingDialog {
        id: griddingDialog
        objectName: "griddingDialog"
        controller: appWindow.controller
        txt: appWindow.txt
    }

    HarmonizeDialog {
        id: harmonizeDialog
        objectName: "harmonizeDialog"
        controller: appWindow.controller
        txt: appWindow.txt
    }

    // Renaming a layer renames the **view** of a dataset, never the dataset:
    // the same file may sit in the stack twice, raw and normalized, and
    // telling them apart is what the name is for (ADR-MSP-002).
    Dialog {
        id: renameDialog
        objectName: "renameDialog"
        title: appWindow.txt["layer.rename.title"]
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 380
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: {
            var active = appWindow.controller.layers.activeLayer()
            renameField.text = (active && active.name) ? active.name : ""
            renameField.selectAll()
            renameField.forceActiveFocus()
        }
        onAccepted: appWindow.controller.layers.setName(
                        appWindow.controller.layers.activeId, renameField.text)

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.spacingSm
            Label {
                text: appWindow.txt["layer.rename.explain"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            TextField {
                id: renameField
                objectName: "renameField"
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                onAccepted: renameDialog.accept()
            }
        }
    }

    DecisionModel {
        id: decisionModel
        objectName: "decisionModel"
        controller: appWindow.controller
        criteria: appWindow.criteria
        ahp: appWindow.lastAhp
        correlations: appWindow.lastCorrelations
        onRunRequested: function (request) { appWindow.runDecision(request) }
    }

    PotentialFieldsDialog {
        id: potentialFieldsDialog
        objectName: "potentialFieldsDialog"
        controller: appWindow.controller
        onRunRequested: function (operator, params, inputs) {
            appWindow.controller.submit(operator, params, inputs)
        }
    }

    ScenariosDialog {
        id: scenariosDialog
        objectName: "scenariosDialog"
        controller: appWindow.controller
        onRunRequested: function (operator, params) {
            appWindow.controller.measureScenario(operator, params)
        }
    }

    ImportWizard {
        id: importWizard
        // Named so a headless driver can reach it. Evidence of this screen has
        // to come from the real screen, and driving it needs a handle.
        objectName: "importWizard"
        controller: appWindow.controller
    }

    // ---- what the menus open ---------------------------------------------

    FileDialog {
        id: diagnosticPicker
        objectName: "diagnosticPicker"
        title: appWindow.txt["dialog.diagnostic.title"]
        fileMode: FileDialog.SaveFile
        nameFilters: ["JSON (*.json)"]
        onAccepted: appWindow.controller.exportDiagnostic(
                        selectedFile.toString().replace("file://", ""))
    }

    FileDialog {
        id: mapExportPicker
        objectName: "mapExportPicker"
        title: appWindow.txt["dialog.exportMap.title"]
        fileMode: FileDialog.SaveFile
        nameFilters: ["PNG (*.png)"]
        onAccepted: {
            // A picture of the view, with its colour bar, scale bar and CRS —
            // exactly what is on screen. It creates no run and registers no
            // artefact, because it is not a result.
            var target = selectedFile.toString().replace("file://", "")
            mapContainer.grabToImage(function (result) { result.saveToFile(target) })
        }
    }

    // The guide is the model itself, read out. A second, written description
    // of the flow would be a second source, and it would drift.
    Dialog {
        id: workflowGuide
        objectName: "workflowGuide"
        title: appWindow.txt["dialog.guide.title"]
        modal: true
        width: 640
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok

        ColumnLayout {
            width: parent ? parent.width : 600
            spacing: Theme.spacingSm

            Label {
                text: appWindow.txt["dialog.guide.intro"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Repeater {
                model: appWindow.controller.workflow
                delegate: RowLayout {
                    required property int number
                    required property string titleKey
                    required property string purposeKey
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    Label {
                        text: number + "."
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 16
                    }
                    Label {
                        text: appWindow.txt[titleKey]
                        color: Theme.text
                        font.pixelSize: Theme.fontSm
                        font.bold: true
                        Layout.preferredWidth: 110
                    }
                    Label {
                        text: appWindow.txt[purposeKey]
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    Dialog {
        id: shortcutsDialog
        objectName: "shortcutsDialog"
        title: appWindow.txt["dialog.shortcuts.title"]
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok

        GridLayout {
            columns: 2
            columnSpacing: Theme.spacingLg
            rowSpacing: Theme.spacingXs

            component Key: Label {
                color: Theme.text
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
            }
            component What: Label {
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }

            Key { text: "Ctrl+N" }       What { text: appWindow.txt["menu.file.new"] }
            Key { text: "Ctrl+O" }       What { text: appWindow.txt["menu.file.open"] }
            Key { text: "Ctrl+I" }       What { text: appWindow.txt["menu.file.import"] }
            Key { text: "Ctrl+Z" }       What { text: appWindow.txt["menu.edit.undo"] }
            Key { text: "Ctrl+Shift+Z" } What { text: appWindow.txt["menu.edit.redo"] }
            Key { text: "F11" }          What { text: appWindow.txt["menu.view.fullScreen"] }
            Key { text: "F1" }           What { text: appWindow.txt["menu.help.workflow"] }
        }
    }

    Dialog {
        id: versionsDialog
        objectName: "versionsDialog"
        title: appWindow.txt["dialog.versions.title"]
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok

        GridLayout {
            columns: 2
            columnSpacing: Theme.spacingLg
            rowSpacing: Theme.spacingXs

            Label { text: appWindow.txt["inspector.app"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
            Label {
                text: appWindow.controller.appVersion
                color: Theme.text; font.pixelSize: Theme.fontSm; font.family: Theme.fontMono
            }
            Label { text: appWindow.txt["inspector.worker"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
            Label {
                text: appWindow.controller.workerVersion
                color: Theme.text; font.pixelSize: Theme.fontSm; font.family: Theme.fontMono
            }
            Label { text: appWindow.txt["inspector.project"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
            Label {
                text: appWindow.controller.projectName.length > 0
                      ? appWindow.controller.projectName
                      : appWindow.txt["dialog.versions.none"]
                color: Theme.text; font.pixelSize: Theme.fontSm; font.family: Theme.fontMono
            }
        }
    }

    Dialog {
        id: aboutDialog
        objectName: "aboutDialog"
        title: appWindow.txt["dialog.about.title"]
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok

        ColumnLayout {
            spacing: Theme.spacingSm
            Label {
                text: "GeoPotential Professional"
                color: Theme.text
                font.pixelSize: Theme.fontLg
                font.bold: true
            }
            Label {
                Layout.maximumWidth: 460
                wrapMode: Text.WordWrap
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                text: appWindow.txt["dialog.about.body"]
            }
        }
    }

    Dialog {
        id: errorDialog
        property string text: ""
        property string detail: ""
        anchors.centerIn: parent
        modal: true
        title: appWindow.txt["dialog.error.title"]
        standardButtons: Dialog.Ok
        ColumnLayout {
            spacing: Theme.spacingSm
            Label {
                text: errorDialog.text
                wrapMode: Text.WordWrap
                Layout.maximumWidth: 460
                color: Theme.text
            }
            Label {
                visible: errorDialog.detail.length > 0
                text: appWindow.txt["dialog.error.detail"].replace("%1", errorDialog.detail)
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
        }
    }

    // The shell opens on the workspace, not on a dialog. With no project the
    // workflow's step 1 is highlighted and says what to do; a modal in the way
    // of an application that has just started is a modal nobody asked for.
    Component.onCompleted: {
        appWindow.applyPanels()
        controller.startWorker()
    }
    onClosing: controller.shutdown()
}
