"""Anomalias sintéticas com resultado fechado. FIS-01, FIS-04.

inputs   a geometria da fonte e a grade de observação
output   o campo, **e as suas derivadas**, os dois em forma fechada
unit     mGal para gravimetria; a escala é declarada e não inventada
reference  Blakely, R. J. (1995), "Potential Theory in Gravity and Magnetic
           Applications", Cambridge University Press, §3.1 (esfera) e §12
           (filtros no domínio do número de onda).

**Por que este módulo existe antes de qualquer filtro.** O M7 manda
implementar a suíte sintética primeiro, e a razão é a que o FIS-04 enuncia:
um filtro espectral comparado apenas consigo mesmo passa em qualquer sinal
convencionado errado. Aqui a resposta certa é conhecida em cada célula, e
conhecida **analiticamente**, então cada operador é medido contra ela e não
contra outra execução do mesmo código.

## A convenção, declarada (FIS-02)

- **z é positivo para baixo.** A fonte está em `depth > 0` abaixo do plano de
  observação, que é `z = 0`.
- **`h` é altura, positiva para cima.** Continuar para cima por `h` é observar
  em `z = -h`, o que para uma fonte pontual é a mesma fórmula com
  `depth -> depth + h`. É isso que torna a continuação para cima verificável
  em forma fechada, e não por comparação com outra FFT.
- **A derivada vertical é `d/dz`, com z para baixo.** Ela é o negativo da
  derivada em relação à altura: aproximar-se da fonte aumenta a anomalia.
- **Unidade:** o campo é devolvido em mGal quando `scale` diz mGal. A massa e
  G não são fixados aqui — a amplitude é um parâmetro, porque o que os gates
  medem é a **forma** e a **derivada**, não a constante gravitacional.

## O caso conhecido

A esfera enterrada, cujo efeito vertical no plano é o de uma massa pontual no
seu centro (Blakely §3.1):

    gz(x, y) = A · d / (x² + y² + d²)^(3/2)

com `d` a profundidade do centro e `A` a amplitude. As derivadas saem por
diferenciação direta e estão abaixo, cada uma verificada no ponto sobre a
fonte, onde a álgebra colapsa e o resultado é conferível de cabeça.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def observation_grid(
    half_width: float, spacing: float
) -> tuple[np.ndarray, np.ndarray]:
    """Um plano de observação quadrado, centrado na origem.

    half_width  metade do lado, na unidade do CRS
    spacing     o passo da grade
    returns     (x, y), cada um (n, n), com a fonte em (0, 0)
    """
    axis = np.arange(-half_width, half_width + spacing, spacing, dtype=np.float64)
    return np.meshgrid(axis, axis)


def sphere(
    x: np.ndarray,
    y: np.ndarray,
    *,
    depth: float,
    amplitude: float = 1.0,
    east: float = 0.0,
    north: float = 0.0,
) -> np.ndarray:
    """O efeito vertical de uma esfera enterrada. Blakely §3.1.

    depth      profundidade do centro, positiva para baixo
    amplitude  A na fórmula; a escala física é do chamador
    east/north deslocamento do centro no plano
    returns    (h, w) float64
    """
    if depth <= 0:
        raise ValueError(
            f"a fonte tem de estar abaixo do plano de observação; depth={depth}. "
            f"Uma esfera em z <= 0 não é uma anomalia, é uma singularidade "
            f"no dado."
        )
    r2 = (x - east) ** 2 + (y - north) ** 2 + depth ** 2
    return amplitude * depth / r2 ** 1.5


def sphere_derivatives(
    x: np.ndarray,
    y: np.ndarray,
    *,
    depth: float,
    amplitude: float = 1.0,
    east: float = 0.0,
    north: float = 0.0,
) -> dict[str, np.ndarray]:
    """As três derivadas primeiras, em forma fechada.

    returns  {"dx", "dy", "dz"}; `dz` é d/dz com **z para baixo**

    Verificação de sanidade, no ponto sobre a fonte (x = y = 0), onde
    `r = depth`:

        gz   = A / d²
        dz   = A · (3d² - d²) / d⁵ ... não: veja abaixo
        dx   = dy = 0            por simetria

    `dz` sobre a fonte vale `2A / d³`: aproximar-se da fonte por uma unidade
    aumenta a anomalia, e o sinal positivo é o que diz que z aponta para
    baixo. Um operador espectral que devolva `-2A/d³` está com o eixo
    invertido, e é exatamente isso que o FIS-02 existe para pegar.
    """
    dx_ = x - east
    dy_ = y - north
    r2 = dx_ ** 2 + dy_ ** 2 + depth ** 2
    r5 = r2 ** 2.5
    return {
        # d/dx de A·d·r^-3
        "dx": -3.0 * amplitude * depth * dx_ / r5,
        "dy": -3.0 * amplitude * depth * dy_ / r5,
        # d/dz com z para baixo = -d/dh. Sobre a fonte: A(3d²-d²)/d⁵ = 2A/d³.
        "dz": amplitude * (3.0 * depth ** 2 - r2) / r5,
    }


def sphere_continued(
    x: np.ndarray,
    y: np.ndarray,
    *,
    depth: float,
    height: float,
    amplitude: float = 1.0,
    east: float = 0.0,
    north: float = 0.0,
) -> np.ndarray:
    """A mesma esfera, observada `height` acima do plano original.

    Para uma fonte pontual, subir o observador é o mesmo que afundar a fonte:
    a resposta é a fórmula com `depth + height`. É por isso que a continuação
    para cima tem aqui um caso conhecido exato, e não uma comparação de uma
    FFT com outra.
    """
    if height < 0:
        raise ValueError(
            f"height={height}: continuar para *baixo* amplifica ruído sem "
            f"limite e não é o que este caso conhecido cobre."
        )
    return sphere(x, y, depth=depth + height, amplitude=amplitude,
                  east=east, north=north)


def conventions() -> dict[str, Any]:
    """O que o FIS-02 manda declarar, num objeto que vai para o manifesto."""
    return {
        "sign": "z positivo para baixo; a derivada vertical cresce ao "
                "aproximar-se da fonte",
        "height": "h positivo para cima; continuar para cima usa exp(-|k| h)",
        "axis": "x para leste, y para norte, na unidade do CRS da grade",
        "unit": "a do campo de entrada; um filtro linear não muda a unidade, "
                "e uma derivada divide pela unidade de comprimento",
        "orientation": "linha 0 é o topo da grade (norte), como o GeoTIFF",
        "reference": "Blakely (1995), Potential Theory in Gravity and Magnetic "
                     "Applications, sections 3.1 and 12",
    }
