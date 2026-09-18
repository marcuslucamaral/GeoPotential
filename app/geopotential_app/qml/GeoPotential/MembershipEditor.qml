import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 9.5 — the Membership Editor.
//
// MSP-07 asks for five things shown **at the same time**: histogram, unit,
// physical sense, curve, spatial preview. Simultaneity is the requirement, not
// a layout preference — choosing anchors while looking at the distribution is
// a different act from choosing them from a form, and the second one produces
// anchors that sit in empty parts of the range.
//
// So the curve is drawn over the histogram, on one horizontal axis in the
// data's own unit, with the direction stated in words beside it.
Dialog {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    title: root.txt["membership.title"]
    modal: true
    width: 820
    height: 620
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton

    // The criterion being shaped: its path, its statistics, its unit.
    property var criterion: ({})
    property string functionName: "linear_increasing"
    // Direcional. Em graus: o azimute que recebe pertinência 1, e a distância
    // angular que recebe 0,5. **Não** reaproveita `spread`, que já existe
    // para small/large e é um intervalo de valores, não um ângulo — duas
    // grandezas diferentes com um nome só é como uma passa a ser lida como a
    // outra.
    property string preferred: "0"
    property string angularSpread: "90"
    property string xMin: ""
    property string xMax: ""
    property string midpoint: ""
    property string centre: ""
    property string spread: "5"
    property bool higherIsBetter: true

    signal membershipChosen(var spec)
    //: Trocar a camada sem fechar o diálogo.
    signal layerChosen(string layerId)

    //: As camadas que podem receber uma pertinência: harmonizadas e
    //: originais em grade. Um mapa de fundo não pode, e uma tabela ainda não
    //: virou grade — oferecê-las seria oferecer uma escolha que falha.
    property var choosable: []

    readonly property int indexOfCurrent: {
        for (var i = 0; i < choosable.length; ++i)
            if (choosable[i].path === (criterion.path || ""))
                return i
        return -1
    }

    readonly property var stats: criterion.statistics || ({})
    readonly property bool ready: stats.min !== undefined

    // ---- classes -------------------------------------------------------
    // Geologia, uso do solo e solo não têm curva: têm um código por classe e
    // uma nota por código. `membership.categorical` recusa qualquer código
    // que não recebeu nota — silenciosamente pontuar zero transformaria uma
    // lacuna de dado em afirmação científica — então a tela precisa listar os
    // códigos que o arquivo realmente tem, e não deixar aplicar até que todos
    // tenham nota.
    readonly property var classInfo: stats.classes || null
    readonly property bool isCategorical: functionName === "categorical"
    readonly property var classCodes: classInfo && classInfo.codes ? classInfo.codes : []
    // A legenda, quando o arquivo traz uma: um nome por código, na mesma ordem
    // em que os códigos são listados, e a origem da afirmação junto.
    readonly property var classNames: classInfo && classInfo.labels
                                      ? classInfo.labels : []
    readonly property bool hasLegend: classNames.length > 0
    readonly property string legendSource: classInfo && classInfo.label_source
                                           ? classInfo.label_source : ""
    // Quantos códigos a legenda **não** nomeia. Uma legenda parcial é um
    // estado real, e é diferente de não ter legenda nenhuma.
    readonly property int classesUnnamed: {
        var n = 0
        for (var i = 0; i < classNames.length; ++i)
            if (!classNames[i]) n += 1
        return n
    }

    function classLabel(index) {
        return index >= 0 && index < classNames.length
               ? String(classNames[index]) : ""
    }
    // {código: nota}, sempre como texto — é o que o campo edita, e um número
    // meio digitado ("0.") não é um número.
    property var classScores: ({})

    // Quantas classes ainda estão sem nota. Zero é o que libera o Aplicar.
    readonly property int classesMissing: {
        var n = 0
        for (var i = 0; i < classCodes.length; ++i) {
            var raw = classScores[String(classCodes[i])]
            var v = parseFloat(raw)
            if (raw === undefined || raw === "" || isNaN(v) || v < 0 || v > 1)
                n += 1
        }
        return n
    }

    function setClassScore(code, text) {
        // Reatribuir o objeto inteiro: mudar uma chave dentro dele não
        // dispara a notificação da propriedade, e `classesMissing` ficaria
        // parado no valor anterior.
        var next = {}
        for (var k in root.classScores) next[k] = root.classScores[k]
        next[String(code)] = text
        root.classScores = next
    }

    function classMapping() {
        var out = {}
        for (var i = 0; i < classCodes.length; ++i) {
            var code = classCodes[i]
            out[String(code)] = parseFloat(root.classScores[String(code)])
        }
        return out
    }

    background: Rectangle {
        color: Theme.surface
        border.color: Theme.border
        radius: Theme.radius
    }
    header: Label {
        text: root.title + (root.criterion.name ? " — " + root.criterion.name : "")
        color: Theme.text
        font.pixelSize: Theme.fontLg
        font.bold: true
        padding: Theme.spacingMd
    }

    // The physical sense, in words. A direction expressed only as a function
    // name is a direction nobody checks.
    readonly property string physicalSense: {
        switch (functionName) {
        case "linear_increasing": return "more is more favourable"
        case "linear_decreasing": return "less is more favourable"
        case "sigmoidal":         return higherIsBetter
                                    ? "more is more favourable, with a soft threshold"
                                    : "less is more favourable, with a soft threshold"
        case "gaussian":          return "a middle value is most favourable"
        case "small":             return "small values are favourable"
        case "large":             return "large values are favourable"
        // Direção não é grandeza: 359° e 1° estão a dois graus um do outro, e
        // toda função acima os poria nas pontas opostas da faixa.
        case "circular":          return "a direction is most favourable"
        // Classe não é magnitude: entre geologia 2 e geologia 3 não há "mais".
        case "categorical":       return "each class carries the score it was given"
        default:                  return ""
        }
    }

    function spec() {
        var s = {
            "path": root.criterion.path || "",
            "name": root.criterion.name || "",
            "unit": root.criterion.unit || "",
            "function": root.functionName,
            "higher_is_better": root.higherIsBetter
        }
        // Categórica não tem âncora: tem a tabela. Mandar as duas coisas faria
        // o worker escolher, e quem escolhe é esta tela.
        if (root.isCategorical) {
            s["mapping"] = root.classMapping()
            return s
        }
        if (xMin.length > 0) s["x_min"] = parseFloat(xMin)
        if (xMax.length > 0) s["x_max"] = parseFloat(xMax)
        if (midpoint.length > 0) s["midpoint"] = parseFloat(midpoint)
        if (centre.length > 0) s["center"] = parseFloat(centre)
        if (spread.length > 0) s["spread"] = parseFloat(spread)
        return s
    }

    // Fill the anchors from the data the first time, so the operator adjusts
    // a real starting point instead of typing into empty fields.
    // Read from `criterion` directly, never through `ready` or `stats`: those
    // are bindings on the same property, and inside its change handler they
    // have not re-evaluated yet. Going through them left every anchor empty,
    // which made the curve a flat line along the bottom — drawn, and
    // meaningless. The storyboard caught it by counting pixels of the curve's
    // own colour.
    // A camada que as notas de classe pertencem. Trocar de camada zera a
    // tabela; a descrição da **mesma** camada chegando depois não zera, ou o
    // que já foi digitado se perderia quando o worker responde.
    property string scoredPath: ""

    onCriterionChanged: {
        var path = (criterion && criterion.path) || ""
        if (path !== scoredPath) {
            // **Toda** âncora é da camada anterior, não só as notas de classe.
            // Guardá-las ao trocar de camada produziu um mapa cientificamente
            // errado e silencioso: aberto numa camada de 2,25 a 2,86 e
            // reaberto num MDE de 120 a 1005, o `x_max` continuava 100 e todo
            // pixel saturava em 1 — a faixa do resultado saía "1,0000 a
            // 1,0000" e nada na tela dizia por quê.
            scoredPath = path
            classScores = ({})
            xMin = ""
            xMax = ""
            midpoint = ""
            centre = ""
        }
        // As estatísticas podem chegar depois do caminho: o pedido é
        // read-only e a resposta vem pelo sinal. Por isso preencher é uma
        // segunda fase, e não um `else` da primeira.
        var s = criterion && criterion.statistics ? criterion.statistics : null
        if (!s || s.min === undefined) return
        var mid = Number((s.min + s.max) / 2).toPrecision(6)
        if (xMin.length === 0) xMin = Number(s.min).toPrecision(6)
        if (xMax.length === 0) xMax = Number(s.max).toPrecision(6)
        if (midpoint.length === 0) midpoint = mid
        if (centre.length === 0) centre = mid
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingMd

        // ---- the distribution, with the curve on top -------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 220
            color: Theme.surfaceAlt
            border.color: Theme.border
            radius: Theme.radius

            Histogram {
                txt: root.txt
                id: distribution
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                counts: root.stats.histogram ? root.stats.histogram.counts : []
                edges: root.stats.histogram ? root.stats.histogram.edges : []
                unit: root.criterion.unit || ""
            }

            // The curve, in the same horizontal coordinates as the histogram.
            //
            // Drawn as a Repeater of segments rather than with `Canvas`:
            // Canvas does not composite under the offscreen platform, so the
            // curve was missing from every captured frame while appearing
            // correct in a live window. A declarative polyline renders the
            // same way everywhere, which is what makes the evidence usable.
            //
            // Sampling the membership here would put a scientific rule in the
            // view. The authoritative implementation is
            // `worker/decision/membership.py`; this draws the shape so anchors
            // can be chosen against the distribution, and the spatial preview
            // is what proves the two agree.
            Item {
                id: curve
                anchors.fill: distribution
                anchors.bottomMargin: 16
                readonly property int segments: 96

                Repeater {
                    model: curve.segments
                    delegate: Rectangle {
                        required property int index
                        readonly property real y0: curve.heightAt(index)
                        readonly property real y1: curve.heightAt(index + 1)
                        x: index * (curve.width / curve.segments)
                        width: Math.max(2, curve.width / curve.segments + 1)
                        y: Math.min(y0, y1)
                        height: Math.max(2, Math.abs(y1 - y0))
                        color: Theme.warn
                        // Uma curva sobre códigos de classe desenharia uma
                        // ordem que não existe entre eles.
                        visible: root.ready && !root.isCategorical
                    }
                }

                function heightAt(i) {
                    if (!root.ready) return height
                    var lo = root.stats.min, hi = root.stats.max
                    if (!(hi > lo)) return height
                    var x = lo + (hi - lo) * (i / segments)
                    return height - root.membershipAt(x) * height
                }
            }

            Label {
                anchors { left: parent.left; top: parent.top; margins: Theme.spacingSm }
                text: "1.0"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            Label {
                anchors { right: parent.right; top: parent.top; margins: Theme.spacingSm }
                text: root.physicalSense
                color: Theme.warn
                font.pixelSize: Theme.fontSm
            }
        }

        // ---- the controls -----------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            // Qual camada recebe a pertinência, escolhida **aqui**.
            //
            // Antes era preciso fechar o diálogo, clicar na camada certa no
            // painel e reabrir — a tela agia sobre a camada ativa e não dizia
            // que agia, nem deixava trocar.
            ColumnLayout {
                Label { text: root.txt["membership.layer"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                ComboBox {
                    objectName: "membershipLayer"
                    model: root.choosable
                    textRole: "name"
                    currentIndex: root.indexOfCurrent
                    onActivated: root.layerChosen(
                        root.choosable[currentIndex].layerId)
                    Layout.preferredWidth: 230
                    enabled: root.choosable.length > 1
                }
            }
            ColumnLayout {
                Label { text: root.txt["membership.function"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                ComboBox {
                    objectName: "membershipFunction"
                    model: ["linear_increasing", "linear_decreasing", "sigmoidal",
                            "gaussian", "small", "large", "circular", "categorical"]
                    currentIndex: Math.max(0, model.indexOf(root.functionName))
                    onActivated: root.functionName = currentText
                    Layout.preferredWidth: 190
                }
            }
            ColumnLayout {
                visible: root.functionName.indexOf("linear") === 0
                Label { text: root.txt["membership.xmin"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    text: root.xMin
                    onTextEdited: root.xMin = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            ColumnLayout {
                visible: root.functionName.indexOf("linear") === 0
                Label { text: root.txt["membership.xmax"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    text: root.xMax
                    onTextEdited: root.xMax = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            ColumnLayout {
                visible: root.functionName === "small" || root.functionName === "large"
                Label { text: root.txt["membership.midpoint"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    text: root.midpoint
                    onTextEdited: root.midpoint = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            ColumnLayout {
                visible: root.functionName === "sigmoidal" || root.functionName === "gaussian"
                Label { text: root.txt["membership.centre"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    text: root.centre
                    onTextEdited: root.centre = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            // Direcional: o azimute preferido e a distância angular que vale
            // meia pertinência. Em graus, os dois.
            ColumnLayout {
                visible: root.functionName === "circular"
                Label { text: root.txt["membership.preferred"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    objectName: "membershipPreferred"
                    text: root.preferred
                    onTextEdited: root.preferred = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            ColumnLayout {
                visible: root.functionName === "circular"
                Label { text: root.txt["membership.spread"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                TextField {
                    text: root.angularSpread
                    onTextEdited: root.angularSpread = text
                    Layout.preferredWidth: 110
                    font.pixelSize: Theme.fontSm
                }
            }
            Item { Layout.fillWidth: true }
        }

        // ---- a tabela de classes -----------------------------------------
        // Um código por linha, com a fração de área que ele ocupa e a nota que
        // recebe. A fração está aqui porque uma classe que cobre 0,3 % do mapa
        // e uma que cobre 40 % não merecem o mesmo cuidado, e sem o número a
        // tela não deixa isso ver.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 180
            visible: root.isCategorical
            color: Theme.surfaceAlt
            border.color: root.classesMissing > 0 ? Theme.warn : Theme.border
            radius: Theme.radius

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                spacing: Theme.spacingSm

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd
                    Label {
                        text: root.txt["membership.class.code"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 70
                    }
                    // A coluna do nome só existe quando o arquivo diz um. Uma
                    // coluna vazia em toda linha seria a tela prometendo uma
                    // legenda que não tem.
                    Label {
                        visible: root.hasLegend
                        text: root.txt["membership.class.name"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 170
                    }
                    Label {
                        text: root.txt["membership.class.share"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 80
                    }
                    Label {
                        text: root.txt["membership.class.score"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                    }
                    Item { Layout.fillWidth: true }
                    // De onde vieram os nomes. Um rótulo afirma o que um
                    // código significa, e uma afirmação sem origem não é
                    // conferível.
                    Label {
                        objectName: "membershipLegendSource"
                        visible: root.hasLegend
                        text: (root.txt["membership.class.legend"] || "")
                                  .replace("%1", root.legendSource)
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                    }
                    Label {
                        objectName: "membershipClassCount"
                        text: root.classCodes.length + " " + root.txt["membership.classes"]
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                    }
                }

                // Sem códigos não há tabela, e o motivo é diferente conforme o
                // caso: ou a camada é contínua, ou tem classes demais para
                // pontuar à mão. Dizer qual é dos dois é o que permite agir.
                Label {
                    objectName: "membershipClassNotice"
                    Layout.fillWidth: true
                    visible: root.classCodes.length === 0
                    wrapMode: Text.WordWrap
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    text: !root.classInfo
                          ? root.txt["membership.class.none"]
                          : root.txt["membership.class.tooMany"]
                                .replace("%1", root.classInfo.distinct)
                                .replace("%2", root.classInfo.limit)
                }

                ListView {
                    objectName: "membershipClassTable"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.classCodes.length > 0
                    clip: true
                    model: root.classCodes
                    spacing: 2
                    ScrollBar.vertical: ScrollBar {}

                    delegate: RowLayout {
                        required property int index
                        required property var modelData
                        width: ListView.view ? ListView.view.width : 0
                        spacing: Theme.spacingMd

                        readonly property int count: root.classInfo
                            && root.classInfo.counts
                            ? root.classInfo.counts[index] : 0

                        Label {
                            text: Number(parent.modelData).toFixed(0)
                            color: Theme.text
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                            Layout.preferredWidth: 70
                        }
                        // Um código que a legenda não menciona fica visivelmente
                        // sem nome. Inventar "classe 3" faria uma legenda
                        // ausente parecer presente.
                        Label {
                            objectName: "membershipClassName_"
                                        + Number(parent.modelData).toFixed(0)
                            visible: root.hasLegend
                            text: root.classLabel(parent.index) || "—"
                            color: root.classLabel(parent.index)
                                   ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            Layout.preferredWidth: 170
                            elide: Text.ElideRight
                        }
                        Label {
                            text: root.stats.valid
                                  ? (parent.count / root.stats.valid * 100).toFixed(1) + " %"
                                  : "—"
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                            Layout.preferredWidth: 80
                        }
                        TextField {
                            objectName: "membershipClassScore_" + Number(parent.modelData).toFixed(0)
                            text: root.classScores[String(parent.modelData)] || ""
                            placeholderText: "0.0"
                            onTextEdited: root.setClassScore(parent.modelData, text)
                            Layout.preferredWidth: 90
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }

        // Uma legenda parcial é um estado real, e é diferente de não ter
        // legenda nenhuma. Não bloqueia nada: o código sem nome continua
        // pontuável, e quem decide se sabe o bastante é quem pontua.
        Label {
            objectName: "membershipLegendPartial"
            Layout.fillWidth: true
            visible: root.isCategorical && root.hasLegend
                     && root.classesUnnamed > 0
            wrapMode: Text.WordWrap
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            text: (root.txt["membership.class.unnamed"] || "")
                      .replace("%1", root.classesUnnamed)
        }

        // Por que o Aplicar está desligado. Um botão cinza sem motivo é a
        // mesma parede que um erro sem texto.
        Label {
            objectName: "membershipClassMissing"
            Layout.fillWidth: true
            visible: root.isCategorical && root.classesMissing > 0
            wrapMode: Text.WordWrap
            color: Theme.warn
            font.pixelSize: Theme.fontSm
            text: root.txt["membership.class.missing"]
                      .replace("%1", root.classesMissing)
        }

        // ---- what the numbers mean ---------------------------------------
        GridLayout {
            columns: 4
            Layout.fillWidth: true
            columnSpacing: Theme.spacingMd

            component Fact: RowLayout {
                property string key: ""
                property string value: ""
                Layout.fillWidth: true
                Label {
                    text: key; color: Theme.textMuted
                    font.pixelSize: Theme.fontSm; Layout.preferredWidth: 74
                }
                Label {
                    text: value; color: Theme.text
                    font.pixelSize: Theme.fontSm; font.family: Theme.fontMono
                    Layout.fillWidth: true; elide: Text.ElideRight
                }
            }

            Fact { key: "Unit"; value: root.criterion.unit || "—" }
            Fact { key: "Range"; value: root.ready
                    ? Number(root.stats.min).toPrecision(5) + " to "
                      + Number(root.stats.max).toPrecision(5) : "" }
            Fact { key: "Valid"; value: root.ready
                    ? (root.stats.valid_fraction * 100).toFixed(1) + " %" : "" }
            Fact { key: "Result"; value: "membership [0-1], dimensionless" }
        }

        Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            text: root.txt["membership.note"]
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button { text: root.txt["dialog.cancel"]; onClicked: root.close() }
            Button {
                // Named so a headless driver can press the real button.
                objectName: "membershipApply"
                text: root.txt["membership.apply"]
                highlighted: true
                // Categórica só aplica com a tabela inteira preenchida: o
                // worker recusaria o código sem nota de qualquer forma, e
                // recusar aqui diz onde está a lacuna em vez de devolver um
                // job vermelho.
                enabled: root.ready && !(root.isCategorical
                    && (root.classCodes.length === 0 || root.classesMissing > 0))
                onClicked: { root.membershipChosen(root.spec()); root.close() }
            }
        }
    }

    // The curve's shape, for drawing only. The authoritative implementation is
    // `worker/decision/membership.py`; this exists so the operator can see the
    // shape while choosing anchors, and the spatial preview is what proves the
    // two agree.
    function membershipAt(x) {
        var lo = parseFloat(xMin), hi = parseFloat(xMax)
        switch (functionName) {
        case "linear_increasing":
            if (!(hi > lo)) return 0
            return Math.max(0, Math.min(1, (x - lo) / (hi - lo)))
        case "linear_decreasing":
            if (!(hi > lo)) return 0
            return Math.max(0, Math.min(1, (hi - x) / (hi - lo)))
        case "sigmoidal": {
            var c = parseFloat(centre), s = parseFloat(spread) || 1
            var span = (stats.max - stats.min) || 1
            return 1 / (1 + Math.exp(-(s * 4 / span) * (x - c)))
        }
        case "circular": {
            var pref = parseFloat(root.preferred)
            var sp = Math.max(1, parseFloat(root.angularSpread))
            // A distância angular pelo caminho curto, e o cosseno levantado —
            // a mesma conta que `membership.circular` faz no worker.
            var delta = Math.abs(((x - pref + 180) % 360 + 360) % 360 - 180)
            var scaled = Math.min(delta / sp, 2)
            return 0.5 * (1 + Math.cos(Math.PI * scaled / 2))
        }
        case "gaussian": {
            var m = parseFloat(centre)
            var sd = ((stats.max - stats.min) / 6) || 1
            return Math.exp(-0.5 * Math.pow((x - m) / sd, 2))
        }
        case "small": {
            var mp = parseFloat(midpoint) || 1
            return 1 / (1 + Math.pow(Math.max(x, 0) / mp, parseFloat(spread) || 5))
        }
        case "large": {
            var mpl = parseFloat(midpoint) || 1
            return 1 / (1 + Math.pow(Math.max(x, 1e-9) / mpl, -(parseFloat(spread) || 5)))
        }
        }
        return 0
    }
}
