# V-M7 — Potential Fields Essentials

Data: `2026-09-04`
Versão: app `0.7.00`, worker `0.4.00`, protocolo `1.0.0`, schema `1.3.0`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-14, MSP-15, §9.4, §23

## Resultado

`PASS`.

| Item | Valor |
|---|---|
| Gate | **34 de 34** |
| Testes | **795** unit/contract/integration + 59 checagens de interface |
| Storyboards | **10**, **49 quadros**; `potential_fields` é o novo, com 4 |
| Operadores | **26 registrados** (eram 18); `PLANNED` caiu para **um** |
| Suíte nova | `--only potential-fields`, 53 testes |

## A ordem que a norma manda, e por quê

> *Implemente primeiro a suíte sintética. Somente depois implemente a
> interface final.* — M7

Foi feito nessa ordem, e a razão apareceu em execução, não em teoria: **dois
defeitos reais foram encontrados pela suíte, e nenhum deles seria visto por um
filtro comparado consigo mesmo.**

## Os oito gates FIS

| Gate | Como foi cumprido |
|---|---|
| **FIS-01** caso conhecido | A esfera enterrada (Blakely §3.1): `gz = A·d/(x²+y²+d²)^1,5`, com as três derivadas em forma fechada. Geometria, parâmetros e resultado documentados em `synthetic.py`. Sobre a fonte o fechado colapsa para `A/d²` e `2A/d³`, conferíveis de cabeça. |
| **FIS-02** convenção | `z positivo para baixo`, `h positivo para cima`, `x` leste e `y` norte, a unidade por transformação, linha 0 no norte. Declaradas em `synthetic.conventions()`, **viajam em todo manifesto**, e aparecem na tela. |
| **FIS-03** borda | Reflexão + taper de cosseno + recorte. Modo, fração, células, taper e os dois tamanhos vão para o manifesto de toda execução. |
| **FIS-04** independência | Cada operador é medido contra a **forma fechada**, nunca contra outra FFT. A continuação para cima tem o caso exato: para uma fonte pontual, subir o observador é a mesma fórmula com a fonte mais funda. |
| **FIS-05** tolerância | Quatro constantes no topo da suíte, com a razão de cada uma. Nenhuma por caso de teste — uma tolerância por teste é uma tolerância ajustada depois. |
| **FIS-06** regressão | Mesma entrada, mesma saída, verificado; a procedência viaja com o resultado; trocar o padding muda o resultado, o que é o que torna registrá-lo útil. |
| **FIS-07** paridade Python/C++ | **Não se aplica**: não há implementação em C++, e ADR-007 mantém o backend em Python até uma medição pedir outra coisa. Registrado como não aplicável em vez de dado como cumprido. |
| **FIS-08** visual | Storyboard `potential_fields`, 4 quadros, com o resultado no canvas ao lado do original. |

## Os dois defeitos que a suíte pegou

### 1. O taper decaía para o nível errado

O taper leva a região refletida a um nível constante. Ele levava à **média** da
grade. Na esfera de referência o campo vale ~0,17 na borda e ~3,5 de média,
porque a anomalia é toda positiva e concentrada — então o taper construía um
degrau de 0,17 para 3,5 logo fora do dado, que é exatamente a borda que ele
existe para evitar.

Medido, na derivada vertical:

| | erro máximo na borda |
|---|---|
| sem padding | 3,13e-4 |
| padding sem taper | 1,85e-4 |
| padding + taper **para a média** | **5,74e-4** — pior que não ter |
| padding + taper **para a borda** | **1,56e-4** — o melhor dos quatro |

O teste que pegou é `test_padding_reduces_the_error_at_the_edge`, que afirma
a razão de o padding existir em vez de assumi-la.

### 2. O coeficiente de Nyquist, só em grade de lado par

`fftfreq` põe a frequência de Nyquist numa única posição, negativa, sem a
positiva correspondente. Um multiplicador ímpar em `k` — toda derivada
horizontal de ordem ímpar — **deixa de ser hermitiano exatamente ali**, e a
inversa sai com parte imaginária concentrada naquela linha e naquela coluna.

A suíte sintética roda numa grade 201 × 201, **ímpar**, e passava. Foi o campo
real de 4096 × 4096 que acendeu a checagem de hermitianidade em
`spectral.apply_filter` — a checagem que existe justamente porque descartar a
parte imaginária com `.real` esconderia um erro de convenção em vez de
mostrá-lo.

