"""Level 1 — reading the six formats, and planning resources.

MSP-03 names six: CSV, XYZ, GeoTIFF, COG, GeoPackage, Shapefile. MSP-06 says
no high-cost operation runs without a resource estimate.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from geopotential_worker.grid.planner import MB, Policy, plan_operation
from geopotential_worker.io.describe import (
    MAX_CLASSES,
    UnsupportedFormat,
    _classes,
    _statistics,
    classify,
    describe,
    sidecar_metadata,
)

ROOT = Path(__file__).resolve().parents[2]
def _data_dir() -> Path:
    """`data/` inside the tree when there is one, beside it otherwise.

    Both layouts are legitimate: the development workspace keeps the datasets
    as a sibling, and a clone of the repository carries them inside. See
    `tools/datadir.py`.
    """
    import os

    declared = os.environ.get("GEOPOTENTIAL_DATA")
    if declared:
        return Path(declared).expanduser().resolve()
    inside = ROOT / "data"
    return inside if inside.is_dir() else (ROOT.parent / "data").resolve()


DATA = _data_dir()
RASTER = DATA / "utah_forge" / "Distance_to_fault.tif"
TABLE = DATA / "utah_forge" / "anomaly_bouger_easting_northin_bouger.csv"
SHAPEFILE = DATA / "synthetic" / "blocks.shp"
GEOPACKAGE = DATA / "synthetic" / "traverse.gpkg"


class Classification(unittest.TestCase):
    def test_the_six_formats_are_recognised(self) -> None:
        self.assertEqual(classify(Path("a.tif")), "raster")
        self.assertEqual(classify(Path("a.cog")), "raster")
        self.assertEqual(classify(Path("a.gpkg")), "vector")
        self.assertEqual(classify(Path("a.shp")), "vector")
        self.assertEqual(classify(Path("a.csv")), "table")
        self.assertEqual(classify(Path("a.xyz")), "table")

    def test_an_unsupported_format_names_what_is_supported(self) -> None:
        with self.assertRaises(UnsupportedFormat) as ctx:
            classify(Path("report.pdf"))
        message = str(ctx.exception)
        self.assertIn("report.pdf", message)
        for expected in ("GeoTIFF", "GeoPackage", "Shapefile", "CSV"):
            self.assertIn(expected, message)

    def test_a_file_with_no_extension_is_refused_clearly(self) -> None:
        with self.assertRaises(UnsupportedFormat) as ctx:
            classify(Path("dataset"))
        self.assertIn("no extension", str(ctx.exception))


@unittest.skipUnless(RASTER.exists(), "the smoke dataset is absent")
class Rasters(unittest.TestCase):
    def test_a_geotiff_reports_what_the_wizard_shows(self) -> None:
        d = describe(RASTER)
        self.assertEqual(d.kind, "raster")
        self.assertEqual(d.driver, "GTiff")
        self.assertEqual(d.crs, "EPSG:26912")
        self.assertEqual(d.crs_unit, "metre")
        self.assertFalse(d.geographic)
        self.assertEqual(d.detail["width"], 979)
        self.assertEqual(d.detail["pixel_size_x"], 10.0)
        self.assertEqual(d.fields, ["band 1"])

    def test_statistics_include_a_histogram(self) -> None:
        """Section 9.3 shows one, and M5's membership editor will need it."""
        stats = describe(RASTER).statistics
        self.assertIn("histogram", stats)
        self.assertEqual(len(stats["histogram"]["counts"]), 32)
        self.assertEqual(len(stats["histogram"]["edges"]), 33)
        self.assertLess(stats["p2"], stats["p98"])
        self.assertAlmostEqual(stats["valid_fraction"], 0.8387, places=3)

    def test_the_serializable_form_holds_no_arrays(self) -> None:
        """It crosses the IPC boundary as JSON; a raster never does."""
        import json

        payload = describe(RASTER).as_dict()
        self.assertFalse([k for k in payload if k.startswith("_")])
        json.dumps(payload)  # raises if anything unserializable slipped in

    def test_a_declared_nodata_is_honoured(self) -> None:
        """Gate G3: declaring a value has to change what the rules see."""
        described = describe(RASTER, overrides={"nodata": 0.0})
        self.assertEqual(described.nodata, 0.0)
        self.assertEqual(described.detail["_declared_nodata"], 0.0)


