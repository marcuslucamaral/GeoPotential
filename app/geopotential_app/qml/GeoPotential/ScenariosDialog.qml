import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// M6 — o que muda se a escolha tivesse sido outra. MSP-11, §17.
//
// O mapa do M5 responde "onde". Esta tela responde as duas perguntas que
// decidem se alguém age sobre ele:
//
//   **de quais critérios este resultado depende** — tira-se um por vez e
//   mede-se o quanto o mapa e o seu ranking se mexem;
//   **o quanto a resposta depende de um parâmetro** — varre-se gamma, ou o
//   peso de um critério, e mede-se o mesmo.
//
// **Esta tela não decide nada.** Ela mostra o que foi medido e não troca peso
// nenhum, não re-roda a agregação por conta própria e não esconde critério.
// Quem escolhe é quem opera, e é por isso que o botão diz "medir" e não
// "otimizar" (P-173).
//
// Todo número aparece com o tamanho da amostra sobre a qual foi medido
// (P-174): um rho sobre 300 células e um sobre 300 000 não são a mesma
// evidência, e a tabela não deixa confundir os dois.
Dialog {
    id: root

    required property var controller
    readonly property var txt: controller.tr.strings

    // A análise que está sendo questionada. Vem do Decision Model, e é a
    // mesma lista de critérios que produziu o mapa: um cenário medido contra
    // outra análise não mede nada.
    property var criteria: []
    property string method: "fuzzy_gamma"
    property real gamma: 0.7
    property var weights: []

    // O que o worker devolveu. Nulo até alguém pedir.
    property var leaveOneOut: null
    property var sweep: null
    property bool measuring: false

    property string sweptParameter: "gamma"
    property string sweptCriterion: ""

    signal runRequested(string operator, var params)

    readonly property bool ready: criteria.length >= 2
    readonly property bool canSweepGamma: method === "fuzzy_gamma"
    readonly property bool hasWeights: weights.length > 0

    title: root.txt["scenarios.title"]
    modal: true
    width: 900
    height: Math.min(680, parent ? parent.height - 2 * Theme.spacingLg : 680)
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
    }

    // Not `reset()`: `Dialog` already has one, from its standard buttons,
    // and overriding it silently is how a click on Reset stops doing what a
    // reader of the Qt docs expects.
    function clearMeasurements() {
        leaveOneOut = null
        sweep = null
        measuring = false
    }

    // Os parâmetros da análise, montados uma vez. Os dois operadores recebem
    // exatamente os mesmos: eles são o mesmo cálculo com uma coisa mudada.
    function analysis() {
        var p = {
            "criteria": root.criteria,
            "method": root.method,
            "gamma": root.gamma,
            "top_fraction": 0.1
        }
        if (root.weights.length > 0)
            p["weights"] = root.weights
        return p
    }

    function fixed(value, places) {
        return (value === null || value === undefined)
               ? "—" : Number(value).toFixed(places)
    }

    Connections {
        target: root.controller
        function onScenarioMeasured(kind, result) {
            root.measuring = false
            if (kind === "scenarios.leave_one_out")
                root.leaveOneOut = result
            else if (kind === "scenarios.sensitivity")
                root.sweep = result
        }
    }

    contentItem: ScrollView {
        id: scroller
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: scroller.availableWidth
            spacing: Theme.spacingMd

            Label {
                Layout.fillWidth: true
                text: root.txt["scenarios.explain"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                visible: !root.ready
                text: root.txt["scenarios.needsTwo"]
                color: Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            // ---- de quais critérios o resultado depende ------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Label {
                    text: root.txt["scenarios.loo"]
                    color: Theme.text
                    font.pixelSize: Theme.fontMd
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Button {
                    objectName: "scenariosRunLoo"
                    text: root.txt["scenarios.measure"]
                    enabled: root.ready && !root.measuring
                    onClicked: {
                        root.measuring = true
                        root.leaveOneOut = null
                        root.runRequested("scenarios.leave_one_out",
                                          root.analysis())
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                text: root.txt["scenarios.loo.hint"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            // Cabeçalho da tabela. As colunas são as duas perguntas
            // diferentes: quanto o mapa se mexeu, e se as *mesmas* melhores
            // áreas continuam as melhores.
            RowLayout {
                Layout.fillWidth: true
                visible: root.leaveOneOut !== null
                spacing: Theme.spacingSm
                Label { Layout.preferredWidth: 170
                        text: root.txt["scenarios.col.dropped"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                Label { Layout.preferredWidth: 90
                        text: root.txt["scenarios.col.change"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                Label { Layout.preferredWidth: 90
                        text: root.txt["scenarios.col.rho"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                Label { Layout.preferredWidth: 110
                        text: root.txt["scenarios.col.top"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                Label { Layout.fillWidth: true
                        text: root.txt["scenarios.col.cells"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
            }

            Repeater {
                model: (root.leaveOneOut && root.leaveOneOut.criteria)
                       ? root.leaveOneOut.criteria : []
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    // O primeiro da lista é aquele cuja remoção move mais o
                    // mapa: é dele que a resposta mais depende.
                    Label {
                        Layout.preferredWidth: 170
                        text: (index === 0 ? "▸ " : "   ") + modelData.dropped
                        color: index === 0 ? Theme.warn : Theme.text
                        font.pixelSize: Theme.fontSm
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 90
                        text: root.fixed(modelData.mean_abs_change, 4)
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.preferredWidth: 90
                        text: root.fixed(modelData.spearman, 3)
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.preferredWidth: 110
                        text: modelData.top_agreement === null
                              ? "—"
                              : Math.round(modelData.top_agreement * 100) + " %"
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.cells_compared
                        color: Theme.textMuted
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                }
            }

            // A limitação viaja com o resultado. Quem não a conhece vai supor
            // o contrário.
            Label {
                Layout.fillWidth: true
                visible: root.leaveOneOut !== null
                text: root.leaveOneOut ? "⚠ " + root.leaveOneOut.limitation : ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1
                        color: Theme.border }

            // ---- o quanto depende de um parâmetro ------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm

                Label {
                    text: root.txt["scenarios.sweep"]
                    color: Theme.text
                    font.pixelSize: Theme.fontMd
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                ComboBox {
                    objectName: "scenariosParameter"
                    Layout.preferredWidth: 190
                    implicitHeight: Theme.controlHeight
                    property var keys: {
                        var k = []
                        if (root.canSweepGamma) k.push("gamma")
                        if (root.hasWeights) k.push("weight")
                        return k
                    }
                    model: {
                        var labels = []
                        for (var i = 0; i < keys.length; ++i)
                            labels.push(root.txt["scenarios.param." + keys[i]])
                        return labels
                    }
                    currentIndex: Math.max(0, keys.indexOf(root.sweptParameter))
                    onActivated: root.sweptParameter = keys[index]
                }
                ComboBox {
                    objectName: "scenariosCriterion"
                    Layout.preferredWidth: 160
                    implicitHeight: Theme.controlHeight
                    visible: root.sweptParameter === "weight"
                    model: {
                        var names = []
                        for (var i = 0; i < root.criteria.length; ++i)
                            names.push(root.criteria[i].name)
                        return names
                    }
                    onActivated: root.sweptCriterion = currentText
                    Component.onCompleted: {
                        if (root.criteria.length > 0)
                            root.sweptCriterion = root.criteria[0].name
                    }
                }
                Button {
                    objectName: "scenariosRunSweep"
                    text: root.txt["scenarios.measure"]
                    enabled: root.ready && !root.measuring
                             && (root.sweptParameter !== "weight"
                                 || root.sweptCriterion.length > 0)
                    onClicked: {
                        root.measuring = true
                        root.sweep = null
                        var p = root.analysis()
                        p["parameter"] = root.sweptParameter
                        // Uma grade irregular: as pontas, o meio, e o valor
                        // que a run usou. É o que alguém quer ver.
                        p["values"] = root.sweptParameter === "gamma"
                                      ? [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]
                                      : [0.05, 0.2, 0.4, 0.6, 0.8]
                        if (root.sweptParameter === "weight")
                            p["criterion"] = root.sweptCriterion
                        root.runRequested("scenarios.sensitivity", p)
                    }
                }
            }

            Repeater {
                model: (root.sweep && root.sweep.rows) ? root.sweep.rows : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    Label {
                        Layout.preferredWidth: 170
                        text: "   " + root.sweptParameter + " = "
                              + Number(modelData.value).toFixed(2)
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.preferredWidth: 90
                        text: root.fixed(modelData.mean_abs_change, 4)
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.preferredWidth: 90
                        text: root.fixed(modelData.spearman, 3)
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.preferredWidth: 110
                        text: modelData.top_agreement === null
                              ? "—"
                              : Math.round(modelData.top_agreement * 100) + " %"
                        color: Theme.text
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.cells_compared
                        color: Theme.textMuted
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                visible: root.sweep !== null
                text: root.sweep
                      ? root.txt["scenarios.worst"]
                            .replace("%1", root.fixed(
                                root.sweep.worst_mean_abs_change, 4))
                            .replace("%2", root.sweep.worst_top_agreement === null
                                     ? "—"
                                     : Math.round(
                                         root.sweep.worst_top_agreement * 100) + " %")
                      : ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
        }
    }

    footer: Rectangle {
        color: Theme.surface
        implicitHeight: bar.implicitHeight + 2 * Theme.spacingMd

        RowLayout {
            id: bar
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Label {
                Layout.fillWidth: true
                text: root.measuring ? root.txt["scenarios.measuring"]
                                     : root.txt["scenarios.decides"]
                color: root.measuring ? Theme.accent : Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
            Button {
                text: root.txt["dialog.close"] || root.txt["decision.close"]
                onClicked: root.close()
            }
        }
    }
}
