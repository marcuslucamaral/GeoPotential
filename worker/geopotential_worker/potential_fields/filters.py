"""As transformações de campos potenciais. MSP-14, MSP-15.

inputs   uma grade regular do campo, e o pixel em unidade de comprimento
output   a grade transformada, com a procedência da borda
unit     declarada por transformação abaixo; nenhuma delas é adimensional
         por acidente
reference  Blakely (1995) §12 para os operadores espectrais;
           Nabighian (1972) para o sinal analítico;
           Miller & Singh (1994) para o tilt;
           Baranov (1957) para a redução ao polo.

Todas passam por `spectral.apply_filter`, então todas registram o mesmo
padding e o mesmo taper, e nenhuma pode esquecer de declarar a borda.

**O que cada uma é, e o que ela não é.** Estas são transformações lineares e
determinísticas de um campo medido. Nenhuma delas é interpretação: o tilt
realça bordas, não as encontra; o espectro radial estima uma profundidade
média por banda, e não a profundidade de um corpo. O §23 do documento
normativo é explícito — *não transforme diagnóstico espectral em interpretação
automática* — e é por isso que nada aqui devolve um contorno, uma classe ou uma
lista de alvos.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import spectral

#: O que cada transformação faz com a unidade do campo de entrada. Vai para o
#: manifesto: uma derivada de mGal não é mGal, e um mapa rotulado errado é um
#: mapa que alguém vai ler errado.
UNITS = {
    "derivative_x": "{unit}/{length}",
    "derivative_y": "{unit}/{length}",
    "derivative_z": "{unit}/{length}",
    "total_horizontal_gradient": "{unit}/{length}",
    "analytic_signal": "{unit}/{length}",
    "tilt": "rad",
    "upward_continuation": "{unit}",
    "residual": "{unit}",
    "reduction_to_pole": "{unit}",
}

#: Que tipo de campo o dado é. **Não é metadado decorativo**: cinco das oito
#: transformações abaixo só existem porque o campo satisfaz a equação de
#: Laplace na região sem fontes, e num dado que não a satisfaz elas calculam
#: uma quantidade que não existe.
#:
#: `other` é o dado contínuo qualquer — um MDE, uma resistividade interpolada,
#: uma espessura. Nele valem as derivadas horizontais, o gradiente horizontal
#: total e o espectro, que são matemática de grade e não física de potencial.
FIELD_KINDS = ("gravity", "magnetic", "other")

#: As que precisam do campo ser harmônico, e por quê.
#:
#: Num campo potencial, `d/dz` é obtido do dado **horizontal** pelo operador
#: `|k|`, e esse `|k|` vem de Laplace: para uma função harmônica,
#: `d²φ/dz² = -(d²φ/dx² + d²φ/dy²)`, o que no domínio de Fourier dá
#: `dφ̂/dz = ±|k|φ̂`. Aplicar isso a um MDE é **inferir uma dimensão que o dado
#: não tem** — a elevação não continua para cima, ela é a superfície.
#:
#: A continuação para cima é o mesmo argumento na forma mais direta: ela *é* a
#: solução de Laplace com valores de contorno. Num dado não potencial ela é um
#: passa-baixa com um nome físico que ali não significa nada, e quem lê o mapa
#: vai supor que significa.
NEEDS_HARMONIC = {
    "derivative_z": "a derivada vertical é inferida do dado horizontal por |k|, "
                    "que sai da equação de Laplace",
    "analytic_signal": "usa a derivada vertical",
    "tilt": "usa a derivada vertical",
    "upward_continuation": "é a solução de Laplace com valores de contorno",
    "regional_residual": "é continuação para cima",
    "reduction_to_pole": "depende da natureza dipolar do campo magnético",
}


class FieldKindError(ValueError):
    """A transformação pedida não é definida para este tipo de campo."""


def require_harmonic(transform: str, field_kind: str) -> None:
    """Recusa uma transformação de campo potencial num dado que não é um.

    transform   a chave em `NEEDS_HARMONIC`
    field_kind  o que a pessoa declarou que o dado é

    A recusa **nomeia a alternativa**: num dado não potencial o realce de borda
    continua disponível pelo gradiente horizontal total, que usa só derivadas
    horizontais e é matemática de grade.
    """
    if field_kind not in FIELD_KINDS:
        raise FieldKindError(
            f"field_kind={field_kind!r} não é um dos declarados: "
            f"{', '.join(FIELD_KINDS)}."
        )
    if field_kind != "other":
        if transform == "reduction_to_pole" and field_kind != "magnetic":
            raise FieldKindError(
                "a redução ao polo depende da natureza dipolar do campo "
                "magnético e da direção do campo geomagnético. Num campo "
                f"gravimétrico ela não é definida."
            )
        return
    reason = NEEDS_HARMONIC.get(transform)
    if reason is None:
        return
    raise FieldKindError(
        f"esta transformação não é definida para um campo que não é potencial: "
        f"{reason}. O dado foi declarado como 'outro', que é o dado contínuo "
        f"qualquer — um MDE, uma resistividade, uma espessura. Nele continuam "
        f"válidos as derivadas horizontais, o gradiente horizontal total e o "
        f"espectro radial, que são matemática de grade e não física de campo "
        f"potencial."
    )


#: Abaixo desta inclinação, a redução ao polo é instável: o denominador do
#: operador de Baranov tende a zero na direção da declinação, e o resultado
#: amplifica ruído numa faixa de números de onda. MSP-15 manda avisar.
UNSTABLE_INCLINATION_DEG = 30.0


def _length_unit(crs_unit: str | None) -> str:
    return crs_unit or "unidade do CRS"


def derivative(
    values: np.ndarray,
    pixel: tuple[float, float],
    *,
    axis: str,
    order: int = 1,
    **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Derivada direcional de ordem `order`. Blakely §12.

    axis   "x", "y" ou "z"; z é **para baixo**
    order  1 ou 2. Ordens maiores amplificam ruído sem que ninguém tenha
           pedido, e são recusadas por nome.
    """
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis={axis!r}: é 'x', 'y' ou 'z'")
    if order not in (1, 2):
        raise ValueError(
            f"order={order}: só 1 e 2. Uma derivada de ordem 3 multiplica o "
            f"espectro por |k|³ e o que sai é ruído com a forma do dado."
        )

    def response(kx, ky, k):                      # noqa: ANN001
        if axis == "z":
            # z para baixo: +|k|. O gate FIS-01 decide este sinal contra a
            # esfera. |k| é par em k, então não tem o problema de Nyquist.
            return k ** order

        multiplier = (1j * kx) ** order if axis == "x" else (1j * ky) ** order
        if order % 2 == 0:
            return multiplier

        # **O coeficiente de Nyquist não tem par conjugado.** Numa grade de
        # lado par, `fftfreq` põe a frequência de Nyquist numa única posição,
        # negativa, sem a positiva correspondente. Um multiplicador ímpar em
        # k — que é o caso de toda derivada horizontal de ordem ímpar —
        # deixa de ser hermitiano exatamente ali, e o resultado da inversa
        # sai com uma parte imaginária concentrada naquela linha e naquela
        # coluna.
        #
        # Zerar o coeficiente de Nyquist é o tratamento padrão, e o custo é
        # aquilo que ele descarta: a componente de menor comprimento de onda
        # que a grade consegue representar, que é justamente onde a amostragem
        # já não distingue sinal de alias.
        #
        # Só aparece em lado **par**. A suíte sintética roda numa grade
        # 201 x 201, ímpar, e passava; foi o campo real 4096 x 4096 que
        # acendeu a checagem de hermitianidade.
        # `kx` tem forma (1, largura) e `ky` tem (altura, 1): a derivada em x
        # não depende de ky, então só o Nyquist do **seu** eixo precisa ser
        # zerado. Zerar na forma cheia seria zerar uma linha inteira que não
        # tem problema nenhum.
        multiplier = np.array(multiplier, copy=True)
        length = multiplier.shape[1] if axis == "x" else multiplier.shape[0]
        if length % 2 == 0:
            if axis == "x":
                multiplier[:, length // 2] = 0.0
            else:
                multiplier[length // 2, :] = 0.0
        return multiplier

    out, provenance = spectral.apply_filter(values, pixel, response, **border)
    return out, {"axis": axis, "order": order, "border": provenance}


def total_horizontal_gradient(
    values: np.ndarray, pixel: tuple[float, float], **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """THG = sqrt((df/dx)² + (df/dy)²). Realça bordas laterais.

    Positivo por construção, e máximo sobre um contato vertical — o que faz
    dele um realce de borda e **não** um detector: quem decide que ali há um
    contato é quem interpreta.
    """
    dx, prov_x = derivative(values, pixel, axis="x", **border)
    dy, _ = derivative(values, pixel, axis="y", **border)
    thg = np.sqrt(dx.astype(np.float64) ** 2 + dy.astype(np.float64) ** 2)
    return thg.astype(np.float32), {"components": ["dx", "dy"],
                                    "border": prov_x["border"]}


def analytic_signal(
    values: np.ndarray, pixel: tuple[float, float], **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """|A| = sqrt(dx² + dy² + dz²). Nabighian (1972).

    Em duas dimensões o seu máximo fica sobre a fonte independentemente da
    direção de magnetização, que é a razão de ele existir em magnetometria.
    Em três dimensões essa independência é aproximada, e dizer isso aqui é
    mais barato do que alguém supor o contrário.
    """
    dx, prov_x = derivative(values, pixel, axis="x", **border)
    dy, _ = derivative(values, pixel, axis="y", **border)
    dz, _ = derivative(values, pixel, axis="z", **border)
    amplitude = np.sqrt(dx.astype(np.float64) ** 2
                        + dy.astype(np.float64) ** 2
                        + dz.astype(np.float64) ** 2)
    return amplitude.astype(np.float32), {
        "components": ["dx", "dy", "dz"],
        "limitation": ("a independência da direção de magnetização é exata em "
                       "2D e aproximada em 3D; Nabighian (1972)"),
        "border": prov_x["border"],
    }


def tilt(
    values: np.ndarray, pixel: tuple[float, float], **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """tilt = atan2(dz, THG). Miller & Singh (1994).

    Em **radianos**, em [-π/2, π/2]. O zero cai perto da borda da fonte e o
    valor é limitado, o que faz do tilt um realce que não depende da amplitude
    do campo — e é por isso que ele é útil e é também por isso que ele não diz
    nada sobre magnitude.
    """
    dz, prov = derivative(values, pixel, axis="z", **border)
    thg, _ = total_horizontal_gradient(values, pixel, **border)
    angle = np.arctan2(dz.astype(np.float64), thg.astype(np.float64))
    return angle.astype(np.float32), {
        "range_rad": [-np.pi / 2, np.pi / 2],
        "note": "adimensional em amplitude: o tilt realça, não mede",
        "border": prov["border"],
    }


def upward_continuation(
    values: np.ndarray, pixel: tuple[float, float], *, height: float, **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Observa o mesmo campo `height` acima. exp(-|k|h), Blakely §12.

    height  positivo, para cima, na unidade do pixel

    Continuar para **baixo** é o mesmo operador com h negativo e é uma
    amplificação sem limite superior: `exp(+|k|h)` cresce com o número de
    onda, e o que cresce mais depressa é o ruído. Recusado por nome.
    """
    height = float(height)
    if height <= 0:
        raise ValueError(
            f"height={height}: a continuação para cima pede altura positiva. "
            f"Continuar para baixo amplifica o ruído exponencialmente com o "
            f"número de onda, e não é o que este operador faz."
        )

    def response(kx, ky, k):                      # noqa: ANN001
        return np.exp(-k * height)

    out, provenance = spectral.apply_filter(values, pixel, response, **border)
    return out, {"height": height, "border": provenance}


def regional_residual(
    values: np.ndarray, pixel: tuple[float, float], *, height: float, **border,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Separa o campo em regional e residual pela continuação para cima.

    returns  (regional, residual, procedência), com residual = campo - regional

    **É uma escolha, não uma medida.** A altura decide o que conta como
    regional, e uma altura diferente dá uma separação diferente, com as mesmas
    aparências de correção. Ela vai para o manifesto, e a soma das duas partes
    reconstrói o campo exatamente — o que é a única coisa aqui que se pode
    verificar.
    """
    regional, provenance = upward_continuation(values, pixel, height=height,
                                               **border)
    residual = (np.asarray(values, dtype=np.float64)
                - regional.astype(np.float64)).astype(np.float32)
    return regional, residual, {
        "method": "upward continuation",
        "height": float(height),
        "choice": ("a altura decide o que é regional; outra altura é outra "
                   "separação, igualmente bem-comportada"),
        **provenance,
    }


def reduction_to_pole(
    values: np.ndarray,
    pixel: tuple[float, float],
    *,
    inclination: float,
    declination: float,
    magnetization_inclination: float | None = None,
    magnetization_declination: float | None = None,
    **border,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Redução ao polo. Baranov (1957). MSP-15.

    inclination/declination  do campo geomagnético, em graus
    magnetization_*          da magnetização, quando diferente do campo;
                             ausente, assume-se induzida e igual ao campo

    **Instável em baixa latitude magnética**, e o resultado diz isso: perto do
    equador o denominador do operador tende a zero na direção da declinação e
    a RTP amplifica uma faixa de números de onda sem limite. Abaixo de
    `UNSTABLE_INCLINATION_DEG` a procedência traz um alerta que a interface é
    obrigada a mostrar — MSP-15 pede isso por escrito.
    """
    inc = np.radians(float(inclination))
    dec = np.radians(float(declination))
    minc = np.radians(float(magnetization_inclination)
                      if magnetization_inclination is not None
                      else float(inclination))
    mdec = np.radians(float(magnetization_declination)
                      if magnetization_declination is not None
                      else float(declination))

    def response(kx, ky, k):                      # noqa: ANN001
        # Baranov: a razão entre a resposta no polo e a resposta na latitude
        # do levantamento. Os dois vetores de direção entram como um fator
        # cada; a magnetização e o campo são separados porque remanência é o
        # caso em que eles diferem.
        with np.errstate(divide="ignore", invalid="ignore"):
            theta_f = (np.sin(inc)
                       + 1j * np.cos(inc) * (kx * np.sin(dec) + ky * np.cos(dec))
                       / np.where(k == 0, 1.0, k))
            theta_m = (np.sin(minc)
                       + 1j * np.cos(minc) * (kx * np.sin(mdec) + ky * np.cos(mdec))
                       / np.where(k == 0, 1.0, k))
            operator = 1.0 / (theta_f * theta_m)
        # k = 0 é a média do campo, que a RTP não redefine. Deixá-la passar
        # inalterada é o que preserva o nível.
        operator = np.where(k == 0, 1.0, operator)
        return np.where(np.isfinite(operator), operator, 0.0)

    out, border_provenance = spectral.apply_filter(values, pixel, response,
                                                   **border)
    unstable = abs(float(inclination)) < UNSTABLE_INCLINATION_DEG
    return out, {
        "inclination": float(inclination),
        "declination": float(declination),
        "magnetization_inclination": (float(magnetization_inclination)
                                      if magnetization_inclination is not None
                                      else float(inclination)),
        "magnetization_declination": (float(magnetization_declination)
                                      if magnetization_declination is not None
                                      else float(declination)),
        "assumed_induced": magnetization_inclination is None,
        "unstable": unstable,
        "warning": (
            f"inclinação {inclination:g}° está abaixo de "
            f"{UNSTABLE_INCLINATION_DEG:g}°: perto do equador magnético a RTP "
            f"amplifica uma faixa de números de onda sem limite, na direção da "
            f"declinação. Compare com o sinal analítico, que não depende da "
            f"direção de magnetização." if unstable else ""),
        "border": border_provenance,
    }


def radial_spectrum(
    values: np.ndarray, pixel: tuple[float, float], *, bins: int = 40, **border,
) -> dict[str, Any]:
    """O espectro de potência radialmente promediado. MSP-14.

    returns  {"wavenumber", "log_power", "bins"} — listas, para o manifesto

    **É um diagnóstico, e nada aqui o transforma em interpretação.** A
    inclinação de um trecho reto do log-espectro relaciona-se com uma
    profundidade média de fontes (Spector & Grant, 1970), mas *qual* trecho é
    reto é uma leitura humana, e escolher os trechos automaticamente é
    exatamente o que o §23 proíbe. Por isso este devolve a curva e nenhum
    número de profundidade.
    """
    padded = spectral.pad(values, **border)
    kx, ky, k = spectral.wavenumbers(padded.values.shape, pixel)
    power = np.abs(np.fft.fft2(padded.values)) ** 2

    flat_k = k.ravel()
    flat_power = power.ravel()
    keep = flat_k > 0
    flat_k, flat_power = flat_k[keep], flat_power[keep]
    if flat_k.size == 0:
        return {"wavenumber": [], "log_power": [], "bins": 0,
                "note": "a grade não tem número de onda diferente de zero"}

    edges = np.linspace(flat_k.min(), flat_k.max(), int(bins) + 1)
    index = np.clip(np.digitize(flat_k, edges) - 1, 0, int(bins) - 1)
    total = np.bincount(index, weights=flat_power, minlength=int(bins))
    count = np.bincount(index, minlength=int(bins))
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_power = np.where(count > 0, total / np.maximum(count, 1), np.nan)
        log_power = np.log(mean_power)
    centres = 0.5 * (edges[:-1] + edges[1:])
    ok = np.isfinite(log_power)
    return {
        "wavenumber": centres[ok].tolist(),
        "log_power": log_power[ok].tolist(),
        "bins": int(ok.sum()),
        "unit": "wavenumber em rad por unidade de comprimento; potência em log",
        "boundary": ("diagnóstico espectral; a inclinação de um trecho reto "
                     "relaciona-se com profundidade média de fontes (Spector & "
                     "Grant, 1970) e escolher o trecho é leitura humana"),
        "border": padded.provenance,
    }
