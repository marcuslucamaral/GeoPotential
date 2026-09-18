# M5.6 — Gridding: dado esparso vira critério

Status: `PASS` em `2026-09-03`
Entry gate: `OPEN` — M5.5 verde, 30/30, `../validation/V-M5_5-interface.md`
Exit gate: `PASS` — 31/31, `../validation/V-M5_6-gridding.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-06 (Grid Engine),
§18.1 (estratégia de escalonamento), §16 (nunca um valor silencioso)

## Por que existe

O MSP-06 pede seis coisas do Grid Engine. O M5 entregou três e o registro de
operadores ainda promete as outras para um milestone que já fechou:

```
registrados: grid.difference, grid.harmonize
planejados : grid.idw -> "M5", grid.euclidean_distance -> "M5"
```

A consequência foi encontrada com dados reais, não por leitura de código:
**`grid.harmonize` só abre raster.** `harmonize()` chama `read_raster()` e a
aplicação filtra `kind != "raster"` antes de oferecer qualquer camada. Um CSV
importa, passa pela QA/QC, é desenhado como nuvem de pontos — e para aí.

Na prática, `../data/utah_forge/anomaly_bouger_easting_northin_bouger.csv`, uma
anomalia Bouguer com 3 735 pontos, **não consegue entrar na MCDA**. E o
`Distance_to_fault.tif` que o projeto usa como critério é o produto de uma
transformada de distância feita **fora** desta aplicação, porque o operador que
a faria não existe aqui.

Metade dos dados de um projeto real não atravessa o fluxo. Isso é anterior ao
M6: não adianta explicar um resultado que não pôde ser calculado.

## Objetivo

**Levar dado esparso — pontos e vetores — a uma grade de análise, com a grade
declarada e o custo estimado antes de qualquer alocação.**

O gate é uma frase: *um CSV de pontos em `../data/` vira um critério
`NORMALIZED` num mapa de prospectividade, e a pessoa escolheu o pixel, a área e
o método, sem que nada tenha sido assumido em silêncio.*

## Escopo

### Os três operadores

| Operador | Entrada | Interpola? | Para quê |
|---|---|---|---|
| `grid.idw` | pontos (CSV/XYZ, ou vetor de pontos) | **sim** | campo contínuo a partir de amostras esparsas — Shepard (1968) |
| `grid.euclidean_distance` | qualquer feição | **não** | distância até a feição mais próxima; é como se produz um `Distance_to_fault` |
| `grid.rasterize` | polígonos, linhas, pontos | **não** | queima o valor de um atributo nas células que a feição cobre |

Só `grid.idw` estima valor onde não se mediu. Os outros dois transferem para a
grade um fato que já existe, e chamá-los de interpolação seria errado.

### A grade é declarada, nunca inferida

Os três recebem a mesma especificação de grade, e é aqui que mora o pedido
explícito de controlar pixel e área:

| Parâmetro | Regra |
|---|---|
| `target_crs` | obrigatório. Não existe CRS padrão (ADR-004). |
| `pixel_size` | obrigatório, na unidade do CRS. Decide o que a análise inteira resolve. |
| `bounds` | **opcional**. Ausente, é a extensão do dado; presente, é a área escolhida — recortar a análise a uma região é uma decisão, e também é como se reduz o custo. |
| `bounds_crs` | opcional; o CRS em que `bounds` foi escrito, quando não for o alvo. |

Uma grade grande demais não é um problema a descobrir no meio da execução: o
`plan_operation` do M3 já existe e passa a ser consultado **antes de alocar**,
com `REFUSE` nomeando o que reduzir.

### Fora

- **Krigagem, mínima curvatura, spline.** O IDW é o método que o MSP-06 nomeia.
  Um segundo interpolador sem um caso que o exija é escopo que ninguém pediu.
- **Rasterização de atributo categórico com tabela de classes.** Queimar um
  valor numérico entra; o mapeamento classe → código é do editor de critérios.
- **Blocos em disco / memory mapping.** O `Policy.BLOCKED` do planner processa
  em janelas de linhas, que é o §18.1 na ordem que ele mesmo define: blocos e
  janelas antes de memory mapping.
- **Interface para os três.** Entram no fluxo pelo diálogo de harmonização, que
  passa a aceitar dado esparso. Telas próprias, se necessárias, são M6.

## Decisões que precisam estar registradas antes do código

### D1 — uma célula fora do raio é nula, nunca extrapolada

O IDW com raio de busca deixa `NaN` onde não há amostra suficiente. A
alternativa — usar o vizinho mais próximo por mais longe que esteja — preenche
o mapa inteiro e inventa dado onde não há levantamento. Um mapa com buraco diz
a verdade; um mapa cheio de extrapolação parece melhor e é pior.

`min_points` existe pela mesma razão: uma célula decidida por uma única amostra
distante é uma célula sem informação, com aparência de informação.

### D2 — raio e distância são operações métricas

Um raio em graus não é uma distância. `grid.idw` e `grid.euclidean_distance`
recusam CRS geográfico, como toda operação métrica neste projeto. `rasterize`
não mede nada e não precisa recusar — mas a grade que ele produz alimenta a
mesma análise, então a recusa vale para os três, por consistência e para que
nenhum critério chegue à agregação numa grade em graus.

### D3 — pixel anisotrópico é legal, inclusive na distância

`distance_transform_edt` aceita `sampling=(py, px)`. Colapsar os dois num
escalar seria silenciosamente errado em toda grade que não fosse quadrada.

## As etapas

### E1 — a especificação de grade, compartilhada

`grid/spec.py`: constrói um `TargetGrid` a partir de `target_crs`,
`pixel_size`, `bounds` opcional e a extensão do dado, consultando o planner.
Um lugar só decide o que é a grade, para que os três operadores não venham a
discordar sobre o que "pixel de 40 m sobre esta área" significa.

Aceitação:

- A1 Sem `bounds`, a grade cobre a extensão do dado; com `bounds`, cobre
  exatamente a área pedida, e a diferença aparece no manifesto.
- A2 `bounds` num CRS diferente do alvo é transformado, e o CRS em que foi
  escrito fica registrado.
- A3 Uma grade que não cabe na memória é **recusada antes de alocar**, com a
  mensagem dizendo o que reduzir — pixel, área ou ambos.
- A4 Pixel não positivo, `bounds` invertido ou degenerado são recusados por
  nome.

### E2 — `grid.idw`

`grid/idw.py` mais `operators/idw_op.py`. Shepard (1968), `w = 1/d^p`, com
`cKDTree` para a busca de vizinhos. **Sem laço Python por pixel**: a árvore é
consultada para todas as células de um bloco de uma vez.

Aceitação:

- A5 Numa célula que coincide com uma amostra, o resultado é o valor da
  amostra, exatamente.
- A6 Com `power` alto o campo tende ao vizinho mais próximo; com `power`
  baixo, à média — verificado numericamente, não por inspeção.
- A7 Célula sem amostra dentro do raio é `NaN`; com menos de `min_points`
  também.
- A8 O resultado fica dentro do intervalo das amostras usadas: IDW é uma média
  ponderada e não pode extrapolar acima do máximo nem abaixo do mínimo.
- A9 CRS geográfico é recusado por nome.
- A10 Nenhum laço no caminho de cálculo itera sobre pixels ou sobre pontos.

### E3 — `grid.euclidean_distance`

`grid/distance.py` mais o operador. `distance_transform_edt` sobre a máscara
das feições, com `sampling` da resolução real.

Aceitação:

- A11 A distância numa célula que contém a feição é zero.
- A12 Contra um caso analítico — um ponto único numa grade — a distância bate
  com `hypot` dentro da tolerância declarada antes da execução.
- A13 Pixel anisotrópico dá a distância certa; a média dos dois lados dá a
  errada, e o teste distingue os dois.
- A14 `max_distance`, quando dado, corta em `NaN` acima dele, e o corte é
  registrado no manifesto.

### E4 — `grid.rasterize`

`grid/rasterize.py` mais o operador, sobre `rasterio.features`.

Aceitação:

- A15 Um polígono com valor conhecido produz exatamente aquele valor dentro
  dele e `NaN` fora.
- A16 `all_touched` muda o resultado nas bordas, e a escolha é registrada.
- A17 Um campo de atributo ausente é recusado nomeando as colunas que existem.

### E5 — o fluxo aceita dado esparso

`harmonizableDatasets` deixa de filtrar por raster: passa a oferecer também
tabelas e vetores, dizendo **como** cada um chega à grade. O diálogo escolhe o
método por tipo de dado e nomeia o que vai acontecer.

Aceitação:

- A18 Um CSV de `../data/utah_forge/` chega ao mapa de prospectividade pelo
  fluxo da interface, sem argumento de linha de comando.
- A19 O manifesto da run registra o método, o raio, a potência, o pixel e a
  área — o suficiente para reproduzir a grade.

### E6 — evidência e fechamento

Storyboard, relatório de validação, `PROJECT_STATE`, `README`, e o registro de
operadores sem promessas para milestones fechados.

## Gate M5.6

| # | O que prova | Como |
|---|---|---|
| G1 | A grade é escolhida | pixel e área declarados aparecem no manifesto; nada é inferido em silêncio |
| G2 | O custo é estimado antes de alocar | uma grade grande demais é recusada, e a mensagem diz o que reduzir |
| G3 | O IDW é o IDW | caso analítico, comportamento com a potência, limites do intervalo |
| G4 | O que não interpola, não interpola | distância e rasterização batem com cálculo independente |
| G5 | Sem laço por pixel | verificado pelo que cada laço itera, como em `points` e `geometry` |
| G6 | Dado esparso vira critério | um CSV real percorre o fluxo até a prospectividade |
| G7 | Nada regrediu | 30/30 anteriores verdes |

## Contratos protegidos que este milestone acrescenta

| ID | Contrato |
|---|---|
| P-146 | A grade de saída é declarada — CRS, pixel e área — e registrada no manifesto |
| P-147 | Uma grade que não cabe é recusada antes de alocar, nomeando o que reduzir |
| P-148 | IDW não extrapola: o resultado fica dentro do intervalo das amostras usadas |
| P-149 | Célula sem amostra suficiente no raio é nula, nunca preenchida |
| P-150 | Raio e distância são recusados em CRS geográfico |
| P-151 | A distância euclidiana respeita pixel anisotrópico |
| P-152 | Rasterizar transfere um valor existente e nunca estima um |
| P-153 | Nenhum laço Python itera pixels ou pontos no caminho de gridding |

## Ordem de trabalho

E1 → E2 → E3 → E4 → E5 → E6, com o gate completo ao fim de cada etapa e parada
na primeira regressão.
