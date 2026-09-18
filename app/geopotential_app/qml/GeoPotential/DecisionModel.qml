import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 9.6 — the Decision Model.
//
// Groups, criteria, weights, AHP, the consistency ratio, the operator, the
// correlation warnings and the justifications, on one screen — because they
// are one decision. A weight chosen without seeing the consistency ratio, or
// an operator chosen without seeing which criteria are correlated, is a
// decision made with the relevant fact off screen.
//
// The refusals are visible rather than discovered: Run is disabled while the
// matrix is inconsistent, and the reason is on the button.
Dialog {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    title: root.txt["decision.title"]
    modal: true
    width: 860
    height: 660
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton

    property var criteria: []          // [{name, path, unit, function, group}]
    property var ahp: ({})             // the last weights result
    property var correlations: []      // findings from the last aggregation
    property string method: "fuzzy_gamma"
    property real gamma: 0.7
    property string overrideReason: ""

    // ---- os pesos ------------------------------------------------------
    // A combinação linear ponderada **recusa** rodar sem eles, e até `0.8.08`
    // esta tela exibia os do AHP e mandava o pedido sem nenhum: quem escolhia
    // o método ponderado recebia um job vermelho no lugar do mapa.
    //
    // Duas fontes, nesta ordem: o AHP quando ele foi calculado, e a edição
    // direta quando não. Peso igual é o ponto de partida **declarado** — um
    // default silencioso aqui seria uma escolha científica que ninguém fez.
    property var manualWeights: ({})

    //: Quais critérios entram. Ausente da tabela significa "entra": um
    //: critério recém-aplicado não deve precisar ser ligado à mão.
    property var excluded: ({})

    function isUsed(name) { return excluded[name] !== true }

    function use(name, on) {
        var next = {}
        for (var k in excluded) next[k] = excluded[k]
        next[name] = !on
        excluded = next
    }

    //: Os critérios que de fato vão para o operador.
    readonly property var chosen: {
        var out = []
        for (var i = 0; i < criteria.length; ++i)
            if (excluded[criteria[i].name] !== true)
                out.push(criteria[i])
        return out
    }

    readonly property bool usesWeights: method === "weighted_linear_combination"

    //: {nome: peso}, normalizado para somar 1. Pesos que não somam 1 não são
    //: pesos: são uma escala arbitrária que muda o mapa sem dizer.
    readonly property var weightByName: {
        var out = {}, total = 0, i
        for (i = 0; i < chosen.length; ++i) {
            var name = chosen[i].name
            var w = (hasWeights && ahp.weights_by_name[name] !== undefined)
                    ? Number(ahp.weights_by_name[name])
                    : Number(manualWeights[name] !== undefined
                             ? manualWeights[name] : 1)
            if (!(w > 0)) w = 0
            out[name] = w
            total += w
        }
        if (!(total > 0)) {
            // Todos zerados: volta ao igual, porque zero peso em tudo não é
            // uma ponderação, é a ausência de uma.
            for (i = 0; i < chosen.length; ++i)
                out[chosen[i].name] = 1 / Math.max(1, chosen.length)
            return out
        }
        for (i = 0; i < chosen.length; ++i)
            out[chosen[i].name] = out[chosen[i].name] / total
        return out
    }

    //: De onde os pesos vieram. Um peso afirma uma prioridade, e a origem da
    //: afirmação entra na procedência junto com ela.
    readonly property string weightSource: hasWeights ? "ahp" : "manual"

    function setWeight(name, text) {
        var next = {}
        for (var k in manualWeights) next[k] = manualWeights[k]
        next[name] = Number(text)
        manualWeights = next
    }

    //: O pedido que sai desta tela, montado num lugar só.
    //:
    //: `weights` só acompanha o método que os usa: mandá-los para o gamma
    //: registraria na procedência uma escolha que não afetou o resultado.
    function request() {
        var out = {
            "method": root.method,
            "gamma": root.gamma,
            "criteria": root.chosen,
            "override_reason": root.overrideReason
        }
        if (root.usesWeights) {
            var list = []
            for (var i = 0; i < root.chosen.length; ++i) {
                var name = root.chosen[i].name
                list.push({"name": name, "weight": root.weightByName[name]})
            }
            out["weights"] = list
            out["weight_source"] = root.weightSource
        }
        return out
    }

    signal runRequested(var request)

    readonly property bool hasWeights: ahp.weights_by_name !== undefined
    readonly property bool consistent: ahp.consistent === true
    readonly property bool needsOverride: hasWeights && !consistent
                                          && overrideReason.length === 0

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

    contentItem: ColumnLayout {
        spacing: Theme.spacingMd

        // ---- criteria and their weights ---------------------------------
        Label {
            text: root.txt["decision.criteria"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.letterSpacing: 1
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.preferredHeight: 190
            clip: true
            model: root.criteria
            spacing: 2

            Label {
                anchors.centerIn: parent
                visible: list.count === 0
                text: root.txt["decision.noCriteria"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontMd
            }

            delegate: Rectangle {
                required property var modelData
                width: list.width
                height: 34
                color: Theme.surfaceAlt
                radius: Theme.radius

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.spacingSm
                    anchors.rightMargin: Theme.spacingSm
                    spacing: Theme.spacingSm

                    Label {
                        text: modelData.name
                        color: Theme.text
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.preferredWidth: 200
                        elide: Text.ElideRight
                    }
                    // Entra ou não entra nesta análise. Uma tela que só
                    // anuncia o que vai fazer não deixa ninguém mudar de
                    // ideia sem refazer a pertinência de tudo.
                    CheckBox {
                        objectName: "decisionUse_" + modelData.name
                        checked: root.isUsed(modelData.name)
                        onToggled: root.use(modelData.name, checked)
                        implicitHeight: Theme.controlHeight
                    }
                    Label {
                        text: modelData.group || "ungrouped"
                        color: modelData.group ? Theme.accent : Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 110
                    }
                    Label {
                        text: modelData.function || ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 150
                    }
                    Label {
                        text: modelData.unit || ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 60
                    }
                    Item { Layout.fillWidth: true }

                    // The weight, bound by name. The stack's order is
                    // authoritative and this reads from it rather than from a
                    // parallel list that could drift out of step.
                    //
                    // Editável quando não há AHP: o peso é uma decisão, e uma
                    // tela que o mostra sem deixar mudá-lo obriga quem opera a
                    // aceitar o que não escolheu.
                    TextField {
                        objectName: "decisionWeight_" + modelData.name
                        visible: root.usesWeights && !root.hasWeights
                        text: root.manualWeights[modelData.name] !== undefined
                              ? String(root.manualWeights[modelData.name]) : "1"
                        onTextEdited: root.setWeight(modelData.name, text)
                        validator: DoubleValidator { bottom: 0 }
                        horizontalAlignment: Text.AlignRight
                        Layout.preferredWidth: 64
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                    }
                    Label {
                        text: root.usesWeights
                              ? (root.weightByName[modelData.name] * 100).toFixed(1) + " %"
                              : "—"
                        color: root.usesWeights ? Theme.text : Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.preferredWidth: 62
                        horizontalAlignment: Text.AlignRight
                    }
                }
            }
        }

        // ---- the consistency ratio, stated ------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            visible: root.hasWeights
            radius: Theme.radius
            color: Theme.surfaceAlt
            border.color: root.consistent ? Theme.ok : Theme.error

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingSm
                anchors.rightMargin: Theme.spacingSm

                Label {
                    text: root.hasWeights
                          ? "CR = " + root.ahp.cr.toFixed(4)
                            + "  (threshold " + root.ahp.threshold.toFixed(2)
                            + ", lambda max " + root.ahp.lambda_max.toFixed(4) + ")"
                          : ""
                    color: root.consistent ? Theme.text : Theme.error
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: root.consistent
                          ? "consistent"
                          : "inconsistent — the judgments contradict each other"
                    color: root.consistent ? Theme.ok : Theme.error
                    font.pixelSize: Theme.fontSm
                }
            }
        }

        // An override is a person overruling a numerical check. It is typed
        // here, in words, and it goes into the manifest.
        RowLayout {
            Layout.fillWidth: true
            visible: root.hasWeights && !root.consistent
            Label {
                text: root.txt["decision.justification"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                Layout.preferredWidth: 90
            }
            TextField {
                text: root.overrideReason
                onTextEdited: root.overrideReason = text
                placeholderText: root.txt["decision.justification.hint"]
                Layout.fillWidth: true
                font.pixelSize: Theme.fontSm
            }
        }

        // ---- double counting ---------------------------------------------
        Label {
            text: root.txt["decision.correlation"]
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            font.letterSpacing: 1
            visible: root.correlations.length > 0
        }
        Repeater {
            model: root.correlations
            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: warning.implicitHeight + 2 * Theme.spacingSm
                color: Theme.surfaceAlt
                radius: Theme.radius

                Rectangle {
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                    width: 3
                    color: Theme.warn
                    radius: Theme.radius
                }
                Label {
                    id: warning
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    anchors.leftMargin: Theme.spacingMd
                    text: modelData.message
                    color: Theme.text
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }
        }

        Item { Layout.fillHeight: true }

        // ---- operator and run --------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            ColumnLayout {
                Label { text: root.txt["decision.operator"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                ComboBox {
                    model: ["fuzzy_gamma", "fuzzy_product", "fuzzy_sum",
                            "weighted_linear_combination"]
                    currentIndex: Math.max(0, model.indexOf(root.method))
                    onActivated: root.method = currentText
                    Layout.preferredWidth: 220
                }
            }
            ColumnLayout {
                visible: root.method === "fuzzy_gamma"
                Label {
                    text: root.txt["decision.gamma"] + root.gamma.toFixed(2)
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                }
                Slider {
                    from: 0; to: 1; value: root.gamma
                    onMoved: root.gamma = value
                    Layout.preferredWidth: 200
                    ToolTip.text: root.txt["decision.gamma.hint"]
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                }
            }
            Item { Layout.fillWidth: true }
            Button { text: root.txt["decision.close"]; onClicked: root.close() }
            Button {
                objectName: "decisionRun"
                text: root.txt["decision.run"]
                highlighted: enabled
                enabled: root.chosen.length > 0 && !root.needsOverride
                onClicked: {
                    root.runRequested(root.request())
                    root.close()
                }
                ToolTip.text: root.needsOverride
                    ? "The comparison matrix is inconsistent. Revise the "
                      + "judgments, or write a justification above."
                    : (root.chosen.length === 0
                       ? "No criterion is selected to combine."
                       : "Combine the criteria into a suitability map.")
                ToolTip.visible: hovered
                ToolTip.delay: 300
            }
        }
    }
}
