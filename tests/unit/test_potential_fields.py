"""M7 E1 — campos potenciais, contra o caso conhecido. §23, gates FIS-01..08.

O M7 manda implementar a suíte sintética **primeiro**, e a razão está no
FIS-04: um filtro espectral comparado apenas consigo mesmo passa em qualquer
convenção de sinal. Aqui a resposta certa é conhecida analiticamente em cada
célula, e cada operador é medido contra ela.

## As tolerâncias, fixadas antes de qualquer execução (FIS-05)

Uma derivada por FFT de um campo suave numa grade finita não é exata: ela erra
por truncamento do espectro e pela borda. Os números abaixo foram escolhidos
pelo que a teoria permite, não pelo que o teste precisava para passar, e são
**relativos ao pico da resposta analítica** — um erro absoluto num campo cuja
amplitude é um parâmetro não quer dizer nada.

    DERIVATIVE_REL   0.02    2 % do pico, na região interior
    CONTINUATION_REL 0.01    1 % do pico; a continuação suaviza e erra menos
    TILT_REL         0.10    10 % de π/2. O tilt é o ângulo de uma razão, e
                             onde o denominador tende a zero — sobre a fonte e
                             longe dela — um erro pequeno nas derivadas vira um
                             erro grande no ângulo. A razão é do método, não do
                             código, e por isso a tolerância é separada em vez
                             de a das derivadas ser afrouxada.
    EXACT_REL        1.2e-7  identidades algébricas **num pipeline float32**.
                             `regional + residual == campo` é exato em ℝ; os
                             arrays são float32 por contrato, e o épsilon do
                             float32 é 1,19e-7. Uma tolerância de 1e-10 aqui
                             não estaria medindo a identidade, estaria medindo
                             a largura do tipo.

**A região interior** é o quarto central da grade. As bordas de uma FFT são
onde o padding age, e o FIS-03 trata delas separadamente — misturar as duas
coisas numa tolerância só é como se esconde um erro de borda dentro de uma
média.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from geopotential_worker.potential_fields import filters  # noqa: E402
from geopotential_worker.potential_fields import spectral  # noqa: E402
from geopotential_worker.potential_fields import synthetic  # noqa: E402

DERIVATIVE_REL = 0.02
CONTINUATION_REL = 0.01
TILT_REL = 0.10
EXACT_REL = float(np.finfo(np.float32).eps)

#: A anomalia de referência: uma esfera a 2 km, numa grade de 200 m sobre
#: 40 km. Documentada aqui, e é a mesma em toda a suíte (FIS-01).
DEPTH = 2000.0
SPACING = 200.0
HALF_WIDTH = 20000.0
AMPLITUDE = 1.0e9          # leva o pico a ~250 mGal, uma anomalia realista


def _field():
    x, y = synthetic.observation_grid(HALF_WIDTH, SPACING)
    values = synthetic.sphere(x, y, depth=DEPTH, amplitude=AMPLITUDE)
    return x, y, values


def _interior(array: np.ndarray) -> np.ndarray:
    """O quarto central: onde a borda não alcança."""
    h, w = array.shape
    return array[h // 4: 3 * h // 4, w // 4: 3 * w // 4]


def _relative_error(got: np.ndarray, want: np.ndarray) -> float:
    """Erro máximo no interior, relativo ao pico da resposta analítica."""
    g, w = _interior(np.asarray(got, float)), _interior(np.asarray(want, float))
    peak = float(np.abs(w).max())
    if peak == 0:
        raise AssertionError("a resposta analítica é identicamente zero")
    return float(np.abs(g - w).max() / peak)


class FIS01TheKnownCase(unittest.TestCase):
    """FIS-01 — a esfera enterrada, com geometria e resultado documentados."""

    def test_the_peak_is_over_the_source(self) -> None:
        x, y, values = _field()
        row, column = np.unravel_index(np.argmax(values), values.shape)
        self.assertAlmostEqual(float(x[row, column]), 0.0, delta=SPACING)
        self.assertAlmostEqual(float(y[row, column]), 0.0, delta=SPACING)

    def test_the_peak_matches_the_closed_form(self) -> None:
        """Sobre a fonte, gz = A/d². Conferível de cabeça."""
        _, _, values = _field()
        self.assertAlmostEqual(float(values.max()), AMPLITUDE / DEPTH ** 2,
                               delta=AMPLITUDE / DEPTH ** 2 * 1e-3)

    def test_a_source_above_the_plane_is_refused(self) -> None:
        x, y = synthetic.observation_grid(1000.0, 100.0)
        with self.assertRaises(ValueError) as raised:
            synthetic.sphere(x, y, depth=0.0)
        self.assertIn("abaixo do plano", str(raised.exception))

    def test_the_analytic_vertical_derivative_is_positive_over_the_source(self) -> None:
        """A convenção inteira num sinal: z para baixo, aproximar-se aumenta.

        Sobre a fonte o fechado colapsa para 2A/d³, que é positivo.
        """
        x, y, _ = _field()
        dz = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                          amplitude=AMPLITUDE)["dz"]
        centre = dz[dz.shape[0] // 2, dz.shape[1] // 2]
        self.assertGreater(float(centre), 0.0)
        self.assertAlmostEqual(float(centre), 2.0 * AMPLITUDE / DEPTH ** 3,
                               delta=abs(2.0 * AMPLITUDE / DEPTH ** 3) * 1e-6)


class FIS02TheConvention(unittest.TestCase):
    """FIS-02 — sinal, unidade, eixo, altitude e orientação, declarados."""

    def test_every_convention_is_stated(self) -> None:
        stated = synthetic.conventions()
        for key in ("sign", "height", "axis", "unit", "orientation",
                    "reference"):
            self.assertTrue(stated.get(key), f"{key} não foi declarado")

    def test_the_spectral_vertical_derivative_has_the_declared_sign(self) -> None:
        """O gate que decide a convenção: contra o fechado, não contra outro
        filtro. Um `-|k|` no lugar de `+|k|` reprova aqui e em nenhum outro
        lugar."""
        x, y, values = _field()
        want = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                            amplitude=AMPLITUDE)["dz"]
        got, _ = filters.derivative(values, (SPACING, SPACING), axis="z")
        self.assertLess(_relative_error(got, want), DERIVATIVE_REL)

    def test_the_horizontal_derivatives_match_the_closed_form(self) -> None:
        x, y, values = _field()
        want = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                            amplitude=AMPLITUDE)
        for axis in ("x", "y"):
            with self.subTest(axis=axis):
                got, _ = filters.derivative(values, (SPACING, SPACING),
                                            axis=axis)
                self.assertLess(_relative_error(got, want[f"d{axis}"]),
                                DERIVATIVE_REL)

    def test_an_unknown_axis_or_order_is_refused_by_name(self) -> None:
        _, _, values = _field()
        with self.assertRaises(ValueError):
            filters.derivative(values, (SPACING, SPACING), axis="w")
        with self.assertRaises(ValueError) as raised:
            filters.derivative(values, (SPACING, SPACING), axis="z", order=3)
        self.assertIn("ruído", str(raised.exception))

    def test_an_anisotropic_pixel_is_carried_through_both_axes(self) -> None:
        """`0.5*(px+py)` está errado em toda grade que não é quadrada."""
        kx, ky, _ = spectral.wavenumbers((16, 32), (10.0, 40.0))
        self.assertNotAlmostEqual(float(np.abs(kx).max()),
                                  float(np.abs(ky).max()))


class TheNyquistCoefficient(unittest.TestCase):
    """O defeito que só aparece em grade de lado **par**.

    `fftfreq` põe a frequência de Nyquist numa única posição, negativa, sem a
    positiva correspondente. Um multiplicador ímpar em k — toda derivada
    horizontal de ordem ímpar — deixa de ser hermitiano exatamente ali, e a
    inversa sai com parte imaginária.

    A suíte sintética roda numa grade 201 x 201, **ímpar**, e passava. Foi o
    campo real 4096 x 4096 que acendeu a checagem de hermitianidade em
    `spectral.apply_filter`. Este teste é a grade par que faltava.
    """

    def _even_field(self, height: int = 64, width: int = 64):
        x, y = np.meshgrid(np.arange(width) * SPACING - width * SPACING / 2,
                           np.arange(height) * SPACING - height * SPACING / 2)
        return synthetic.sphere(x, y, depth=DEPTH, amplitude=AMPLITUDE)

    def test_an_odd_derivative_on_an_even_grid_stays_real(self) -> None:
        values = self._even_field()
        self.assertEqual(values.shape, (64, 64))
        for axis in ("x", "y"):
            with self.subTest(axis=axis):
                got, _ = filters.derivative(values, (SPACING, SPACING),
                                            axis=axis)
                self.assertTrue(np.all(np.isfinite(got)))

    def test_it_stays_real_on_a_grid_even_in_one_axis_only(self) -> None:
        values = self._even_field(height=64, width=65)
        for axis in ("x", "y"):
            with self.subTest(axis=axis):
                got, _ = filters.derivative(values, (SPACING, SPACING),
                                            axis=axis)
                self.assertTrue(np.all(np.isfinite(got)))

    def test_the_composites_survive_an_even_grid(self) -> None:
        """O que quebrou de verdade foi o tilt, que passa por dx e dy."""
        values = self._even_field()
        for name in ("total_horizontal_gradient", "analytic_signal", "tilt"):
            with self.subTest(transform=name):
                got, _ = getattr(filters, name)(values, (SPACING, SPACING))
                self.assertTrue(np.all(np.isfinite(got)))

    def test_the_even_grid_derivative_still_matches_the_closed_form(self) -> None:
        """Zerar o Nyquist descarta o menor comprimento de onda da grade. Isso
        não pode custar a exatidão onde a resposta é conhecida."""
        height = width = 128
        x, y = np.meshgrid(np.arange(width) * SPACING - width * SPACING / 2,
                           np.arange(height) * SPACING - height * SPACING / 2)
        values = synthetic.sphere(x, y, depth=DEPTH, amplitude=AMPLITUDE)
        want = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                            amplitude=AMPLITUDE)["dx"]
        got, _ = filters.derivative(values, (SPACING, SPACING), axis="x")
        self.assertLess(_relative_error(got, want), DERIVATIVE_REL)


class FIS03TheBorder(unittest.TestCase):
    """FIS-03 — padding, taper, extensão e recorte, registrados."""

    def test_the_border_is_recorded_on_every_run(self) -> None:
        _, _, values = _field()
        _, provenance = filters.derivative(values, (SPACING, SPACING), axis="z")
        border = provenance["border"]
        for key in ("mode", "pad_fraction", "pad_cells", "taper",
                    "original_shape", "extended_shape"):
            self.assertIn(key, border, f"{key} não foi registrado")

    def test_the_result_comes_back_the_original_size(self) -> None:
        _, _, values = _field()
        got, _ = filters.derivative(values, (SPACING, SPACING), axis="z")
        self.assertEqual(got.shape, values.shape)

    def test_padding_reduces_the_error_at_the_edge(self) -> None:
        """A razão de o padding existir, medida em vez de afirmada."""
        x, y, values = _field()
        want = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                            amplitude=AMPLITUDE)["dz"]
        without, _ = filters.derivative(values, (SPACING, SPACING), axis="z",
                                        fraction=0.0, taper=0.0)
        with_pad, _ = filters.derivative(values, (SPACING, SPACING), axis="z")

        def edge_error(got):
            band = np.abs(np.asarray(got, float) - want)[:4, :]
            return float(band.max())

        self.assertLess(edge_error(with_pad), edge_error(without),
                        "o padding não melhorou a borda; ou ele não está "
                        "sendo aplicado, ou não serve para o que diz servir")

    def test_the_taper_decays_to_the_border_and_not_to_the_mean(self) -> None:
        """O defeito que esta suíte pegou.

        A anomalia é toda positiva e concentrada: vale ~0,17 na borda e ~3,5
        de média. Um taper que leva a região refletida à média constrói um
        degrau logo fora do dado, e o erro na borda **piora**. Contra a borda,
        melhora.
        """
        x, y, values = _field()
        want = synthetic.sphere_derivatives(x, y, depth=DEPTH,
                                            amplitude=AMPLITUDE)["dz"]

        def edge_error(got):
            return float(np.abs(np.asarray(got, float) - want)[:4, :].max())

        no_taper, _ = filters.derivative(values, (SPACING, SPACING), axis="z",
                                         taper=0.0)
        with_taper, _ = filters.derivative(values, (SPACING, SPACING), axis="z")
        self.assertLess(edge_error(with_taper), edge_error(no_taper),
                        "o taper piorou a borda: ele está decaindo para o "
                        "nível errado")

    def test_a_null_stays_null(self) -> None:
        """A FFT preencheu a lacuna para poder rodar. O resultado ali é
        interpolação da própria média, não medida."""
        _, _, values = _field()
        holed = values.copy()
        holed[50:55, 60:65] = np.nan
        got, provenance = filters.derivative(holed, (SPACING, SPACING), axis="z")
        self.assertTrue(np.all(np.isnan(got[50:55, 60:65])))
        self.assertEqual(provenance["border"]["nulls_filled_with_mean"], 25)

    def test_an_all_null_grid_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            spectral.pad(np.full((10, 10), np.nan))

    def test_an_absurd_padding_is_refused(self) -> None:
        _, _, values = _field()
        with self.assertRaises(ValueError):
            spectral.pad(values, fraction=5.0)


class FIS04Independence(unittest.TestCase):
    """FIS-04 — comparado com um cálculo independente, não com outra FFT."""

    def test_upward_continuation_matches_the_deeper_sphere(self) -> None:
        """O caso conhecido exato: para uma fonte pontual, subir o observador
        é a mesma fórmula com a fonte mais funda. Nenhuma FFT do lado direito
        da igualdade."""
        x, y, values = _field()
        height = 1000.0
        want = synthetic.sphere_continued(x, y, depth=DEPTH, height=height,
                                          amplitude=AMPLITUDE)
        got, _ = filters.upward_continuation(values, (SPACING, SPACING),
                                             height=height)
        self.assertLess(_relative_error(got, want), CONTINUATION_REL)

    def test_the_total_horizontal_gradient_matches_the_closed_form(self) -> None:
        x, y, values = _field()
        d = synthetic.sphere_derivatives(x, y, depth=DEPTH, amplitude=AMPLITUDE)
        want = np.sqrt(d["dx"] ** 2 + d["dy"] ** 2)
        got, _ = filters.total_horizontal_gradient(values, (SPACING, SPACING))
        self.assertLess(_relative_error(got, want), DERIVATIVE_REL)

    def test_the_analytic_signal_matches_the_closed_form(self) -> None:
        x, y, values = _field()
        d = synthetic.sphere_derivatives(x, y, depth=DEPTH, amplitude=AMPLITUDE)
        want = np.sqrt(d["dx"] ** 2 + d["dy"] ** 2 + d["dz"] ** 2)
        got, _ = filters.analytic_signal(values, (SPACING, SPACING))
        self.assertLess(_relative_error(got, want), DERIVATIVE_REL)

    def test_the_tilt_matches_the_closed_form(self) -> None:
        x, y, values = _field()
        d = synthetic.sphere_derivatives(x, y, depth=DEPTH, amplitude=AMPLITUDE)
        want = np.arctan2(d["dz"], np.sqrt(d["dx"] ** 2 + d["dy"] ** 2))
        got, _ = filters.tilt(values, (SPACING, SPACING))
        # O tilt é um ângulo: o erro é relativo a π/2, o seu alcance. E é o
        # ângulo de uma razão, mal condicionado onde o denominador some.
        error = float(np.abs(_interior(np.asarray(got, float))
                             - _interior(want)).max())
        self.assertLess(error / (np.pi / 2), TILT_REL)

    def test_the_tilt_stays_inside_its_declared_range(self) -> None:
        """[-π/2, π/2] não é uma observação sobre este dado: é o alcance de
        atan2 com denominador não negativo, e um valor fora dele seria um THG
        negativo, que não existe."""
        _, _, values = _field()
        got, provenance = filters.tilt(values, (SPACING, SPACING))
        finite = np.asarray(got, float)[np.isfinite(got)]
        self.assertGreaterEqual(float(finite.min()), -np.pi / 2 - 1e-6)
        self.assertLessEqual(float(finite.max()), np.pi / 2 + 1e-6)
        self.assertEqual(provenance["range_rad"], [-np.pi / 2, np.pi / 2])


class FIS05Tolerance(unittest.TestCase):
    """FIS-05 — as tolerâncias existem, e valem para todos os operadores."""

    def test_the_tolerances_are_module_constants(self) -> None:
        """Fixadas num lugar, antes das medições, e não por caso de teste.
        Uma tolerância por teste é uma tolerância ajustada depois."""
        for value in (DERIVATIVE_REL, CONTINUATION_REL, TILT_REL, EXACT_REL):
            self.assertGreater(value, 0.0)
        self.assertLess(CONTINUATION_REL, DERIVATIVE_REL,
                        "a continuação suaviza; ela tem de errar menos que "
                        "uma derivada, e a ordem das tolerâncias diz isso")
        self.assertGreater(TILT_REL, DERIVATIVE_REL,
                           "o tilt é o ângulo de uma razão e é mal "
                           "condicionado onde o denominador some; a ordem "
                           "das tolerâncias tem de dizer isso")


class FIS06Regression(unittest.TestCase):
    """FIS-06 — o resultado é reprodutível, e a procedência viaja com ele."""

    def test_the_same_input_gives_the_same_output(self) -> None:
        _, _, values = _field()
        first, _ = filters.tilt(values, (SPACING, SPACING))
        second, _ = filters.tilt(values, (SPACING, SPACING))
        np.testing.assert_array_equal(first, second)

    def test_the_border_choice_changes_the_result(self) -> None:
        """Se mudar o padding não mudasse nada, registrá-lo seria decoração."""
        _, _, values = _field()
        a, _ = filters.upward_continuation(values, (SPACING, SPACING),
                                           height=2000.0, fraction=0.1)
        b, _ = filters.upward_continuation(values, (SPACING, SPACING),
                                           height=2000.0, fraction=0.5)
        self.assertFalse(np.allclose(a, b))

    def test_every_transformation_declares_its_unit(self) -> None:
        for name in ("derivative_z", "total_horizontal_gradient",
                     "analytic_signal", "tilt", "upward_continuation",
                     "residual", "reduction_to_pole"):
            self.assertIn(name, filters.UNITS)
        self.assertEqual(filters.UNITS["tilt"], "rad")


class TheOperatorsThatRefuse(unittest.TestCase):
    """Um operador que aceita o que não sabe fazer é pior que um ausente."""

    def test_downward_continuation_is_refused_by_name(self) -> None:
        _, _, values = _field()
        with self.assertRaises(ValueError) as raised:
            filters.upward_continuation(values, (SPACING, SPACING),
                                        height=-500.0)
        self.assertIn("amplifica o ruído", str(raised.exception))

    def test_a_non_positive_pixel_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            spectral.wavenumbers((8, 8), (0.0, 10.0))


class RegionalAndResidual(unittest.TestCase):
    """A única coisa verificável numa separação que é uma escolha."""

    def test_the_two_parts_reconstruct_the_field(self) -> None:
        _, _, values = _field()
        regional, residual, _ = filters.regional_residual(
            values, (SPACING, SPACING), height=3000.0)
        rebuilt = regional.astype(np.float64) + residual.astype(np.float64)
        self.assertLess(_relative_error(rebuilt, values), EXACT_REL)

    def test_the_height_is_recorded_as_a_choice(self) -> None:
        _, _, values = _field()
        _, _, provenance = filters.regional_residual(
            values, (SPACING, SPACING), height=3000.0)
        self.assertEqual(provenance["height"], 3000.0)
        self.assertIn("a altura decide o que é regional", provenance["choice"])

    def test_a_higher_continuation_leaves_more_in_the_residual(self) -> None:
        """Continuar mais alto tira mais do regional: é o que a escolha faz."""
        _, _, values = _field()
        _, low, _ = filters.regional_residual(values, (SPACING, SPACING),
                                              height=1000.0)
        _, high, _ = filters.regional_residual(values, (SPACING, SPACING),
                                               height=5000.0)
        self.assertGreater(float(np.abs(_interior(high)).mean()),
                           float(np.abs(_interior(low)).mean()))


class ReductionToPole(unittest.TestCase):
    """MSP-15 — e o alerta de estabilidade, que é obrigatório."""

    def test_at_the_pole_it_changes_almost_nothing(self) -> None:
        """A 90° de inclinação o campo já está reduzido ao polo."""
        _, _, values = _field()
        got, provenance = filters.reduction_to_pole(
            values, (SPACING, SPACING), inclination=90.0, declination=0.0)
        self.assertLess(_relative_error(got, values), DERIVATIVE_REL)
        self.assertFalse(provenance["unstable"])
        self.assertEqual(provenance["warning"], "")

    def test_low_inclination_carries_the_instability_warning(self) -> None:
        """Perto do equador magnético a RTP amplifica sem limite, e MSP-15
        manda avisar. Um alerta que não sai não é um alerta."""
        _, _, values = _field()
        _, provenance = filters.reduction_to_pole(
            values, (SPACING, SPACING), inclination=5.0, declination=0.0)
        self.assertTrue(provenance["unstable"])
        self.assertIn("equador magnético", provenance["warning"])
        self.assertIn("sinal analítico", provenance["warning"],
                      "o alerta tem de dizer o que fazer no lugar")

    def test_remanence_is_recorded_when_it_is_declared(self) -> None:
        _, _, values = _field()
        _, provenance = filters.reduction_to_pole(
            values, (SPACING, SPACING), inclination=60.0, declination=-20.0,
            magnetization_inclination=30.0, magnetization_declination=10.0)
        self.assertFalse(provenance["assumed_induced"])
        self.assertEqual(provenance["magnetization_inclination"], 30.0)

    def test_induced_magnetisation_is_stated_as_an_assumption(self) -> None:
        _, _, values = _field()
        _, provenance = filters.reduction_to_pole(
            values, (SPACING, SPACING), inclination=60.0, declination=-20.0)
        self.assertTrue(provenance["assumed_induced"])


class TheRadialSpectrumIsADiagnostic(unittest.TestCase):
    """§23 — não transforme diagnóstico espectral em interpretação."""

    def test_it_returns_a_curve(self) -> None:
        _, _, values = _field()
        got = filters.radial_spectrum(values, (SPACING, SPACING), bins=20)
        self.assertGreater(got["bins"], 5)
        self.assertEqual(len(got["wavenumber"]), len(got["log_power"]))

    def test_it_returns_no_depth(self) -> None:
        """A inclinação de um trecho reto dá uma profundidade média; qual
        trecho é reto é leitura humana, e escolher automaticamente é o que o
        §23 proíbe."""
        _, _, values = _field()
        got = filters.radial_spectrum(values, (SPACING, SPACING))
        for key in got:
            self.assertNotIn("depth", key.lower())
            self.assertNotIn("profundidade", key.lower())
        self.assertIn("leitura humana", got["boundary"])

    def test_power_falls_with_wavenumber_for_a_buried_source(self) -> None:
        """Uma fonte enterrada é um filtro passa-baixa: o espectro cai. Se
        subisse, a convenção do número de onda estaria invertida."""
        _, _, values = _field()
        got = filters.radial_spectrum(values, (SPACING, SPACING), bins=20)
        power = np.array(got["log_power"])
        self.assertGreater(float(power[0]), float(power[-1]))


class TheOperators(unittest.TestCase):
    """M7 E2 — os oito, sobre um GeoTIFF real, pelo registro."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import rasterio  # noqa: F401
        except Exception as exc:                     # pragma: no cover
            raise unittest.SkipTest(f"rasterio não está instalado: {exc}")

    def setUp(self) -> None:
        from affine import Affine
        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.domain.grid import TargetGrid
        from geopotential_worker.io.writers import write_geotiff

        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        x, y, values = _field()
        height, width = values.shape
        self.grid = TargetGrid(
            transform=Affine(SPACING, 0.0, -HALF_WIDTH,
                             0.0, -SPACING, HALF_WIDTH),
            crs=CrsInfo.from_user_input("EPSG:26912", source="test"),
            width=width, height=height)
        artifact = write_geotiff(values.astype(np.float32), self.grid,
                                 self.out / "field.tif",
                                 tags={"GEOPOTENTIAL_UNIT": "mGal"})
        self.field = str(artifact.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ctx(self):
        from geopotential_worker.operators.base import Context

        class _Ctx(Context):
            def __init__(self, output_dir):
                self.output_dir = output_dir
                self.emitted = []
                self.messages = []

            def progress(self, stage, fraction, message=""):
                self.messages.append(message)

            def check_cancel(self):
                pass

            def emit(self, name, artifact):
                self.emitted.append((name, artifact))

        return _Ctx(self.out)

    def _run(self, operator: str, params: dict, source: str | None = None):
        from geopotential_worker.operators import registry

        op = registry.get(operator)
        ctx = self._ctx()
        # A esfera sintética é uma anomalia gravimétrica; o harness declara
        # isso, e os testes que querem outro tipo passam o seu.
        params = {"field_kind": "gravity", **params}
        return op.run([source or self.field], op.validate(params), ctx), ctx

    def test_the_eight_are_registered_and_none_is_still_planned(self) -> None:
        from geopotential_worker.operators import registry

        for name in ("potential_fields.derivative",
                     "potential_fields.total_horizontal_gradient",
                     "potential_fields.analytic_signal",
                     "potential_fields.tilt",
                     "potential_fields.upward_continuation",
                     "potential_fields.regional_residual",
                     "potential_fields.rtp",
                     "potential_fields.radial_spectrum"):
            with self.subTest(operator=name):
                self.assertIn(name, registry.capabilities())
                self.assertNotIn(name, registry.PLANNED)

    def test_every_result_carries_the_conventions(self) -> None:
        """FIS-02: a convenção viaja com o resultado, e não fica só no
        docstring de um módulo que ninguém abre ao ler um manifesto."""
        manifest, _ = self._run("potential_fields.tilt",
                                {"result_name": "tilt"})
        for key in ("sign", "height", "axis", "unit", "orientation"):
            self.assertTrue(manifest["conventions"].get(key))

    def test_every_result_carries_the_border(self) -> None:
        """FIS-03, no manifesto e não só no módulo."""
        manifest, _ = self._run("potential_fields.derivative",
                                {"axis": "z", "result_name": "dz"})
        border = manifest["filter"]["border"]
        self.assertEqual(border["mode"], "reflect")
        self.assertEqual(border["pad_fraction"], 0.25)

    def test_a_derivative_is_labelled_per_length(self) -> None:
        """Uma derivada de mGal não é mGal, e um mapa rotulado errado é um
        mapa que alguém vai ler errado."""
        manifest, _ = self._run(
            "potential_fields.derivative",
            {"axis": "z", "unit": "mGal", "result_name": "dz"})
        self.assertEqual(manifest["unit"], "mGal/metre")

    def test_the_tilt_is_labelled_in_radians(self) -> None:
        manifest, _ = self._run("potential_fields.tilt",
                                {"unit": "nT", "result_name": "tilt"})
        self.assertEqual(manifest["unit"], "rad")

    def test_regional_and_residual_are_two_artefacts(self) -> None:
        manifest, ctx = self._run(
            "potential_fields.regional_residual",
            {"height": 3000.0, "unit": "mGal", "result_name": "sep"})
        names = sorted(n for n, _ in ctx.emitted)
        self.assertEqual(names, ["sep_regional", "sep_residual"])
        self.assertEqual(manifest["separation"]["height"], 3000.0)

    def test_downward_continuation_is_refused_at_the_operator(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError):
            self._run("potential_fields.upward_continuation",
                      {"height": -100.0, "result_name": "down"})

    def test_a_geographic_crs_is_refused_by_name(self) -> None:
        """Num CRS geográfico o pixel está em graus e |k| não é um número de
        onda. P-14, no caminho dos campos potenciais."""
        from affine import Affine
        from geopotential_worker.domain.crs import CrsInfo
        from geopotential_worker.domain.grid import TargetGrid
        from geopotential_worker.io.writers import write_geotiff
        from geopotential_worker.operators.base import ParameterError

        geographic = TargetGrid(
            transform=Affine(0.01, 0.0, -110.0, 0.0, -0.01, 40.0),
            crs=CrsInfo.from_user_input("EPSG:4326", source="test"),
            width=64, height=64)
        artifact = write_geotiff(
            np.random.default_rng(3).random((64, 64)).astype(np.float32),
            geographic, self.out / "geographic.tif")
        with self.assertRaises(ParameterError) as raised:
            self._run("potential_fields.tilt", {"result_name": "t"},
                      source=str(artifact.path))
        message = str(raised.exception)
        self.assertIn("geográfico", message)
        self.assertIn("número de onda", message)

    def test_the_rtp_warning_reaches_the_progress_channel(self) -> None:
        """MSP-15 manda avisar. Um alerta que só existe no manifesto é um
        alerta que ninguém lê a tempo."""
        manifest, ctx = self._run(
            "potential_fields.rtp",
            {"field_kind": "magnetic", "inclination": 5.0,
             "declination": 0.0, "result_name": "rtp"})
        self.assertTrue(manifest["rtp"]["unstable"])
        self.assertTrue(any("equador magnético" in m for m in ctx.messages),
                        "o alerta de instabilidade não saiu no progresso")

    def test_the_radial_spectrum_records_the_kind_without_restricting(self) -> None:
        """O espectro é o espectro de qualquer raster. O que depende do campo
        ser potencial é ler a inclinação como profundidade — e isso é leitura
        humana, que o §23 preserva."""
        manifest, _ = self._run("potential_fields.radial_spectrum",
                                {"field_kind": "other", "bins": 8})
        self.assertEqual(manifest["field_kind"], "other")
        self.assertFalse(manifest["harmonic_required"])

    def test_the_radial_spectrum_is_read_only(self) -> None:
        from geopotential_worker.operators import registry

        self.assertTrue(registry.get("potential_fields.radial_spectrum").read_only)
        before = set(p.name for p in self.out.iterdir())
        manifest, ctx = self._run("potential_fields.radial_spectrum",
                                  {"bins": 16})
        self.assertEqual(ctx.emitted, [])
        self.assertEqual(set(p.name for p in self.out.iterdir()), before)
        self.assertGreater(manifest["radial_spectrum"]["bins"], 4)

    def test_an_operator_refuses_a_non_potential_field(self) -> None:
        """No caminho real: pelo registro, com validate, como o worker faz."""
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            self._run("potential_fields.tilt",
                      {"field_kind": "other", "result_name": "t"})
        self.assertIn("não é potencial", str(raised.exception))

    def test_the_horizontal_derivative_runs_on_a_non_potential_field(self) -> None:
        """d/dx é derivada espacial pura. Recusá-la seria recusar o que é
        legítimo — um realce de borda num MDE, por exemplo."""
        manifest, ctx = self._run(
            "potential_fields.derivative",
            {"field_kind": "other", "axis": "x", "result_name": "dx"})
        self.assertEqual(len(ctx.emitted), 1)
        self.assertFalse(manifest["harmonic_required"])

    def test_the_vertical_derivative_is_refused_on_the_same_field(self) -> None:
        """O eixo decide, não o operador: d/dx passa e d/dz não."""
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError):
            self._run("potential_fields.derivative",
                      {"field_kind": "other", "axis": "z", "result_name": "dz"})

    def test_the_declared_kind_goes_into_the_manifest(self) -> None:
        """É a suposição mais forte de todo este caminho, e por isso fica ao
        lado da convenção e não só na tela."""
        manifest, _ = self._run("potential_fields.tilt",
                                {"field_kind": "magnetic", "result_name": "t"})
        self.assertEqual(manifest["field_kind"], "magnetic")
        self.assertTrue(manifest["harmonic_required"])

    def test_the_rtp_is_refused_on_a_gravity_field(self) -> None:
        from geopotential_worker.operators.base import ParameterError

        with self.assertRaises(ParameterError) as raised:
            self._run("potential_fields.rtp",
                      {"field_kind": "gravity", "inclination": 60.0,
                       "declination": 0.0, "result_name": "rtp"})
        self.assertIn("dipolar", str(raised.exception))

    def test_the_kind_has_no_default(self) -> None:
        """Um default aqui seria a aplicação supondo o que o dado é."""
        from geopotential_worker.operators import registry

        for name in ("potential_fields.tilt", "potential_fields.rtp",
                     "potential_fields.upward_continuation"):
            with self.subTest(operator=name):
                spec = [p for p in registry.get(name).parameters
                        if p.name == "field_kind"]
                self.assertEqual(len(spec), 1, f"{name} não pede field_kind")
                self.assertTrue(spec[0].required)

    def test_two_inputs_are_refused(self) -> None:
        from geopotential_worker.operators import registry
        from geopotential_worker.operators.base import ParameterError

        op = registry.get("potential_fields.tilt")
        with self.assertRaises(ParameterError):
            op.run([self.field, self.field],
                   op.validate({"result_name": "t"}), self._ctx())


