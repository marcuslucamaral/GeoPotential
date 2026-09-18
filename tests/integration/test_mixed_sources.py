"""A corrente inteira do Utah FORGE: `.csv` e `.tif` na mesma análise.

Este é o caminho que o produto existe para percorrer, e **ele nunca tinha sido
testado de ponta a ponta**. As peças estavam: o M5.6/M5.7 gateia o gridding de
CSV, o M5 gateia a agregação de rasters, o M6 gateia os cenários. A corrente
que liga as três, não.

    dois .csv  --grid.tin_cubic-->  duas grades novas
    + um .tif que já existe
    --grid.harmonize-->  três camadas numa grade só
    --decision.aggregate-->  o mapa

O que só aparece na corrente:

1. **As três grades são diferentes** — cada CSV gera a sua a partir da própria
   extensão, e o raster tem a dele, de 10 m. Agregar sem harmonizar tem de ser
   recusado nomeando a camada, e é.
2. **A política de extensão decide o resultado inteiro.** `intersection` dá
   100 % de células com score; `union` dá 27,7 %, porque um score precisa de
   todos os critérios (ADR-004) e a união inclui onde só um deles mediu.
   Nenhuma das duas está errada — elas respondem a perguntas diferentes, e a
   escolha vai para o manifesto.
3. **A propriedade tem de ser declarada.** Um CSV traz várias colunas de valor;
   qual delas é o critério é uma decisão, e o operador recusa sem ela.

Tolerâncias, fixadas antes de medir: a fração válida do agregado tem de bater
com a interseção das máscaras a `0,005` — meio ponto percentual, que é folga
para arredondamento e nada mais.
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

from geopotential_worker.operators import registry  # noqa: E402
from geopotential_worker.operators.base import Context, ParameterError  # noqa: E402

DATA = _DATA / "utah_forge"
RASTER = DATA / "Distance_to_fault.tif"
DENSITY = DATA / "density_modified_500m.csv"
VP = DATA / "vp_500_m.csv"

MASK_AGREEMENT = 0.005
PIXEL = 40.0
CRS = "EPSG:26912"


def _available() -> bool:
    return RASTER.is_file() and DENSITY.is_file() and VP.is_file()


class _Ctx(Context):
    """Um diretório por operação, que é o que o Project Store faz.

    Reusar um diretório entre duas execuções foi o que fez a primeira versão
    deste teste medir a saída da segunda acreditando ser a da primeira — e foi
    o que expôs que `write_geotiff` sobrescrevia em silêncio.
    """

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


@unittest.skipUnless(_available(), f"os fixtures de {DATA} não estão aqui")
class CsvAndRasterInOneAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        for module in ("rasterio", "pandas", "scipy"):
            try:
                __import__(module)
            except Exception as exc:                   # pragma: no cover
                raise unittest.SkipTest(f"{module} não instalado: {exc}")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, operator: str, params: dict, inputs, folder: str):
        op = registry.get(operator)
        ctx = _Ctx(self.root / folder)
        return op.run(list(inputs), op.validate(params), ctx), ctx

    def _grid_a_csv(self, source: Path, column: str, unit: str, name: str,
                    folder: str | None = None):
        """`folder` distingue duas execuções da mesma grade no mesmo teste.

        Sem ele, chamar a corrente duas vezes escreve `densidade.tif` duas
        vezes no mesmo lugar — e desde que o escritor recusa sobrescrever
        (P-24), isso falha em vez de produzir silenciosamente a segunda. É o
        contrato pegando o próprio teste, que é o que ele deve fazer.
        """
        _, ctx = self._run("grid.tin_cubic", {
            "target_crs": CRS, "source_crs": CRS, "pixel_size": PIXEL,
            "x_field": "Easting[m]", "y_field": "Northing[m]",
            "value_field": column, "unit": unit, "result_name": name,
        }, [str(source)], folder or f"grid_{name}")
        return ctx.emitted[0][1].path

    # ---- a propriedade é declarada, nunca adivinhada ----------------------

    def test_a_csv_without_a_declared_value_column_is_refused(self) -> None:
        """Um CSV traz várias colunas de valor. Qual delas é o critério é uma
        decisão de quem opera, e a recusa lista as que existem."""
        with self.assertRaises(ParameterError) as raised:
            self._run("grid.tin_cubic", {
                "target_crs": CRS, "source_crs": CRS, "pixel_size": PIXEL,
                "x_field": "Easting[m]", "y_field": "Northing[m]",
                "unit": "km/s", "result_name": "sem_coluna",
            }, [str(VP)], "sem_coluna")
        message = str(raised.exception)
        self.assertIn("value_field", message)
        self.assertIn("Vp[km/s]", message,
                      "a recusa tem de listar as colunas que existem")

    def test_two_columns_of_one_csv_are_two_different_criteria(self) -> None:
        """`vp_500_m.csv` tem Vp e Vs. Escolher uma não é detalhe: é qual
        grandeza vira critério."""
        vp = self._grid_a_csv(VP, "Vp[km/s]", "km/s", "vp")
        vs = self._grid_a_csv(VP, "Vs[km/s]", "km/s", "vs")
        import rasterio

        with rasterio.open(vp) as a, rasterio.open(vs) as b:
            first, second = a.read(1), b.read(1)
        both = np.isfinite(first) & np.isfinite(second)
        self.assertTrue(both.any())
        self.assertFalse(np.allclose(first[both], second[both]),
                         "as duas colunas produziram o mesmo raster")

    # ---- as grades não coincidem, e isso é recusado -----------------------

    def test_the_three_sources_are_on_three_different_grids(self) -> None:
        import rasterio

        density = self._grid_a_csv(DENSITY, "Density[g/cm3]", "g/cm3", "densidade")
        vp = self._grid_a_csv(VP, "Vp[km/s]", "km/s", "vp")
        shapes = set()
        for path in (density, vp, RASTER):
            with rasterio.open(path) as src:
                shapes.add((src.shape, src.res,
                            tuple(round(v) for v in src.bounds)))
        self.assertEqual(len(shapes), 3,
                         "as três fontes já vieram numa grade só; então este "
                         "teste não está testando a harmonização")

    def test_aggregating_before_harmonising_is_refused_by_name(self) -> None:
        density = self._grid_a_csv(DENSITY, "Density[g/cm3]", "g/cm3", "densidade")
        with self.assertRaises(ValueError) as raised:
            self._run("decision.aggregate", {
                "criteria": [
                    {"path": str(density), "name": "densidade",
                     "unit": "g/cm3", "function": "linear_increasing"},
                    {"path": str(RASTER), "name": "distancia",
                     "unit": "m", "function": "linear_decreasing"},
                ], "method": "fuzzy_gamma", "result_name": "cedo_demais",
            }, [], "cedo_demais")
        message = str(raised.exception)
        self.assertIn("different grid", message)
        self.assertIn("distancia", message)
        self.assertIn("Harmonize", message)

    # ---- a corrente inteira, nas duas políticas ---------------------------

    def _chain(self, policy: str):
        density = self._grid_a_csv(DENSITY, "Density[g/cm3]", "g/cm3",
                                   "densidade", f"grid_densidade_{policy}")
        vp = self._grid_a_csv(VP, "Vp[km/s]", "km/s", "vp", f"grid_vp_{policy}")
        manifest, ctx = self._run("grid.harmonize", {
            "target_crs": CRS, "pixel_size": PIXEL, "extent_policy": policy,
            "layers": [
                {"path": str(density), "name": "densidade", "unit": "g/cm3"},
                {"path": str(vp), "name": "vp", "unit": "km/s"},
                {"path": str(RASTER), "name": "distancia", "unit": "m"},
            ],
        }, [], f"harm_{policy}")
        paths = {name: artifact.path for name, artifact in ctx.emitted}

        aggregated, _ = self._run("decision.aggregate", {
            "criteria": [
                {"path": str(paths["densidade_harmonized"]), "name": "densidade",
                 "unit": "g/cm3", "function": "linear_increasing"},
                {"path": str(paths["vp_harmonized"]), "name": "vp",
                 "unit": "km/s", "function": "linear_decreasing"},
                {"path": str(paths["distancia_harmonized"]), "name": "distancia",
                 "unit": "m", "function": "linear_decreasing"},
            ], "method": "fuzzy_gamma", "gamma": 0.7,
            "result_name": "prospectividade",
        }, [], f"agg_{policy}")
        return manifest, paths, aggregated

    def _masks(self, paths: dict):
        import rasterio

        masks = {}
        for name, path in paths.items():
            with rasterio.open(path) as src:
                masks[name] = np.isfinite(src.read(1))
        return masks

    def test_the_intersection_policy_scores_every_cell(self) -> None:
        """Onde as três mediram, as três respondem."""
        _, paths, aggregated = self._chain("intersection")
        masks = self._masks(paths)
        for name, mask in masks.items():
            self.assertGreater(mask.mean(), 0.99, f"{name} veio com buracos")
        self.assertGreater(aggregated["result"]["valid_fraction"], 0.99)

    def test_the_union_policy_scores_only_the_overlap(self) -> None:
        """A união inclui onde só um mediu, e ali não há score: um score
        precisa de todos os critérios (ADR-004). Não é erro — é a pergunta
        que a política faz."""
        _, paths, aggregated = self._chain("union")
        masks = self._masks(paths)
        overlap = np.logical_and.reduce(list(masks.values()))
        self.assertLess(overlap.mean(), 0.9,
                        "a união não incluiu área fora de alguma camada; "
                        "então ela não está diferindo da interseção")
        self.assertGreater(aggregated["result"]["valid_fraction"], 0.05)

    def test_the_score_is_null_exactly_where_a_criterion_is(self) -> None:
        """A propriedade que liga as duas políticas: a fração válida do
        agregado **é** a interseção das máscaras. Se elas divergissem, algum
        operador estaria inventando ou perdendo célula."""
        for policy in ("intersection", "union"):
            with self.subTest(policy=policy):
                _, paths, aggregated = self._chain(policy)
                overlap = np.logical_and.reduce(
                    list(self._masks(paths).values()))
                self.assertAlmostEqual(
                    aggregated["result"]["valid_fraction"],
                    float(overlap.mean()), delta=MASK_AGREEMENT)

    def test_the_extent_policy_is_recorded(self) -> None:
        """Ela decide o resultado inteiro — 100 % contra 28 % de células com
        score — então tem de estar no manifesto."""
        for policy in ("intersection", "union"):
            with self.subTest(policy=policy):
                manifest, _, _ = self._chain(policy)
                self.assertEqual(manifest["params"]["extent_policy"], policy)

    def test_the_two_policies_give_different_grids(self) -> None:
        narrow, _, _ = self._chain("intersection")
        wide, _, _ = self._chain("union")
        self.assertLess(narrow["grid"]["width"], wide["grid"]["width"])
        self.assertLess(narrow["grid"]["height"], wide["grid"]["height"])

    def test_the_manifest_carries_every_source_back_to_its_file(self) -> None:
        """Dois CSV e um raster entraram; a linhagem tem de dizer isso."""
        _, _, aggregated = self._chain("intersection")
        names = {c["name"] for c in aggregated["criteria"]}
        self.assertEqual(names, {"densidade", "vp", "distancia"})
        for criterion in aggregated["criteria"]:
            self.assertTrue(criterion["source_hash"])
            self.assertTrue(Path(criterion["source_path"]).is_file())


@unittest.skipUnless(_available(), f"os fixtures de {DATA} não estão aqui")
class AnOutputIsNeverSilentlyOverwritten(unittest.TestCase):
    """P-24, na camada onde os bytes chegam ao disco.

    A regra era imposta só no Project Store, pelo UNIQUE de `artifact.path`, e
    `write_geotiff` substituía o que estivesse lá. Na aplicação os dois nunca
    se encontravam, porque cada run escreve no seu diretório — o buraco só
    apareceu quando um harness rodou duas operações no mesmo diretório e
    mediu a saída da segunda acreditando ser a da primeira.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _grid(self):
        from affine import Affine

        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.domain.grid import TargetGrid

        return TargetGrid(
            transform=Affine(10.0, 0.0, 0.0, 0.0, -10.0, 100.0),
            crs=CrsInfo.from_user_input(CRS, source="test"),
            width=10, height=10)

    def test_writing_over_an_existing_artefact_is_refused(self) -> None:
        from geopotential_worker.io.writers import write_geotiff

        grid = self._grid()
        path = self.out / "x.tif"
        write_geotiff(np.ones((10, 10), np.float32), grid, path)
        with self.assertRaises(FileExistsError) as raised:
            write_geotiff(np.zeros((10, 10), np.float32), grid, path)
        self.assertIn("P-24", str(raised.exception))

    def test_the_first_file_survives_the_refusal(self) -> None:
        import rasterio

        from geopotential_worker.io.writers import write_geotiff

        grid = self._grid()
        path = self.out / "x.tif"
        write_geotiff(np.ones((10, 10), np.float32), grid, path)
        with self.assertRaises(FileExistsError):
            write_geotiff(np.zeros((10, 10), np.float32), grid, path)
        with rasterio.open(path) as src:
            self.assertTrue(np.allclose(src.read(1), 1.0),
                            "a recusa destruiu o arquivo que ela protegia")

    def test_no_temporary_file_survives_the_refusal(self) -> None:
        """P-29: uma escrita falha não deixa `.tmp` para trás."""
        from geopotential_worker.io.writers import write_geotiff

        grid = self._grid()
        path = self.out / "x.tif"
        write_geotiff(np.ones((10, 10), np.float32), grid, path)
        with self.assertRaises(FileExistsError):
            write_geotiff(np.zeros((10, 10), np.float32), grid, path)
        self.assertEqual(list(self.out.glob("*.tmp")), [])

    def test_a_caller_that_means_it_can_say_so(self) -> None:
        import rasterio

        from geopotential_worker.io.writers import write_geotiff

        grid = self._grid()
        path = self.out / "x.tif"
        write_geotiff(np.ones((10, 10), np.float32), grid, path)
        write_geotiff(np.zeros((10, 10), np.float32), grid, path, overwrite=True)
        with rasterio.open(path) as src:
            self.assertTrue(np.allclose(src.read(1), 0.0))


