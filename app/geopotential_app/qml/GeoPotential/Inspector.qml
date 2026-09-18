import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential

// Section 8, right inspector: properties, unit, style, parameters, metadata,
// a provenance summary.
//
// Every value is shown with its unit, and the unit follows the CRS. A pixel
// size labelled `m` beside a geographic CRS is a falsehood on screen.
Rectangle {
    id: root
    required property var controller
    // Two sources, deliberately separate:
    //   `description` — what the worker read from the file, at full resolution
    //   `view`        — what the canvas is currently displaying
    // Conflating them would let a decimated view's statistics be read as the
    // dataset's, which is the same error the readout rule exists to prevent.
    property var description: ({})
    property var view: ({})
    // Which layer this is about. The Inspector reads the **active** layer, not
    // whatever was described last: those are different things the moment a
    // second layer exists.
    property var activeLayer: ({})

    readonly property var txt: controller.tr.strings

    color: Theme.surface

    Rectangle {
        anchors { top: parent.top; bottom: parent.bottom; left: parent.left }
        width: 1
        color: Theme.border
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        clip: true

        ColumnLayout {
            width: root.width - 2 * Theme.spacingSm
            spacing: Theme.spacingXs

            Label {
                text: root.txt["inspector.caption"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1
                Layout.bottomMargin: Theme.spacingXs
            }

            Label {
                visible: !root.description.name && root.view.lod === undefined
                text: root.txt["inspector.empty"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontMd
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            component Row_: RowLayout {
                property string key: ""
                property string value: ""
                property string hint: ""
                visible: value.length > 0
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Label {
                    text: key
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSm
                    Layout.preferredWidth: 96
                }
                Label {
                    id: valueLabel
                    text: value
                    color: Theme.text
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                    Layout.fillWidth: true
                    elide: Text.ElideMiddle

                    // A Label is not a Control and has no `hovered`; the
                    // handler supplies it. The tooltip also carries the full
                    // text, because an elided value is not a readable value.
                    HoverHandler { id: valueHover }
                    ToolTip.text: hint.length > 0 ? hint : value
                    ToolTip.visible: valueHover.hovered
                                     && (hint.length > 0 || valueLabel.truncated)
                    ToolTip.delay: 400
                }
            }

            Label {
                text: root.txt["inspector.theData"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1
                Layout.topMargin: Theme.spacingXs
                visible: root.description.name !== undefined
            }
            Row_ {
                key: root.txt["inspector.layer"]
                value: root.activeLayer && root.activeLayer.name
                       ? root.activeLayer.name : (root.description.name || "")
            }
            Row_ {
                key: root.txt["inspector.crs"]
                value: root.description.crs || ""
                hint: root.txt["inspector.crs.tip"]
            }
            Row_ {
                key: root.txt["inspector.crsUnit"]
                value: root.description.crs_unit || ""
            }
            Row_ {
                key: root.txt["inspector.valueUnit"]
                value: root.description.unit || ""
                hint: root.txt["inspector.valueUnit.tip"]
            }
            Row_ {
                key: root.txt["inspector.size"]
                value: root.description.width
                       ? root.txt["inspector.size.value"]
                             .replace("%1", root.description.width)
                             .replace("%2", root.description.height)
                       : ""
            }
            Row_ {
                key: root.txt["inspector.valid"]
                value: root.description.statistics
                       && root.description.statistics.valid_fraction !== undefined
                       ? root.txt["inspector.valid.value"].replace("%1",
                           (root.description.statistics.valid_fraction * 100).toFixed(1))
                       : ""
                hint: root.txt["inspector.valid.tip"]
            }
            Row_ {
                key: root.txt["inspector.range"]
                value: root.description.statistics
                       && root.description.statistics.min !== undefined
                       ? root.txt["inspector.range.value"]
                             .replace("%1", root.description.statistics.min.toFixed(4))
                             .replace("%2", root.description.statistics.max.toFixed(4))
                       : ""
            }
            Row_ {
                key: root.txt["inspector.mean"]
                value: root.description.statistics && root.description.statistics.mean !== undefined ? root.description.statistics.mean.toFixed(4) : ""
            }
            // The distribution, from the 32 bins the worker computed. Section
            // 9.3 asks for it, and M5's membership curve will sit on top of it.
            Histogram {
                txt: root.txt
                // `!!` because a QML bool binding refuses `undefined`, and
                // `statistics` is absent until the worker has described the
                // dataset.
                visible: !!(root.description.statistics
                            && root.description.statistics.histogram)
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingSm
                counts: root.description.statistics
                        && root.description.statistics.histogram
                        ? root.description.statistics.histogram.counts : []
                edges: root.description.statistics
                       && root.description.statistics.histogram
                       ? root.description.statistics.histogram.edges : []
                unit: root.description.unit || ""
            }

            Rectangle {
                visible: root.view.lod !== undefined
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingSm
                height: 1
                color: Theme.border
            }
            Label {
                text: root.txt["inspector.theView"]
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 1
                visible: root.view.lod !== undefined
            }

            Row_ {
                key: root.txt["inspector.view"]
                value: root.view.lod !== undefined && root.view.lod > 1
                       ? root.txt["inspector.view.decimated"].replace("%1", root.view.lod)
                       : (root.view.lod !== undefined
                          ? root.txt["inspector.view.full"] : "")
                hint: root.txt["inspector.view.tip"]
            }
            Row_ {
                key: root.txt["inspector.pixelsRead"]
                value: root.view.pixels_read !== undefined
                       ? root.txt["inspector.pixelsRead.value"]
                             .replace("%1", Number(root.view.pixels_read)
                                 .toLocaleString(Qt.locale(), "f", 0))
                             .replace("%2", Number(root.view.width * root.view.height)
                                 .toLocaleString(Qt.locale(), "f", 0))
                       : ""
                hint: root.txt["inspector.pixelsRead.tip"]
            }
            Row_ {
                key: root.txt["inspector.cache"]
                value: root.view.cache
                       ? root.txt["inspector.cache.value"]
                             .replace("%1", root.view.cache.mb)
                             .replace("%2", root.view.cache.entries)
                             .replace("%3", Math.round(root.view.cache.hit_rate * 100))
                       : ""
                hint: root.txt["inspector.cache.tip"]
            }

            Row_ {
                key: root.txt["inspector.colormap"]
                value: root.activeLayer && root.activeLayer.colormap
                       ? root.activeLayer.colormap : (root.view.colormap || "")
                hint: root.txt["colormap.displayOnly"]
            }

            Rectangle {
                visible: root.description.name !== undefined
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingSm
                height: 1
                color: Theme.border
            }

            Label {
                visible: root.description.name !== undefined
                Layout.fillWidth: true
                Layout.topMargin: Theme.spacingSm
                wrapMode: Text.WordWrap
                color: Theme.textMuted
                font.pixelSize: Theme.fontSm
                text: root.txt["inspector.boundary"]
            }

            Row_ {
                key: root.txt["inspector.project"]
                value: root.controller.projectName
                Layout.topMargin: Theme.spacingSm
            }
            Row_ {
                key: root.txt["inspector.app"]
                value: root.controller.appVersion
            }
            Row_ {
                key: root.txt["inspector.worker"]
                value: root.controller.workerVersion
            }
        }
    }
}
