# M6 — Cenários, sensibilidade e explicabilidade

Status: `PASS` — fechado `2026-09-04`, `docs/validation/V-M6-scenarios.md`
Entrada: M5.8 verde, 32 de 32
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-10, MSP-11, MSP-12, §17

## O problema

O M5 entrega um mapa de favorabilidade. Ele não entrega nenhuma resposta para
a pergunta que vem logo depois dele, e que é a pergunta que decide se alguém
usa o resultado:

> **Por que este pixel? E se eu tivesse escolhido diferente?**

Hoje a aplicação produz um número por célula e um manifesto que reproduz o
cálculo. O que falta é o que o §17 lista, onze perguntas por alvo, das quais
nenhuma tem resposta hoje:

| # | Pergunta | Hoje |
|---|---|---|
| 1 | quais critérios dominaram o score | **sem resposta** |
| 2 | qual fração possui dados válidos | por critério no manifesto; não por alvo |
| 3 | como o ranking muda sem cada critério | **sem resposta** |
| 4 | como o alvo muda com os pesos | **sem resposta** |
| 5 | como o alvo muda com gamma | **sem resposta** |
| 6 | como o alvo muda com membership | **sem resposta** |
| 7 | como o alvo muda com resolução | fora do escopo deste milestone |
| 8 | dependência excessiva de camada correlacionada | detectada no M5; não ligada ao alvo |
| 9 | qual run produziu o alvo | no store desde o M2 |
| 10 | qual versão produziu o alvo | no manifesto desde o M2 |
| 11 | quais parâmetros produziram o alvo | no manifesto desde o M2 |

MSP-10 está em boa parte entregue — runs imutáveis, cache por conteúdo, run
filha ao alterar parâmetros, preservação dos pais, difference map — desde o M2
e o M4. O que falta de MSP-10 é **cenário como objeto de primeira classe**: um
conjunto nomeado de escolhas que se compara com outro.

## O que este milestone entrega

Cinco operadores, todos no worker, e uma tela.

| Operador | Responde | Escreve |
|---|---|---|
| `scenarios.leave_one_out` | §17.3 | a tabela; nada em disco |
| `scenarios.sensitivity` | §17.4, §17.5, §17.6 | a tabela de estabilidade por varredura |
| `scenarios.explain` | §17.1, §17.2, §17.8 | a contribuição de cada critério, por alvo |
| `scenarios.rank_targets` | os alvos, ordenados | a tabela de alvos com o que os sustenta |
| `reporting.manifest` | §17.9, §17.10, §17.11 | o manifesto da run, como arquivo |

### E1 — o núcleo numérico

`scenarios/sensitivity.py` e `scenarios/explain.py`. Sem Qt, sem I/O, sem
operador: funções sobre `CriterionStack` e arrays, testáveis contra casos
fechados.

**Contratos:**

- `P-166` Deixar um critério de fora e reagregar é a **mesma** agregação com
  `n-1` critérios — não uma aproximação, não uma re-normalização de pesos feita
  em silêncio. Quando os pesos somavam 1, os restantes são renormalizados e
  **isso é dito no resultado**.
- `P-167` A troca de posição no ranking é medida com Spearman sobre as células
  válidas em **todos** os cenários comparados. Comparar rankings sobre
  conjuntos diferentes de células não é comparar rankings.
- `P-168` A contribuição de um critério para um alvo soma, com os outros, o
  score daquele alvo — para WLC exatamente, e para os operadores fuzzy pela
  decomposição declarada no código, com a sua limitação escrita.
- `P-169` Um cenário que não pode ser calculado — um critério só, pesos que não
  somam 1 — é recusado por nome, e não devolve um número.

### E2 — os operadores

Os cinco acima, com manifesto como os demais. Nenhum sobrescreve nada, e
nenhum dos quatro `scenarios.*` escreve em disco (MSP-10).

**Contratos:**

- `P-170` Um cenário não sobrescreve nada. O pai continua íntegro e
  recuperável.
- `P-171` **Os quatro `scenarios.*` são read-only.** Escrito no plano como
  valendo só para dois; a implementação mostrou que vale para os quatro.
  `leave_one_out` ia escrever um raster de diferença por critério, e isso saiu:
  `grid.difference` é o operador para "a diferença entre dois mapas" desde o
  M4, e um segundo produzindo o mesmo artefato por outro caminho são duas
  implementações de uma coisa. Um cenário diz **o quanto** o mapa se moveria;
  a figura disso é outro pedido, com a sua própria run.
- `P-172` `reporting.manifest` escreve o manifesto de uma run **como arquivo**,
  e o arquivo reproduz a run: entradas com hash, CRS, grade, ordem dos
  critérios, método, parâmetros, versões.

### E3 — a tela

Um painel de cenários: rodar a análise de sensibilidade e ler as duas tabelas.
A explicação de um alvo onde a pessoa clica **não foi entregue** — os
operadores existem e são testados, a tela usa os dois de sensibilidade.

**Contratos:**

- `P-173` A tela mostra o que foi medido, e não decide nada por ninguém: ela
  não troca pesos, não re-roda a agregação e não esconde um critério.
- `P-174` Um número de sensibilidade sempre aparece com a sua unidade e com o
  tamanho da amostra sobre a qual foi medido.

## O que este milestone NÃO entrega

Declarado antes de começar, para a ausência ser escolha e não esquecimento.

- **Variação de resolução (§17.7).** Reamostrar a análise inteira em outra
  grade é uma run completa por resolução, e a resposta depende de decisões de
  harmonização que a pessoa toma na tela do M5.5. Fica para o M7 ou depois.
- **Otimização.** Nada aqui procura o melhor conjunto de pesos. Sensibilidade
  diz o quanto a resposta se mexe; escolher é da pessoa.
- **Monte Carlo.** Varredura determinística de um parâmetro por vez. Amostragem
  aleatória do espaço de parâmetros é outra coisa e precisa de uma decisão
  sobre distribuições que ninguém tomou.
- **Relatório em PDF.** `reporting.report` continua apontando para o M8.
- **Cenários salvos entre projetos.** Um cenário vive na run que o produziu.
