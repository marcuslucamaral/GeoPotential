"""Filtros no domínio do número de onda, com a borda declarada. FIS-02, FIS-03.

inputs   uma grade regular, o pixel em unidade de comprimento, e um filtro
output   a grade filtrada, no mesmo tamanho e na mesma posição
unit     a do campo; um filtro linear não a muda, e uma derivada divide pela
         unidade de comprimento
reference  Blakely, R. J. (1995), "Potential Theory in Gravity and Magnetic
           Applications", §12: os operadores no domínio de Fourier.

## A convenção, uma vez (FIS-02)

    kx = 2π · fx,  ky = 2π · fy,  |k| = sqrt(kx² + ky²)

com `fx`, `fy` as frequências de `numpy.fft.fftfreq` sobre o pixel. Daí:

    ∂/∂x      ->  i · kx
    ∂/∂y      ->  i · ky
    ∂/∂z      ->  |k|          z **para baixo**
    cont. ^h  ->  exp(-|k| h)  h **para cima**, h > 0

`∂/∂z` ser `+|k|` e não `-|k|` é a convenção inteira num sinal: com z para
baixo, aproximar-se da fonte aumenta a anomalia. O módulo `synthetic.py` tem o
caso fechado que decide isso, e o gate FIS-01 o executa em vez de acreditar
neste parágrafo.

## A borda, sempre declarada (FIS-03)

Uma FFT assume periodicidade. Um campo que não fecha nas bordas — e nenhum
fecha — produz ringing e um degrau na emenda. Então:

1. **padding por reflexão**, que faz o campo encontrar-se consigo mesmo com
   derivada contínua, em vez de com zero;
2. **taper de cosseno** sobre a região refletida, para a transição não
   introduzir a sua própria borda;
3. **recorte** de volta ao tamanho original.

Os quatro números — modo, largura, fração do taper, tamanho estendido — vão
para o manifesto de toda execução. Um filtro espectral cujo padding não foi
registrado não é reproduzível, e a diferença entre 10 % e 50 % de extensão é
visível no resultado.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

#: Quanto a grade cresce em cada lado, como fração do lado original. 0.25 é o
#: usual na literatura de campos potenciais e é o suficiente para |k| pequeno
#: (continuação alta) não enxergar a emenda. É um parâmetro porque é uma
#: escolha, e ela vai para o manifesto.
DEFAULT_PAD_FRACTION = 0.25

#: Que fração da região refletida recebe o cosseno. 1.0 suaviza toda ela.
DEFAULT_TAPER = 1.0


class Padded:
    """Uma grade estendida, mais o que é preciso para desfazer a extensão."""

    def __init__(self, values: np.ndarray, pad_y: int, pad_x: int,
                 shape: tuple[int, int], provenance: dict[str, Any]) -> None:
        self.values = values
        self.pad_y = pad_y
        self.pad_x = pad_x
        self.shape = shape
        self.provenance = provenance

    def crop(self, values: np.ndarray) -> np.ndarray:
        """De volta ao tamanho e à posição originais."""
        height, width = self.shape
        return values[self.pad_y:self.pad_y + height,
                      self.pad_x:self.pad_x + width]


def pad(
    values: np.ndarray,
    *,
    fraction: float = DEFAULT_PAD_FRACTION,
    taper: float = DEFAULT_TAPER,
) -> Padded:
    """Estende a grade por reflexão e suaviza a região estendida.

    values    (h, w); NaN é preenchido pela média antes de refletir, porque
              uma FFT não tem o que fazer com um nulo — e isso é dito na
              procedência em vez de acontecer em silêncio
    fraction  quanto crescer de cada lado, como fração do lado
    taper     fração da região refletida que recebe o cosseno
    returns   Padded
    """
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"a grade tem de ser 2D; recebi shape {values.shape}")
    if not (0.0 <= fraction <= 2.0):
        raise ValueError(
            f"fraction={fraction}: fora de [0, 2]. Estender mais que o dobro "
            f"do lado não melhora a borda e multiplica o custo da FFT."
        )
    if not (0.0 <= taper <= 1.0):
        raise ValueError(f"taper={taper}: é uma fração da região refletida")

    height, width = values.shape
    finite = np.isfinite(values)
    filled_count = int((~finite).sum())
    if filled_count == values.size:
        raise ValueError("a grade não tem nenhum valor finito para filtrar")
    filled = values.copy()
    if filled_count:
        # A média, e não zero: um zero no meio de um campo de 30 mGal é um
        # degrau, e um degrau é exatamente o que a FFT transforma em ringing.
        filled[~finite] = float(values[finite].mean())

    pad_y = int(round(height * fraction))
    pad_x = int(round(width * fraction))
    extended = np.pad(filled, ((pad_y, pad_y), (pad_x, pad_x)), mode="reflect") \
        if (pad_y or pad_x) else filled.copy()

    if (pad_y or pad_x) and taper > 0:
        extended = _taper_edges(extended, pad_y, pad_x, taper,
                                _border_level(filled))

    provenance = {
        "mode": "reflect",
        "pad_fraction": float(fraction),
        "pad_cells": [pad_y, pad_x],
        "taper": float(taper),
        "taper_window": "cosine (Hann half-window over the reflected region)",
        "original_shape": [height, width],
        "extended_shape": list(extended.shape),
        "nulls_filled_with_mean": filled_count,
    }
    return Padded(extended, pad_y, pad_x, (height, width), provenance)


def _border_level(values: np.ndarray) -> float:
    """O nível para o qual a região refletida decai: a **borda**, não a média.

    Medido, não suposto. Na esfera sintética de referência o campo vale ~0,17
    na borda e ~3,5 de média, porque a anomalia é toda positiva e concentrada.
    Levar a região refletida à média constrói um degrau de 0,17 para 3,5 logo
    fora do dado — e o erro na borda da derivada vertical passa de 1,8e-4
    (padding sem taper) para 5,7e-4 (padding com taper para a média). Contra a
    borda, cai para o valor registrado em `docs/validation/V-M7-*`.

    O taper existe para a emenda não introduzir a sua própria borda. Um taper
    que decai para o lugar errado introduz exatamente isso.
    """
    ring = np.concatenate([values[0, :], values[-1, :],
                           values[:, 0], values[:, -1]])
    return float(ring.mean())


def _taper_edges(values: np.ndarray, pad_y: int, pad_x: int, taper: float,
                 level: float) -> np.ndarray:
    """Leva a região refletida ao nível médio com meia janela de cosseno.

    Vetorizado: uma janela 1D por eixo, aplicada por produto externo. Um laço
    por célula aqui seria a mesma coisa 10⁶ vezes mais devagar (ADR-007).
    """
    height, width = values.shape

    def window(size: int, margin: int) -> np.ndarray:
        w = np.ones(size, dtype=np.float64)
        ramp = int(round(margin * taper))
        if ramp <= 0:
            return w
        # Meia janela de Hann: 0 na ponta, 1 onde o dado original começa.
        edge = 0.5 * (1.0 - np.cos(np.pi * np.arange(ramp) / ramp))
        w[:ramp] = edge
        w[-ramp:] = edge[::-1]
        return w

    wy = window(height, pad_y)[:, None]
    wx = window(width, pad_x)[None, :]
    weight = wy * wx
    return level + (values - level) * weight


def wavenumbers(shape: tuple[int, int], pixel: tuple[float, float]):
    """(kx, ky, |k|) para uma grade, em radianos por unidade de comprimento.

    pixel  (px, py), os dois positivos e **não** promediados: um pixel
           anisotrópico é legal, e `0.5*(px+py)` está errado em toda grade
           que não é quadrada.
    """
    height, width = shape
    px, py = float(pixel[0]), float(pixel[1])
    if px <= 0 or py <= 0:
        raise ValueError(f"o pixel tem de ser positivo nos dois eixos; ({px}, {py})")
    kx = 2.0 * np.pi * np.fft.fftfreq(width, d=px)[None, :]
    ky = 2.0 * np.pi * np.fft.fftfreq(height, d=py)[:, None]
    magnitude = np.sqrt(kx ** 2 + ky ** 2)
    return kx, ky, magnitude


def apply_filter(
    values: np.ndarray,
    pixel: tuple[float, float],
    response: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
    *,
    fraction: float = DEFAULT_PAD_FRACTION,
    taper: float = DEFAULT_TAPER,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Aplica um filtro no domínio do número de onda e recorta de volta.

    response  f(kx, ky, |k|) -> a resposta complexa, do tamanho estendido
    returns   (grade filtrada, procedência da borda)

    A parte imaginária é descartada **depois** de verificada: um filtro cuja
    resposta não é hermitiana devolve um campo complexo, e engolir isso com
    `.real` esconde um erro de convenção em vez de mostrá-lo.
    """
    padded = pad(values, fraction=fraction, taper=taper)
    kx, ky, magnitude = wavenumbers(padded.values.shape, pixel)
    spectrum = np.fft.fft2(padded.values)
    filtered = np.fft.ifft2(spectrum * response(kx, ky, magnitude))

    residual = float(np.abs(filtered.imag).max())
    scale = float(np.abs(filtered.real).max()) or 1.0
    if residual / scale > 1e-6:
        raise ValueError(
            f"a resposta deste filtro não é hermitiana: sobrou uma parte "
            f"imaginária de {residual:.3g} contra {scale:.3g} de parte real. "
            f"Descartá-la esconderia um erro de convenção."
        )

    out = padded.crop(filtered.real)
    # O nulo do dado de entrada continua nulo na saída: a FFT preencheu a
    # lacuna para poder rodar, e o resultado ali é interpolação da própria
    # média, não medida.
    out = np.where(np.isfinite(np.asarray(values, dtype=np.float64)), out, np.nan)
    return out.astype(np.float32), padded.provenance
