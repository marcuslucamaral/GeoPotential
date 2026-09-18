"""O caminho MCDA num domínio que não é o geotérmico. A lacuna de evidência.

`../data/conditioning_factors/` são 20 camadas de suscetibilidade a
deslizamento — MDE, declividade, TWI, curvatura, uso do solo, geologia, solo,
floresta — de uma bacia na Coreia, em `EPSG:5186`. **Nada de geofísica.**

A aplicação sempre foi agnóstica de domínio por desenho: importar, QA/QC,
harmonizar, pertinência, AHP, agregação e cenários recebem qualquer raster
como critério. Mas até esta suíte **isso nunca tinha sido provado**: todo gate
rodava sobre o dataset geotérmico de Utah, e a única menção a este arquivo em
toda a árvore era uma linha no relatório do M0 dizendo que nada o usava.

Rodar aqui achou dois defeitos que o dataset de Utah não podia achar, porque
ele não tem os tipos de dado que os expõem:

1. **`categorical` estava declarada e não ligada.** Pedi-la dava
   `membership 'categorical' is not known; use one of categorical, ...` — uma
   mensagem que se contradiz na própria frase. Utah não tem camada de classes;
   aqui geologia, uso do solo e os quatro de solo são todas classes.

2. **Direção não tinha pertinência.** `aspect` é azimute: 359° e 1° estão a
   dois graus um do outro, e toda função deste projeto os punha nas pontas
   opostas — medido, 0,9989 contra 0,0028. Utah não tem camada direcional.

As tolerâncias, fixadas antes de medir: as identidades de pertinência são
exatas a `1e-6` em float32; o resto é asserção de ordem ou de recusa.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

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


_DATA = _data_dir()
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.decision import membership as mf  # noqa: E402
from geopotential_worker.operators import registry  # noqa: E402
from geopotential_worker.operators.base import Context  # noqa: E402

DATA = _DATA / "conditioning_factors"
EXACT = 1e-6

#: As camadas por tipo. É a razão de este dataset ser o teste certo: ele tem
#: os três, e o de Utah tem só o primeiro.
CONTINUOUS = ("slope.tif", "twi.tif", "ls_factor.tif", "dem.tif")
CATEGORICAL = ("geology.tif", "landcover.tif", "soil_drainage.tif")
DIRECTIONAL = ("aspect.tif",)


def _available() -> bool:
    return DATA.is_dir() and (DATA / "slope.tif").is_file()


class _Ctx(Context):
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.emitted: list = []

    def progress(self, stage, fraction, message=""):  # noqa: ANN001
        pass

    def check_cancel(self):
        pass

    def emit(self, name, artifact):  # noqa: ANN001
        self.emitted.append((name, artifact))


@unittest.skipUnless(_available(), f"{DATA} não está no repositório")
class TheMcdaPathOnAnotherDomain(unittest.TestCase):
    """Importar, checar, normalizar e agregar dado que não é geofísico."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import rasterio  # noqa: F401
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest(f"rasterio não instalado: {exc}")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, operator: str, params: dict, inputs=()):
        op = registry.get(operator)
        ctx = _Ctx(self.out)
        return op.run(list(inputs), op.validate(params), ctx), ctx

    # ---- o que o dataset é ------------------------------------------------

    def test_every_layer_is_on_one_grid_and_one_metric_crs(self) -> None:
        """A premissa da agregação: pixels que não estão no mesmo lugar não
        são comparáveis. Verificado, não suposto."""
        grids = set()
        for name in CONTINUOUS + CATEGORICAL + DIRECTIONAL:
            manifest, _ = self._run("io.describe_dataset", {},
                                    [str(DATA / name)])
            described = manifest["description"]
            self.assertEqual(described["crs"], "EPSG:5186")
            self.assertFalse(described["geographic"])
            grids.add((described["width"], described["height"],
                       described["pixel_size_x"], described["pixel_size_y"]))
        self.assertEqual(len(grids), 1,
                         f"as camadas não estão numa grade só: {grids}")

    def test_the_sentinel_nodata_became_null(self) -> None:
        """`-9999` no arquivo, NaN em memória (P-30). Se não virasse, entraria
        na faixa da pertinência e puxaria toda a normalização."""
        manifest, _ = self._run("io.describe_dataset", {},
                                [str(DATA / "slope.tif")])
        described = manifest["description"]
        self.assertEqual(described["nodata"], -9999.0)
        self.assertGreater(described["statistics"]["min"], -1.0,
                           "o sentinela entrou nas estatísticas como valor")
        self.assertLess(described["statistics"]["valid_fraction"], 1.0)

    # ---- contínuo: o caminho que Utah já cobria ---------------------------

    def test_a_continuous_analysis_aggregates(self) -> None:
        criteria = [
            {"path": str(DATA / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
            {"path": str(DATA / "twi.tif"), "name": "TWI",
             "unit": "adimensional", "function": "linear_increasing"},
            {"path": str(DATA / "ls_factor.tif"), "name": "LS",
             "unit": "adimensional", "function": "linear_increasing"},
        ]
        manifest, ctx = self._run(
            "decision.aggregate",
            {"criteria": criteria, "method": "fuzzy_gamma", "gamma": 0.7,
             "result_name": "suscetibilidade"})
        result = manifest["result"]
        self.assertGreater(result["valid_fraction"], 0.99)
        self.assertGreaterEqual(result["min"], 0.0)
        self.assertLessEqual(result["max"], 1.0)
        self.assertEqual(len(ctx.emitted), 1)

    # ---- categórico: o primeiro defeito -----------------------------------

    def test_a_class_layer_can_be_a_criterion(self) -> None:
        """P-187. `categorical` estava no módulo e não estava ligada ao
        operador: a mensagem de erro listava `categorical` entre as opções
        válidas enquanto recusava `categorical`."""
        criteria = [
            {"path": str(DATA / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
            {"path": str(DATA / "geology.tif"), "name": "geologia",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 0.2, 2: 0.5, 3: 0.8, 4: 1.0}},
        ]
        manifest, _ = self._run(
            "decision.aggregate",
            {"criteria": criteria, "method": "fuzzy_gamma",
             "result_name": "com_geologia"})
        self.assertGreater(manifest["result"]["valid_fraction"], 0.99)
        # A tabela de classes entra na procedência: sem ela ninguém reproduz
        # a análise, porque a nota de cada classe é a decisão inteira.
        geology = [c for c in manifest["criteria"] if c["name"] == "geologia"][0]
        self.assertEqual(geology["anchors"]["mapping"],
                         {1.0: 0.2, 2.0: 0.5, 3.0: 0.8, 4.0: 1.0})

    def test_an_unmapped_class_is_refused_by_code(self) -> None:
        """P-12. Pontuar zero uma classe sem nota transforma uma lacuna de
        dado numa afirmação científica."""
        criteria = [
            {"path": str(DATA / "geology.tif"), "name": "geologia",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 0.2, 2: 0.5}},
            {"path": str(DATA / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
        ]
        with self.assertRaises(ValueError) as raised:
            self._run("decision.aggregate",
                      {"criteria": criteria, "method": "fuzzy_gamma",
                       "result_name": "faltando"})
        message = str(raised.exception)
        self.assertIn("not mapped", message)
        self.assertIn("3", message)
        self.assertIn("4", message)

    def test_categorical_without_a_mapping_is_refused(self) -> None:
        with self.assertRaises(ValueError) as raised:
            self._run("decision.aggregate",
                      {"criteria": [{"path": str(DATA / "geology.tif"),
                                     "name": "geologia", "unit": "classe",
                                     "function": "categorical"}],
                       "method": "fuzzy_product", "result_name": "sem_tabela"})
        self.assertIn("mapping", str(raised.exception))

    def test_every_class_layer_in_this_dataset_can_be_mapped(self) -> None:
        """As classes presentes são poucas e inteiras — o que torna a tabela
        escrevível à mão, que é o pressuposto de `categorical`."""
        import rasterio

        for name in CATEGORICAL:
            with self.subTest(layer=name):
                with rasterio.open(DATA / name) as src:
                    values = src.read(1)
                    present = np.unique(values[values != src.nodata])
                self.assertLess(len(present), 25,
                                f"{name} tem {len(present)} classes; isso não "
                                f"é uma camada categórica escrevível à mão")
                np.testing.assert_allclose(present, np.round(present),
                                           atol=EXACT)

    # ---- direcional: o segundo defeito ------------------------------------

    def test_a_linear_membership_breaks_on_a_direction(self) -> None:
        """O defeito, demonstrado em vez de descrito: 359° e 1° estão a dois
        graus um do outro, e a linear os separa por toda a faixa."""
        angles = np.array([[1.0, 359.0]])
        linear = mf.linear_increasing(angles, 0.0, 360.0)
        self.assertGreater(abs(float(linear[0, 1]) - float(linear[0, 0])), 0.9,
                           "se a linear não separasse os dois, este teste não "
                           "estaria testando nada")

    def test_the_circular_membership_treats_them_as_neighbours(self) -> None:
        """P-188."""
        angles = np.array([[1.0, 359.0]])
        got = mf.circular(angles, 0.0, 90.0)
        self.assertLess(abs(float(got[0, 1]) - float(got[0, 0])), 0.01)

    def test_the_circular_membership_is_one_at_the_preferred_azimuth(self) -> None:
        got = mf.circular(np.array([[0.0, 90.0, 180.0, 270.0]]), 0.0, 90.0)
        self.assertAlmostEqual(float(got[0, 0]), 1.0, delta=EXACT)
        self.assertAlmostEqual(float(got[0, 1]), 0.5, delta=EXACT)
        self.assertAlmostEqual(float(got[0, 2]), 0.0, delta=EXACT)
        self.assertAlmostEqual(float(got[0, 3]), 0.5, delta=EXACT)

    def test_it_is_symmetric_around_the_preferred_direction(self) -> None:
        """Os ângulos são embrulhados para [0, 360) pelo teste, porque a
        função **recusa** um azimute negativo em vez de adivinhar se ele é um
        ângulo do outro lado ou um sentinela."""
        for preferred in (0.0, 45.0, 200.0, 359.0):
            with self.subTest(preferred=preferred):
                before = (preferred - 30.0) % 360.0
                after = (preferred + 30.0) % 360.0
                got = mf.circular(np.array([[before, after]]), preferred, 90.0)
                self.assertAlmostEqual(float(got[0, 0]), float(got[0, 1]),
                                       delta=EXACT)

    def test_a_negative_angle_is_refused_and_not_wrapped(self) -> None:
        """Embrulhar em silêncio escolheria uma das duas leituras possíveis e
        estaria errado na outra."""
        with self.assertRaises(ValueError) as raised:
            mf.circular(np.array([[-30.0, 90.0]]), 0.0, 90.0)
        message = str(raised.exception)
        self.assertIn("[0, 360)", message)
        self.assertIn("flat cell", message)

    def test_a_flat_cell_is_refused_by_name(self) -> None:
        """`-1` não é um azimute perto de zero: é "esta pergunta não se aplica
        aqui". Deixá-lo passar daria quase pertinência cheia a uma célula que
        não tem direção nenhuma. Este dataset tem 6 053 delas."""
        import rasterio

        with rasterio.open(DATA / "aspect.tif") as src:
            values = src.read(1).astype(np.float64)
            values[values == src.nodata] = np.nan
        flat = int((values == -1.0).sum())
        self.assertGreater(flat, 0, "o fixture não tem célula plana")

        with self.assertRaises(ValueError) as raised:
            mf.circular(values, 0.0, 90.0)
        message = str(raised.exception)
        self.assertIn("flat cell", message)
        self.assertIn("nodata", message,
                      "a recusa tem de dizer o que fazer no lugar")
        self.assertIn("[0, 360)", message)

    def test_an_impossible_spread_is_refused(self) -> None:
        for spread in (0.0, -10.0, 200.0):
            with self.subTest(spread=spread):
                with self.assertRaises(ValueError):
                    mf.circular(np.array([[0.0]]), 0.0, spread)

    def test_aspect_reaches_an_analysis_once_the_flat_cells_are_null(self) -> None:
        """O caminho inteiro, com o dado direcional dentro — que é o que a
        recusa acima deixa a pessoa fazer."""
        import rasterio

        from geopotential_worker.io.writers import write_geotiff
        from geopotential_worker.domain.grid import TargetGrid
        from geopotential_worker.domain.crs import CrsInfo

        with rasterio.open(DATA / "aspect.tif") as src:
            values = src.read(1).astype(np.float32)
            values[values == src.nodata] = np.nan
            values[values == -1.0] = np.nan       # plano: sem direção
            grid = TargetGrid(
                transform=src.transform,
                crs=CrsInfo.from_user_input(str(src.crs), source="aspect"),
                width=src.width, height=src.height)
        cleaned = write_geotiff(values, grid, self.out / "aspect_sem_plano.tif",
                                tags={"GEOPOTENTIAL_UNIT": "grau"})

        manifest, _ = self._run(
            "decision.aggregate",
            {"criteria": [
                {"path": str(cleaned.path), "name": "orientação",
                 "unit": "grau", "function": "circular",
                 "preferred": 180.0, "spread": 90.0},
                {"path": str(DATA / "slope.tif"), "name": "declividade",
                 "unit": "grau", "function": "linear_increasing"},
            ], "method": "fuzzy_gamma", "result_name": "com_orientacao"})

        self.assertGreater(manifest["result"]["valid_fraction"], 0.98)
        aspect = [c for c in manifest["criteria"]
                  if c["name"] == "orientação"][0]
        self.assertEqual(aspect["anchors"]["preferred"], 180.0)

    # ---- os três tipos juntos ---------------------------------------------

    def test_one_analysis_mixes_continuous_categorical_and_directional(self) -> None:
        """O que o dataset de Utah não conseguia montar, e que é o caso comum
        fora da geofísica."""
        criteria = [
            {"path": str(DATA / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
            {"path": str(DATA / "twi.tif"), "name": "TWI",
             "unit": "adimensional", "function": "linear_increasing"},
            {"path": str(DATA / "geology.tif"), "name": "geologia",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 0.2, 2: 0.5, 3: 0.8, 4: 1.0}},
            {"path": str(DATA / "soil_drainage.tif"), "name": "drenagem",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2}},
        ]
        weights = [{"name": "declividade", "weight": 0.4},
                   {"name": "TWI", "weight": 0.25},
                   {"name": "geologia", "weight": 0.2},
                   {"name": "drenagem", "weight": 0.15}]
        manifest, _ = self._run(
            "decision.aggregate",
            {"criteria": criteria, "method": "weighted_linear_combination",
             "weights": weights, "result_name": "suscetibilidade_mista"})

        self.assertEqual(len(manifest["criterion_order"]), 4)
        self.assertGreater(manifest["result"]["valid_fraction"], 0.99)
        self.assertLessEqual(manifest["result"]["max"], 1.0)

    def test_sensitivity_runs_on_this_analysis_too(self) -> None:
        """M6 sobre um domínio que não é geofísico: se os cenários só
        funcionassem em Utah, eles seriam do dataset e não do produto."""
        criteria = [
            {"path": str(DATA / "slope.tif"), "name": "declividade",
             "unit": "grau", "function": "linear_increasing"},
            {"path": str(DATA / "twi.tif"), "name": "TWI",
             "unit": "adimensional", "function": "linear_increasing"},
            {"path": str(DATA / "geology.tif"), "name": "geologia",
             "unit": "classe", "function": "categorical",
             "mapping": {1: 0.2, 2: 0.5, 3: 0.8, 4: 1.0}},
        ]
        manifest, ctx = self._run(
            "scenarios.leave_one_out",
            {"criteria": criteria, "method": "fuzzy_gamma", "gamma": 0.7,
             "top_fraction": 0.1})
        rows = manifest["leave_one_out"]["criteria"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(ctx.emitted, [])
        for row in rows:
            self.assertGreater(row["cells_compared"], 100000)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
