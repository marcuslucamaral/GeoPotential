import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// §9.4 — a bancada de campos potenciais. MSP-14, MSP-15.
//
// Os sete requisitos da seção, e onde cada um está:
//
//   selecionar operador     o seletor, com o que cada um faz numa linha
//   definir parâmetros      os campos que aquele operador realmente aceita
//   comparar orig./proc.    o resultado entra como camada, ao lado do original
//   registrar convenções    o bloco de convenção, sempre visível
//   visualizar warnings     o alerta de instabilidade da RTP, em amarelo
//   executar                o botão
//   reproduzir              tudo o que é enviado vai para o manifesto da run
//
// **A borda é um parâmetro, não um detalhe.** Padding e taper aparecem na
// tela porque a diferença entre 10 % e 50 % de extensão é visível no
// resultado, e um filtro espectral cuja borda não foi escolhida é um filtro
// cujo resultado ninguém reproduz.
//
// **Nada aqui interpreta.** O tilt realça bordas; não as encontra. O espectro
// radial é diagnóstico e não devolve profundidade — o §23 proíbe transformar
// diagnóstico espectral em interpretação automática, e a tela repete isso onde
// alguém possa esquecer.
Dialog {
    id: root

    required property var controller
    readonly property var txt: controller.tr.strings

    // A camada sobre a qual o filtro roda. Um campo potencial é um raster
    // numa grade métrica; a tela não escolhe por ninguém.
    property var layers: []
    property int selected: -1

    // O que o dado **é**. Cinco das transformações só existem porque o campo
    // satisfaz Laplace; num dado que não satisfaz, elas calculam uma
    // quantidade que não existe. Declarado, e não adivinhado a partir da
    // unidade — que nem sempre está no arquivo.
    property string fieldKind: "gravity"
    property string operator: "potential_fields.tilt"
    property string axis: "z"
    property string order: "1"
    // Não `height`: `Dialog` já tem uma, e a dele é a altura da janela.
    // Duas coisas com um nome só é como um campo de altura de continuação
    // passa a redimensionar o diálogo.
    property string continuationHeight: "1000"
    property string inclination: "-30"
    property string declination: "-21"
    property string padFraction: "0.25"
    property string taper: "1.0"

    signal runRequested(string operator, var params, var inputs)

    readonly property var layer: (selected >= 0 && selected < layers.length)
                                 ? layers[selected] : null

    // Cada operador, o que ele faz, e o que ele pede. As chaves são os nomes
    // dos operadores e não são traduzidas: só os rótulos são, para uma
    // mudança de idioma não trocar qual operador um clique seleciona.
    // `harmonic`: precisa que o campo seja potencial. `magneticOnly`: só faz
    // sentido em magnetometria.
    readonly property var operators: [
        {"key": "potential_fields.derivative",                 "needs": "axis",
         "harmonic": false, "magneticOnly": false},
        {"key": "potential_fields.total_horizontal_gradient",  "needs": "",
         "harmonic": false, "magneticOnly": false},
        {"key": "potential_fields.analytic_signal",            "needs": "",
         "harmonic": true,  "magneticOnly": false},
        {"key": "potential_fields.tilt",                       "needs": "",
         "harmonic": true,  "magneticOnly": false},
        {"key": "potential_fields.upward_continuation",        "needs": "height",
         "harmonic": true,  "magneticOnly": false},
        {"key": "potential_fields.regional_residual",          "needs": "height",
         "harmonic": true,  "magneticOnly": false},
        {"key": "potential_fields.rtp",                        "needs": "magnetic",
         "harmonic": true,  "magneticOnly": true}
    ]

    function specOf(key) {
        for (var i = 0; i < operators.length; ++i)
            if (operators[i].key === key) return operators[i]
        return null
    }

    // Por que este operador não está disponível para o campo declarado — a
    // frase que vai no rótulo, do jeito que os menus desabilitados já fazem.
    // Um controle desabilitado não recebe hover, então a razão não pode ficar
    // numa dica.
    function reasonFor(key) {
        var spec = specOf(key)
        if (spec === null)
            return ""
        if (spec.magneticOnly && root.fieldKind !== "magnetic")
            return root.txt["pf.only.magnetic"]
        if (spec.harmonic && root.fieldKind === "other")
            return root.txt["pf.only.potential"]
        // A derivada é o caso em que o eixo decide: d/dz precisa, d/dx não.
        if (key === "potential_fields.derivative" && root.axis === "z"
            && root.fieldKind === "other")
            return root.txt["pf.only.potential"]
        return ""
    }

    readonly property string operatorReason: reasonFor(operator)

    function needsOf(key) {
        for (var i = 0; i < operators.length; ++i)
            if (operators[i].key === key) return operators[i].needs
        return ""
    }

    readonly property string needs: needsOf(operator)
    readonly property bool needsAxis: needs === "axis"
    readonly property bool needsHeight: needs === "height"
    readonly property bool needsMagnetic: needs === "magnetic"
    // MSP-15: perto do equador magnético a RTP amplifica sem limite. O aviso
    // aparece **antes** de executar, e não depois no manifesto.
    readonly property bool unstable:
        needsMagnetic && Math.abs(parseFloat(inclination)) < 30

    readonly property bool ready:
        layer !== null
        && operatorReason.length === 0
        && parseFloat(padFraction) >= 0
        && (!needsHeight || parseFloat(continuationHeight) > 0)

    title: root.txt["pf.title"]
    modal: true
    width: 780
    height: Math.min(660, parent ? parent.height - 2 * Theme.spacingLg : 660)
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
    }

    // `snapshot()` é a pilha inteira como dicionários simples — a mesma que
    // o painel de camadas lê. Um filtro precisa do caminho do arquivo, então
    // uma camada sem caminho (um AOI, um mapa de fundo) fica de fora.
    function reload() {
        var out = []
        var stack = controller.layers.snapshot()
        for (var i = 0; i < stack.length; ++i)
            if (stack[i].path && String(stack[i].path).length > 0)
                out.push(stack[i])
        layers = out
        selected = out.length > 0 ? 0 : -1
    }

    onOpened: root.reload()

    function parameters() {
        var p = {
            "field_kind": root.fieldKind,
            "pad_fraction": parseFloat(root.padFraction),
            "taper": parseFloat(root.taper),
            "result_name": root.resultName(),
            "unit": (root.layer && root.layer.unit) ? root.layer.unit : ""
        }
        if (root.needsAxis) {
            p["axis"] = root.axis
            p["order"] = parseInt(root.order)
        }
        if (root.needsHeight)
            p["height"] = parseFloat(root.continuationHeight)
        if (root.needsMagnetic) {
            p["inclination"] = parseFloat(root.inclination)
            p["declination"] = parseFloat(root.declination)
        }
        return p
    }

    function resultName() {
        var base = root.layer ? String(root.layer.name).replace(/\.[^.]+$/, "")
                              : "field"
        var suffix = root.operator.split(".")[1]
        return base + "_" + suffix + (root.needsAxis ? "_" + root.axis : "")
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
                text: root.txt["pf.explain"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                visible: root.layers.length === 0
                text: root.txt["pf.noLayer"]
                color: Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                visible: root.layers.length > 0
                columns: 2
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingSm

                Label { text: root.txt["pf.field"]; color: Theme.textMuted
                        font.pixelSize: Theme.fontSm }
                ComboBox {
                    objectName: "pfLayer"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    model: {
                        var names = []
                        for (var i = 0; i < root.layers.length; ++i)
                            names.push(root.layers[i].name)
                        return names
                    }
                    currentIndex: root.selected
                    onActivated: root.selected = index
                }

                Label { text: root.txt["pf.kind"]; color: Theme.textMuted
                        font.pixelSize: Theme.fontSm }
                ComboBox {
                    objectName: "pfKind"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    property var keys: ["gravity", "magnetic", "other"]
                    model: [root.txt["pf.kind.gravity"],
                            root.txt["pf.kind.magnetic"],
                            root.txt["pf.kind.other"]]
                    currentIndex: Math.max(0, keys.indexOf(root.fieldKind))
                    onActivated: root.fieldKind = keys[index]
                }

                Label { text: root.txt["pf.operator"]; color: Theme.textMuted
                        font.pixelSize: Theme.fontSm }
                ComboBox {
                    objectName: "pfOperator"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    property var keys: {
                        var k = []
                        for (var i = 0; i < root.operators.length; ++i)
                            k.push(root.operators[i].key)
                        return k
                    }
                    // A razão vai **no rótulo**, e não numa dica: um item
                    // indisponível não recebe hover, e uma razão parada ali é
                    // uma razão que ninguém alcança. É a mesma regra que os
                    // menus desabilitados seguem desde o M5.5.
                    model: {
                        var labels = []
                        for (var i = 0; i < keys.length; ++i) {
                            var why = root.reasonFor(keys[i])
                            labels.push((root.txt["pf.op." + keys[i]] || keys[i])
                                        + (why.length > 0 ? "  —  " + why : ""))
                        }
                        return labels
                    }
                    currentIndex: Math.max(0, keys.indexOf(root.operator))
                    onActivated: root.operator = keys[index]
                }
            }

            // O que o operador escolhido faz, numa linha, e o que ele não faz.
            Label {
                Layout.fillWidth: true
                visible: root.layers.length > 0
                text: root.txt["pf.does." + root.operator] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            // ---- os parâmetros que este operador aceita ------------------
            GridLayout {
                Layout.fillWidth: true
                visible: root.layers.length > 0
                columns: 2
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingSm

                Label { visible: root.needsAxis; text: root.txt["pf.axis"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                RowLayout {
                    visible: root.needsAxis
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    ComboBox {
                        objectName: "pfAxis"
                        Layout.preferredWidth: 150
                        implicitHeight: Theme.controlHeight
                        property var keys: ["x", "y", "z"]
                        model: [root.txt["pf.axis.x"], root.txt["pf.axis.y"],
                                root.txt["pf.axis.z"]]
                        currentIndex: Math.max(0, keys.indexOf(root.axis))
                        onActivated: root.axis = keys[index]
                    }
                    Label { text: root.txt["pf.order"]; color: Theme.textMuted
                            font.pixelSize: Theme.fontSm }
                    TextField {
                        Layout.preferredWidth: 60
                        implicitHeight: Theme.controlHeight
                        text: root.order
                        font.family: Theme.fontMono
                        onTextChanged: root.order = text
                    }
                }

                Label { visible: root.needsHeight; text: root.txt["pf.height"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                RowLayout {
                    visible: root.needsHeight
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        objectName: "pfHeight"
                        Layout.preferredWidth: 110
                        implicitHeight: Theme.controlHeight
                        text: root.continuationHeight
                        validator: DoubleValidator { bottom: 0 }
                        font.family: Theme.fontMono
                        onTextChanged: root.continuationHeight = text
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.txt["pf.height.hint"]
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                    }
                }

                Label { visible: root.needsMagnetic
                        text: root.txt["pf.field.geomagnetic"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                RowLayout {
                    visible: root.needsMagnetic
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    Label { text: root.txt["pf.symbol.inclination"]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm }
                    TextField {
                        objectName: "pfInclination"
                        Layout.preferredWidth: 80
                        implicitHeight: Theme.controlHeight
                        text: root.inclination
                        font.family: Theme.fontMono
                        onTextChanged: root.inclination = text
                    }
                    Label { text: root.txt["pf.symbol.declination"]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm }
                    TextField {
                        Layout.preferredWidth: 80
                        implicitHeight: Theme.controlHeight
                        text: root.declination
                        font.family: Theme.fontMono
                        onTextChanged: root.declination = text
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.txt["pf.degrees"]
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                }

                // A borda é um parâmetro. Sempre visível, para todo operador.
                Label { text: root.txt["pf.border"]; color: Theme.textMuted
                        font.pixelSize: Theme.fontSm }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        objectName: "pfPadding"
                        Layout.preferredWidth: 70
                        implicitHeight: Theme.controlHeight
                        text: root.padFraction
                        font.family: Theme.fontMono
                        onTextChanged: root.padFraction = text
                    }
                    Label { text: root.txt["pf.taper"]; color: Theme.textMuted
                            font.pixelSize: Theme.fontSm }
                    TextField {
                        Layout.preferredWidth: 70
                        implicitHeight: Theme.controlHeight
                        text: root.taper
                        font.family: Theme.fontMono
                        onTextChanged: root.taper = text
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.txt["pf.border.hint"]
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // Por que este operador não vale para este campo. Aparece antes
            // de executar, e o botão fica desabilitado junto.
            Rectangle {
                Layout.fillWidth: true
                visible: root.operatorReason.length > 0
                Layout.preferredHeight: kindWarning.implicitHeight
                                        + 2 * Theme.spacingSm
                color: Theme.surfaceAlt
                border.color: Theme.warn
                radius: Theme.radius

                Label {
                    id: kindWarning
                    objectName: "pfKindWarning"
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    text: root.operatorReason
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }

            // ---- o alerta, antes de executar (MSP-15) --------------------
            Rectangle {
                Layout.fillWidth: true
                visible: root.unstable
                Layout.preferredHeight: warning.implicitHeight + 2 * Theme.spacingSm
                color: Theme.surfaceAlt
                border.color: Theme.warn
                radius: Theme.radius

                Label {
                    id: warning
                    objectName: "pfWarning"
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    text: root.txt["pf.rtp.unstable"]
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }

            // ---- as convenções, sempre (FIS-02) -------------------------
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: conventions.implicitHeight
                                        + 2 * Theme.spacingSm
                color: Theme.surfaceAlt
                border.color: Theme.border
                radius: Theme.radius

                Label {
                    id: conventions
                    objectName: "pfConventions"
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    text: root.txt["pf.conventions"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
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
                text: root.ready ? root.txt["pf.willRun"].replace(
                                       "%1", root.resultName())
                                 : root.txt["pf.blocked"]
                color: root.ready ? Theme.ok : Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
            Button {
                text: root.txt["dialog.close"]
                onClicked: root.close()
            }
            Button {
                objectName: "pfRun"
                text: root.txt["pf.run"]
                enabled: root.ready
                highlighted: enabled
                onClicked: {
                    root.runRequested(root.operator, root.parameters(),
                                      [root.layer.path])
                    root.close()
                }
            }
        }
    }
}
