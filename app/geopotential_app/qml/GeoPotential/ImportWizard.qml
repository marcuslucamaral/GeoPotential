import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import GeoPotential

// Section 9.2 — the Import Wizard.
//
// Detect format, CRS, unit, fields, NoData, extent and problems BEFORE the
// dataset enters the project. The rule this screen exists to enforce:
// **no invalid data is added without its diagnosis being shown.**
//
// So Import is disabled until the checks have run, and stays disabled while a
// BLOCKER stands, with the blocking findings on screen rather than behind a
// dialog the user dismisses.
Dialog {
    id: root
    required property var controller

    readonly property var txt: controller.tr.strings

    title: root.txt["import.title"]
    modal: true
    width: 780
    // Never taller than the window it is centred in. A modal cannot be moved,
    // so a dialog that runs off the bottom of the screen puts its own buttons
    // out of reach with nothing the person can do about it.
    height: Math.min(720, parent ? parent.height - 2 * Theme.spacingLg : 720)
    anchors.centerIn: Overlay.overlay
    standardButtons: Dialog.NoButton

    property string path: ""
    property var description: ({})
    property var report: ({})
    property var plan: null
    property bool checking: false

    // What the operator asserts about a file that does not say for itself.
    // Every one of these is recorded as a declaration, not applied silently.
    property string declaredCrs: ""
    property string declaredUnit: ""
    property string declaredNodata: ""
    // Which column is X, which is Y, which carries the measurement. Declared
    // here or guessed by the reader — and the difference is visible.
    property string declaredX: ""
    property string declaredY: ""
    property string declaredValue: ""
    // Which layer of a multi-layer GeoPackage. A26: when a file holds more
    // than one, the choice is asked for — reading the first is a guess, and a
    // guess about which dataset this is would be recorded as the dataset.
    property string declaredLayer: ""

    readonly property var availableLayers: (description && description.layers) || []
    // A file with several layers and none chosen is not importable yet. This
    // blocks the button on its own, beside whatever QA/QC decides.
    readonly property bool layerUndecided: availableLayers.length > 1
                                           && declaredLayer.length === 0

    // The file's own extent, in its own CRS. Shown with the CRS beside it in
    // the grid, because a pair of numbers without one is not a location.
    readonly property string extentText: {
        var e = description && description.extent
        if (!e || e.length !== 4)
            return ""
        var digits = description.geographic ? 5 : 1
        // Through `Number()`: a description handed straight from Python can
        // carry a numpy scalar, which reaches QML as an opaque wrapper with
        // no `toFixed`. The worker is fixed at the source; this keeps the
        // panel readable whatever hands it a description.
        return Number(e[0]).toFixed(digits) + ", "
             + Number(e[1]).toFixed(digits) + "  …  "
             + Number(e[2]).toFixed(digits) + ", "
             + Number(e[3]).toFixed(digits)
    }

    readonly property bool described: description && description.kind !== undefined
    readonly property bool validated: report && report.usable !== undefined
    readonly property bool usable: validated && report.usable

    function clearWizard() {
        path = ""; description = ({}); report = ({}); plan = null
        declaredCrs = ""; declaredUnit = ""; declaredNodata = ""
        declaredX = ""; declaredY = ""; declaredValue = ""
        declaredLayer = ""
        checking = false
    }

    function declarations() {
        var d = {}
        if (declaredCrs.length > 0) d["crs"] = declaredCrs
        if (declaredUnit.length > 0) d["unit"] = declaredUnit
        if (declaredNodata.length > 0) d["nodata"] = parseFloat(declaredNodata)
        if (declaredX.length > 0) d["x_field"] = declaredX
        if (declaredY.length > 0) d["y_field"] = declaredY
        if (declaredValue.length > 0) d["value_field"] = declaredValue
        if (declaredLayer.length > 0) d["layer"] = declaredLayer
        return d
    }

    function inspect() {
        if (path.length === 0) return
        checking = true
        // The previous verdict is cleared *before* the new one is asked for.
        // Leaving it on screen is how a red "cannot be used" stayed under a
        // CRS that had just been declared, and the file looked refused when it
        // was not.
        report = ({})
        controller.describeDataset(path, declarations())
        controller.validateDataset(path, declarations())
    }

    // True while the description is being copied into the declaration fields.
    //
    // The prefill exists so the person corrects rather than types — and it
    // writes the same fields that a person types into, so it fired the
    // re-check that had just produced it. A raster carries its own CRS, so
    // opening the wizard on one read the file **twice**: describe, validate,
    // prefill, describe again, validate again, for no answer that changed.
    property bool prefilling: false

    // Typing a declaration re-checks by itself, once the typing settles.
    // Requiring a click on "Re-check" makes the screen disagree with the
    // fields above it, and nobody reads a button as "this is now stale".
    Timer {
        id: recheck
        interval: 450
        onTriggered: root.inspect()
    }

    onDeclaredCrsChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredUnitChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredNodataChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredXChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredYChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredValueChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()
    onDeclaredLayerChanged: if (root.path.length > 0 && !root.prefilling) recheck.restart()

    Connections {
        target: root.controller
        function onDatasetDescribed(d) {
            root.description = d
            // Pre-fill from the file, so the operator corrects rather than
            // types — and without asking for the file to be read again: this
            // is the answer that just came back, not a new question.
            root.prefilling = true
            if (root.declaredCrs.length === 0 && d.crs) root.declaredCrs = d.crs
            if (root.declaredUnit.length === 0 && d.unit) root.declaredUnit = d.unit
            root.prefilling = false
        }
        function onDatasetValidated(v) {
            root.report = v.report
            root.plan = v.plan
            root.checking = false
        }
    }

    FileDialog {
        id: filePicker
        title: root.txt["import.pick"]
        nameFilters: [
            "All supported (*.tif *.tiff *.cog *.gpkg *.shp *.csv *.xyz *.txt)",
            "Rasters (*.tif *.tiff *.cog)",
            "Vectors (*.gpkg *.shp *.geojson)",
            "Tables (*.csv *.xyz *.txt)",
            "All files (*)"
        ]
        onAccepted: {
            root.clearWizard()
            root.path = selectedFile.toString().replace("file://", "")
            root.inspect()
        }
    }

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

    // The content scrolls; the decision does not. How tall this column gets
    // depends on the file — a CSV brings a preview, a histogram and an
    // attribute table — and none of that may decide whether Import can be
    // clicked.
    contentItem: ScrollView {
        id: scroller
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: scroller.availableWidth
            spacing: Theme.spacingMd

        // ---- 1. the file -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm
            Label {
                text: root.txt["import.file"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                Layout.preferredWidth: 70
            }
            TextField {
                text: root.path
                placeholderText: root.txt["import.noFile"]
                readOnly: true
                Layout.fillWidth: true
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontSm
            }
            Button {
                text: root.txt["import.choose"]
                onClicked: filePicker.open()
            }
        }

        // ---- 2. what was detected ---------------------------------------
        GroupBox {
            title: root.txt["import.detected"]
            Layout.fillWidth: true
            visible: root.described
            background: Rectangle {
                color: Theme.surfaceAlt
                border.color: Theme.border
                radius: Theme.radius
            }
            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            GridLayout {
                columns: 3
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingXs
                anchors.fill: parent

                component Cell: RowLayout {
                    property string key: ""
                    property string value: ""
                    spacing: Theme.spacingSm
                    Layout.fillWidth: true
                    Label {
                        text: key
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        Layout.preferredWidth: 74
                    }
                    Label {
                        text: value.length > 0 ? value : "—"
                        color: value.length > 0 ? Theme.text : Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        Layout.fillWidth: true
                        Layout.minimumWidth: 90
                        elide: Text.ElideRight
                    }
                }

                // Shared by every kind.
                Cell { key: root.txt["fact.format"]
                       value: (root.description.driver || "") + " · " + (root.description.kind || "") }
                Cell { key: root.txt["fact.crs"]; value: root.description.crs || "" }
                Cell { key: root.txt["fact.crsUnit"]; value: root.description.crs_unit || "" }
                Cell { key: root.txt["fact.extent"]; value: root.extentText }

                // ---- a raster's own facts (MSP-03) -----------------------
                Cell {
                    visible: root.description.kind === "raster"
                    key: root.txt["fact.size"]
                    value: root.description.width
                           ? root.description.width + " x " + root.description.height + " px"
                           : ""
                }
                Cell {
                    visible: root.description.kind === "raster"
                    key: root.txt["fact.pixel"]
                    // Two numbers, never averaged: an anisotropic pixel is
                    // legal and collapsing it into one is silently wrong.
                    value: root.description.pixel_size_x !== undefined
                           ? root.description.pixel_size_x.toFixed(3) + " x "
                             + root.description.pixel_size_y.toFixed(3)
                           : ""
                }
                Cell {
                    visible: root.description.kind === "raster"
                    key: root.txt["fact.bands"]
                    value: root.description.bands !== undefined
                           ? String(root.description.bands)
                             + (root.description.dtype ? " · " + root.description.dtype : "")
                           : ""
                }
                Cell {
                    visible: root.description.kind === "raster"
                    key: root.txt["fact.overviews"]
                    value: root.description.overviews !== undefined
                           ? (root.description.cloud_optimized
                              ? root.txt["fact.cog"].replace("%1", root.description.overviews)
                              : String(root.description.overviews))
                           : ""
                }
                Cell {
                    visible: root.description.kind === "raster"
                    key: root.txt["fact.nodata"]
                    value: root.description.nodata !== null
                           && root.description.nodata !== undefined
                           ? String(root.description.nodata)
                           : root.txt["fact.notDeclared"]
                }

                // ---- a vector's own facts --------------------------------
                Cell {
                    visible: root.description.kind === "vector"
                    key: root.txt["fact.features"]
                    value: root.description.features !== undefined
                           ? String(root.description.features) : ""
                }
                Cell {
                    visible: root.description.kind === "vector"
                    key: root.txt["fact.geometry"]
                    value: (root.description.geometry_kinds || []).join(", ")
                }
                Cell {
                    // A GeoPackage holding more than one layer has to be asked
                    // about, not guessed at (A26).
                    visible: root.description.kind === "vector"
                             && (root.description.layers || []).length > 0
                    key: root.txt["fact.layers"]
                    value: (root.description.layers || []).join(", ")
                }

                // ---- a table's own facts ---------------------------------
                Cell {
                    visible: root.description.kind === "table"
                    key: root.txt["fact.rows"]
                    value: root.description.rows !== undefined
                           ? String(root.description.rows) : ""
                }

                // Shared again, and last: what the values are.
                Cell { key: root.txt["fact.fields"]
                       value: (root.description.fields || []).join(", ") }
                Cell {
                    key: root.txt["fact.valid"]
                    value: root.description.statistics
                           && root.description.statistics.valid_fraction !== undefined
                           ? (root.description.statistics.valid_fraction * 100).toFixed(1) + " %"
                           : ""
                }
                Cell {
                    key: root.txt["fact.range"]
                    value: root.description.statistics
                           && root.description.statistics.min !== undefined
                           ? root.description.statistics.min.toFixed(3) + " … "
                             + root.description.statistics.max.toFixed(3)
                             + (root.description.unit ? " " + root.description.unit : "")
                           : ""
                }
            }
        }

        // ---- 3. what the operator declares -------------------------------
        // ---- which column is what ------------------------------------------
        //
        // A table with six columns has one measurement and five other things.
        // The reader guesses; the guess is shown, is changeable, and shows up
        // in the verdict as a guess (§16: never a silent value).
        // ---- which layer of a container file -----------------------------
        //
        // A GeoPackage holds any number of layers. Reading the first one and
        // importing it under the file's name records a dataset nobody chose
        // (A26). So: the list is shown, the choice is required, and until it
        // is made the import is blocked with that as the reason.
        GroupBox {
            id: layerBox
            title: root.txt["import.layers"]
            Layout.fillWidth: true
            visible: root.described && root.availableLayers.length > 1

            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            RowLayout {
                anchors.fill: parent
                spacing: Theme.spacingMd

                ComboBox {
                    id: layerChoice
                    Layout.preferredWidth: 240
                    implicitHeight: Theme.controlHeight
                    // A leading empty entry, so "none chosen" is a state the
                    // control can actually be in and not a hidden default.
                    model: [root.txt["import.layers.choose"]].concat(
                               root.availableLayers)
                    currentIndex: root.declaredLayer.length === 0
                                  ? 0
                                  : root.availableLayers.indexOf(root.declaredLayer) + 1
                    onActivated: root.declaredLayer =
                                 index === 0 ? "" : textAt(index)
                }
                Label {
                    Layout.fillWidth: true
                    text: root.layerUndecided
                          ? root.txt["import.layers.undecided"]
                                .replace("%1", root.availableLayers.length)
                          : root.txt["import.layers.chosen"]
                                .replace("%1", root.declaredLayer)
                    color: root.layerUndecided ? Theme.warn : Theme.ok
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }
        }

        GroupBox {
            id: columnsBox
            title: root.txt["import.columns"]
            Layout.fillWidth: true
            visible: root.described && root.description.kind === "table"

            readonly property var fields: root.description.fields || []
            readonly property var declaredFields: root.description.fields_declared || []

            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            GridLayout {
                anchors.fill: parent
                columns: 3
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingXs

                component Chooser: ColumnLayout {
                    property string caption: ""
                    property string role: ""
                    property string current: ""
                    signal picked(string field)
                    Layout.fillWidth: true
                    spacing: 0

                    Label {
                        text: parent.caption
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                    ComboBox {
                        Layout.fillWidth: true
                        implicitHeight: Theme.controlHeight
                        model: columnsBox.fields
                        currentIndex: Math.max(0, columnsBox.fields.indexOf(parent.current))
                        onActivated: parent.picked(textAt(index))
                    }
                    Label {
                        text: columnsBox.declaredFields.indexOf(parent.role) >= 0
                              ? root.txt["import.columns.declared"]
                              : root.txt["import.columns.guessed"]
                        color: columnsBox.declaredFields.indexOf(parent.role) >= 0
                               ? Theme.ok : Theme.warn
                        font.pixelSize: Theme.fontSm
                    }
                }

                Chooser {
                    caption: root.txt["import.columns.x"]
                    role: "x_field"
                    current: root.description.x_field || ""
                    onPicked: function (field) { root.declaredX = field }
                }
                Chooser {
                    caption: root.txt["import.columns.y"]
                    role: "y_field"
                    current: root.description.y_field || ""
                    onPicked: function (field) { root.declaredY = field }
                }
                Chooser {
                    caption: root.txt["import.columns.value"]
                    role: "value_field"
                    current: root.description.value_field || ""
                    onPicked: function (field) { root.declaredValue = field }
                }

                Label {
                    Layout.columnSpan: 3
                    Layout.fillWidth: true
                    text: root.txt["import.columns.tip"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }
        }

        // ---- what is in the file ------------------------------------------
        //
        // ADR-MSP-004: bounded, decimated and declared. It answers "is this the
        // file I meant" and nothing else — every number the project uses is
        // read from the file itself, never from here.
        GroupBox {
            id: previewBox
            title: root.txt["import.preview"]
            Layout.fillWidth: true
            visible: root.described

            readonly property var preview: root.description.preview || ({})
            readonly property var columns: preview.columns || []
            readonly property var rows: preview.rows || []

            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.spacingXs

                Label {
                    visible: previewBox.preview.kind === undefined
                             && root.description.kind !== "raster"
                    text: root.txt["import.preview.none"]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                }

                // The picture and the distribution, side by side: MSP-03 asks
                // for both, and one without the other answers half the
                // question. The map draws the file; the histogram says where
                // its values sit.
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 190
                    spacing: Theme.spacingMd

                    PreviewMap {
                        id: previewMap
                        objectName: "previewMap"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumWidth: 180
                        txt: root.txt
                        description: root.described ? root.description : ({})
                    }

                    ColumnLayout {
                        Layout.preferredWidth: 240
                        Layout.fillHeight: true
                        spacing: Theme.spacingXs
                        visible: histogram.ready

                        Label {
                            text: root.txt["import.histogram"]
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                        }
                        Histogram {
                            id: histogram
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            txt: root.txt
                            unit: root.description.unit || ""
                            counts: root.description.statistics
                                    && root.description.statistics.histogram
                                    ? root.description.statistics.histogram.counts : []
                            edges: root.description.statistics
                                   && root.description.statistics.histogram
                                   ? root.description.statistics.histogram.edges : []
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd
                    visible: previewBox.preview.kind !== undefined

                    Label {
                        text: previewBox.preview.source_rows !== undefined
                              ? root.txt["import.preview.rows"]
                                    .replace("%1", previewBox.preview.source_rows)
                                    .replace("%2", previewBox.rows.length)
                              : ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        visible: previewBox.preview.points !== undefined
                        text: root.txt["import.preview.points"]
                                  .replace("%1", previewBox.preview.source_rows || 0)
                                  .replace("%2", previewBox.preview.shown || 0)
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                    Label {
                        visible: previewBox.preview.source_features !== undefined
                        text: root.txt["import.preview.features"]
                                  .replace("%1", previewBox.preview.source_features)
                                  .replace("%2", previewBox.preview.shown || 0)
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        visible: previewBox.preview.decimated === true
                                 || previewBox.preview.truncated === true
                        text: root.txt["import.preview.decimated"]
                        color: Theme.warn
                        font.pixelSize: Theme.fontSm
                    }
                }

                // The attribute table, the way a person checks a file: the
                // column names and the first rows, as they are written.
                Rectangle {
                    visible: previewBox.rows.length > 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: 150
                    color: Theme.surfaceAlt
                    border.color: Theme.border
                    radius: Theme.radius
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingXs
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spacingMd
                            Repeater {
                                model: previewBox.columns
                                delegate: Label {
                                    required property string modelData
                                    text: modelData
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSm
                                    font.bold: true
                                    Layout.preferredWidth: 110
                                    elide: Text.ElideRight
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: Theme.border
                        }

                        ListView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: previewBox.rows
                            delegate: RowLayout {
                                required property var modelData
                                spacing: Theme.spacingMd
                                Repeater {
                                    model: modelData
                                    delegate: Label {
                                        required property string modelData
                                        text: modelData
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontSm
                                        font.family: Theme.fontMono
                                        Layout.preferredWidth: 110
                                        elide: Text.ElideRight
                                    }
                                }
                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }
        }

        GroupBox {
            title: root.txt["import.declare"]
            Layout.fillWidth: true
            background: Rectangle {
                color: Theme.surfaceAlt
                border.color: Theme.border
                radius: Theme.radius
            }
            label: Label {
                text: parent.title
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                padding: Theme.spacingXs
            }

            RowLayout {
                anchors.fill: parent
                spacing: Theme.spacingMd

                ColumnLayout {
                    Label { text: "CRS"; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                    TextField {
                        text: root.declaredCrs
                        onTextEdited: root.declaredCrs = text
                        placeholderText: "EPSG:26912"
                        Layout.preferredWidth: 160
                        font.pixelSize: Theme.fontSm
                    }
                }
                ColumnLayout {
                    Label { text: root.txt["import.unit"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                    ComboBox {
                        id: unitBox
                        editable: true
                        // The first entry says "not declared" instead of being
                        // blank: an empty row reads as a control that failed to
                        // load, and this one is empty on purpose.
                        readonly property string none: root.txt["import.unit.none"]
                        model: [none, "m", "mGal", "g/cm3", "nT", "degC", "mW/m2"]
                        currentIndex: root.declaredUnit.length === 0
                                      ? 0 : Math.max(0, model.indexOf(root.declaredUnit))
                        onEditTextChanged: root.declaredUnit =
                            (editText === none ? "" : editText)
                        Layout.preferredWidth: 150
                    }
                }
                ColumnLayout {
                    Label { text: root.txt["import.nodata"]; color: Theme.textMuted; font.pixelSize: Theme.fontSm }
                    TextField {
                        text: root.declaredNodata
                        onTextEdited: root.declaredNodata = text
                        placeholderText: "-9999"
                        Layout.preferredWidth: 110
                        font.pixelSize: Theme.fontSm
                    }
                }
                Button {
                    text: root.checking ? root.txt["import.checking"] : root.txt["import.recheck"]
                    enabled: root.path.length > 0 && !root.checking
                    onClicked: root.inspect()
                    Layout.alignment: Qt.AlignBottom
                }
                Item { Layout.fillWidth: true }
            }
        }

        // Why the unit is asked for at all, and which ones this file's own
        // magnitudes would not contradict. The shortlist comes from the same
        // table QA/QC judges the answer against, so the two cannot disagree —
        // and it is a shortlist, never a value applied on someone's behalf.
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            visible: root.described && root.declaredUnit.length === 0

            Label {
                Layout.fillWidth: true
                text: root.txt["import.unit.why"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                readonly property var stats: root.description.statistics || ({})
                readonly property var candidates: stats.unit_candidates || []
                readonly property int known: stats.unit_count || 0
                // Shown only when the file's own magnitudes actually excluded
                // something. A narrow range sits inside every wide one, so a
                // list of all six units is the honest answer to a question
                // that told us nothing — and printing it would be noise.
                visible: stats.min !== undefined
                         && (candidates.length === 0
                             || (known > 0 && candidates.length < known))
                text: candidates.length > 0
                      ? root.txt["import.unit.candidates"]
                            .replace("%1", candidates.join(", "))
                      : root.txt["import.unit.noCandidates"]
                color: candidates.length > 0 ? Theme.accent : Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
        }

        // ---- 4. the verdict ----------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            visible: root.validated || root.checking
            radius: Theme.radius
            color: Theme.surfaceAlt
            border.color: root.checking ? Theme.border
                        : root.usable ? Theme.ok : Theme.error

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingSm
                anchors.rightMargin: Theme.spacingSm
                Label {
                    text: root.checking ? root.txt["import.verdict.pending"]
                                        : (root.report.summary || "")
                    color: root.checking ? Theme.textMuted
                         : root.usable ? Theme.text : Theme.error
                    font.pixelSize: Theme.fontSm
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Label {
                    visible: root.plan !== null && root.plan !== undefined
                    text: root.plan ? "≈ " + root.plan.ram_mb.toFixed(0) + " MB RAM · "
                          + root.plan.policy : ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                }
            }
        }

        // ---- 5. the findings, in full ------------------------------------
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.report.findings || []
            spacing: Theme.spacingXs

            Label {
                anchors.centerIn: parent
                visible: parent.count === 0 && root.validated
                text: root.txt["import.clean"]
                color: Theme.ok
                font.pixelSize: Theme.fontMd
            }
            Label {
                anchors.centerIn: parent
                visible: !root.validated && !root.checking
                text: root.txt["import.pickFirst"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontMd
            }

            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width
                height: findingText.implicitHeight + 2 * Theme.spacingSm
                color: Theme.surfaceAlt
                radius: Theme.radius

                Rectangle {
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                    width: 3
                    radius: Theme.radius
                    color: modelData.severity === "BLOCKER" ? Theme.error
                         : modelData.severity === "WARNING" ? Theme.warn : Theme.accent
                }

                ColumnLayout {
                    id: findingText
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    anchors.leftMargin: Theme.spacingMd
                    spacing: 2

                    RowLayout {
                        spacing: Theme.spacingSm
                        Label {
                            text: modelData.severity
                            color: modelData.severity === "BLOCKER" ? Theme.error
                                 : modelData.severity === "WARNING" ? Theme.warn : Theme.accent
                            font.pixelSize: Theme.fontSm
                            font.bold: true
                        }
                        Label {
                            text: modelData.rule
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSm
                            font.family: Theme.fontMono
                        }
                    }
                    Label {
                        text: modelData.what
                        color: Theme.text
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: modelData.why
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: "→ " + modelData.fix
                        color: Theme.accent
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
        }
    }

    // The decision, pinned. It is the dialog's **footer** and not the last row
    // of the content, so it cannot be pushed off the bottom by a file with a
    // tall preview — which is exactly what a CSV did: the preview and the
    // attribute table grew the column past the dialog, the content spilled
    // over the background, and Import went off the screen with no way to
    // scroll to it and no way to move a centred modal.
    footer: Rectangle {
        color: Theme.surface
        implicitHeight: decision.implicitHeight + 2 * Theme.spacingMd

        RowLayout {
            id: decision
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
        Layout.fillWidth: true
        spacing: Theme.spacingSm

        Label {
            text: root.checking ? root.txt["import.verdict.pending"]
                  : !root.validated ? root.txt["import.verdict.first"]
                  // An undecided layer is named as the reason before the
                  // QA/QC verdict is, because it is the one the person can
                  // act on with the control right above.
                  : root.layerUndecided ? root.txt["import.verdict.layer"]
                  : root.usable ? root.txt["import.verdict.ok"]
                                : root.txt["import.verdict.blocked"]
            color: root.checking || !root.validated ? Theme.textMuted
                 : root.layerUndecided ? Theme.warn
                 : root.usable ? Theme.ok : Theme.error
            font.pixelSize: Theme.fontSm
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        Button {
            text: root.txt["dialog.cancel"]
            onClicked: { root.clearWizard(); root.close() }
        }
        Button {
            // Named so a headless driver can press the real button
            // rather than calling what the button calls.
            objectName: "importButton"
            text: root.txt["import.import"]
            // The whole point of the screen: disabled until the checks
            // have run, while a BLOCKER stands, and while a container
            // file's layer has not been chosen (A26).
            enabled: root.usable && !root.checking && !root.layerUndecided
            highlighted: enabled
            onClicked: {
                var kind = root.description.kind || "raster"
                if (root.controller.importDataset(root.path, kind).length > 0) {
                    root.clearWizard()
                    root.close()
                }
            }
            ToolTip.text: enabled
                ? root.txt["import.import.tip"]
                : root.layerUndecided
                  ? root.txt["import.import.tip.layer"]
                  : (root.validated
                     ? root.txt["import.import.tip.blocked"]
                     : root.txt["import.import.tip.unchecked"])
            ToolTip.visible: hovered
            ToolTip.delay: 300
        }
    }
}
}
