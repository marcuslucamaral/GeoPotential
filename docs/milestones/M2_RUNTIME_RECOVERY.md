# M2 — Runtime, Project Store e recovery

Status: `PASS`
Entry gate: `OPEN` — M0 e a fatia vertical do M1 verdes, 9/9
Exit gate: `PASS` — 11/11, `../validation/V-M2-runtime-recovery.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §20 M2, §7.4, §13, §14, §32, §33

## Objetivo

Fazer o produto **sobreviver ao que dá errado**. O M1 provou que o caminho
feliz funciona ponta a ponta. O M2 prova que matar a interface, matar o worker,
cancelar no meio, ou desligar durante o commit **não corrompe o projeto e não
inventa um resultado**.

## Escopo

Dentro:

| Item | O que significa aqui |
|---|---|
| lifecycle | fechar a janela encerra os filhos, sempre, inclusive quando o worker está travado |
| cancelamento | cooperativo, sem registrar nada, e sem deixar `.tmp` para trás |
| logs | quatro canais separados (§32): aplicação, científico, worker, crash — com timestamp, versão, `job_id`, `run_id`, operador, estágio, erro, duração e recursos |
| diagnóstico exportável | um arquivo que o usuário envia ao suporte, sem dado científico dentro |
| autosave | estado da sessão gravado em `recovery/`, **nunca confundido com commit científico** |
| recovery | ao reabrir: detectar job interrompido, detectar artefato órfão, oferecer ação |
| SQLite | tabelas que faltavam: `job_journal`, `session`, `command_log` |
| restart do worker | matar o worker e continuar, com o projeto intacto |
| commands | pilha de comandos com undo/redo para o que altera domínio (§7.4) |
| Project Hub | criar, abrir, recuperar, duplicar, relinkar, listar recentes (§9.1) |
| relink | uma entrada externa que mudou de lugar é reapontada, com hash conferido |

Fora (nomeado para que a ausência seja escolha):

- Import Wizard, Data Inspector, QA/QC — **M3**
- reprojeção, resampling, IDW, grid planner — **M3**
- LOD, tiles, overviews, pan, zoom, AOI — **M4**
- AHP, Fuzzy Gamma/Product/Sum, WLC — **M5**
- cenários, sensibilidade, explicabilidade, ranking — **M6**
- gravity, magnetics — **M7**
- empacotamento `.deb`, instalação em máquina limpa — **M8**

## Gate M2

Cada linha é um check executável em `--self-test`, e cada uma tem de ser capaz
de falhar.

| # | Exigência do §20 | Como é provado |
|---|---|---|
| G1 | fechar a janela encerra os filhos | PID do worker morto após `shutdown()`; e após `shutdown()` sobre um worker que ignora `shutdown` (deadline vencido → `kill`) |
| G2 | matar o worker permite restart | `SIGKILL` no worker, supervisor detecta `crashed`, `restartWorker()` volta a `ready`, novo job roda até `Succeeded` |
| G3 | cancelar não corrompe o projeto | job cancelado: nenhuma run, nenhum artefato, nenhum `.tmp`, projeto reabre e o catálogo bate |
| G4 | reabrir recupera o estado | matar durante `Running`; reabrir marca o job como `Interrupted`, não como `Succeeded`, e o artefato órfão é detectado |
| G5 | run concluída permanece imutável | já verde no M1; permanece no gate |

Testes de kill exigidos pelo §20, todos os quatro:

| Teste | O que não pode acontecer |
|---|---|
| kill forçado da UI | worker órfão sobrevivendo ao pai |
| kill forçado do worker | projeto corrompido; supervisor preso em `ready` |
| kill durante `Running` | job registrado como `Succeeded`; artefato parcial registrado |
| kill durante `Committing` | run commitada pela metade; artefato registrado sem run |

## Invariantes que o M2 acrescenta

Entram em `PROJECT_STATE.md` como contratos protegidos.

- **Autosave não é commit.** O que está em `recovery/` descreve uma sessão, não
  um resultado. Nada em `recovery/` pode virar `run` sem passar pelo caminho
  normal de commit.
- **Um job interrompido é `Interrupted`, nunca `Succeeded`.** Ao reabrir, todo
  job que estava em `Running` ou `Committing` e cujo processo morreu é
  reclassificado, e a reclassificação é registrada como evento de provenance.
- **Um artefato órfão é visível e nunca é adotado em silêncio.** Arquivo em
  `artifacts/<job_id>/` sem linha em `artifact` é listado pela recuperação; o
  usuário decide descartar ou reprocessar. O sistema não o vincula sozinho.
- **Um `.tmp` sobrevivente é lixo, nunca um resultado.** A recuperação apaga,
  registrando o que apagou.
- **O log do worker nunca chega cru ao usuário.** `safe_message` na interface,
  `detail_ref` apontando para a linha do log.
- **O diagnóstico exportável não carrega dado científico** — caminhos, versões,
  hashes, estados e erros; nunca valores de pixel.
- **Um comando desfeito não desfaz ciência.** `undo` reverte estado de projeto
  (ordem, seleção, vínculo de dataset); nunca apaga uma run imutável.

## Ordem de trabalho

1. Logging em quatro canais + diagnóstico exportável.
2. Tabelas novas no Project Store + migração aditiva por versão de schema.
3. Journal de job e passe de recuperação (órfãos, `.tmp`, interrompidos).
4. Restart do worker com o projeto intacto; deadline de shutdown com `kill`.
5. Pilha de comandos com undo/redo.
6. Project Hub: criar, abrir, recuperar, duplicar, relinkar, recentes.
7. Testes de kill (os quatro) + checks no `--self-test`.
8. Relatório de validação e atualização do `PROJECT_STATE.md`.

Nenhum item avança com o gate do anterior vermelho.

## Fechamento

Fechado em `2026-09-01` com **11/11** no gate e **35/35** no `--self-test`.
Evidência: `../validation/V-M2-runtime-recovery.md`.

Os cinco itens do gate G1–G5 e os quatro testes de kill estão verdes. Entregue
integralmente: lifecycle com deadline real de shutdown, cancelamento, os quatro
canais de log, diagnóstico exportável, autosave por journal write-ahead,
recovery, as três tabelas novas em SQLite, restart do worker, pilha de comandos
com undo/redo, e relink.

**Um item do escopo saiu parcial, e a divisão é registrada aqui em vez de
ficar implícita:**

| Item | Entregue | Carregado para M3 |
|---|---|---|
| Project Hub (§9.1) | o *passe* de recuperação, e os comandos `ImportDataset`, `RelinkDataset` e `DiscardOrphans` — validados, com undo onde faz sentido, e cobertos pelo gate | as *superfícies*: criar, abrir, recuperar, duplicar, relinkar e listar recentes. Nada em QML chama `relinkDataset` ou `importDataset` ainda. |

A razão de dividir assim: o M3 constrói o Import Wizard e o Data Inspector, que
são as telas onde importar e relinkar realmente pertencem. Construir um
seletor de arquivos separado no M2 significaria construí-lo duas vezes, e a
segunda versão apagaria a primeira. Os comandos existem e estão gateados; o que
falta é a superfície que os chama.

Duas ausências que não estavam no escopo e ficam nomeadas: durabilidade contra
queda de energia (os kills são `SIGKILL` em processo; nada testa um filesystem
que mente sobre `fsync`) e concorrência (um worker, um job por vez; fila,
escalonador e backpressure são §18.1).