class WhatTheDataActuallyIs(unittest.TestCase):
    """P-185, P-186 — cinco transformações só existem se o campo for potencial.

    Num campo potencial, `d/dz` é obtido do dado **horizontal** pelo operador
    `|k|`, e esse `|k|` vem da equação de Laplace: para uma função harmônica,
    `d²φ/dz² = -(d²φ/dx² + d²φ/dy²)`, o que no domínio de Fourier dá
    `dφ̂/dz = ±|k|φ̂`. Aplicar isso a um MDE é **inferir uma dimensão que o
    dado não tem** — a elevação não continua para cima, ela é a superfície.

    Antes disto, os operadores aceitavam qualquer raster métrico e rodavam uma
    continuação para cima num MDE sem dizer nada. O manifesto registrava a
    convenção e a borda, e não registrava a suposição mais forte de todas.
    """

    HARMONIC = ("derivative_z", "analytic_signal", "tilt",
                "upward_continuation", "regional_residual",
                "reduction_to_pole")
    GRID_MATHS = ("derivative_horizontal", "total_horizontal_gradient",
                  "radial_spectrum")

    def test_the_harmonic_ones_are_refused_on_a_non_potential_field(self) -> None:
        for transform in self.HARMONIC:
            with self.subTest(transform=transform):
                with self.assertRaises(filters.FieldKindError) as raised:
                    filters.require_harmonic(transform, "other")
                self.assertIn("não é potencial", str(raised.exception))

    def test_the_refusal_names_what_still_works(self) -> None:
        """Uma recusa que não diz a alternativa manda a pessoa embora."""
        with self.assertRaises(filters.FieldKindError) as raised:
            filters.require_harmonic("tilt", "other")
        message = str(raised.exception)
        self.assertIn("gradiente horizontal total", message)
        self.assertIn("derivadas horizontais", message)

    def test_grid_maths_works_on_any_continuous_field(self) -> None:
        """dx, dy, THG e o espectro são matemática de grade: um MDE, uma
        resistividade, uma espessura. Recusá-los seria recusar o que é
        legítimo."""
        for transform in self.GRID_MATHS:
            for kind in filters.FIELD_KINDS:
                with self.subTest(transform=transform, kind=kind):
                    filters.require_harmonic(transform, kind)

    def test_the_rtp_is_magnetic_only(self) -> None:
        filters.require_harmonic("reduction_to_pole", "magnetic")
        for kind in ("gravity", "other"):
            with self.subTest(kind=kind):
                with self.assertRaises(filters.FieldKindError):
                    filters.require_harmonic("reduction_to_pole", kind)

    def test_an_undeclared_kind_is_refused(self) -> None:
        """Não há default: adivinhar 'isto parece gravimetria' a partir de uma
        faixa de valores é o tipo de suposição que este projeto não faz."""
        for kind in ("", "geofisica", None):
            with self.subTest(kind=kind):
                with self.assertRaises(filters.FieldKindError):
                    filters.require_harmonic("tilt", str(kind))

    def test_every_needs_harmonic_entry_says_why(self) -> None:
        for transform, reason in filters.NEEDS_HARMONIC.items():
            self.assertGreater(len(reason), 20,
                               f"{transform} recusa sem dizer por quê")


class NoPythonLoopOverCells(unittest.TestCase):
    """P-153, ADR-007."""

    def test_no_loop_iterates_cells_or_pixels(self) -> None:
        import re

        for module in (spectral, filters, synthetic):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if not stripped.startswith("for "):
                    continue
                iterated = stripped.split(" in ", 1)[-1].rstrip(":")
                self.assertNotRegex(
                    iterated, r"\bcell\b|pixel|célula",
                    f"{Path(module.__file__).name}: {stripped}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
