"""Os operadores de campos potenciais. MSP-14, MSP-15, gates FIS.

    potential_fields.derivative                  d/dx, d/dy, d/dz
    potential_fields.total_horizontal_gradient   realce de borda lateral
    potential_fields.analytic_signal             Nabighian (1972)
    potential_fields.tilt                        Miller & Singh (1994)
    potential_fields.upward_continuation         Blakely §12
    potential_fields.regional_residual           separação por continuação
    potential_fields.rtp                         Baranov (1957)
    potential_fields.radial_spectrum             diagnóstico; read-only

Todos passam pelo mesmo caminho espectral, então todos registram o mesmo
padding e o mesmo taper — o FIS-03 não depende de nenhum deles se lembrar.

**A grade tem de ser regular e métrica.** Um número de onda é `rad` por
unidade de comprimento; num CRS geográfico o pixel está em graus e `|k|` não
é um número de onda. Recusado por nome, como toda operação métrica neste
projeto (`P-14`).

**Nada aqui interpreta.** Um tilt realça bordas, não as encontra; o espectro
radial é um diagnóstico e não devolve profundidade. O §23 do documento
normativo é explícito sobre a segunda, e a primeira segue a mesma regra.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..domain.crs import CrsInfo
from ..io.readers import read_raster
from ..io.writers import write_geotiff
from ..potential_fields import filters, synthetic
from .base import Context, Operator, Parameter, ParameterError

#: O que o dado **é**, declarado por quem opera.
#:
#: Não é metadado decorativo: cinco das transformações só existem porque o
#: campo satisfaz Laplace na região sem fontes, e num dado que não a satisfaz
#: elas calculam uma quantidade que não existe. `other` é o dado contínuo
#: qualquer — um MDE, uma resistividade, uma espessura — e nele o operador
#: recusa por nome, dizendo o que continua valendo.
#:
#: Declarado e não inferido: a unidade nem sempre está no arquivo, e adivinhar
#: "isto parece gravimetria" a partir de uma faixa de valores é exatamente o
#: tipo de suposição que este projeto não faz (ADR-004, no espírito).
FIELD_KIND_PARAMETER = Parameter(
    name="field_kind", type="str", required=True,
    choices=filters.FIELD_KINDS,
    doc="O que este dado é: `gravity`, `magnetic` ou `other`. As "
        "transformações que dependem da derivada vertical só são definidas "
        "para um campo potencial; a redução ao polo, só para magnético.")

#: A borda, declarada da mesma forma por todo operador (FIS-03).
BORDER_PARAMETERS = (
    Parameter(name="pad_fraction", type="float", default=0.25,
              minimum=0.0, maximum=2.0, unit="fração do lado",
              doc="Quanto a grade cresce de cada lado antes da FFT. A "
                  "diferença entre 10 % e 50 % é visível no resultado, e o "
                  "valor vai para o manifesto."),
    Parameter(name="taper", type="float", default=1.0, minimum=0.0, maximum=1.0,
              unit="fração da região refletida",
              doc="Quanto da região refletida recebe o cosseno. O taper decai "
                  "para o nível da **borda** do dado, não para a média."),
    Parameter(name="result_name", type="str", required=True,
              doc="Nome do resultado, e do arquivo."),
)


def _read_field(inputs: Sequence[str], name: str):
    """A grade, o pixel e o CRS — recusando o que não dá para filtrar."""
    if len(inputs) != 1:
        raise ParameterError(
            f"{name}: espera exatamente um raster; recebi {len(inputs)}")
    path = Path(inputs[0])
    source = read_raster(str(path))
    grid = source.grid

    crs = grid.crs
    if isinstance(crs, CrsInfo) and crs.is_geographic:
        raise ParameterError(
            f"{crs.name} é um CRS geográfico, então o pixel está em graus e "
            f"|k| não é um número de onda. Um filtro de campos potenciais "
            f"precisa de uma grade métrica; harmonize para uma antes."
        )

    px, py = grid.pixel_size
    return source.values, (float(px), float(py)), grid, path


def _write(ctx: Context, values, grid, name: str, unit: str, operator: str,
           version: str, tags: dict[str, str] | None = None):
    artifact = write_geotiff(
        np.asarray(values, dtype=np.float32), grid,
        ctx.output_dir / f"{name}.tif",
        tags={
            "GEOPOTENTIAL_STAGE": "RAW",
            "GEOPOTENTIAL_UNIT": unit,
            "GEOPOTENTIAL_OPERATOR": f"{operator}@{version}",
            **(tags or {}),
        },
    )
    ctx.emit(name, artifact)
    return artifact


class _FieldOperator(Operator):
    """O que os oito compartilham: ler, filtrar, escrever, registrar."""

    #: Como a unidade do campo se transforma. Uma derivada de mGal não é mGal.
    unit_template = "{unit}"

    def _unit(self, source_unit: str | None, length_unit: str) -> str:
        return self.unit_template.format(unit=source_unit or "unidade do campo",
                                         length=length_unit)

    def _border(self, params: dict[str, Any]) -> dict[str, float]:
        return {"fraction": float(params["pad_fraction"]),
                "taper": float(params["taper"])}

    #: A chave em `filters.NEEDS_HARMONIC` que este operador representa.
    #: Vazia quando a transformação é matemática de grade e vale em qualquer
    #: campo contínuo.
    transform_key = ""

    def _require_kind(self, params: dict[str, Any],
                      key: str | None = None) -> str:
        """Recusa a transformação quando o campo declarado não a comporta.

        `key` sobrescreve `transform_key` para o caso em que a resposta
        depende de um parâmetro — a derivada, cujo eixo decide se ela precisa
        do campo ser harmônico. **Passado como argumento e não escrito no
        objeto**: o registro guarda uma instância só por operador, e gravar o
        eixo nela vazaria de uma execução para a seguinte.
        """
        kind = str(params.get("field_kind") or "")
        try:
            filters.require_harmonic(key or self.transform_key or self.name,
                                     kind)
        except filters.FieldKindError as refusal:
            raise ParameterError(str(refusal)) from refusal
        return kind

    def _manifest(self, path: Path, grid, params, extra: dict[str, Any],
                  unit: str) -> dict[str, Any]:
        return {
            "operator": self.name,
            "operator_version": self.version,
            "reference": self.reference,
            "inputs": [{"role": "field", "path": str(path.resolve())}],
            "params": params,
            "grid": grid.describe(),
            "unit": unit,
            # O que a pessoa declarou que o dado é. É a suposição mais forte
            # de todo este caminho — que o campo é harmônico — e por isso ela
            # fica no manifesto ao lado da convenção, e não só na tela.
            "field_kind": params.get("field_kind"),
            "harmonic_required": bool(filters.NEEDS_HARMONIC.get(
                ("derivative_z" if params.get("axis") == "z"
                 else self.transform_key or self.name))),
            # FIS-02: a convenção viaja com todo resultado, e não fica só no
            # docstring de um módulo que ninguém abre ao ler um manifesto.
            "conventions": synthetic.conventions(),
            **extra,
        }


class DerivativeOperator(_FieldOperator):
    """Derivada direcional. Blakely §12."""

    name = "potential_fields.derivative"
    version = "1.0.0"
    unit_template = "{unit}/{length}"
    summary = "Derivada de primeira ou segunda ordem em x, y ou z (z para baixo)."
    reference = ("Blakely (1995), Potential Theory in Gravity and Magnetic "
                 "Applications, section 12; MSP-14/15.")

    parameters = BORDER_PARAMETERS + (FIELD_KIND_PARAMETER,) + (
        Parameter(name="axis", type="str", required=True, choices=("x", "y", "z"),
                  doc="Eixo. z é positivo **para baixo**: a derivada vertical "
                      "cresce ao aproximar-se da fonte."),
        Parameter(name="order", type="int", default=1, minimum=1, maximum=2,
                  doc="1 ou 2. Ordem 3 multiplica o espectro por |k|³ e o que "
                      "sai é ruído com a forma do dado."),
        Parameter(name="unit", type="str", default=None,
                  doc="Unidade do campo de entrada, para rotular a saída."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        # Só a derivada **vertical** precisa do campo ser harmônico; d/dx e
        # d/dy são derivadas espaciais puras e valem em qualquer grade.
        key = "derivative_z" if params["axis"] == "z" else "derivative_horizontal"
        self._require_kind(params, key)
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("filter", 0.0, f"d/d{params['axis']}")
        ctx.check_cancel()
        try:
            out, provenance = filters.derivative(
                values, pixel, axis=params["axis"], order=int(params["order"]),
                **self._border(params))
        except ValueError as refusal:
            raise ParameterError(str(refusal)) from refusal
        ctx.progress("filter", 1.0, "filtrado")

        unit = self._unit(params.get("unit"),
                          getattr(grid.crs, "unit", None) or "m")
        artifact = _write(ctx, out, grid, params["result_name"], unit,
                          self.name, self.version,
                          {"GEOPOTENTIAL_AXIS": str(params["axis"])})
        ctx.progress("commit", 1.0, artifact.path.name)
        return self._manifest(path, grid, params, {"filter": provenance}, unit)


class _CompositeOperator(_FieldOperator):
    """Os três que combinam derivadas: THG, sinal analítico, tilt."""

    function = staticmethod(lambda *a, **k: None)

    parameters = BORDER_PARAMETERS + (FIELD_KIND_PARAMETER,) + (
        Parameter(name="unit", type="str", default=None,
                  doc="Unidade do campo de entrada, para rotular a saída."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        self._require_kind(params)
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("filter", 0.0, self.name.split(".")[-1])
        ctx.check_cancel()
        out, provenance = type(self).function(values, pixel,
                                              **self._border(params))
        ctx.progress("filter", 1.0, "filtrado")

        unit = self._unit(params.get("unit"),
                          getattr(grid.crs, "unit", None) or "m")
        artifact = _write(ctx, out, grid, params["result_name"], unit,
                          self.name, self.version)
        ctx.progress("commit", 1.0, artifact.path.name)
        return self._manifest(path, grid, params, {"filter": provenance}, unit)


class TotalHorizontalGradientOperator(_CompositeOperator):
    name = "potential_fields.total_horizontal_gradient"
    version = "1.0.0"
    unit_template = "{unit}/{length}"
    # Só dx e dy: matemática de grade, vale em qualquer campo contínuo.
    transform_key = ""
    function = staticmethod(filters.total_horizontal_gradient)
    summary = ("sqrt(dx² + dy²): realça bordas laterais. Realça, não as "
               "encontra.")
    reference = "Blakely (1995) section 12; MSP-14/15."


class AnalyticSignalOperator(_CompositeOperator):
    name = "potential_fields.analytic_signal"
    version = "1.0.0"
    unit_template = "{unit}/{length}"
    transform_key = "analytic_signal"
    function = staticmethod(filters.analytic_signal)
    summary = ("sqrt(dx² + dy² + dz²). Independente da direção de magnetização "
               "em 2D; aproximadamente em 3D.")
    reference = ("Nabighian, M. N. (1972), Geophysics 37(3), 507-517; MSP-15.")


class TiltOperator(_CompositeOperator):
    name = "potential_fields.tilt"
    version = "1.0.0"
    unit_template = "rad"
    transform_key = "tilt"
    function = staticmethod(filters.tilt)
    summary = "atan2(dz, THG), em radianos, limitado a [-pi/2, pi/2]."
    reference = ("Miller, H. G. & Singh, V. (1994), J. Applied Geophysics "
                 "32(2-3), 213-217; MSP-14/15.")


class UpwardContinuationOperator(_FieldOperator):
    """Observar o mesmo campo mais alto. Blakely §12."""

    name = "potential_fields.upward_continuation"
    version = "1.0.0"
    transform_key = "upward_continuation"
    summary = "Continua o campo para cima por uma altura declarada."
    reference = "Blakely (1995) section 12; MSP-14/15."

    parameters = BORDER_PARAMETERS + (FIELD_KIND_PARAMETER,) + (
        Parameter(name="height", type="float", required=True, minimum=1e-9,
                  unit="unidade do CRS",
                  doc="Altura, positiva para cima. Continuar para baixo "
                      "amplifica o ruído exponencialmente com |k| e é "
                      "recusado."),
        Parameter(name="unit", type="str", default=None,
                  doc="Unidade do campo; a continuação não a muda."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        self._require_kind(params)
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("filter", 0.0, f"h = {params['height']}")
        ctx.check_cancel()
        try:
            out, provenance = filters.upward_continuation(
                values, pixel, height=float(params["height"]),
                **self._border(params))
        except ValueError as refusal:
            raise ParameterError(str(refusal)) from refusal
        ctx.progress("filter", 1.0, "continuado")

        unit = self._unit(params.get("unit"), "")
        artifact = _write(ctx, out, grid, params["result_name"], unit,
                          self.name, self.version,
                          {"GEOPOTENTIAL_HEIGHT": str(params["height"])})
        ctx.progress("commit", 1.0, artifact.path.name)
        return self._manifest(path, grid, params, {"filter": provenance}, unit)


class RegionalResidualOperator(_FieldOperator):
    """Separa regional e residual pela continuação para cima."""

    name = "potential_fields.regional_residual"
    version = "1.0.0"
    transform_key = "regional_residual"
    summary = ("Regional por continuação para cima; residual = campo − "
               "regional. A altura é uma escolha, e vai no manifesto.")
    reference = "Blakely (1995) section 12; MSP-14."

    parameters = BORDER_PARAMETERS + (FIELD_KIND_PARAMETER,) + (
        Parameter(name="height", type="float", required=True, minimum=1e-9,
                  unit="unidade do CRS",
                  doc="A altura que decide o que é regional. Outra altura é "
                      "outra separação, igualmente bem-comportada."),
        Parameter(name="unit", type="str", default=None,
                  doc="Unidade do campo; a separação não a muda."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        self._require_kind(params)
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("filter", 0.0, f"h = {params['height']}")
        ctx.check_cancel()
        regional, residual, provenance = filters.regional_residual(
            values, pixel, height=float(params["height"]),
            **self._border(params))
        ctx.progress("filter", 1.0, "separado")

        unit = self._unit(params.get("unit"), "")
        name = params["result_name"]
        for suffix, array in (("regional", regional), ("residual", residual)):
            ctx.check_cancel()
            _write(ctx, array, grid, f"{name}_{suffix}", unit,
                   self.name, self.version, {"GEOPOTENTIAL_PART": suffix})
        ctx.progress("commit", 1.0, f"{name}_regional, {name}_residual")
        return self._manifest(path, grid, params,
                              {"separation": provenance}, unit)


class ReductionToPoleOperator(_FieldOperator):
    """Redução ao polo, com o alerta de estabilidade. MSP-15."""

    name = "potential_fields.rtp"
    version = "1.0.0"
    transform_key = "reduction_to_pole"
    summary = ("Baranov (1957). Instável em baixa inclinação, e o resultado "
               "diz isso.")
    reference = ("Baranov, V. (1957), Geophysics 22(2), 359-382; MSP-15.")

    parameters = BORDER_PARAMETERS + (FIELD_KIND_PARAMETER,) + (
        Parameter(name="inclination", type="float", required=True,
                  minimum=-90.0, maximum=90.0, unit="graus",
                  doc="Inclinação do campo geomagnético no levantamento."),
        Parameter(name="declination", type="float", required=True,
                  minimum=-180.0, maximum=180.0, unit="graus",
                  doc="Declinação do campo geomagnético no levantamento."),
        Parameter(name="magnetization_inclination", type="float", default=None,
                  minimum=-90.0, maximum=90.0, unit="graus",
                  doc="Da magnetização, quando há remanência. Ausente, "
                      "assume-se induzida — e a suposição é registrada."),
        Parameter(name="magnetization_declination", type="float", default=None,
                  minimum=-180.0, maximum=180.0, unit="graus",
                  doc="Da magnetização, quando há remanência."),
        Parameter(name="unit", type="str", default=None,
                  doc="Unidade do campo; a RTP não a muda."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        self._require_kind(params)
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("filter", 0.0,
                     f"I = {params['inclination']}°, D = {params['declination']}°")
        ctx.check_cancel()
        out, provenance = filters.reduction_to_pole(
            values, pixel,
            inclination=float(params["inclination"]),
            declination=float(params["declination"]),
            magnetization_inclination=params.get("magnetization_inclination"),
            magnetization_declination=params.get("magnetization_declination"),
            **self._border(params))
        if provenance["unstable"]:
            # Um alerta que só existe no manifesto é um alerta que ninguém lê
            # a tempo. Ele também sai no progresso, que a interface mostra.
            ctx.progress("filter", 0.9, provenance["warning"])
        ctx.progress("filter", 1.0, "reduzido ao polo")

        unit = self._unit(params.get("unit"), "")
        artifact = _write(ctx, out, grid, params["result_name"], unit,
                          self.name, self.version,
                          {"GEOPOTENTIAL_RTP_INCLINATION":
                           str(params["inclination"])})
        ctx.progress("commit", 1.0, artifact.path.name)
        return self._manifest(path, grid, params, {"rtp": provenance}, unit)


class RadialSpectrumOperator(_FieldOperator):
    """O espectro de potência radialmente promediado. Diagnóstico, read-only."""

    name = "potential_fields.radial_spectrum"
    version = "1.0.0"
    read_only = True
    summary = ("Espectro de potência radial. É diagnóstico: não devolve "
               "profundidade, e escolher o trecho reto é leitura humana.")
    reference = ("Spector, A. & Grant, F. S. (1970), Geophysics 35(2), "
                 "293-302; MSP-14, section 23.")

    parameters = (
        # Registrado, e não restritivo: o espectro de potência é o espectro de
        # qualquer raster. O que depende do campo ser potencial é a *leitura*
        # da inclinação de um trecho reto como profundidade média — e essa
        # leitura é humana, que é justamente o que o §23 preserva.
        Parameter(name="field_kind", type="str", default="other",
                  choices=filters.FIELD_KINDS,
                  doc="O que este dado é. Aqui ele não restringe nada: o "
                      "espectro é o espectro de qualquer raster. Vai para o "
                      "manifesto porque quem ler a curva depois precisa saber "
                      "de que campo ela é."),
        Parameter(name="pad_fraction", type="float", default=0.25,
                  minimum=0.0, maximum=2.0, unit="fração do lado",
                  doc="Como nos demais filtros."),
        Parameter(name="taper", type="float", default=1.0, minimum=0.0,
                  maximum=1.0, unit="fração da região refletida",
                  doc="Como nos demais filtros."),
        Parameter(name="bins", type="int", default=40, minimum=4,
                  doc="Quantas bandas de número de onda."),
    )

    def run(self, inputs, params, ctx):                    # noqa: ANN001
        values, pixel, grid, path = _read_field(inputs, self.name)
        ctx.progress("spectrum", 0.0, "transformando")
        ctx.check_cancel()
        spectrum = filters.radial_spectrum(
            values, pixel, bins=int(params["bins"]),
            fraction=float(params["pad_fraction"]),
            taper=float(params["taper"]))
        ctx.progress("spectrum", 1.0, f"{spectrum['bins']} bandas")
        return self._manifest(path, grid, params,
                              {"radial_spectrum": spectrum}, "log potência")