@unittest.skipUnless(TABLE.exists(), "the table fixture is absent")
class Tables(unittest.TestCase):
    def test_a_csv_reports_its_columns_and_guesses_the_coordinates(self) -> None:
        d = describe(TABLE)
        self.assertEqual(d.kind, "table")
        self.assertEqual(d.fields, ["easting", "northing", "gCBGA"])
        self.assertEqual(d.detail["x_field"], "easting")
        self.assertEqual(d.detail["y_field"], "northing")
        self.assertEqual(d.detail["value_field"], "gCBGA")
        self.assertEqual(d.detail["rows"], 3735)

    def test_a_table_has_no_crs_of_its_own(self) -> None:
        """Which is why the sidecar exists, and why absence is a finding."""
        self.assertIsNone(describe(TABLE).crs)

    def test_a_sidecar_supplies_the_crs(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        try:
            csv = tmp / "points.csv"
            csv.write_text("easting,northing,v\n1,2,3\n4,5,6\n", encoding="utf-8")
            csv.with_suffix(".meta.json").write_text(
                '{"source_crs": "EPSG:26912", "unit": "mGal"}', encoding="utf-8"
            )
            self.assertEqual(sidecar_metadata(csv)["source_crs"], "EPSG:26912")
            d = describe(csv)
            self.assertEqual(d.crs, "EPSG:26912")
            self.assertEqual(d.unit, "mGal")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_override_beats_the_sidecar(self) -> None:
        """The operator's declaration is the most recent statement of fact."""
        tmp = Path(tempfile.mkdtemp())
        try:
            csv = tmp / "points.csv"
            csv.write_text("easting,northing,v\n1,2,3\n", encoding="utf-8")
            csv.with_suffix(".meta.json").write_text(
                '{"source_crs": "EPSG:4326"}', encoding="utf-8"
            )
            self.assertEqual(describe(csv, overrides={"crs": "EPSG:26912"}).crs,
                             "EPSG:26912")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(SHAPEFILE.exists() and GEOPACKAGE.exists(),
                     "vector fixtures absent; run ../tools/make_synthetic_data.py")
class Vectors(unittest.TestCase):
    def test_a_shapefile_is_described(self) -> None:
        d = describe(SHAPEFILE)
        self.assertEqual(d.kind, "vector")
        self.assertGreater(d.detail["features"], 0)
        self.assertTrue(d.detail["geometry_kinds"])
        self.assertIsNotNone(d.extent)

    def test_a_geopackage_is_described_and_lists_its_layers(self) -> None:
        d = describe(GEOPACKAGE)
        self.assertEqual(d.kind, "vector")
        self.assertGreater(d.detail["features"], 0)
        self.assertTrue(d.detail["layers"],
                        "a GeoPackage often holds several layers; name them")


class PlausibleUnits(unittest.TestCase):
    """The shortlist the wizard offers, from the table QA/QC judges against.

    It narrows a choice; it never makes one. A Bouguer anomaly between -243
    and -169 fits mGal — and fits metres too, which is exactly why this may
    not be applied as a guess.
    """

    def test_a_range_can_fit_more_than_one_unit(self) -> None:
        from geopotential_worker.qc.rules import plausible_units

        fits = plausible_units(-243.0, -169.0)
        self.assertIn("mGal", fits)
        self.assertGreater(len(fits), 1, "a single answer would be a guess")

    def test_a_range_outside_every_table_entry_fits_nothing(self) -> None:
        from geopotential_worker.qc.rules import plausible_units

        self.assertEqual(plausible_units(-1e12, 1e12), [])

    def test_containment_is_all_this_claims(self) -> None:
        """A narrow range sits inside every wide one, so a density between 2.2
        and 2.9 contradicts nothing — and the shortlist says so by listing
        everything. That is the honest answer and a useless hint, which is why
        the screen shows it only when it excluded something."""
        from geopotential_worker.qc.rules import UNIT_RANGES, plausible_units

        fits = plausible_units(2.2, 2.9)
        self.assertIn("g/cm3", fits)
        self.assertEqual(len(fits), len(UNIT_RANGES))

    def test_a_wide_range_does_exclude(self) -> None:
        from geopotential_worker.qc.rules import UNIT_RANGES, plausible_units

        fits = plausible_units(-243.0, -169.0)
        self.assertLess(len(fits), len(UNIT_RANGES))
        self.assertNotIn("g/cm3", fits)

    def test_a_non_finite_bound_answers_nothing(self) -> None:
        from geopotential_worker.qc.rules import plausible_units

        self.assertEqual(plausible_units(float("nan"), 1.0), [])

    def test_the_description_carries_the_shortlist(self) -> None:
        stats = describe(TABLE).as_dict()["statistics"]
        self.assertIn("unit_candidates", stats)
        self.assertIn("mGal", stats["unit_candidates"])
        self.assertEqual(stats["unit_count"], 6)
        self.assertLess(len(stats["unit_candidates"]), stats["unit_count"],
                        "this file's range should have excluded something")

    def test_the_shortlist_and_the_verdict_read_one_table(self) -> None:
        """A second copy of the ranges in the app would drift, and the wizard
        would offer a unit the QA/QC then flags."""
        from geopotential_worker.qc import rules

        self.assertIs(
            rules.plausible_units.__globals__["UNIT_RANGES"], rules.UNIT_RANGES)


class TheDescriptionIsPlainPython(unittest.TestCase):
    """`as_dict` is the serializable form. Numpy scalars are not it.

    `json.dumps` accepts a `numpy.float64` because it subclasses `float`, so a
    leak passes every encoding test and then arrives in QML as an opaque
    wrapper — no `toFixed`, no arithmetic, a panel that renders nothing. This
    checks the types rather than the encoding.
    """

    PLAIN = (bool, int, float, str, type(None))

    def _walk(self, value, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self.assertIsInstance(key, str, f"{path}: a non-string key")
                self._walk(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                self._walk(item, f"{path}[{index}]")
        else:
            # `type(...) is` and not `isinstance`: `numpy.float64` *is* a
            # `float` by inheritance, which is precisely why this leak was
            # invisible to every check that asked `isinstance`.
            self.assertIn(
                type(value), self.PLAIN,
                f"{path} is {type(value).__module__}.{type(value).__name__}, "
                f"not plain Python: {value!r}")

    def test_a_vector_description_holds_only_plain_types(self) -> None:
        self._walk(describe(SHAPEFILE).as_dict(), "vector")

    def test_a_geopackage_description_holds_only_plain_types(self) -> None:
        self._walk(describe(GEOPACKAGE).as_dict(), "gpkg")

    def test_a_raster_description_holds_only_plain_types(self) -> None:
        self._walk(describe(RASTER).as_dict(), "raster")


class Planning(unittest.TestCase):
    """MSP-06: no high-cost operation runs without an estimate."""

    def test_a_small_grid_runs_in_memory(self) -> None:
        plan = plan_operation("test", width=1000, height=1000, layers=1)
        self.assertIs(plan.policy, Policy.IN_MEMORY)
        self.assertTrue(plan.fits)
        self.assertEqual(plan.pixels, 1_000_000)
        self.assertAlmostEqual(plan.ram_bytes, 1_000_000 * 4 * 3)

    def test_a_huge_grid_is_blocked_not_refused(self) -> None:
        """Section 18.1: blocks and windows before memory mapping."""
        plan = plan_operation("test", width=60_000, height=60_000, layers=8)
        self.assertIn(plan.policy, (Policy.BLOCKED, Policy.REFUSE))
        if plan.policy is Policy.BLOCKED:
            self.assertIsNotNone(plan.block_rows)
            self.assertGreaterEqual(plan.block_rows, 1)
            self.assertLessEqual(plan.block_rows, 60_000)

    def test_the_estimate_states_its_assumptions(self) -> None:
        """An estimate that hides its assumptions cannot be argued with."""
        plan = plan_operation("test", width=100, height=100)
        self.assertTrue(plan.assumptions)
        self.assertTrue(any("float32" in a for a in plan.assumptions))
        self.assertTrue(any("working copies" in a for a in plan.assumptions))

    def test_the_summary_names_both_resources(self) -> None:
        summary = plan_operation("harmonize", width=500, height=500).summary()
        self.assertIn("harmonize", summary)
        self.assertIn("memory", summary)
        self.assertIn("disk", summary)

    def test_more_layers_cost_more(self) -> None:
        one = plan_operation("t", width=1000, height=1000, layers=1).ram_bytes
        eight = plan_operation("t", width=1000, height=1000, layers=8).ram_bytes
        self.assertEqual(eight, one * 8)

    def test_the_plan_is_serializable(self) -> None:
        import json

        json.dumps(plan_operation("t", width=10, height=10).as_dict())


class ClassCodes(unittest.TestCase):
    """The class codes a raster actually carries, exposed so they can be scored.

    `membership.categorical` refuses a code it was given no score for, which is
    the right refusal — scoring an unknown class zero turns a data gap into a
    scientific claim. But the Membership Editor could not list the codes, so
    the only way to satisfy that refusal was to already know them. Geology,
    land use and soil were unreachable through the interface; it is where the
    person using the product stopped.
    """

    def test_integer_codes_are_listed_with_their_counts(self) -> None:
        found = _classes(np.array([1, 2, 2, 3, 5, 5, 5], dtype=float))
        self.assertEqual(found["codes"], [1.0, 2.0, 3.0, 5.0])
        self.assertEqual(found["counts"], [1, 2, 1, 3])
        self.assertEqual(found["distinct"], 4)

    def test_a_gap_in_the_codes_is_not_invented(self) -> None:
        """4 is absent from the data, so 4 must not appear in the table: a
        class nobody has cannot be given a score that means anything."""
        found = _classes(np.array([1, 2, 3, 5], dtype=float))
        self.assertNotIn(4.0, found["codes"])

    def test_negative_codes_survive(self) -> None:
        found = _classes(np.array([-3, -3, 0, 7], dtype=float))
        self.assertEqual(found["codes"], [-3.0, 0.0, 7.0])
        self.assertEqual(found["counts"], [2, 1, 1])

    def test_a_continuous_field_has_no_classes(self) -> None:
        """Three distinct values do not make a code. Guessing here would put a
        scientific claim inside a heuristic."""
        self.assertIsNone(_classes(np.array([0.5, 1.5, 2.5])))

    def test_too_many_codes_are_counted_but_not_listed(self) -> None:
        """An integer elevation model is integral and is not a class raster.
        Saying how many there are is what lets the screen explain itself."""
        found = _classes(np.arange(200.0))
        self.assertEqual(found["distinct"], 200)
        self.assertEqual(found["codes"], [])
        self.assertEqual(found["limit"], MAX_CLASSES)

    def test_a_wide_integer_range_costs_no_sort(self) -> None:
        """Bounded by arithmetic, not by sorting every pixel."""
        self.assertIsNone(_classes(np.arange(0.0, 200_000.0)))

    def test_statistics_carries_classes_only_when_there_are_some(self) -> None:
        coded = _statistics(np.array([1, 1, 2, np.nan, 3], dtype=float))
        self.assertEqual(coded["classes"]["codes"], [1.0, 2.0, 3.0])
        # Counted over the valid pixels only; the NaN is not a class.
        self.assertEqual(sum(coded["classes"]["counts"]), coded["valid"])
        self.assertNotIn("classes", _statistics(np.array([0.1, 0.7, 2.3])))

    def test_the_real_class_layers_are_recognised(self) -> None:
        """The landslide dataset has all three kinds, which is why it is the
        one this is checked against."""
        factors = DATA / "conditioning_factors"
        if not (factors / "geology.tif").is_file():
            self.skipTest(f"{factors} não está no repositório")
        for name, expected in (("geology.tif", 4), ("landcover.tif", 9),
                               ("soil_drainage.tif", 5)):
            with self.subTest(layer=name):
                found = describe(factors / name).statistics["classes"]
                self.assertEqual(found["distinct"], expected)
                self.assertEqual(len(found["codes"]), expected)
        for name in ("slope.tif", "aspect.tif"):
            with self.subTest(layer=name):
                self.assertNotIn(
                    "classes", describe(factors / name).statistics,
                    f"{name} é contínua e foi oferecida como classes")


class ClassLegends(unittest.TestCase):
    """What a class code *means*, when the file says so.

    The table could score `1`, `2`, `3` since `0.8.03` and could not say which
    was granite. Three places carry a legend and all three are read; which one
    answered comes back with it, because a label asserts what a code means and
    an assertion without a source is not checkable.

    The two XML shapes are not guessed. Both were confirmed against GDAL 3.12
    before being parsed here: a hand-written RAT reads back through
    `GetDefaultRAT()` with these codes and names, and `SetCategoryNames` writes
    exactly this `<CategoryNames>` block.
    """

    RAT = """<PAMDataset>
  <PAMRasterBand band="1">
    <GDALRasterAttributeTable tableType="thematic">
      <FieldDefn index="0">
        <Name>VALUE</Name><Type>0</Type><Usage>5</Usage>
      </FieldDefn>
      <FieldDefn index="1">
        <Name>COUNT</Name><Type>0</Type><Usage>1</Usage>
      </FieldDefn>
      <FieldDefn index="2">
        <Name>CLASS_NAME</Name><Type>2</Type><Usage>2</Usage>
      </FieldDefn>
      <Row index="0"><F>1</F><F>9</F><F>granito</F></Row>
      <Row index="1"><F>2</F><F>9</F><F>xisto</F></Row>
      <Row index="2"><F>7</F><F>9</F><F>aluvião</F></Row>
    </GDALRasterAttributeTable>
  </PAMRasterBand>
</PAMDataset>
"""

    CATEGORIES = """<PAMDataset>
  <PAMRasterBand band="1">
    <CategoryNames>
      <Category>fundo</Category>
      <Category>granito</Category>
      <Category>xisto</Category>
    </CategoryNames>
  </PAMRasterBand>
</PAMDataset>
"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raster = self.root / "geologia.tif"
        self.raster.write_bytes(b"")          # só o nome importa ao leitor

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _labels(self):
        from geopotential_worker.io.class_labels import read_labels

        return read_labels(self.raster)

    def _write(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")

    def test_nothing_beside_the_file_means_no_legend(self) -> None:
        """E isso não é um erro: os códigos continuam pontuáveis sem nome."""
        self.assertIsNone(self._labels())

    def test_the_attribute_table_names_the_code_it_labels(self) -> None:
        """A RAT diz qual código cada nome pertence, e 7 não é a terceira
        linha por acaso — é o valor que está escrito nela."""
        self._write("geologia.tif.aux.xml", self.RAT)
        labels, source = self._labels()
        self.assertEqual(labels, {1.0: "granito", 2.0: "xisto",
                                  7.0: "aluvião"})
        self.assertEqual(source, "attribute table")

    def test_category_names_are_positional(self) -> None:
        """`CategoryNames` não nomeia o código: ele o implica pela posição,
        a partir de zero. O terceiro item rotula o código 2."""
        self._write("geologia.tif.aux.xml", self.CATEGORIES)
        labels, source = self._labels()
        self.assertEqual(labels, {0.0: "fundo", 1.0: "granito",
                                  2.0: "xisto"})
        self.assertEqual(source, "category names")

    def test_the_project_sidecar_wins_over_a_travelling_table(self) -> None:
        """O `.meta.json` é o que alguém escreveu para este projeto de
        propósito; a RAT pode ter viajado com o arquivo de outro estudo."""
        self._write("geologia.tif.aux.xml", self.RAT)
        self._write("geologia.meta.json",
                    json.dumps({"classes": {"1": "arenito"}}))
        labels, source = self._labels()
        self.assertEqual(source, "sidecar")
        self.assertEqual(labels, {1.0: "arenito"})

    def test_a_broken_legend_is_an_absent_legend(self) -> None:
        """Uma legenda ilegível nunca impede o raster de ser usado."""
        self._write("geologia.tif.aux.xml", "<PAMDataset><não fecha")
        self._write("geologia.meta.json", "{isto não é JSON")
        self.assertIsNone(self._labels())

    def test_a_label_is_one_bounded_line(self) -> None:
        """Uma legenda que não cabe numa linha não é uma legenda, e uma
        célula de tabela não mostra um parágrafo."""
        from geopotential_worker.io.class_labels import MAX_LABEL

        self._write("geologia.meta.json", json.dumps(
            {"classes": {"1": "granito\n  porfirítico   " + "x" * 400}}))
        labels, _ = self._labels()
        self.assertLessEqual(len(labels[1.0]), MAX_LABEL)
        self.assertNotIn("\n", labels[1.0])
        self.assertTrue(labels[1.0].startswith("granito porfirítico "))

    # ---- o que chega ao editor -------------------------------------------

    def test_the_legend_reaches_the_statistics_positionally(self) -> None:
        """A tela emparelha nome e código sem re-derivar a ordem."""
        import numpy as np

        from geopotential_worker.io.describe import _classes

        self._write("geologia.tif.aux.xml", self.RAT)
        found = _classes(np.array([1, 1, 2, 7], dtype=float), self.raster)
        self.assertEqual(found["codes"], [1.0, 2.0, 7.0])
        self.assertEqual(found["labels"], ["granito", "xisto", "aluvião"])
        self.assertEqual(found["label_source"], "attribute table")
        self.assertEqual(found["labelled"], 3)

    def test_a_code_the_legend_skips_stays_visibly_unnamed(self) -> None:
        """Inventar "classe 3" faria uma legenda ausente parecer presente."""
        import numpy as np

        from geopotential_worker.io.describe import _classes

        self._write("geologia.meta.json",
                    json.dumps({"classes": {"1": "granito", "7": "aluvião"}}))
        found = _classes(np.array([1, 2, 7], dtype=float), self.raster)
        self.assertEqual(found["labels"], ["granito", "", "aluvião"])
        self.assertEqual(found["labelled"], 2)

    def test_a_legend_for_another_raster_is_not_reported(self) -> None:
        """Nomear zero dos códigos presentes é a legenda de outro arquivo, e
        mostrá-la seria pior do que não mostrar nenhuma."""
        import numpy as np

        from geopotential_worker.io.describe import _classes

        self._write("geologia.meta.json",
                    json.dumps({"classes": {"88": "basalto"}}))
        found = _classes(np.array([1, 2, 3], dtype=float), self.raster)
        self.assertNotIn("labels", found)
        self.assertNotIn("label_source", found)

    def test_without_a_source_the_codes_still_come_back(self) -> None:
        """A legenda é um extra. Quem chama `_classes` sem caminho — uma
        tabela, um array em memória — continua recebendo os códigos."""
        import numpy as np

        from geopotential_worker.io.describe import _classes

        found = _classes(np.array([1, 2, 3], dtype=float))
        self.assertEqual(found["codes"], [1.0, 2.0, 3.0])
        self.assertNotIn("labels", found)


if __name__ == "__main__":
    unittest.main()
