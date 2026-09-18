# M5 — Geothermal Decision Engine

Status: `PASS`
Entry gate: `OPEN` — M4 verde, 18/18
Exit gate: `PASS` — 20/20, `../validation/V-M5-decision-engine.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §20 M5, MSP-06, MSP-07,
MSP-08, §9.5, §9.6, §15, §15.1, §16

## Objetivo

**Produzir um mapa de prospectividade que alguém possa defender.** O M3 disse
se o dado serve; o M4 mostrou-o. O M5 transforma dados em decisão — e a
diferença entre um resultado e um número plausível está inteiramente nas
recusas.

O gate é um fluxo, não uma lista:

```
dados → QA/QC → harmonização → membership → AHP/pesos → MCDA → prospectividade
```

Três frases do documento governam o milestone:

- §16: **"Nunca use valores silenciosos."** Todo default é documentado,
  editável, visível e versionado.
- MSP-08: **"Não aceite AHP inconsistente de forma silenciosa."** `CR` acima do
  limite bloqueia ou exige justificativa registrada.
- §15.1: evidências correlacionadas **não recebem pesos independentes** sem
  aviso, grupo hierárquico ou justificativa registrada.

## Escopo

Dentro:

| Item | O que significa aqui |
|---|---|
| harmonização | reprojetar, reamostrar e recortar cada camada para um `TargetGrid` comum — o motor do MSP-06 que o M3 deixou fora |
| membership | as seis funções sobre um critério do grid, como operador, com os anchors registrados |
| Membership Editor | §9.5: curva, histograma, preview espacial, unidade e sentido físico **ao mesmo tempo** |
| AHP | Saaty: autovetor principal, `lambda_max`, `CI`, `RI`, `CR` |
| consistency ratio | `CR >= 0.10` **bloqueia**; prosseguir exige justificativa gravada |
| Fuzzy Gamma / Product / Sum | Zimmermann e Zysno (1980) |
| combinação ponderada | WLC com restrições booleanas |
| máscaras | AOI e máscara comum de validade aplicadas a uma run |
| grupos | critérios em grupos hierárquicos, com pesos por grupo |
| alertas de correlação | §15.1: correlação calculada entre critérios normalizados, sinalizada acima do limiar |
| Decision Model | §9.6: grupos, critérios, pesos, AHP, CR, operadores, warnings, justificativas |
| storyboard | `tools/storyboards/m5.py`, o fluxo inteiro em sequência |

Fora (nomeado):

- cenários, sensibilidade, leave-one-out, explicabilidade, ranking — **M6**
- gravity, magnetics — **M7**
- hillshade — precisa de um DEM e de convenção de iluminação declarada; volta
  quando houver o operador que o produz
- vetores no canvas — carregado do M4; entra quando um critério vetorial
  precisar ser desenhado
- relatórios e exportação — **M6/M8**

## Gate M5

O §20 pede um fluxo completo. Cada seta é um check.

| # | Etapa | Como é provada |
|---|---|---|
| G1 | dados → QA/QC | os critérios reais passam pelas regras do M3 e são `usable` |
| G2 | QA/QC → harmonização | camadas em grids diferentes chegam a **um** `TargetGrid`, e a diferença entre elas passa a ser calculável |
| G3 | harmonização → membership | cada critério vira `NORMALIZED` em `[0,1]`, com anchors e unidade de origem no manifesto |
| G4 | membership → AHP/pesos | pesos de uma matriz recíproca, com `CR` reportado; `CR >= 0.10` recusado por nome |
| G5 | AHP/pesos → MCDA | Gamma, Product, Sum e WLC sobre a pilha normalizada, cada um batendo com cálculo independente |
| G6 | MCDA → prospectividade | um mapa em `[0,1]` com manifesto que o reproduz: entradas, hashes, grid, método, parâmetros, pesos e ordem dos critérios |

Recusas que o gate exige, cada uma nomeando o que corrigir:

| Recusa | Porque |
|---|---|
| agregar um critério `RAW` | a soma de mGal com g/cm³ não é nada |
| pesos que não somam 1 | a escala do resultado deixa de ser `[0,1]` |
| `CR >= 0.10` | uma matriz inconsistente não produz mapa sem override gravado |
| `n > 10` no `RI` de Saaty | a tabela é válida até 10; reutilizar 1.49 inventa consistência |
| critérios em grids diferentes | comparar pixels que não estão no mesmo lugar |
| gamma fora de `[0,1]` | fora do intervalo o operador não é uma média ponderada de AND e OR |
| grupo que casa menos camadas que o esperado | D-07 do legacy: vira uma run diferente com o mesmo nome |

## Invariantes que o M5 acrescenta

- **A ordem dos critérios é `CriterionStack.names`,** e a linha *i* da matriz
  AHP liga-se a `names[i]`. Derivar de `list(dict.keys())` em dois lugares é
  como o peso vai parar na camada errada (D-06).
- **Nenhum default silencioso.** Gamma, percentis de clamp, limiar de `CR` e
  limiar de correlação são parâmetros declarados, com valor no manifesto.
- **A agregação define onde todos os critérios são válidos**, e a regra de
  nulos é a mesma em todos os operadores. Dois operadores discordando sobre
  nulos é o defeito.
- **Correlação alta é um aviso com nome**, não um número num relatório: diz
  quais dois critérios, quanto, e o que fazer.
- **Uma justificativa de override é gravada como proveniência** com quem, o
  quê e o `CR` que foi aceito.

## Ordem de trabalho

1. `grid/harmonize.py`: reprojeção, reamostragem e recorte para um `TargetGrid`.
2. `decision/ahp.py`: Saaty, `CR`, e as recusas.
3. `decision/aggregate.py`: Gamma, Product, Sum, WLC, máscaras, grupos.
4. `decision/correlation.py`: dupla contagem (§15.1).
5. Operadores: `grid.harmonize`, `decision.ahp_weights`, `decision.aggregate`.
6. Membership Editor e Decision Model.
7. Storyboard `m5`, checks no `--self-test`, relatório e `PROJECT_STATE.md`.

Nenhum item avança com o gate do anterior vermelho.

## Fechamento

Fechado em `2026-09-01` com **20/20** no gate e **59/59** no `--self-test`,
estável em duas execuções. Evidência: `../validation/V-M5-decision-engine.md`;
storyboard em `../validation/images/m5/`.

As seis setas do fluxo G1–G6 estão verdes, e a agregação bate com um cálculo
independente em numpy **exatamente** (0.00e+00 sobre 90.000 pixels). As sete
recusas do plano existem e são testadas por nome.

**Três itens ficam registrados como não entregues**, em `PROJECT_STATE.md`:
editor de matriz de comparação (pertence ao M6), hillshade e critérios
vetoriais no canvas (carregados do M4, esperando um operador que os produza), e
presets nomeados do MSP-07 — as funções estão documentadas e seus parâmetros
gravados por run, mas não há preset reutilizável entre projetos.

O storyboard, construído no início deste milestone, encontrou três defeitos que
nada mais encontrou: o stretch recalculado por vista, a curva de pertinência
que não desenhava, e um check do self-test que dependia do histórico. Os três
estão descritos no relatório.
