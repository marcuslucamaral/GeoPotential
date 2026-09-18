import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// MSP-06 — sparse data onto a grid, before it can be a criterion.
//
// Harmonisation reprojects and resamples a **raster**. A table of samples and
// a vector of features get to a grid another way, and the way is a scientific
// decision, not plumbing:
//
//   grid.idw                 estimates a value where nothing was measured
//   grid.tin_linear          the same, over a Delaunay triangulation
//   grid.tin_cubic           the same, Clough-Tocher, smooth
//   grid.euclidean_distance  measures the distance to the nearest feature
//   grid.rasterize           transfers a value the feature already carries
//
// Only the first three interpolate, and the screen says so — because a
// distance field described as an interpolation puts an estimate in a lineage
// that has none.
//
// The three interpolators are the ones QGIS offers, and none of them is the
// right default. IDW is a weighted mean: it is pulled toward the local average
// and it flattens a gradient, which is what makes a lattice of samples come
// out mottled. The triangulated pair follow the gradient and stop at the
// convex hull. Which is better is a property of the survey, not a preference,
// so the screen offers to **measure** it — `grid.cross_validate` holds samples
// out and reports each method's error in the data's own unit (ADR-MSP-007).
//
// The grid is declared here too: CRS, pixel, and an area that defaults to the
// data's extent but does not have to be it.
Dialog {
    id: root

    required property var controller
    property var txt: ({})

    property var datasets: []
    property int selected: -1
    property string method: "grid.idw"

    property string targetCrs: ""
    property string pixelSize: ""
    property string radius: ""
    property string power: "2"
    // The operator's own documented default. The screen used to send 3, which
    // is a different, stricter analysis than the one the operator documents —
    // a default that exists only in the interface is the silent default §16
    // forbids. Raising it is an explicit choice to leave sparser areas null.
    property string minPoints: "1"
    // Only a triangulated method takes it, and only when it is set: absent,
    // the convex hull of the samples is the limit, which is what QGIS does.
    property string maxDistance: ""
    property bool wholeExtent: true
    property string boundsText: ""

    // What `grid.cross_validate` last measured for this dataset, and whether
    // it is still running. Cleared when the dataset changes, because an error
    // measured on one survey says nothing about another.
    property var comparison: null
    property bool comparing: false

    // How fine the grid is, as a fraction of the survey's own spacing.
    //
    // A pixel equal to the spacing gives one cell per sample and a picture
    // with no gradient in it at all — the interpolation has nowhere to vary.
    // Dividing the spacing is what lets the field show what it does between
    // samples; dividing it too far only makes a bigger file, because there is
    // no information below the sample spacing to recover.
    readonly property var details: [
        {"key": "coarse", "divisor": 1},
        {"key": "balanced", "divisor": 3},
        {"key": "fine", "divisor": 5}
    ]
    property string detail: "balanced"

    function divisorFor(key) {
        for (var i = 0; i < details.length; ++i)
            if (details[i].key === key) return details[i].divisor
        return 3
    }

    // The grid the current pixel and area would produce. Shown before the run
    // because "10 x 6" and "50 x 30" are different answers to the same
    // question, and the person cannot see which one they asked for.
    readonly property var gridSize: {
        var px = parseFloat(pixelSize)
        var e = wholeExtent ? (dataset ? dataset.extent : null) : parsedBounds()
        if (!(px > 0) || !e || e.length !== 4)
            return null
        var w = Math.max(1, Math.floor((e[2] - e[0]) / px))
        var h = Math.max(1, Math.floor((e[3] - e[1]) / px))
        return {"width": w, "height": h, "mb": (w * h * 4) / 1048576}
    }

    readonly property var dataset: (selected >= 0 && selected < datasets.length)
                                   ? datasets[selected] : null
    // Estimating a value nobody measured. The three that do it are named here
    // once; `usesRadius` is narrower, because only IDW has a search radius —
    // a triangulation is bounded by the samples' convex hull instead.
    readonly property bool interpolates:
        method === "grid.idw" || method === "grid.tin_linear"
        || method === "grid.tin_cubic"
    readonly property bool usesRadius: method === "grid.idw"
    readonly property bool triangulated:
        method === "grid.tin_linear" || method === "grid.tin_cubic"
    readonly property bool ready:
        dataset !== null && !dataset.missing
        && targetCrs.length > 0 && parseFloat(pixelSize) > 0
        && (!usesRadius || parseFloat(radius) > 0)
        && (wholeExtent || root.parsedBounds().length === 4)

    function parsedBounds() {
        var parts = boundsText.split(",")
        var out = []
        for (var i = 0; i < parts.length; ++i) {
            var v = parseFloat(parts[i].trim())
            if (!isNaN(v)) out.push(v)
        }
        return out.length === 4 ? out : []
    }

    title: txt["gridding.title"] || ""
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 600
    height: Math.min(660, parent ? parent.height - 2 * Theme.spacingLg : 660)
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    function reload() {
        datasets = controller.griddableDatasets()
        selected = datasets.length > 0 ? 0 : -1
        applyDataset()
    }

    function applyDataset() {
        // An error measured on one survey says nothing about another, so the
        // previous dataset's comparison does not survive the switch.
        comparison = null
        comparing = false
        if (dataset === null)
            return
        method = (dataset.methods && dataset.methods.length > 0)
                 ? dataset.methods[0] : "grid.idw"
        if (targetCrs.length === 0)
            targetCrs = dataset.crs || ""
        // A radius is proposed from the survey's own spacing, not from a
        // number chosen here. Three times the median distance between a
        // sample and its nearest neighbour: below the spacing almost every
        // cell comes out null, and the person has no way to guess that from
        // the file. It is a starting point and it is editable.
        if (dataset.spacing > 0) {
            if (radius.length === 0)
                radius = String(Math.round(dataset.spacing * 3))
            if (pixelSize.length === 0)
                root.applyDetail()
        }
    }

    // The pixel follows the chosen detail; the radius follows the survey's
    // density and not the pixel, because how far a sample can speak for is a
    // property of the data, not of the picture.
    function applyDetail() {
        if (dataset === null || !(dataset.spacing > 0))
            return
        pixelSize = String(
            Math.max(1, Math.round(dataset.spacing / divisorFor(detail))))
    }

    onOpened: root.reload()
    onSelectedChanged: root.applyDataset()

    contentItem: ScrollView {
        id: scroller
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: scroller.availableWidth
            spacing: Theme.spacingMd

            Label {
                Layout.fillWidth: true
                text: root.txt["gridding.explain"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                visible: root.datasets.length === 0
                text: root.txt["gridding.none"] || ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                visible: root.datasets.length > 0
                columns: 2
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingSm

                Label {
                    text: root.txt["gridding.dataset"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                ComboBox {
                    objectName: "griddingDataset"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    model: {
                        var names = []
                        for (var i = 0; i < root.datasets.length; ++i)
                            names.push(root.datasets[i].name
                                       + "  ·  " + root.datasets[i].kind)
                        return names
                    }
                    currentIndex: root.selected
                    onActivated: root.selected = index
                }

                Label {
                    text: root.txt["gridding.method"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                ComboBox {
                    objectName: "griddingMethod"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    // The keys are the operator names and are not translated;
                    // only the labels are, so a language change cannot change
                    // which operator a click selects.
                    property var keys: (root.dataset && root.dataset.methods)
                                       ? root.dataset.methods : []
                    model: {
                        var labels = []
                        for (var i = 0; i < keys.length; ++i)
                            labels.push(root.txt["gridding.method." + keys[i]]
                                        || keys[i])
                        return labels
                    }
                    currentIndex: Math.max(0, keys.indexOf(root.method))
                    onActivated: root.method = keys[index]
                }
            }

            // What the chosen method does to the data, in one line. It is the
            // difference between a measurement and an estimate.
            Label {
                Layout.fillWidth: true
                visible: root.dataset !== null
                // Both estimate; they stop for different reasons, and saying
                // "inside the radius" of a method that has no radius would be
                // describing a control that is not on the screen.
                text: root.triangulated
                      ? (root.txt["gridding.estimates.tin"] || "")
                      : (root.interpolates
                         ? (root.txt["gridding.estimates"] || "")
                         : (root.txt["gridding.transfers"] || ""))
                color: root.interpolates ? Theme.warn : Theme.ok
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            // Clough-Tocher is C1 across every triangle edge, so at a sharp
            // step the cubic bends past the samples it is fitting. It is a
            // property of the method, it is recorded in the manifest, and it
            // is not clamped (ADR-MSP-007) — so it is said here, before the
            // run, and not discovered afterwards in a colour bar.
            Label {
                Layout.fillWidth: true
                visible: root.method === "grid.tin_cubic"
                text: root.txt["gridding.cubic.overshoot"] || ""
                color: Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            // The measurement. Not a recommendation the screen makes up: the
            // worker holds a fifth of the samples out, predicts them with each
            // method, and reports the error in the data's own unit. Nothing
            // here changes the chosen method — the person does.
            ColumnLayout {
                Layout.fillWidth: true
                visible: root.dataset !== null && root.dataset.kind === "table"
                spacing: Theme.spacingXs

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    Button {
                        objectName: "griddingCompare"
                        text: root.txt["gridding.compare"] || ""
                        enabled: root.dataset !== null && !root.dataset.missing
                                 && root.targetCrs.length > 0 && !root.comparing
                        onClicked: {
                            root.comparison = null
                            root.comparing = true
                            root.controller.compareInterpolationMethods(
                                root.dataset.path, root.comparisonParameters())
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.comparing
                              ? (root.txt["gridding.compare.running"] || "")
                              : (root.txt["gridding.compare.hint"] || "")
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                    }
                }

                // One line per method: the error, and how much of the held-out
                // set it could answer at all. Both, because a method that wins
                // on 60 % of the points has not won.
                Repeater {
                    model: (root.comparison && root.comparison.methods)
                           ? root.comparison.methods : []
                    delegate: Label {
                        required property var modelData
                        Layout.fillWidth: true
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontSm
                        color: (root.comparison
                                && root.comparison.recommended === modelData.method)
                               ? Theme.ok : Theme.textMuted
                        text: {
                            var label = root.txt["gridding.method." + modelData.method]
                                        || modelData.method
                            if (!modelData.applies)
                                return "   " + label + " — " + (modelData.note || "")
                            var mark = (root.comparison.recommended === modelData.method)
                                       ? " ◀ " + (root.txt["gridding.compare.best"] || "")
                                       : ""
                            return "   " + label
                                   + "   RMSE " + Number(modelData.rmse).toPrecision(3)
                                   + "   " + (root.txt["gridding.compare.coverage"] || "")
                                       .replace("%1", Math.round(modelData.coverage * 100))
                                   + mark
                        }
                    }
                }
                Label {
                    Layout.fillWidth: true
                    visible: root.comparison !== null
                             && root.comparison.recommended !== undefined
                             && root.comparison.recommended !== null
                    text: (root.txt["gridding.compare.scored"] || "")
                              .replace("%1", root.comparison
                                       ? root.comparison.scored_on : 0)
                              .replace("%2", root.comparison
                                       ? root.comparison.folds : 0)
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    wrapMode: Text.WordWrap
                }
            }

            // Distance on a table of samples measures the survey, not the
            // ground. It is legitimate and it is almost never what someone
            // reaching for a criterion wants, so it says so.
            Label {
                Layout.fillWidth: true
                visible: root.dataset !== null
                         && root.method === "grid.euclidean_distance"
                text: (root.dataset && root.dataset.kind === "table")
                      ? (root.txt["gridding.distance.onSamples"] || "")
                      : (root.txt["gridding.distance.onFeatures"] || "")
                color: (root.dataset && root.dataset.kind === "table")
                       ? Theme.warn : Theme.textMuted
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                visible: root.dataset !== null
                columns: 2
                columnSpacing: Theme.spacingMd
                rowSpacing: Theme.spacingSm

                Label {
                    text: root.txt["harmonize.crs"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                TextField {
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    text: root.targetCrs
                    placeholderText: "EPSG:26912"
                    font.family: Theme.fontMono
                    onTextChanged: root.targetCrs = text
                }

                Label {
                    text: root.txt["gridding.detail"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                ComboBox {
                    objectName: "griddingDetail"
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    enabled: root.dataset !== null && root.dataset.spacing > 0
                    model: [root.txt["gridding.detail.coarse"],
                            root.txt["gridding.detail.balanced"],
                            root.txt["gridding.detail.fine"]]
                    currentIndex: {
                        for (var i = 0; i < root.details.length; ++i)
                            if (root.details[i].key === root.detail) return i
                        return 1
                    }
                    onActivated: {
                        root.detail = root.details[index].key
                        root.applyDetail()
                    }
                }

                Label {
                    text: root.txt["harmonize.pixel"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        objectName: "griddingPixel"
                        Layout.preferredWidth: 110
                        implicitHeight: Theme.controlHeight
                        text: root.pixelSize
                        validator: DoubleValidator { bottom: 0 }
                        font.family: Theme.fontMono
                        onTextChanged: root.pixelSize = text
                    }
                    // The grid this pixel actually produces, before the run.
                    // "10 x 6" and "50 x 30" are different answers, and the
                    // person cannot see which one they asked for.
                    Label {
                        Layout.fillWidth: true
                        visible: root.gridSize !== null
                        text: root.gridSize
                              ? (root.txt["gridding.gridSize"] || "")
                                    .replace("%1", root.gridSize.width)
                                    .replace("%2", root.gridSize.height)
                                    .replace("%3", root.gridSize.mb.toFixed(1))
                              : ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        elide: Text.ElideRight
                    }
                }

                Label {
                    visible: root.usesRadius
                    text: root.txt["gridding.radius"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                RowLayout {
                    visible: root.usesRadius
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        objectName: "griddingRadius"
                        Layout.preferredWidth: 110
                        implicitHeight: Theme.controlHeight
                        text: root.radius
                        validator: DoubleValidator { bottom: 0 }
                        font.family: Theme.fontMono
                        onTextChanged: root.radius = text
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: root.dataset !== null && root.dataset.spacing > 0
                        text: (root.txt["gridding.spacing"] || "")
                                  .replace("%1", root.dataset
                                           ? Math.round(root.dataset.spacing) : 0)
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                    }
                }

                Label {
                    visible: root.usesRadius
                    text: root.txt["gridding.power"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                RowLayout {
                    visible: root.usesRadius
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        Layout.preferredWidth: 70
                        implicitHeight: Theme.controlHeight
                        text: root.power
                        font.family: Theme.fontMono
                        onTextChanged: root.power = text
                    }
                    Label {
                        text: root.txt["gridding.minPoints"] || ""
                        color: Theme.textMuted; font.pixelSize: Theme.fontSm
                    }
                    TextField {
                        Layout.preferredWidth: 70
                        implicitHeight: Theme.controlHeight
                        text: root.minPoints
                        font.family: Theme.fontMono
                        onTextChanged: root.minPoints = text
                    }
                }

                Label {
                    visible: root.triangulated
                    text: root.txt["gridding.maxDistance"] || ""
                    color: Theme.textMuted; font.pixelSize: Theme.fontSm
                }
                RowLayout {
                    visible: root.triangulated
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm
                    TextField {
                        objectName: "griddingMaxDistance"
                        Layout.preferredWidth: 110
                        implicitHeight: Theme.controlHeight
                        text: root.maxDistance
                        validator: DoubleValidator { bottom: 0 }
                        font.family: Theme.fontMono
                        onTextChanged: root.maxDistance = text
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.txt["gridding.maxDistance.hint"] || ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSm
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // The area. The default is the data's own extent; naming a smaller
            // one is how a person limits both the analysis and its cost.
            ColumnLayout {
                Layout.fillWidth: true
                visible: root.dataset !== null
                spacing: Theme.spacingXs

                CheckBox {
                    objectName: "griddingWholeExtent"
                    text: root.txt["gridding.wholeExtent"] || ""
                    checked: root.wholeExtent
                    onToggled: root.wholeExtent = checked
                }
                TextField {
                    objectName: "griddingBounds"
                    visible: !root.wholeExtent
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    text: root.boundsText
                    placeholderText: root.txt["gridding.bounds.hint"] || ""
                    font.family: Theme.fontMono
                    onTextChanged: root.boundsText = text
                }
            }
        }
    }

    footer: Rectangle {
        color: Theme.surface
        implicitHeight: decision.implicitHeight + 2 * Theme.spacingMd

        RowLayout {
            id: decision
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            Label {
                Layout.fillWidth: true
                text: root.ready ? (root.txt["gridding.willRun"] || "")
                                 : (root.txt["gridding.blocked"] || "")
                color: root.ready ? Theme.ok : Theme.warn
                font.pixelSize: Theme.fontSm
                wrapMode: Text.WordWrap
            }
            Button {
                text: root.txt["dialog.cancel"] || ""
                onClicked: root.close()
            }
            Button {
                objectName: "griddingRun"
                text: root.txt["gridding.run"] || ""
                enabled: root.ready
                highlighted: enabled
                onClicked: {
                    // The file is the job's **input**, not a parameter: the
                    // store records a run's inputs from that list, and a run
                    // whose inputs are empty has no lineage to the data it
                    // was computed from.
                    root.controller.submit(root.method, root.parameters(),
                                           [root.dataset.path])
                    root.close()
                }
            }
        }
    }

    // What the operator is asked for. Every value here was typed or chosen;
    // nothing is inferred, which is the whole point of the screen.
    function parameters() {
        var d = root.dataset
        var p = {
            "target_crs": root.targetCrs,
            "pixel_size": parseFloat(root.pixelSize),
            "result_name": d.name.replace(/\.[^.]+$/, "")
                           + "_" + root.method.split(".")[1],
            "source_crs": d.crs || root.targetCrs
        }
        if (!root.wholeExtent)
            p["bounds"] = root.parsedBounds()
        if (d.kind === "table") {
            p["x_field"] = d.xField
            p["y_field"] = d.yField
        }
        if (root.method === "grid.idw") {
            p["unit"] = d.unit || ""
            p["value_field"] = d.valueField
            p["radius"] = parseFloat(root.radius)
            p["power"] = parseFloat(root.power)
            p["min_points"] = parseInt(root.minPoints)
        } else if (root.triangulated) {
            // No radius: a triangulation is bounded by the samples' convex
            // hull. `max_distance` is the optional extra limit, and it is sent
            // only when it was typed — sending 0 would null the whole grid.
            p["unit"] = d.unit || ""
            p["value_field"] = d.valueField
            if (parseFloat(root.maxDistance) > 0)
                p["max_distance"] = parseFloat(root.maxDistance)
        } else if (root.method === "grid.rasterize") {
            p["unit"] = d.unit || ""
            p["value_field"] = d.valueField
        }
        return p
    }

    // What `grid.cross_validate` is asked for: the parameters the run would
    // use, so the comparison scores the run about to be made and not a
    // textbook default.
    function comparisonParameters() {
        var d = root.dataset
        var p = {
            "target_crs": root.targetCrs,
            "source_crs": d.crs || root.targetCrs,
            "value_field": d.valueField,
            "radius": parseFloat(root.radius) > 0
                      ? parseFloat(root.radius)
                      : Math.max(1, Math.round((d.spacing || 1) * 3)),
            "power": parseFloat(root.power),
            "min_points": parseInt(root.minPoints),
            "folds": 5
        }
        if (d.kind === "table") {
            p["x_field"] = d.xField
            p["y_field"] = d.yField
        }
        if (parseFloat(root.maxDistance) > 0)
            p["max_distance"] = parseFloat(root.maxDistance)
        return p
    }

    // The measurement arrives as a probe result, like every other read-only
    // answer from the worker. It is advice: it moves nothing on the screen
    // by itself, and the person still chooses the method.
    Connections {
        target: root.controller
        function onMethodsCompared(result) {
            root.comparing = false
            root.comparison = result
        }
    }
}
