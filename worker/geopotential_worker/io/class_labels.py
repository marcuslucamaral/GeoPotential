"""What a class code means, when the file says so.

A class raster stores `1`, `2`, `3`. The Membership Editor can score those
codes since `0.8.03`, but scoring `3` without knowing it means gnaisse means
the person has to hold the legend in their head or in another window.

Three places carry the legend, and this reads all three. Which one answered is
returned with the labels: a label is an **assertion about what a code means**,
so where it came from is part of the provenance, not a detail.

| Source | Written by | Shape |
|---|---|---|
| `<name>.meta.json` | this project | `{"classes": {"1": "granito"}}` |
| `<name>.tif.aux.xml` RAT | QGIS, ArcGIS, GDAL | `<GDALRasterAttributeTable>` |
| `<name>.tif.aux.xml` categories | GDAL | `<CategoryNames>`, index is the code |

The XML shapes are not guessed. Both were confirmed against GDAL 3.12: a
hand-written RAT reads back through `GetDefaultRAT()` with the same codes and
names, and `SetCategoryNames` writes exactly the `<CategoryNames>` block parsed
here.

Parsed with the standard library. `osgeo.gdal` would read all three in one
call and is installed in the development environment, but it is not a declared
dependency of either package and would have to be added to the frozen bundle
to work on a machine that only has the release.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

#: GDAL's `GFU_Name` — the column of a RAT that holds the class name.
#: `GDALRATFieldUsage`, gdal_rat.h.
USAGE_NAME = 2
#: `GFU_MinMax`, `GFU_Min`, `GFU_Max` — the columns that hold the code itself.
USAGE_VALUE = (5, 3, 4)

#: Longest label kept. A RAT column can hold a paragraph; a table cell cannot,
#: and a legend that does not fit on one line is not a legend.
MAX_LABEL = 120


def read_labels(path: str | Path) -> tuple[dict[float, str], str] | None:
    """The legend for a class raster, and which source stated it.

    path     the raster
    returns  ({code: label}, source name), or None when nothing states one

    The order is deliberate. `<name>.meta.json` is what somebody wrote for this
    project on purpose, so it wins over a table that may have travelled with
    the file from another study. Within the sidecar-less case the RAT wins over
    `CategoryNames`, because a RAT names the code it labels while
    `CategoryNames` only implies it by position.
    """
    path = Path(path)
    for source, reader in (("sidecar", _from_sidecar),
                           ("attribute table", _from_rat),
                           ("category names", _from_categories)):
        try:
            labels = reader(path)
        except (OSError, ValueError, ET.ParseError):
            # A legend that cannot be read is a legend that is absent. It never
            # stops the raster being used: the codes still score without names.
            continue
        if labels:
            return labels, source
    return None


def _clean(text: str) -> str:
    """One line, bounded. Whitespace in a legend is formatting, not meaning."""
    return " ".join(text.split())[:MAX_LABEL]


def _from_sidecar(path: Path) -> dict[float, str]:
    """`<name>.meta.json`, the convention this project already uses for a CSV's
    CRS. `classes` maps a code, written as a string, to its name."""
    sidecar = path.with_suffix(".meta.json")
    if not sidecar.exists():
        return {}
    declared = json.loads(sidecar.read_text(encoding="utf-8"))
    classes = declared.get("classes")
    if not isinstance(classes, dict):
        return {}
    labels: dict[float, str] = {}
    for code, label in classes.items():
        try:
            labels[float(code)] = _clean(str(label))
        except (TypeError, ValueError):
            # A key that is not a number is not a class code. Skipping it is
            # better than refusing the whole legend over one bad row.
            continue
    return labels


def _pam(path: Path) -> ET.Element | None:
    """The `<PAMRasterBand>` of band 1, from `<name>.tif.aux.xml`."""
    aux = path.with_suffix(path.suffix + ".aux.xml")
    if not aux.exists():
        return None
    root = ET.fromstring(aux.read_text(encoding="utf-8"))
    for band in root.findall("PAMRasterBand"):
        if band.get("band", "1") == "1":
            return band
    return None


def _from_rat(path: Path) -> dict[float, str]:
    """The RAT's value column and name column, paired row by row."""
    band = _pam(path)
    if band is None:
        return {}
    table = band.find("GDALRasterAttributeTable")
    if table is None:
        return {}

    value_column = name_column = None
    for field in table.findall("FieldDefn"):
        usage = field.find("Usage")
        if usage is None or usage.text is None:
            continue
        index = int(field.get("index", "-1"))
        if int(usage.text) in USAGE_VALUE and value_column is None:
            value_column = index
        elif int(usage.text) == USAGE_NAME and name_column is None:
            name_column = index
    if name_column is None:
        return {}

    labels: dict[float, str] = {}
    for row in table.findall("Row"):
        cells = [cell.text or "" for cell in row.findall("F")]
        if name_column >= len(cells):
            continue
        # No value column declared: the row index is the code, which is what
        # GDAL itself falls back to.
        raw = (cells[value_column] if value_column is not None
               and value_column < len(cells) else row.get("index", ""))
        try:
            code = float(raw)
        except (TypeError, ValueError):
            continue
        label = _clean(cells[name_column])
        if label:
            labels[code] = label
    return labels


def _from_categories(path: Path) -> dict[float, str]:
    """`<CategoryNames>`, where the **position** is the code.

    GDAL writes the list from 0 up, so the third entry labels the code 2. An
    empty entry is a gap in the list, not a class named "".
    """
    band = _pam(path)
    if band is None:
        return {}
    categories = band.find("CategoryNames")
    if categories is None:
        return {}
    labels: dict[float, str] = {}
    for code, entry in enumerate(categories.findall("Category")):
        label = _clean(entry.text or "")
        if label:
            labels[float(code)] = label
    return labels