Corrigido zerando o coeficiente de Nyquist do eixo derivado, que é o
tratamento padrão. `TheNyquistCoefficient` é a grade par que faltava na suíte.

## O que foi entregue

| | |
|---|---|
| `potential_fields/synthetic.py` | a esfera, as suas derivadas e a continuação, todas em forma fechada |
| `potential_fields/spectral.py` | padding, taper, números de onda, e a checagem de hermitianidade |
| `potential_fields/filters.py` | derivadas, THG, sinal analítico, tilt, continuação, regional/residual, RTP, espectro radial |
| 8 operadores | `potential_fields.*`, com convenção e borda em todo manifesto |
| `PotentialFieldsDialog.qml` | a bancada do §9.4, com os sete requisitos |

## O que a bancada cumpre, do §9.4

| Requisito | Onde |
|---|---|
| selecionar operador | seletor com os sete, e o que cada um faz numa linha |
| definir parâmetros | trocar de operador esconde o que ele não aceita — verificado no quadro 2 |
| comparar original/processado | o resultado entra como camada; o original continua na pilha (1 → 2 camadas, quadro 3) |
| registrar convenções | bloco sempre visível, 275 caracteres, quadro 2 |
| visualizar warnings | RTP em I = 5° acende o alerta **antes** de executar, quadro 4 |
| executar | quadro 3: run commitada, 1 artefato |
| reproduzir | o manifesto traz convenção, borda (`reflect`) e parâmetros |

## Contratos novos

| ID | Contrato | Gate |
|---|---|---|
| P-175 | Um operador de campos potenciais é medido contra a forma fechada, nunca contra outra FFT | `--only potential-fields` |
| P-176 | A convenção — sinal, altura, eixo, unidade, orientação — viaja em todo manifesto e aparece na tela | `--only potential-fields`, storyboard |
| P-177 | Modo, fração, taper e tamanhos da borda vão para todo manifesto | `--only potential-fields`, storyboard |
| P-178 | Uma resposta não hermitiana é recusada, nunca convertida com `.real` | `--only potential-fields` |
| P-179 | Um nulo da entrada continua nulo na saída: a FFT preencheu para poder rodar | `--only potential-fields` |
| P-180 | A continuação para baixo é recusada por nome | `--only potential-fields` |
| P-181 | Um CRS geográfico é recusado: em graus, `\|k\|` não é número de onda | `--only potential-fields` |
| P-182 | A RTP em baixa inclinação avisa antes de executar, e diz o que usar no lugar | `--only potential-fields`, storyboard |
| P-183 | Uma derivada é rotulada por unidade de comprimento; o tilt, em radianos | `--only potential-fields`, storyboard |
| P-184 | O espectro radial devolve a curva e nenhuma profundidade (§23) | `--only potential-fields` |

## O que este milestone NÃO entrega

- **Ingestão de line data e de XYZ com histórico de reduções.** MSP-14 pede;
  o que existe é o caminho de grid. Um levantamento aerogeofísico chega em
  linhas, e a direção de linha, o espaçamento e o histórico de reduções são
  metadados que a QA/QC ainda não lê.
- **IGRF.** MSP-15 o condiciona a metadados de data, posição, altitude e
  unidade que a aplicação ainda não coleta. Executá-lo sem eles seria inventar
  o campo de referência.
- **RTE (redução ao equador).** A RTP está; a RTE é o caso de baixa latitude
  e precisa da mesma decisão sobre estabilidade, tomada explicitamente.
- **Extração de lineamentos.** MSP-15 pede extração determinística **com
  edição e confirmação humana**. Sem as duas últimas, a primeira é
  interpretação automática, que é o que o §23 proíbe.
- **Minimum curvature.** MSP-14 a condiciona a validação; o gridding do M5.6
  entrega IDW e os dois triangulados.
- **Comparação lado a lado na tela.** O resultado entra como camada ao lado do
  original, e a vista dividida do M4 existe; ligá-las num modo de comparação
  dedicado não foi feito.
- **FIS-07, paridade Python/C++.** Não há C++, por ADR-007. Não aplicável.
- **O espectro radial não tem tela.** O operador existe, é read-only e é
  testado; desenhar a curva é uma tela que não foi feita.