@unittest.skipUnless(_available(), f"os fixtures de {DATA} não estão aqui")
class BothPoliciesBeforeChoosing(unittest.TestCase):
    """A escolha da extensão decide o resultado inteiro, e era feita às cegas.

    A tela de harmonização pedia interseção ou união antes de qualquer número
    existir. Os dois números estavam neste relatório desde o `0.8.01` — 100 %
    contra 27,7 % de células com score — mas quem operava só os via depois de
    rodar, uma vez cada, e comparando de cabeça.

    `grid.compare_policies` mede as duas antes. É read-only, e a estimativa é
    produzida chamando `harmonize` numa grade decimada, de forma que não pode
    divergir do operador cujo resultado ela prevê.
    """

    @classmethod
    def setUpClass(cls) -> None:
        for module in ("rasterio", "pandas", "scipy"):
            try:
                __import__(module)
            except Exception as exc:                   # pragma: no cover
                raise unittest.SkipTest(f"{module} não instalado: {exc}")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, operator: str, params: dict, inputs, folder: str):
        op = registry.get(operator)
        ctx = _Ctx(self.root / folder)
        return op.run(list(inputs), op.validate(params), ctx), ctx

    def _grid_a_csv(self, source: Path, column: str, unit: str, name: str,
                    run: str):
        """`run` distingue duas execuções da mesma grade no mesmo teste.

        Sem ele, comparar duas vezes num teste só escreve `vp.tif` duas vezes
        no mesmo lugar, e o `P-24` recusa. O contrato pegou este teste ao ser
        escrito, que é o que ele deve fazer.
        """
        _, ctx = self._run("grid.tin_cubic", {
            "target_crs": CRS, "source_crs": CRS, "pixel_size": PIXEL,
            "x_field": "Easting[m]", "y_field": "Northing[m]",
            "value_field": column, "unit": unit, "result_name": name,
        }, [str(source)], f"{run}_grid_{name}")
        return ctx.emitted[0][1].path

    def _compare(self, run: str = "a", **overrides):
        vp = self._grid_a_csv(VP, "Vp[km/s]", "km/s", "vp", run)
        density = self._grid_a_csv(DENSITY, "Density[g/cm3]", "g/cm3",
                                   "densidade", run)
        params = {
            "target_crs": CRS, "pixel_size": PIXEL,
            "layers": [
                {"path": str(RASTER), "name": "falha", "unit": "m"},
                {"path": str(vp), "name": "Vp", "unit": "km/s"},
                {"path": str(density), "name": "densidade", "unit": "g/cm3"},
            ],
        }
        params.update(overrides)
        manifest, ctx = self._run("grid.compare_policies", params, [],
                                  f"{run}_cmp")
        return manifest, ctx

    def _policy(self, manifest, name):
        found = [p for p in manifest["policies"] if p["policy"] == name]
        self.assertEqual(len(found), 1, f"política {name} ausente do relatório")
        return found[0]

    def test_it_reports_the_two_numbers_the_choice_turns_on(self) -> None:
        """Os mesmos 100 % e 27,7 % que este relatório já media — agora antes
        de escolher, e sem rodar a harmonização."""
        manifest, _ = self._compare()
        intersection = self._policy(manifest, "intersection")
        union = self._policy(manifest, "union")

        self.assertAlmostEqual(intersection["scored_fraction"], 1.0, places=3)
        self.assertAlmostEqual(union["scored_fraction"], 0.277, places=2)
        self.assertGreater(union["cells"], intersection["cells"],
                           "a união tem de dar uma grade maior")

    def test_the_union_adds_no_scored_cell(self) -> None:
        """A leitura que os dois números sozinhos não davam: a área **com
        score** é idêntica. Um score precisa de todos os critérios, então a
        união só acrescenta área vazia — 13 875 células nas duas, contra
        50 020 no total da união."""
        manifest, _ = self._compare()
        intersection = self._policy(manifest, "intersection")
        union = self._policy(manifest, "union")
        self.assertEqual(intersection["scored_cells"], union["scored_cells"])
        self.assertEqual(intersection["cells"], intersection["scored_cells"])
        self.assertGreater(union["cells"], union["scored_cells"])

    def test_the_estimate_says_which_grid_it_was_estimated_on(self) -> None:
        """Uma fração sem a grade em que foi medida é lida como exata."""
        manifest, _ = self._compare(estimate_cells=4096)
        for name in ("intersection", "union"):
            with self.subTest(policy=name):
                facts = self._policy(manifest, name)
                self.assertTrue(facts["estimated"])
                self.assertGreater(facts["decimation"], 1)
                self.assertLessEqual(
                    facts["estimate_width"] * facts["estimate_height"], 4096,
                    "a prévia estourou o orçamento que lhe foi dado")

    def test_a_decimated_estimate_still_finds_the_same_answer(self) -> None:
        """Se a decimação mudasse a resposta, a prévia não serviria para
        decidir. Medida cheia contra 1 célula em cada 64."""
        full, _ = self._compare("cheia", estimate_cells=10_000_000)
        coarse, _ = self._compare("grossa", estimate_cells=1024)
        self.assertEqual(self._policy(full, "intersection")["decimation"], 1)
        for name in ("intersection", "union"):
            with self.subTest(policy=name):
                self.assertAlmostEqual(
                    self._policy(full, name)["scored_fraction"],
                    self._policy(coarse, name)["scored_fraction"],
                    delta=0.02)

    def test_it_registers_nothing(self) -> None:
        """P-53: uma sonda não entra na linhagem do projeto."""
        op = registry.get("grid.compare_policies")
        self.assertTrue(op.read_only)
        _, ctx = self._compare()
        self.assertEqual(ctx.emitted, [],
                         "a comparação emitiu artefato; ela não computa "
                         "resultado nenhum, só mede o que dois resultados "
                         "teriam")

    def test_each_layer_reports_its_own_share(self) -> None:
        """Qual camada encolhe a interseção é o que diz onde agir. Sob união,
        as três cobrem frações diferentes da mesma grade."""
        manifest, _ = self._compare()
        union = self._policy(manifest, "union")
        shares = {row["name"]: row["fraction"]
                  for row in union["per_layer_fraction"]}
        self.assertEqual(set(shares), {"falha", "Vp", "densidade"})
        for name, fraction in shares.items():
            with self.subTest(layer=name):
                self.assertLess(fraction, 1.0)
                self.assertGreater(fraction, 0.0)
        # A menor delas limita a interseção, e nenhuma soma pode superá-la.
        self.assertLessEqual(union["scored_fraction"], min(shares.values()))

    def test_an_empty_intersection_is_an_answer_and_not_a_failure(self) -> None:
        """Camadas que não se sobrepõem é precisamente o que se precisa saber
        antes de escolher a interseção — e faria a harmonização falhar."""
        import numpy as np
        import rasterio

        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.domain.grid import TargetGrid
        from geopotential_worker.io.writers import write_geotiff
        from affine import Affine

        crs = CrsInfo.from_user_input(CRS, source="teste")
        far = []
        for index, origin in enumerate(((0.0, 1000.0), (100_000.0, 1_100_000.0))):
            grid = TargetGrid(
                transform=Affine(10.0, 0.0, origin[0], 0.0, -10.0, origin[1]),
                crs=crs, width=20, height=20)
            path = self.root / f"longe_{index}.tif"
            write_geotiff(np.ones((20, 20), np.float32), grid, path)
            far.append(path)

        manifest, _ = self._run("grid.compare_policies", {
            "target_crs": CRS, "pixel_size": 10.0,
            "layers": [{"path": str(p), "name": f"l{i}", "unit": "m"}
                       for i, p in enumerate(far)],
        }, [], "longe")

        intersection = self._policy(manifest, "intersection")
        self.assertFalse(intersection["available"])
        self.assertIn("overlap", intersection["reason"])
        # E a união continua respondendo: a sonda não desiste por causa da
        # outra política.
        self.assertTrue(self._policy(manifest, "union")["available"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
