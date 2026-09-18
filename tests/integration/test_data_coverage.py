"""Every file under `../data/` is exercised, and none of them silently rots.

The gap this closes was measured, not supposed. Before it existed, 26 of the
56 files in `../data/` were named by no test and no storyboard anywhere in the
tree — twelve landslide layers, two Utah FORGE surveys, and every file in
`data/synthetic/` that M0 produced and then stopped using.

An unused fixture is worse than no fixture. It takes space, it is listed in
the documentation as if it proved something, and when it breaks nothing says
so. So this suite walks the directory rather than naming files: **adding a
file to `../data/` adds it to this gate**, and a file that cannot be read has
to be fixed, removed, or declared.

What it does not do is duplicate the science. Whether IDW interpolates
correctly is `--only interpolation`; whether the QA/QC rules catch a missing
CRS is `--only qc`. This asks a narrower question of every file: **can the
product read you, and are you what your directory says you are?**
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.io.describe import (  # noqa: E402
    RASTER_SUFFIXES,
    TABLE_SUFFIXES,
    VECTOR_SUFFIXES,
    UnsupportedFormat,
    classify,
    describe,
)

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
#: Files that belong to another file and are never described on their own.
#: A shapefile is five files; a CSV states its CRS in a sidecar; a generated
#: directory states what it generated. None of them is a dataset.
COMPANION_SUFFIXES = {".prj", ".dbf", ".shx", ".cpg", ".qix", ".sbn", ".sbx",
                      ".xml", ".md", ".lock"}
COMPANION_NAMES = {"MANIFEST.json"}


def _is_companion(path: Path) -> bool:
    if path.name in COMPANION_NAMES or path.suffix.lower() in COMPANION_SUFFIXES:
        return True
    # `<name>.meta.json` is a sidecar; `<name>.geojson` is not.
    return path.name.endswith(".meta.json")


def _datasets() -> list[Path]:
    """Every file under `../data/` that claims to be a dataset."""
    return sorted(p for p in DATA.rglob("*")
                  if p.is_file() and not _is_companion(p))


@unittest.skipUnless(DATA.is_dir(), f"{DATA} não está aqui")
class EveryFileIsReadable(unittest.TestCase):
    """The walk. No file is named here; the directory is the list."""

    @classmethod
    def setUpClass(cls) -> None:
        for module in ("rasterio", "pandas", "geopandas"):
            try:
                __import__(module)
            except Exception as exc:                   # pragma: no cover
                raise unittest.SkipTest(f"{module} não instalado: {exc}")

    def test_there_is_something_to_walk(self) -> None:
        """A suíte que anda num diretório vazio passa sem testar nada."""
        found = _datasets()
        self.assertGreaterEqual(
            len(found), 40,
            f"só {len(found)} datasets em {DATA}; a suíte estaria passando "
            f"por não ter o que checar")

    def test_every_file_is_a_format_the_product_claims_to_read(self) -> None:
        """Um arquivo que o produto não lê não é fixture: é lixo no diretório,
        e o diretório é lido como se provasse alguma coisa."""
        strangers = []
        for path in _datasets():
            try:
                classify(path)
            except UnsupportedFormat:
                strangers.append(str(path.relative_to(DATA)))
        self.assertEqual(strangers, [],
                         "formatos que o produto não lê, em ../data/")

    def test_every_file_can_actually_be_described(self) -> None:
        """Ler é o piso. Um fixture defeituoso de propósito continua legível —
        o defeito dele é de CRS, de nodata ou de unidade, não de sintaxe."""
        failures = []
        for path in _datasets():
            try:
                described = describe(path)
            except Exception as exc:                   # noqa: BLE001
                failures.append(f"{path.relative_to(DATA)}: "
                                f"{type(exc).__name__}: {exc}")
                continue
            if described.kind not in ("raster", "vector", "table"):
                failures.append(f"{path.relative_to(DATA)}: kind "
                                f"{described.kind!r}")
        self.assertEqual(failures, [], "arquivos que o worker não consegue ler")

    def test_every_directory_says_what_it_holds(self) -> None:
        """Um diretório de dado sem procedência é dado sem origem. Cada um traz
        um `README.md` ou um `MANIFEST.json` — o primeiro para dado de
        terceiros, o segundo para o que este projeto gerou."""
        undocumented = []
        for path in _datasets():
            folder = path.parent
            if not ((folder / "README.md").exists()
                    or (folder / "MANIFEST.json").exists()):
                undocumented.append(str(folder.relative_to(DATA)))
        self.assertEqual(sorted(set(undocumented)), [],
                         "diretórios de dado sem README.md nem MANIFEST.json")


@unittest.skipUnless(DATA.is_dir(), f"{DATA} não está aqui")
class EveryFormatTheProductClaims(unittest.TestCase):
    """MSP-03 names six formats. A claim with no file behind it is a claim."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import geopandas  # noqa: F401
            import rasterio  # noqa: F401
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest(f"pilha geo ausente: {exc}")
        cls.found = _datasets()

    def _with_suffix(self, *suffixes: str) -> list[Path]:
        return [p for p in self.found if p.suffix.lower() in suffixes]

    def test_each_family_has_a_file(self) -> None:
        for family, suffixes in (("raster", RASTER_SUFFIXES),
                                 ("table", TABLE_SUFFIXES),
                                 ("vector", VECTOR_SUFFIXES)):
            with self.subTest(family=family):
                self.assertTrue(self._with_suffix(*suffixes),
                                f"nenhum arquivo {family} em ../data/")

    def test_geojson_is_present_and_read_as_a_vector(self) -> None:
        """Declarado desde o M3 e sem arquivo nenhum até `0.8.06`: o ramo era
        alcançável só por `.shp` e `.gpkg`."""
        found = self._with_suffix(".geojson")
        self.assertTrue(found, "`.geojson` é declarado legível e não há um")
        described = describe(found[0])
        self.assertEqual(described.kind, "vector")
        self.assertGreater(described.detail["features"], 0)

    def test_the_three_vector_formats_are_all_present(self) -> None:
        """Shapefile, GeoPackage e GeoJSON leem por caminhos diferentes do
        GDAL, e um funcionar não diz nada sobre os outros."""
        for suffix in (".shp", ".gpkg", ".geojson"):
            with self.subTest(format=suffix):
                self.assertTrue(self._with_suffix(suffix))

    def test_a_tiled_raster_with_overviews_exists(self) -> None:
        """O caminho COG: sem pirâmide, o canvas leria o raster inteiro para
        encher uma tela, que é o defeito que o M4 mede."""
        import rasterio

        tiled = []
        for path in self._with_suffix(*RASTER_SUFFIXES):
            with rasterio.open(path) as src:
                if src.profile.get("tiled") and src.overviews(1):
                    tiled.append(path)
        self.assertTrue(tiled, "nenhum raster com tiles e overviews")


