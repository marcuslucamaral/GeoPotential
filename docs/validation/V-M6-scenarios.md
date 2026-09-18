# V-M6 — Cenários, sensibilidade e explicabilidade

Data: `2026-09-04`
Versão: app `0.6.00`, worker `0.3.00`, protocolo `1.0.0`, schema `1.3.0`
Milestone: `docs/milestones/M6_SCENARIOS.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-10, MSP-11, MSP-12, §17

## Resultado

`PASS`. As três etapas E1–E3.

| Item | Valor |
|---|---|
| Gate | **33 de 33** |
| Testes | **742** unit/contract/integration + 59 checagens de interface |
| Storyboards | **9**, **45 quadros**; `scenarios` é o novo, com 4 |
| Operadores | **18 registrados** (eram 13) |
| Suíte nova | `--only scenarios`, 50 testes |

## O problema que este milestone fecha

O M5 entrega um mapa de favorabilidade. Ele não respondia a pergunta que vem
logo depois, e que é a que decide se alguém usa o resultado:

> **Por que este pixel? E se eu tivesse escolhido diferente?**

Das onze perguntas do §17, sete não tinham resposta. Agora têm.

| # | Pergunta | Onde |
|---|---|---|
| 1 | quais critérios dominaram o score | `scenarios.explain` |
| 2 | qual fração possui dados válidos | `scenarios.explain`, por alvo |
| 3 | como o ranking muda sem cada critério | `scenarios.leave_one_out` |
| 4 | como o alvo muda com os pesos | `scenarios.sensitivity`, `parameter=weight` |
| 5 | como o alvo muda com gamma | `scenarios.sensitivity`, `parameter=gamma` |
| 6 | como o alvo muda com membership | pelos parâmetros do critério na análise |
| 7 | como o alvo muda com resolução | **não entregue**, declarado no plano |
| 8 | dependência de camada correlacionada | M5, e agora ligada ao alvo pela decomposição |
| 9-11 | qual run, qual versão, quais parâmetros | `reporting.manifest`, como arquivo |

## As decisões que a implementação forçou

**Uma contribuição significa coisas diferentes por operador, e a diferença não
é cosmética.** `weighted_linear_combination` é uma soma, então `w_i · m_i` é a
parcela exata daquele critério e as parcelas somam o score — verificado contra
a aritmética, a `1e-9`. Os operadores fuzzy são produtos, e **não existe
decomposição aditiva de um produto**: o que se reporta é a parcela do
logaritmo, que é uma leitura real de qual fator puxou o produto, e **não** é
uma fração do score. Cada resultado carrega o nome da decomposição que usou,
para que um número nunca seja lido sob o significado errado.

**Um critério em zero decide a célula sozinho.** Num produto, um fator zero é a
resposta inteira, e parcelas de `-inf` não explicam nada. O resultado nomeia o
critério como veto em vez de calcular.

**Comparar rankings sobre conjuntos diferentes de células não é comparar
rankings.** Tirar um critério muda quais células são nulas — um score precisa
de todos os critérios (ADR-004) — então a linha de base e o cenário têm
máscaras diferentes. O rho é medido sobre a interseção, e o tamanho dela vai ao
lado de cada número: um rho sobre 300 células e um sobre 300 000 não são a
mesma evidência.

**Os quatro `scenarios.*` são read-only.** `leave_one_out` chegou a escrever um
raster de diferença por critério, e isso foi removido: `grid.difference` é o
operador para "a diferença entre dois mapas" desde o M4, e um segundo que
produz o mesmo artefato por outro caminho são duas implementações de uma coisa.
Um cenário diz **o quanto** o mapa se moveria; pedir a figura disso é outro
pedido, com o seu operador e a sua run.

**Renormalizar peso é dito, nunca silencioso.** `P-93` proíbe renormalizar em
silêncio, e um operador cujos pesos somam 1 não sobrevive à remoção de um
critério sem isso. A saída é fazer e reportar: `weights_renormalized` vem em
toda linha.

## Contratos novos

| ID | Contrato | Gate |
|---|---|---|
| P-166 | Deixar um critério de fora é a mesma agregação com `n-1`, e a renormalização de pesos é reportada | `--only scenarios` |
| P-167 | O ranking é comparado sobre as células que todo cenário respondeu | `--only scenarios` |
| P-168 | A decomposição é exata para WLC e declarada para os operadores fuzzy | `--only scenarios` |
| P-169 | Um cenário que não pode ser calculado é recusado por nome | `--only scenarios` |
| P-170 | Um cenário não sobrescreve nada; os pais permanecem íntegros | `--only scenarios`, storyboard |
| P-171 | Os quatro `scenarios.*` são read-only: não commitam run nem registram artefato | `--only scenarios`, storyboard |
| P-172 | Um manifesto que não reproduz a run é recusado, não escrito | `--only scenarios` |
| P-173 | A tela mede e não decide: não troca peso, não re-roda, não esconde critério | storyboard `scenarios` |
| P-174 | Todo número de sensibilidade vem com o tamanho da amostra | `--only scenarios`, storyboard |

## Como foi provado

**Na janela real.** Storyboard `scenarios`, 4 quadros, cada um com asserção
numérica sobre o estado da aplicação:

| Quadro | O que ficou provado |
|---|---|
| `01 analysis` | três critérios que discordam, para tirar um ter onde aparecer |
| `02 opened` | a tela pega os três critérios e o operador do Decision Model, e abre **sem** resultado inventado |
| `03 leave_one_out` | 3 linhas, ordenadas pelo que mais move o mapa, **16 587 485 células** comparadas, a limitação junto, **0 runs commitadas**, operador intacto |
| `04 gamma_sweep` | 6 valores; pior caso \|Δ\| médio **0,3951** e **52 %** das melhores áreas mantidas; a primeira medição continua na tela |

O quadro 4 tem uma verificação embutida que vale por si: em `gamma = 0.70`, que
é o valor que a análise usou, a linha mostra `0.0000 / 1.000 / 100 %`. Uma
varredura que não devolvesse zero no próprio ponto de partida estaria medindo
outra coisa.

**Um defeito que o teste pegou.** `np.argsort` põe NaN no **fim** da ordem
crescente, então invertida os nulos vêm primeiro e o primeiro candidato a alvo
nunca é válido. `rank_targets` devolvia zero alvos num mapa com nulos. Foi
encontrado por `test_null_cells_are_never_targets`, não por inspeção.

## O que este milestone NÃO entrega

- **Variação de resolução (§17.7).** Reamostrar a análise inteira em outra
  grade é uma run completa por resolução, e depende de decisões de
  harmonização que a pessoa toma na tela do M5.5.
- **Otimização.** Nada aqui procura o melhor conjunto de pesos.
- **Monte Carlo.** A varredura é determinística, um parâmetro por vez, e a
  limitação disso viaja com o resultado: um desenho um-de-cada-vez não vê
  interação entre critérios (Saltelli et al., 2008, ch. 1).
- **Relatório em PDF.** `reporting.report` continua apontando para o M8.
- **Cenários salvos entre projetos.** Um cenário vive na run que o produziu.
- **A explicação de um alvo não está no mapa.** `scenarios.explain` e
  `scenarios.rank_targets` existem como operadores e são testados; a tela usa
  os dois de sensibilidade. Clicar num pixel e ver a decomposição é o próximo
  passo, e não está feito.
- **A limitação aparece em inglês na tela.** Ela vem do worker, que é
  inglês-only — a lacuna já registrada desde o M5.5, agora visível num lugar a
  mais.
