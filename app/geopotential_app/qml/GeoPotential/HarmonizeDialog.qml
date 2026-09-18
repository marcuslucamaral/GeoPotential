import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Step 4 of the workflow: bring every criterion onto one analysis grid.
//
// This screen exists because the grid cannot be inferred. **There is no
// default CRS** (ADR-004), the pixel size decides what the whole analysis
// resolves, and intersection and union are different maps (P-82) — so all
// three are asked for, pre-filled from the data where that is honest, and
// recorded in the run's manifest as chosen.
//
// It computes nothing. It collects four parameters and submits the operator.
Dialog {
    id: root

    required property var controller
    property var txt: ({})

    // What the project holds that can be harmonized, read when the dialog
    // opens rather than kept: the catalogue is the authority.
    property var datasets: []
    property string targetCrs: ""
    property string pixelSize: ""
    property string extentPolicy: "intersection"

    // ---- a prévia das duas políticas -----------------------------------
    // Interseção e união são mapas diferentes, e a diferença é o resultado
    // inteiro: no Utah FORGE, 100 % contra 27,7 % de células com score. Até
    // aqui a escolha era feita antes de qualquer um dos dois números existir.
    // `grid.compare_policies` é read-only — não registra run nem artefato.
    property var comparison: null
    property bool comparing: false

    function policyFacts(name) {
        if (!comparison || !comparison.policies) return null
        for (var i = 0; i < comparison.policies.length; ++i)
            if (comparison.policies[i].policy === name)
                return comparison.policies[i]
        return null
    }

    // As duas dando o mesmo número de células com score é a leitura mais útil
    // que a prévia produz: significa que a união só acrescenta área vazia.
    readonly property bool sameScoredArea: {
        var a = policyFacts("intersection"), b = policyFacts("union")
        return !!(a && b && a.available && b.available
                  && a.scored_cells === b.scored_cells)
    }

    function compare() {
        if (!root.ready) return
        root.comparison = null
        root.comparing = true
        root.controller.submit("grid.compare_policies", {
            "target_crs": root.targetCrs,
            "pixel_size": parseFloat(root.pixelSize),
            "layers": root.layerRequests()
        }, [])
    }

    Connections {
        target: root.controller
        function onPoliciesCompared(manifest) {
            root.comparing = false
            root.comparison = manifest
        }
    }

    // Trocar o CRS, o pixel ou as camadas invalida a medida: números de uma
    // grade diferente mostrados ao lado dos controles que a definem seriam
    // lidos como sendo desta.
    onTargetCrsChanged: root.comparison = null
    onPixelSizeChanged: root.comparison = null
    onChosenChanged: root.comparison = null

    // Which of the catalogue's rasters go onto the grid. A project keeps its
    // data across sessions, so by the time someone harmonises, the catalogue
    // holds everything ever imported — and an analysis is a chosen subset of
    // it, not all of it.
    property var chosen: ({})

    function isChosen(id) {
        return chosen[id] !== false
    }

    function choose(id, on) {
        var next = {}
        for (var key in chosen) next[key] = chosen[key]
        next[id] = on
        chosen = next
    }

    readonly property int usable: {
        var n = 0
        for (var i = 0; i < datasets.length; ++i)
            if (!datasets[i].missing && isChosen(datasets[i].id)) n += 1
        return n
    }

    // The CRSs the chosen layers are in. More than one is legal — that is
    // what harmonisation is for — but it makes the target a real decision,
    // and an intersection of layers that do not overlap is empty.
    readonly property var crsInUse: {
        var seen = []
        for (var i = 0; i < datasets.length; ++i) {
            var d = datasets[i]
            if (d.missing || !isChosen(d.id) || !d.crs) continue
            if (seen.indexOf(d.crs) < 0) seen.push(d.crs)
        }
        return seen
    }
    // The grid needs somewhere to put every layer, and something to put there.
    readonly property bool ready: usable > 0
                                  && targetCrs.length > 0
                                  && parseFloat(pixelSize) > 0

    title: txt["harmonize.title"] || ""
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 560
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    function reload() {
        datasets = controller.harmonizableDatasets()
        // Offered, not applied: the fields are filled from the data so the
        // person corrects rather than types, and the value that runs is the
        // one left in the field.
        if (datasets.length > 0) {
            if (targetCrs.length === 0)
                targetCrs = datasets[0].crs || ""
            if (pixelSize.length === 0) {
                // The finest pixel among the inputs. Coarser would throw away
                // resolution the data has; finer would invent it.
                var finest = 0
                for (var i = 0; i < datasets.length; ++i) {
                    var px = datasets[i].pixelX
                    var py = datasets[i].pixelY
                    var each = Math.max(px || 0, py || 0)
                    if (each > 0 && (finest === 0 || each < finest))
                        finest = each
                }
                if (finest > 0)
                    pixelSize = String(finest)
            }
        }
    }

    onOpened: root.reload()

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingMd

        Label {
            Layout.fillWidth: true
            text: root.txt["harmonize.explain"] || ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            wrapMode: Text.WordWrap
        }
        Label {
            Layout.fillWidth: true
            text: root.txt["harmonize.explainMore"] || ""
            color: Theme.textMuted
            font.pixelSize: Theme.fontSm
            wrapMode: Text.WordWrap
        }

        // ---- what will be brought onto the grid --------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 140
            color: Theme.surfaceAlt
            border.color: Theme.border
            radius: Theme.radius
            clip: true

            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: Theme.spacingXs
                clip: true
                model: root.datasets
                delegate: RowLayout {
                    required property var modelData
                    width: list.width
                    spacing: Theme.spacingSm

                    CheckBox {
                        checked: root.isChosen(modelData.id)
                        enabled: !modelData.missing
                        onToggled: root.choose(modelData.id, checked)
                        implicitHeight: Theme.controlHeight
                    }
                    Label {
                        text: modelData.name
                        color: modelData.missing ? Theme.error : Theme.text
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 160
                        elide: Text.ElideRight
                    }
                    Label {
                        text: modelData.crs || root.txt["fact.notDeclared"]
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.preferredWidth: 130
                        elide: Text.ElideRight
                    }
                    Label {
                        // Both numbers. Averaging them is silently wrong
                        // everywhere except a square pixel.
                        text: modelData.pixelX
                              ? Number(modelData.pixelX).toFixed(2) + " x "
                                + Number(modelData.pixelY).toFixed(2)
                              : ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.fillWidth: true
                    }
                    Label {
                        visible: modelData.missing
                        text: root.txt["harmonize.missing"] || ""
                        color: Theme.error
                        font.pixelSize: Theme.fontSm
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: root.datasets.length === 0
                text: root.txt["harmonize.none"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                horizontalAlignment: Text.AlignHCenter
                width: parent.width - 2 * Theme.spacingMd
                wrapMode: Text.WordWrap
            }
        }

        // ---- the grid ----------------------------------------------------
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Theme.spacingMd
            rowSpacing: Theme.spacingSm

            Label {
                text: root.txt["harmonize.crs"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            TextField {
                id: crsField
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                text: root.targetCrs
                placeholderText: "EPSG:26912"
                font.family: Theme.fontMono
                onTextChanged: root.targetCrs = text
            }

            Label {
                text: root.txt["harmonize.pixel"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            TextField {
                id: pixelField
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                text: root.pixelSize
                validator: DoubleValidator { bottom: 0 }
                font.family: Theme.fontMono
                onTextChanged: root.pixelSize = text
            }

            Label {
                text: root.txt["harmonize.extent"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
            }
            ComboBox {
                id: policy
                Layout.fillWidth: true
                implicitHeight: Theme.controlHeight
                // Labelled, not raw: "intersection" and "union" are different
                // maps and the difference has to be readable.
                model: [root.txt["harmonize.extent.intersection"],
                        root.txt["harmonize.extent.union"]]
                currentIndex: root.extentPolicy === "union" ? 1 : 0
                onActivated: root.extentPolicy = index === 1 ? "union"
                                                             : "intersection"
            }

            Item {}
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Button {
                    objectName: "harmonizeCompare"
                    text: root.comparing
                          ? (root.txt["harmonize.preview.busy"] || "")
                          : (root.txt["harmonize.preview"] || "")
                    enabled: root.ready && !root.comparing
                    onClicked: root.compare()
                }
                Item { Layout.fillWidth: true }
            }
        }

        // ---- o que cada política daria -----------------------------------
        Rectangle {
            objectName: "harmonizePreview"
            Layout.fillWidth: true
            Layout.preferredHeight: previewBody.implicitHeight + 2 * Theme.spacingSm
            visible: root.comparison !== null
            color: Theme.surfaceAlt
            border.color: Theme.border
            radius: Theme.radius

            ColumnLayout {
                id: previewBody
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                spacing: 2

                Repeater {
                    model: ["intersection", "union"]
                    delegate: RowLayout {
                        required property var modelData
                        readonly property var facts: root.policyFacts(modelData)
                        Layout.fillWidth: true
                        spacing: Theme.spacingMd

                        Label {
                            text: root.txt["harmonize.extent."
                                           + parent.modelData + ".short"]
                                  || parent.modelData
                            color: root.extentPolicy === parent.modelData
                                   ? Theme.text : Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.bold: root.extentPolicy === parent.modelData
                            Layout.preferredWidth: 110
                        }
                        Label {
                            visible: !!parent.facts && parent.facts.available
                            text: parent.facts
                                  ? parent.facts.width + " × " + parent.facts.height
                                  : ""
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                            Layout.preferredWidth: 110
                        }
                        Label {
                            objectName: "harmonizeScored_" + parent.modelData
                            visible: !!parent.facts && parent.facts.available
                            text: parent.facts
                                  ? (parent.facts.scored_fraction * 100).toFixed(1)
                                    + " % " + (root.txt["harmonize.preview.scored"] || "")
                                    + " (" + parent.facts.scored_cells + ")"
                                  : ""
                            color: Theme.text
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                        }
                        // Uma interseção vazia é uma resposta, não uma falha:
                        // é exatamente o que precisa ser sabido antes de
                        // escolhê-la.
                        Label {
                            visible: !!parent.facts && !parent.facts.available
                            text: root.txt["harmonize.preview.empty"] || ""
                            color: Theme.warn
                            font.pixelSize: Theme.fontSm
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                        Item { Layout.fillWidth: true }
                    }
                }

                Label {
                    objectName: "harmonizeSameArea"
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    visible: root.sameScoredArea
                    wrapMode: Text.WordWrap
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    text: (root.txt["harmonize.preview.same"] || "")
                              .replace("%1", root.sameScoredArea
                                  ? root.policyFacts("intersection").scored_cells
                                  : "")
                }
                // A estimativa diz em que grade foi estimada. Uma fração sem
                // isso seria lida como exata.
                Label {
                    Layout.fillWidth: true
                    visible: {
                        var a = root.policyFacts("intersection")
                        return !!(a && a.available && a.estimated)
                    }
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    text: {
                        var a = root.policyFacts("intersection")
                        if (!a || !a.available || !a.estimated) return ""
                        return (root.txt["harmonize.preview.estimated"] || "")
                                   .replace("%1", a.estimate_width)
                                   .replace("%2", a.estimate_height)
                                   .replace("%3", a.decimation * a.decimation)
                    }
                }
                Label {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    text: root.txt["harmonize.preview.note"] || ""
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Label {
                    Layout.fillWidth: true
                    text: root.ready ? (root.txt["harmonize.willRun"] || "")
                                           .replace("%1", root.usable)
                                     : (root.txt["harmonize.blocked"] || "")
                    color: root.ready ? Theme.ok : Theme.warn
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
                // Layers in more than one CRS are exactly what harmonisation
                // is for — and also how an intersection comes out empty, when
                // the areas do not overlap. Said before the click, not after
                // the run fails.
                Label {
                    Layout.fillWidth: true
                    visible: root.crsInUse.length > 1
                    text: (root.txt["harmonize.mixedCrs"] || "")
                              .replace("%1", root.crsInUse.join(", "))
                    color: Theme.warn
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }
            Button {
                text: root.txt["dialog.cancel"] || ""
                onClicked: root.close()
            }
            Button {
                objectName: "harmonizeRun"
                text: root.txt["harmonize.run"] || ""
                enabled: root.ready
                highlighted: enabled
                onClicked: {
                    root.controller.submit("grid.harmonize", {
                        "target_crs": root.targetCrs,
                        "pixel_size": parseFloat(root.pixelSize),
                        "extent_policy": root.extentPolicy,
                        "layers": root.layerRequests()
                    }, [])
                    root.close()
                }
            }
        }
    }

    // The operator's `layers` parameter, in the catalogue's own order.
    function layerRequests() {
        var out = []
        for (var i = 0; i < datasets.length; ++i) {
            if (datasets[i].missing || !isChosen(datasets[i].id))
                continue
            out.push({
                "path": datasets[i].path,
                "name": datasets[i].name,
                "unit": datasets[i].unit || "",
                // Bilinear for a continuous field. A categorical layer must
                // not be averaged, and nothing here declares one yet: that
                // arrives with the criterion editor.
                "resampling": "bilinear"
            })
        }
        return out
    }
}