@unittest.skipUnless((DATA / "conditioning_factors").is_dir(),
                     "o dataset de deslizamento não está aqui")
class EveryLandslideLayer(unittest.TestCase):
    """As vinte camadas, e não as sete que os testes citavam.

    Doze delas nunca tinham sido abertas por gate nenhum. O README do dataset
    declara 863x997, `EPSG:5186`, nodata -9999 para todas — uma declaração que
    vale para as vinte é uma declaração que se pode checar nas vinte.
    """

    FOLDER = DATA / "conditioning_factors"

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import rasterio  # noqa: F401
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest(f"rasterio ausente: {exc}")
        cls.layers = sorted(cls.FOLDER.glob("*.tif"))

    def test_all_twenty_are_there(self) -> None:
        self.assertEqual(len(self.layers), 20,
                         "o README declara 20 GeoTIFFs")

    def test_every_layer_is_on_the_one_grid_the_readme_declares(self) -> None:
        """Se uma estivesse fora da grade, harmonizar as vinte reamostraria
        essa uma sem que nada dissesse."""
        for path in self.layers:
            with self.subTest(layer=path.name):
                described = describe(path)
                self.assertEqual(described.crs, "EPSG:5186")
                self.assertEqual(described.detail["width"], 997)
                self.assertEqual(described.detail["height"], 863)
                self.assertEqual(described.detail["pixel_size_x"], 10.0)

    def test_every_layer_has_values(self) -> None:
        """Uma camada toda nula passa por qualquer teste de leitura e não
        serve de critério para nada."""
        for path in self.layers:
            with self.subTest(layer=path.name):
                stats = describe(path).statistics
                self.assertGreater(stats.get("valid", 0), 0)
                self.assertGreater(stats["valid_fraction"], 0.5)

    def test_the_layers_split_into_the_three_kinds_the_product_handles(self) -> None:
        """Contínua, classe e direção pedem pertinências diferentes, e é por
        isso que este dataset é o certo: ele tem os três. Qual camada é de
        qual tipo sai do arquivo, não de uma lista escrita à mão.
        """
        classes, continuous = [], []
        for path in self.layers:
            found = describe(path).statistics.get("classes")
            (classes if found and found["codes"] else continuous).append(path.name)

        self.assertGreaterEqual(len(classes), 3,
                                f"só {len(classes)} camadas de classe; "
                                f"geologia, uso do solo e solo são classes")
        self.assertGreaterEqual(len(continuous), 8)
        for expected in ("geology.tif", "landcover.tif", "soil_drainage.tif"):
            with self.subTest(layer=expected):
                self.assertIn(expected, classes)
        for expected in ("slope.tif", "twi.tif", "ls_factor.tif"):
            with self.subTest(layer=expected):
                self.assertIn(expected, continuous)

    def test_aspect_is_a_direction_and_carries_the_flat_cell_sentinel(self) -> None:
        """`-1` para célula plana não é um azimute perto de zero. É o dado que
        obrigou `circular` a recusar negativo em vez de embrulhar."""
        import numpy as np
        import rasterio

        with rasterio.open(self.FOLDER / "aspect.tif") as src:
            values = src.read(1)
            valid = values[values != src.nodata]
        self.assertGreater(float(valid.max()), 300.0, "azimute vai até ~360")
        self.assertTrue((valid < 0).any(),
                        "a sentinela de célula plana sumiu do dataset")


