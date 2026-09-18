import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import GeoPotential
import GeoPotential.Canvas

// The picture of a file, before it is a layer. ADR-MSP-004.
//
// Three kinds arrive here and each is drawn by the path that suits it:
//
//   raster  read straight from the file through the canvas's named seam —
//           the ADR is explicit that a raster does *not* travel as a preview,
//           because the canvas already reads windows of it at the right scale;
//   vector  the bounded silhouette the worker sampled, drawn as an outline;
//   table   the bounded point cloud the worker sampled.
//
// It answers one question — "is this the file I meant" — and it is wired to
// nothing else. No project, no store, no operator, no run. The caption says
// when what is on screen is a part of the file rather than the file.
Rectangle {
    id: root

    // What `io.describe_dataset` returned. Setting it redraws.
    property var description: ({})
    property var txt: ({})

    readonly property var preview: (description && description.preview) || ({})
    readonly property string kind: (description && description.kind) || ""
    readonly property bool partial: preview.decimated === true
                                    || preview.truncated === true
    // Whether anything could be drawn at all. A file whose kind we cannot draw
    // says so rather than showing an empty black box that reads as a failure.
    property bool drawn: false

    color: Theme.canvas
    border.color: Theme.border
    radius: Theme.radius
    clip: true

    onDescriptionChanged: root.reload()

    function reload() {
        canvas.clearLayers()
        root.drawn = false
        var d = root.description
        if (!d || !d.kind)
            return

        // Everything is read from `description` itself, never from the derived
        // `preview`/`kind` bindings above: when the description is assigned,
        // this handler can run *before* those re-evaluate, and the map then
        // draws the previous file — or nothing at all, which is what it did.
        var block = d.preview || ({})
        var crs = d.crs || ""
        var name = d.name || ""

        if (d.kind === "raster" && d.path) {
            // The file itself, at the scale the view needs. Nothing about the
            // raster crossed the IPC to get here.
            root.drawn = canvas.addLayer("preview", d.path, name, d.unit || "")
        } else if (d.kind === "vector" && block.parts !== undefined) {
            // Every declared argument, every time: a Qt slot called from QML
            // with fewer than it declares fails with "Insufficient arguments"
            // and returns undefined, which reads here as "nothing to draw".
            root.drawn = canvas.addGeometryLayer("preview", block.parts,
                                                 name, crs, d.crs_unit || "")
        } else if (d.kind === "table" && block.points !== undefined) {
            root.drawn = canvas.addPointLayer("preview", block.points, name,
                                              d.unit || "", crs,
                                              d.crs_unit || "")
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        MapItem {
            id: canvas
            // Never "the canvas": this one shows a file that is not in the
            // project yet. The shell's own map is `mapCanvas`.
            objectName: "previewCanvas"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ground: Theme.canvas
            // A preview is looked at, not worked in: no AOI, no measurement,
            // and no basemap fetching tiles for a file that has not been
            // imported. Pan and zoom stay, because "is this the right file"
            // sometimes needs a closer look.
            toolMode: "pan"
        }

        // What is on screen, and what it leaves out. A silhouette that does
        // not say it is a silhouette is a wrong drawing of the file.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: caption.implicitHeight + 2 * Theme.spacingXs
            color: Theme.surfaceAlt
            visible: caption.text.length > 0

            Label {
                id: caption
                anchors.fill: parent
                anchors.margins: Theme.spacingXs
                elide: Text.ElideRight
                font.pixelSize: Theme.fontSm
                color: root.partial ? Theme.warn : Theme.textMuted
                text: {
                    if (!root.drawn)
                        return root.txt["preview.map.none"] || ""
                    if (root.kind === "raster")
                        return root.txt["preview.map.raster"] || ""
                    if (root.kind === "vector")
                        return (root.txt["preview.map.vector"] || "")
                            .replace("%1", root.preview.shown || 0)
                            .replace("%2", root.preview.source_features || 0)
                    if (root.kind === "table")
                        return (root.txt["preview.map.table"] || "")
                            .replace("%1", (root.preview.points || []).length)
                            .replace("%2", root.preview.source_rows || 0)
                    return ""
                }
            }
        }
    }

    Label {
        anchors.centerIn: parent
        visible: !root.drawn
        text: root.txt["preview.map.empty"] || ""
        color: Theme.textMuted
        font.pixelSize: Theme.fontMd
    }
}
