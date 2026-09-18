# M3 — Data Manager e QA/QC

Status: `PASS`
Entry gate: `OPEN` — M2 verde, 11/11
Exit gate: `PASS` — 15/15, `../validation/V-M3-data-manager-qc.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §20 M3, MSP-03, MSP-04,
MSP-06, §9.1, §9.2, §9.3, §33

## Objetivo

**Nenhum dado entra no projeto sem diagnóstico.** O M1 provou que uma run
funciona; o M2 provou que ela sobrevive a um crash. O M3 responde à pergunta
anterior a ambos: *este dado pode ser usado?* — e responde antes de o dado
entrar, com uma mensagem que diz o que corrigir.

A frase do §9.2 é o critério: **"Não adicione dado inválido ao projeto sem
apresentar diagnóstico."** E a do MSP-04: **"Não reduza QA/QC a warning
genérico."** Um `warning: check your data` é exatamente a falha que este
milestone existe para não cometer.

## Escopo

Dentro:

| Item | O que significa aqui |
|---|---|
| leitura de 6 formatos | CSV, XYZ, GeoTIFF, COG, GeoPackage, Shapefile (MSP-03) |
| descrição sem importar | formato, CRS, unidade, campos, NoData, extensão, estatísticas — lidos **antes** de o dataset entrar no projeto |
| QA/QC espacial | os 14 itens do MSP-04, cada um com severidade e mensagem acionável |
| severidade | `BLOCKER` impede a operação; `WARNING` exige ciência; `INFO` é contexto. Nunca um nível só. |
| grid planner | estimativa de RAM e disco **antes** de uma operação cara (MSP-06) |
| Import Wizard | a tela do §9.2: detectar, mostrar, deixar corrigir, e só então importar |
| Data Inspector | a tela do §9.3: metadados, estatísticas, histograma, cobertura, qualidade, histórico |
| Project Hub | as superfícies do §9.1, carregadas do M2: criar, abrir, recuperar, duplicar, relinkar, recentes |
| datasets defeituosos | derivados de `../data/`, semeados, em `../data/synthetic/msp/broken/` |
| audit trail | toda validação vira `ValidationResult` no Project Store, com o veredicto e quem o produziu |

Fora (nomeado para que a ausência seja escolha):

- reprojeção, resampling, rasterização, IDW, distância — o **motor** do MSP-06
  é M5; o M3 entrega o *planejador* e os contratos
- LOD, tiles, overviews, pan, zoom, AOI — **M4**
- AHP, Fuzzy, WLC — **M5**
- cenários, sensibilidade, ranking — **M6**
- gravity, magnetics — **M7**
- empacotamento — **M8**

## Gate M3

As cinco exigências do §20, cada uma um check executável.

| # | Exigência | Como é provado |
|---|---|---|
| G1 | detectar erros | cada dataset defeituoso derivado produz o achado que lhe corresponde, e não outro |
| G2 | explicar erros | toda mensagem nomeia o dataset, o campo e o que corrigir; um teste rejeita mensagem genérica |
| G3 | permitir correção | um CRS ausente pode ser declarado no wizard e a validação passa a verde sem reimportar |
| G4 | impedir operação inválida | um `BLOCKER` impede o import e impede a submissão de job; testado nos dois caminhos |
| G5 | preservar audit trail | todo veredicto vira `ValidationResult` no store, com dataset, regra, severidade e hora |

## Os defeitos que os fixtures encenam

Derivados, não baixados: `tools/make_broken_fixtures.py`, semeado, escrevendo
em `../data/synthetic/msp/broken/`. Derivar mantém o gate reprodutível e
mantém `../data/` como o único diretório de dados.

| Fixture | Defeito | Severidade esperada |
|---|---|---|
| `no_crs.tif` | nenhum CRS declarado | `BLOCKER` |
| `geographic.tif` | CRS geográfico onde se pede métrica | `BLOCKER` na operação métrica |
| `nodata_undeclared.tif` | array com sentinela `-9999`, `nodata=None` | `BLOCKER` |
| `nodata_is_nan_undeclared.tif` | array com NaN, `nodata=None` | `BLOCKER` |
| `all_null.tif` | todo pixel nulo | `BLOCKER` |
| `non_finite.tif` | `+inf` e `-inf` entre os válidos | `BLOCKER` |
| `anisotropic.tif` | pixel 30 × 10 m | `WARNING` |
| `disjoint.tif` | extensão que não intersecta as demais | `BLOCKER` na harmonização |
| `coarse.tif` | 100 m contra 10 m das demais | `WARNING` |
| `mostly_empty.tif` | 4 % de cobertura válida | `WARNING` |
| `duplicated_points.csv` | coordenadas repetidas com valores diferentes | `WARNING` |
| `gapped_points.csv` | grande vazio amostral no interior | `WARNING` |
| `no_source_crs.csv` | tabela sem `source_crs` | `BLOCKER` |
| `wrong_unit.csv` | unidade declarada incompatível com a magnitude | `WARNING` |

## Invariantes que o M3 acrescenta

- **Descrever não é importar.** Ler metadados nunca cria linha em `dataset`.
- **Um `BLOCKER` bloqueia.** Não é um aviso mais vermelho: o import é recusado
  e a submissão de job é recusada, ambos nomeando a regra.
- **Toda mensagem responde ao §33**: o que falhou, por quê, qual dataset, qual
  parâmetro, o que corrigir, onde está o detalhe técnico.
- **Uma correção declarada é registrada como proveniência**, não aplicada em
  silêncio: declarar o CRS de um arquivo que não o tem é uma afirmação do
  operador, e fica no audit trail como tal.
- **Nenhuma operação cara roda sem estimativa** de RAM e disco.

## Ordem de trabalho

1. Fixtures defeituosos, semeados e derivados.
2. Leitores e `describe` para os seis formatos.
3. `qc/`: regras, severidade, mensagens acionáveis.
4. Grid planner com estimativa de recursos.
5. Operadores `io.describe_dataset` e `qc.validate_dataset`.
6. `ValidationResult` no Project Store.
7. Import Wizard, Data Inspector, Project Hub.
8. Testes, checks no `--self-test`, relatório e `PROJECT_STATE.md`.

Nenhum item avança com o gate do anterior vermelho.

## Fechamento

Fechado em `2026-09-01` com **15/15** no gate e **43/43** no `--self-test`.
Evidência: `../validation/V-M3-data-manager-qc.md`.

Os cinco itens do gate G1–G5 estão verdes, e os catorze fixtures defeituosos
produzem exatamente a regra e a severidade que o `MANIFEST.json` declara.

**Dois itens do escopo saíram parciais, e a divisão fica registrada:**

| Item | Entregue | Carregado para M4 |
|---|---|---|
| Project Hub (§9.1) | os comandos, com undo onde faz sentido, gateados | as superfícies: criar, abrir, recuperar, duplicar, relinkar, recentes |
| Data Inspector (§9.3) | metadados, estatísticas e histograma de 32 bins — calculados, devolvidos e gateados; o wizard mostra os metadados | o painel completo com o histograma desenhado e o histórico de transformações |

A razão de dividir assim é a mesma do M2: o M4 constrói o canvas e os painéis
laterais, que é onde o inspector pertence, e o Project Hub precisa da tela de
abertura que ainda não existe. Construir superfícies provisórias agora seria
construí-las duas vezes.

O **motor** do MSP-06 continua fora: o M3 entrega o planejador de recursos e os
contratos; reprojeção, resampling, rasterização, distância e IDW são M5.