@unittest.skipUnless((DATA / "synthetic" / "msp" / "broken").is_dir(),
                     "os fixtures defeituosos não estão aqui")
class EveryBrokenFixtureIsStillBroken(unittest.TestCase):
    """Cada um carrega exatamente um defeito, e o manifesto diz qual.

    Um fixture defeituoso que silenciosamente deixou de ser defeituoso é um
    gate verde que não testa nada.
    """

    FOLDER = DATA / "synthetic" / "msp" / "broken"

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import rasterio  # noqa: F401
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest(f"rasterio ausente: {exc}")
        cls.manifest = json.loads(
            (cls.FOLDER / "MANIFEST.json").read_text(encoding="utf-8"))

    def test_the_manifest_lists_every_file_in_the_directory(self) -> None:
        listed = {row["file"] for row in self.manifest["fixtures"]}
        present = {p.name for p in self.FOLDER.iterdir()
                   if p.is_file() and not _is_companion(p)}
        self.assertEqual(present - listed, set(),
                         "arquivo no diretório e fora do manifesto: ninguém "
                         "sabe que defeito ele deveria ter")
        self.assertEqual(listed - present, set(),
                         "o manifesto promete um fixture que não está lá")

    def _context(self) -> list[dict]:
        """As outras camadas do projeto, que é o que `extent.overlap` e
        `grid.resolution_mismatch` comparam contra.

        Duas regras não são propriedades de um arquivo sozinho: uma extensão
        só é disjunta *de alguma coisa*, e 100 m só é grosseiro ao lado de
        10 m. A referência é a camada de que o manifesto diz que os fixtures
        foram gerados — escrevê-la à mão aqui seria inventar o contraste que
        a regra mede.
        """
        source = DATA.parent / self.manifest["generated_from"]
        if not source.is_file():
            self.skipTest(f"{source} não está aqui")
        described = describe(source)
        return [{
            "name": source.name,
            "extent": list(described.extent),
            "pixel_size": [described.detail["pixel_size_x"],
                           described.detail["pixel_size_y"]],
        }]

    def test_every_declared_defect_is_still_there(self) -> None:
        """Lido pela regra que o manifesto nomeia, e não por inspeção geral:
        o manifesto é o contrato e é ele que tem de bater."""
        from geopotential_worker.qc.validate import validate

        context = self._context()
        for row in self.manifest["fixtures"]:
            with self.subTest(fixture=row["file"], rule=row["expected_rule"]):
                path = self.FOLDER / row["file"]
                described = describe(path)
                report = validate(described, context=context,
                                  require_metric=True)
                raised = {f["rule"] for f in report.as_dict()["findings"]}
                self.assertIn(
                    row["expected_rule"], raised,
                    f"{row['file']} deveria acusar {row['expected_rule']!r} "
                    f"({row['defect']}); acusou {sorted(raised)}")

    def test_the_declared_severity_is_the_one_raised(self) -> None:
        """Um BLOCKER que virou aviso continua sendo acusado e deixa de
        parar a run, que é o que ele existe para fazer."""
        from geopotential_worker.qc.validate import validate

        context = self._context()
        for row in self.manifest["fixtures"]:
            with self.subTest(fixture=row["file"]):
                described = describe(self.FOLDER / row["file"])
                report = validate(described, context=context,
                                  require_metric=True)
                severities = {f["severity"] for f
                              in report.as_dict()["findings"]
                              if f["rule"] == row["expected_rule"]}
                self.assertEqual(severities, {row["expected_severity"]},
                                 f"{row['file']}: severidade mudou")


@unittest.skipUnless((DATA / "britain_magnetic").is_dir()
                     and (DATA / "bushveld_gravity").is_dir(),
                     "os levantamentos geofísicos reais não estão aqui")
class TheRealGeophysicalSurveys(unittest.TestCase):
    """Magnetometria e gravimetria reais, que este projeto não tinha.

    Até `0.8.06` todo gate do módulo de campos potenciais — RTP, sinal
    analítico, tilt, continuação — rodava sobre um campo sintético que o
    próprio projeto gerava. Isso testa a aritmética e não o dado.

    Os dois vêm com DOI, licença CC-BY e SHA256 publicado, e o checksum de
    origem foi conferido no download.
    """

    MAGNETIC = DATA / "britain_magnetic" / "britain_magnetic_pennines.csv"
    GRAVITY = DATA / "bushveld_gravity" / "bushveld_gravity.csv"

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import pandas  # noqa: F401
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest(f"pandas ausente: {exc}")

    def test_the_magnetic_survey_reads_as_nanotesla(self) -> None:
        described = describe(self.MAGNETIC)
        self.assertEqual(described.kind, "table")
        self.assertEqual(described.unit, "nT")
        self.assertEqual(described.detail["value_field"],
                         "total_field_anomaly_nt")
        self.assertEqual(described.detail["rows"], 4102)

    def test_the_gravity_survey_reads_as_milligal(self) -> None:
        described = describe(self.GRAVITY)
        self.assertEqual(described.unit, "mGal")
        self.assertEqual(described.detail["rows"], 3877)

    def test_both_are_geographic_which_is_the_point(self) -> None:
        """Uma operação métrica em graus é recusada por nome. Estes dois
        provam a recusa contra dado real, e não contra um fixture escrito
        para disparar a recusa."""
        from geopotential_worker.domain.crs import CrsInfo

        for path in (self.MAGNETIC, self.GRAVITY):
            with self.subTest(survey=path.name):
                described = describe(path)
                self.assertEqual(described.crs, "EPSG:4326")
                self.assertTrue(described.geographic)
                crs = CrsInfo.from_user_input(described.crs, source="fixture")
                with self.assertRaises(ValueError) as raised:
                    crs.require_metric("interpolação em metros")
                self.assertIn("metr", str(raised.exception).lower())

    def test_the_sidecar_is_what_makes_the_csv_readable(self) -> None:
        """Um CSV não tem onde dizer CRS nem unidade. Sem o sidecar, ambos
        ficam ausentes — e ausente é reportado, nunca suposto."""
        for path in (self.MAGNETIC, self.GRAVITY):
            with self.subTest(survey=path.name):
                sidecar = path.with_suffix(".meta.json")
                self.assertTrue(sidecar.exists())
                declared = json.loads(sidecar.read_text(encoding="utf-8"))
                for key in ("source_crs", "unit", "x_field", "y_field",
                            "value_field"):
                    self.assertIn(key, declared)

    def test_the_gravity_file_holds_more_than_one_field(self) -> None:
        """`gravity_disturbance_mgal` e `gravity_bouguer_mgal` são campos
        diferentes sobre as mesmas estações. Escolher um por acidente daria
        outro mapa sem dizer nada."""
        import numpy as np
        import pandas as pd

        frame = pd.read_csv(self.GRAVITY)
        for column in ("gravity_mgal", "gravity_disturbance_mgal",
                       "gravity_bouguer_mgal"):
            self.assertIn(column, frame.columns)
        self.assertFalse(np.allclose(frame["gravity_disturbance_mgal"],
                                     frame["gravity_bouguer_mgal"]))

    def test_the_magnetic_anomaly_has_the_sign_change_a_field_has(self) -> None:
        """Um campo de anomalia cruza o zero. Um que não cruza é um campo com
        um nível regional dentro, e os operadores espectrais leriam esse
        nível como sinal."""
        import pandas as pd

        values = pd.read_csv(self.MAGNETIC)["total_field_anomaly_nt"]
        self.assertLess(values.min(), 0.0)
        self.assertGreater(values.max(), 0.0)


class _Ctx:
    """Um diretório por operação, que é o que o Project Store faz."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.emitted: list = []

    def progress(self, stage, fraction, message=""):  # noqa: ANN001
        pass

    def check_cancel(self):
        pass

    def emit(self, name, artifact):  # noqa: ANN001
        self.emitted.append((name, artifact))


@unittest.skipUnless(DATA.is_dir(), f"{DATA} não está aqui")
class TheScienceRunsOnAllOfThem(unittest.TestCase):
    """Ler não é usar.

    A suíte acima prova que todo arquivo abre. Esta faz os que nunca tinham
    entrado em gate nenhum atravessarem o caminho de verdade — interpolação,
    harmonização, agregação, campos potenciais. Doze camadas de deslizamento,
    dois levantamentos do Utah FORGE e a magnetometria real chegaram aqui sem
    nunca terem sido computadas por nada.
    """

    @classmethod
    def setUpClass(cls) -> None:
        for module in ("rasterio", "pandas", "scipy"):
            try:
                __import__(module)
            except Exception as exc:                   # pragma: no cover
                raise unittest.SkipTest(f"{module} não instalado: {exc}")

    def setUp(self) -> None:
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, operator: str, params: dict, inputs, folder: str):
        from geopotential_worker.operators import registry

        op = registry.get(operator)
        ctx = _Ctx(self.root / folder)
        return op.run(list(inputs), op.validate(params), ctx), ctx

    # ---- as vinte camadas, e não as sete que os testes citavam ------------

    @unittest.skipUnless((DATA / "conditioning_factors" / "forest_age.tif").is_file(),
                         "o dataset de deslizamento não está aqui")
    def test_every_landslide_layer_can_be_a_criterion(self) -> None:
        """Doze das vinte nunca tinham sido computadas por gate nenhum.

        Cada uma vira pertinência pela função que o **tipo dela** pede — classe
        ou contínua, lido do arquivo — e a agregação roda sobre as vinte de uma
        vez. Uma camada que não sobrevive a isso é uma camada que o produto
        oferece e não processa.
        """
        folder = DATA / "conditioning_factors"
        criteria = []
        for path in sorted(folder.glob("*.tif")):
            if path.name == "aspect.tif":
                continue           # direção pede `circular`, testada à parte
            found = describe(path).statistics.get("classes")
            if found and found["codes"]:
                criteria.append({
                    "path": str(path), "name": path.stem, "unit": "classe",
                    "function": "categorical",
                    # Nota igual para toda classe: o que se testa aqui é que a
                    # camada atravessa, não qual classe é favorável.
                    "mapping": {code: 0.5 for code in found["codes"]},
                })
            else:
                criteria.append({
                    "path": str(path), "name": path.stem, "unit": "",
                    "function": "linear_increasing",
                })

        self.assertEqual(len(criteria), 19,
                         "o dataset tem 20 camadas, menos o aspecto")
        # Pesos iguais, declarados: a combinação linear **recusa** rodar sem
        # eles — "sem pesos não há combinação, só uma média que ninguém
        # escolheu" — e o que se testa aqui é que cada camada atravessa, não
        # qual delas pesa mais.
        weight = 1.0 / len(criteria)
        manifest, ctx = self._run("decision.aggregate", {
            "criteria": criteria, "method": "weighted_linear_combination",
            "weights": [{"name": c["name"], "weight": weight}
                        for c in criteria],
            "result_name": "todas_as_camadas",
        }, [], "todas")

        self.assertEqual(len(manifest["criteria"]), 19)
        valid = float((manifest.get("result") or {}).get("valid_fraction") or 0)
        self.assertGreater(valid, 0.9,
                           f"só {valid:.1%} das células com score sobre as 19 "
                           f"camadas; alguma está anulando a análise")
        self.assertEqual(len(ctx.emitted), 1)

    # ---- os dois levantamentos do Utah que ninguém tinha aberto -----------

    @unittest.skipUnless((DATA / "utah_forge" / "top_basement_500m.csv").is_file(),
                         "os fixtures do Utah FORGE não estão aqui")
    def test_the_two_unused_utah_surveys_become_grids(self) -> None:
        """`top_basement_500m.csv` e `magtellu_min_depth_500m.csv` estavam no
        repositório desde o M0 e nenhum gate os tinha lido."""
        import rasterio

        # Os dois não são a mesma coisa em duas cópias, e nem escrevem a
        # coluna do mesmo jeito: um traz a elevação do topo do embasamento com
        # nomes entre colchetes, o outro traz **resistividade** magnetotelúrica
        # com nomes sublinhados. Declarar cada um é a única leitura honesta.
        for name, x, y, column, unit in (
            ("top_basement_500m.csv",
             "Easting[m]", "Northing[m]", "Elevation[m]", "m"),
            ("magtellu_min_depth_500m.csv",
             "Easting_m", "Northing_m", "Resistivity_ohmm", "ohm.m"),
        ):
            with self.subTest(survey=name):
                source = DATA / "utah_forge" / name
                self.assertIn(column, describe(source).fields,
                              f"{name} mudou de colunas")
                _, ctx = self._run("grid.tin_cubic", {
                    "target_crs": "EPSG:26912", "source_crs": "EPSG:26912",
                    "pixel_size": 500.0,
                    "x_field": x, "y_field": y,
                    "value_field": column, "unit": unit,
                    "result_name": source.stem,
                }, [str(source)], source.stem)
                artifact = ctx.emitted[0][1].path
                with rasterio.open(artifact) as src:
                    import numpy as np
                    band = src.read(1)
                self.assertTrue(np.isfinite(band).any(),
                                f"{name} virou uma grade toda nula")

    # ---- a magnetometria real, que o módulo nunca tinha visto ------------

    @unittest.skipUnless(
        (DATA / "britain_magnetic" / "britain_magnetic_pennines.csv").is_file(),
        "o levantamento aeromagnético não está aqui")
    def test_the_real_magnetic_survey_reaches_the_potential_field_operators(self) -> None:
        """Toda FIS-01..08 rodava sobre um campo sintético que este projeto
        gerava. Isso testa a aritmética; isto testa o dado.

        A corrente inteira: pontos em graus -> grade métrica -> derivada e
        sinal analítico. O levantamento é geográfico, então a reprojeção é
        parte do teste e não um detalhe.
        """
        import numpy as np
        import rasterio

        source = DATA / "britain_magnetic" / "britain_magnetic_pennines.csv"
        # EPSG:27700, British National Grid: métrico, e o CRS em que este
        # levantamento foi de fato voado.
        _, ctx = self._run("grid.tin_cubic", {
            "target_crs": "EPSG:27700", "source_crs": "EPSG:4326",
            "pixel_size": 1000.0,
            "x_field": "longitude", "y_field": "latitude",
            "value_field": "total_field_anomaly_nt", "unit": "nT",
            "result_name": "magnetico",
        }, [str(source)], "magnetico")
        grid = ctx.emitted[0][1].path

        manifest, ctx = self._run("potential_fields.derivative", {
            "axis": "z", "order": 1, "field_kind": "magnetic",
            "unit": "nT", "result_name": "dz",
        }, [str(grid)], "derivada")
        with rasterio.open(ctx.emitted[0][1].path) as src:
            derivative = src.read(1)
        self.assertTrue(np.isfinite(derivative).any(),
                        "a derivada vertical do campo real saiu toda nula")
        # O que o manifesto tem de registrar: a suposição mais forte de todas.
        self.assertEqual(manifest.get("field_kind"), "magnetic")

        _, ctx = self._run("potential_fields.analytic_signal",
                           {"field_kind": "magnetic", "unit": "nT",
                            "result_name": "sinal_analitico"},
                           [str(grid)], "sinal")
        with rasterio.open(ctx.emitted[0][1].path) as src:
            signal = src.read(1)
        finite = signal[np.isfinite(signal)]
        self.assertTrue(finite.size > 0)
        self.assertTrue((finite >= 0).all(),
                        "o sinal analítico é uma magnitude e saiu negativo "
                        "sobre dado real")

    @unittest.skipUnless(
        (DATA / "bushveld_gravity" / "bushveld_gravity.csv").is_file(),
        "o levantamento gravimétrico não está aqui")
    def test_the_real_gravity_survey_becomes_a_criterion(self) -> None:
        """Gravimetria real num contexto geológico que não é Utah: o Bushveld
        é uma intrusão acamadada, e a anomalia Bouguer aqui vai de -178 a +75
        mGal contra a janela estreita do Utah."""
        import numpy as np
        import rasterio

        source = DATA / "bushveld_gravity" / "bushveld_gravity.csv"
        # EPSG:32735, UTM 35S: métrico, e a zona em que o Bushveld cai.
        _, ctx = self._run("grid.tin_cubic", {
            "target_crs": "EPSG:32735", "source_crs": "EPSG:4326",
            "pixel_size": 5000.0,
            "x_field": "longitude", "y_field": "latitude",
            "value_field": "gravity_bouguer_mgal", "unit": "mGal",
            "result_name": "bouguer",
        }, [str(source)], "bouguer")
        grid = ctx.emitted[0][1].path

        manifest, _ = self._run("decision.aggregate", {
            "criteria": [{"path": str(grid), "name": "bouguer",
                          "unit": "mGal", "function": "linear_decreasing"}],
            "method": "weighted_linear_combination",
            "weights": [{"name": "bouguer", "weight": 1.0}],
            "result_name": "densidade_favoravel",
        }, [], "agregado")
        self.assertEqual(manifest["criteria"][0]["name"], "bouguer")
        with rasterio.open(grid) as src:
            values = src.read(1)
        finite = values[np.isfinite(values)]
        self.assertLess(float(finite.min()), 0.0)
        self.assertGreater(float(finite.max()), 0.0)


@unittest.skipUnless((DATA / "southern_africa").is_dir()
                     and (DATA / "bushveld_gravity").is_dir(),
                     "a região da África Austral não está aqui")
class OneRegionSeveralKinds(unittest.TestCase):
    """Vários tipos de medida sobre o mesmo terreno — o caso que o produto
    existe para consumir, e que nenhum diretório daqui forçava.

    Utah FORGE tem seis tabelas esparsas e um raster, tudo num CRS só e tudo
    geotérmico. O dataset de deslizamento tem vinte camadas, todas raster,
    todas numa grade só. Nenhum dos dois faz o produto atravessar **um raster
    contra um levantamento esparso em dois CRS diferentes** sobre uma área —
    que é o caso comum.

    Aqui: topografia em `EPSG:3857`, gravimetria regional e local em
    `EPSG:4326`, sobre o Bushveld.
    """

    REGION = DATA / "southern_africa"
    TOPOGRAPHY = REGION / "southern_africa_topography.tif"
    GRAVITY = REGION / "southern_africa_gravity.csv"
    BUSHVELD = DATA / "bushveld_gravity" / "bushveld_gravity.csv"

    @classmethod
    def setUpClass(cls) -> None:
        for module in ("rasterio", "pandas", "scipy", "pyproj"):
            try:
                __import__(module)
            except Exception as exc:                   # pragma: no cover
                raise unittest.SkipTest(f"{module} não instalado: {exc}")

    def setUp(self) -> None:
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, operator: str, params: dict, inputs, folder: str):
        from geopotential_worker.operators import registry

        op = registry.get(operator)
        ctx = _Ctx(self.root / folder)
        return op.run(list(inputs), op.validate(params), ctx), ctx

    def test_the_three_really_cover_the_same_ground(self) -> None:
        """Medido, não afirmado. Três arquivos numa pasta chamada "uma região"
        não são uma região até a extensão de um conter a do outro."""
        import pandas as pd
        import pyproj
        import rasterio

        with rasterio.open(self.TOPOGRAPHY) as src:
            to_degrees = pyproj.Transformer.from_crs(
                src.crs, "EPSG:4326", always_xy=True)
            left, bottom = to_degrees.transform(src.bounds.left,
                                                src.bounds.bottom)
            right, top = to_degrees.transform(src.bounds.right, src.bounds.top)

        for name, path in (("regional", self.GRAVITY),
                           ("bushveld", self.BUSHVELD)):
            with self.subTest(survey=name):
                frame = pd.read_csv(path)
                inside = ((frame.longitude > left) & (frame.longitude < right)
                          & (frame.latitude > bottom)
                          & (frame.latitude < top)).mean()
                self.assertGreater(
                    inside, 0.95,
                    f"só {inside:.1%} de {name} cai no raster de topografia; "
                    f"então não é a mesma região")

    def test_the_kinds_really_differ(self) -> None:
        """Três arquivos do mesmo tipo não testam o que este diretório
        promete: um é raster, dois são esparsos, e os CRS não coincidem."""
        topography = describe(self.TOPOGRAPHY)
        gravity = describe(self.GRAVITY)
        self.assertEqual(topography.kind, "raster")
        self.assertEqual(gravity.kind, "table")
        self.assertNotEqual(topography.crs, gravity.crs,
                            "os dois no mesmo CRS não fazem a reprojeção "
                            "entrar no caminho")
        self.assertEqual(topography.unit, "m")
        self.assertEqual(gravity.unit, "mGal")
        self.assertFalse(topography.geographic)
        self.assertTrue(gravity.geographic)

    def test_the_topography_carries_the_pyramid_the_canvas_needs(self) -> None:
        """Sem overviews o canvas leria 4 milhões de pixels para encher uma
        tela, que é o defeito que o M4 mede."""
        import rasterio

        with rasterio.open(self.TOPOGRAPHY) as src:
            self.assertTrue(src.profile.get("tiled"))
            self.assertGreaterEqual(len(src.overviews(1)), 3)
            self.assertEqual(src.width, 2048)

    def test_the_observed_gravity_is_not_an_anomaly(self) -> None:
        """O regional traz gravidade **observada**, perto de 978 000 mGal; o
        Bushveld traz a anomalia, perto de zero. Tratar um como o outro dá um
        mapa diferente sem dizer nada, e é por isso que os dois estão aqui."""
        import pandas as pd

        observed = pd.read_csv(self.GRAVITY)["gravity_mgal"]
        anomaly = pd.read_csv(self.BUSHVELD)["gravity_bouguer_mgal"]
        self.assertGreater(observed.min(), 900_000.0)
        self.assertLess(abs(anomaly.mean()), 1_000.0)

    def test_a_raster_and_a_scattered_survey_reach_one_analysis(self) -> None:
        """A corrente inteira sobre uma região de verdade: o esparso vira
        grade, os dois vão para uma grade só, e a agregação sai.

        É o que nenhum fixture daqui forçava — o Utah tem tudo num CRS, e o
        deslizamento já vem tudo numa grade.
        """
        import numpy as np
        import rasterio

        # EPSG:32735, UTM 35S: métrico, e a zona em que o Bushveld cai.
        target, pixel = "EPSG:32735", 5000.0

        _, ctx = self._run("grid.tin_cubic", {
            "target_crs": target, "source_crs": "EPSG:4326",
            "pixel_size": pixel,
            "x_field": "longitude", "y_field": "latitude",
            "value_field": "gravity_bouguer_mgal", "unit": "mGal",
            "result_name": "bouguer",
        }, [str(self.BUSHVELD)], "bouguer")
        gravity_grid = ctx.emitted[0][1].path

        manifest, ctx = self._run("grid.harmonize", {
            "target_crs": target, "pixel_size": pixel,
            "extent_policy": "intersection",
            "layers": [
                {"path": str(self.TOPOGRAPHY), "name": "elevacao", "unit": "m"},
                {"path": str(gravity_grid), "name": "bouguer", "unit": "mGal"},
            ],
        }, [], "harmonizado")

        self.assertEqual(len(manifest["layers"]), 2)
        self.assertIn("32735", str(manifest["grid"]["crs"]))
        # A interseção medida: 140x89 a 5 km. Fixado porque uma grade que
        # encolhe para meia dúzia de células faria as asserções abaixo
        # passarem sem que nada tenha sido harmonizado.
        cells = manifest["grid"]["width"] * manifest["grid"]["height"]
        self.assertGreater(cells, 10_000,
                           f"a interseção deu {cells} células; o raster e o "
                           f"levantamento mal se encontram")
        on_grid = {layer["name"]: layer["artifact"]
                   for layer in manifest["layers"]}

        # Elevação alta e anomalia baixa: uma pergunta de prospecção, montada
        # com as duas grandezas que só esta região oferece juntas.
        result, ctx = self._run("decision.aggregate", {
            "criteria": [
                {"path": on_grid["elevacao"], "name": "elevacao",
                 "unit": "m", "function": "linear_increasing"},
                {"path": on_grid["bouguer"], "name": "bouguer",
                 "unit": "mGal", "function": "linear_decreasing"},
            ],
            "method": "fuzzy_gamma", "gamma": 0.7,
            "result_name": "prospectividade",
        }, [], "agregado")

        self.assertEqual(len(result["criteria"]), 2)
        valid = float((result.get("result") or {}).get("valid_fraction") or 0)
        # Medido: 88,2 %. O que falta é a borda onde a interpolação do
        # levantamento esparso não alcança.
        self.assertGreater(valid, 0.8,
                           f"só {valid:.1%} das células com score; a "
                           f"interseção das duas fontes está quase vazia")
        with rasterio.open(ctx.emitted[0][1].path) as src:
            scores = src.read(1)
        finite = scores[np.isfinite(scores)]
        self.assertGreaterEqual(float(finite.min()), 0.0)
        self.assertLessEqual(float(finite.max()), 1.0)

    def test_the_region_is_not_one_of_the_two_already_here(self) -> None:
        """Um terceiro domínio: nem geotermia em Utah, nem deslizamento na
        Coreia. Se a extensão coincidisse com uma das outras, este diretório
        não acrescentaria domínio nenhum."""
        described = describe(self.GRAVITY)
        left, bottom, right, top = described.extent
        self.assertLess(left, 40.0)
        self.assertGreater(left, 0.0)
        self.assertLess(top, 0.0, "a África Austral está no hemisfério sul")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
