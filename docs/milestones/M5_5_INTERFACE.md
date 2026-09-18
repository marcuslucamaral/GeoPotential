# M5.5 — Interface profissional

Status: `PASS` em `2026-09-03` — as sete etapas, mais o idioma e o mapa de fundo
Entry gate: `OPEN` — M5 verde, 20/20, `../validation/V-M5-decision-engine.md`
Exit gate: `PASS` — 30/30, `../validation/V-M5_5-interface.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §8 (workspace), §9.1–9.6,
MSP-02 (projeto), MSP-03 (formatos), MSP-04 (QA/QC), MSP-05 (canvas), §16
(nunca use valores silenciosos)
Referências visuais: as três imagens fornecidas em `2026-09-01`, nesta ordem —
(1) workflow vertical e menus, (2) a tela atual do GeoPotential como baseline,
(3) barra vertical de ferramentas do mapa.

## Por que um milestone e não um ajuste dentro do M6

O contrato admite **uma** milestone ativa. O M6 é ciência — cenários,
sensibilidade, explicabilidade, ranking — e o seu gate é "qualquer target é
explicável". O trabalho pedido aqui é a casca: workflow, menus, camadas,
ferramentas, previsualização, CRS, temas, jobs. São gates diferentes, provas
diferentes e riscos diferentes. Misturá-los produziria um gate que ninguém
consegue ler.

O M5.5 entra **antes** do M6 porque o M6 acrescenta seis telas novas (Explain
View, Target Table, comparação de cenários, difference map, sensibilidade,
estabilidade) e todas elas herdam o painel de camadas, a barra de ferramentas e
o workflow. Construí-las sobre a tela atual seria construí-las duas vezes.

## Objetivo

**Tornar o estado do trabalho legível sem que ninguém precise perguntar.** Hoje
a aplicação faz mais do que mostra: o fluxo científico existe e está gated, mas
a tela não diz em que etapa se está, o que está carregado, o que está visível,
o que falhou nem por quê.

O gate é uma frase: *uma pessoa que nunca viu o GeoPotential consegue, sozinha,
ir de um arquivo a um mapa de prospectividade, e em qualquer momento sabe em
que etapa está, o que está bloqueado e por quê.*

## Baseline — o que a segunda imagem mostra, e onde está a causa

Cada achado foi localizado no código. Isto é o diagnóstico pedido; nenhuma
linha abaixo é suposição sobre a imagem.

| # | O que se vê | Causa no código |
|---|---|---|
| B1 | Linhas amarelas sobre o mapa sem explicação | `render/geocanvas/map_item.py:385` `_paint_aoi` desenha sempre que `len(self._aoi) >= 2`. `endAoi()` (l. 433) apenas baixa `_aoi_drawing`; **não limpa os vértices e não há estado visível**. O polígono fica na tela para sempre, sem legenda, sem marcadores de vértice, sem desfazer. |
| B2 | Não existe painel de camadas | Não há representação de pilha na aplicação. `MapItem` guarda **uma** fonte e **uma** comparação (`showArtifact` / `showComparison`, l. 158 e 207). Não há visibilidade, ordem, opacidade, camada ativa nem remoção. |
| B3 | O fluxo importação → QA/QC → harmonização → membership → AHP → agregação não é visível | `qml/GeoPotential/Navigator.qml:31` é um `ListModel` estático de seis rótulos com um campo `ready` **escrito à mão**. Não lê o estado do projeto; não sabe o que já foi feito. |
| B4 | O painel de jobs ocupa muito espaço e interage pouco | `Theme.qml` fixa `bottomPanelHeight: 170` sem recolher nem redimensionar. `JobsPanel.qml` mostra oito campos por job e nenhuma ação; `models/job_model.py:33` expõe oito papéis — sem entradas, saídas, artefatos, tempo decorrido ou nome amigável. |
| B5 | O colormap aparece no Inspector mas não pode ser mudado | `Inspector.qml` linha `key: "Colormap"` é leitura de `canvas.displayState`. `render/colormap.py:38` só tem `viridis`, `magma`, `grey`, `rdbu`, e a escolha é automática (`default_colormap`, l. 70). Não pertence a uma camada porque não há camada. |
| B6 | As ferramentas do mapa não indicam o modo ativo | `CanvasOverlay.qml` tem três `RoundButton` de zoom sem estado. O `MapItem` não tem modo de interação: `mousePressEvent` (l. 275) decide por `self._aoi_drawing`, e nada mais existe — nem identificar, nem medir. |
| B7 | `job failed` fica visível sem dizer qual job | `JobsPanel.qml` mostra `root.controller.status`, uma **string global** (`app_controller.py:82`) escrita pelo último evento; `_fail()` (l. 602) a define. Ela não pertence ao job selecionado nem ao estado atual. |
| B8 | Não fica claro o que está carregado, visível ou selecionado | Consequência de B2. `Inspector.qml` mostra `lastDescription`, que é *o último dataset descrito*, não *a camada ativa*. |
| B9 | Sem barra de menus | `Main.qml` usa `header: TopBar`, uma linha de botões. Não há `MenuBar`, nem atalhos, nem preferências, nem exportação. |
| B10 | A ação Run está presa a um caminho de linha de comando | `Main.qml` `runSmokeOperator()` usa `smokeInput`, herdado da fatia vertical do M1. É exatamente a "injeção usada só por teste" que o pedido manda eliminar. |

O que funciona e **não** se toca: o canvas com LOD e cache (P-66…P-73), a
leitura do valor sob o cursor a partir da fonte (P-70), o Import Wizard com
QA/QC e recusas (P-53…P-61), o Membership Editor com curva sobre histograma
(P-102), o Decision Model com CR bloqueante (P-87), a barra de escala, a nota
de fronteira científica e a barra de estado.

## Escopo

Dentro:

| Item | O que significa aqui |
|---|---|
| Workflow vertical | oito etapas numeradas, **com estado derivado do Project Store**, não escrito à mão |
| Barra de menus | `File`, `Edit`, `View`, `Help`, com atalhos; item sem suporte fica desabilitado **com o motivo visível** |
| Painel de camadas | pilha de exibição: visibilidade, ordem, opacidade, camada ativa, colormap, zoom, propriedades, remoção da vista |
| Barra vertical de ferramentas | navegar, camadas, zoom in/out, extensão total, tela cheia, identificar, AOI, medir distância, medir área, exportar mapa — com o modo ativo destacado e descrito |
| Modo AOI explícito | desenhar, marcar vértices, desfazer o último, finalizar, cancelar, editar, apagar; AOI salva vira camada |
| Colormap por camada | viridis, plasma, inferno, magma, cividis, turbo, cinza, divergente centrado em zero; inverter; min/max; restaurar automático |
| Temas | escuro (atual), claro, alto contraste, automático; preferência persistida fora do projeto |
| Painel de jobs | recolhível, redimensionável, filtro ativos/histórico, detalhe por job, ações (cancelar, repetir, abrir resultado, log) |
| Pré-visualização de importação | raster, vetor e tabela, cada um com o que a MSP-03 exige, antes de importar |
| CRS e coordenadas | CRS do projeto, da camada e da vista; UTM, graus decimais, GMS com hemisfério, CRS original |
| Fluxo real | o Run passa a vir do workflow e das camadas; `smokeInput` sai |

Fora (nomeado, para a ausência ser escolha e não esquecimento):

- **Cenários, difference map de cenários, sensibilidade, explicabilidade,
  ranking** — M6. O painel de camadas e a comparação lado a lado que este
  milestone entrega são a base sobre a qual o M6 os desenha.
- **Vetores desenhados no canvas com índice espacial, seleção e picking** —
  carregado do M4. Este milestone desenha a *pré-visualização* de geometrias na
  importação (limitada e declarada como tal) e a AOI. O caminho vetorial
  completo continua aberto.
- **Hillshade** — precisa de um DEM e de convenção de iluminação declarada.
- **Exportar resultado e relatórios** — M6/M8. O menu terá os itens
  desabilitados com o milestone nomeado. **Exportar mapa** (a imagem do canvas
  com barra de cor, escala e CRS) entra aqui porque não depende do worker.
- **Empacotamento, instalação, SBOM** — M8.

## Três decisões que precisam de ADR antes do código

Nenhuma pode ser tomada dentro de um commit de implementação.

### ADR-MSP-002 — a pilha de exibição não é uma segunda representação do domínio

O contrato proíbe uma segunda representação do objeto de domínio. `Criterion`
sobre um `TargetGrid` é a representação científica e vive no worker;
`CriterionStack.names` é a única ordem que os pesos amarram.

A proposta é um `DisplayLayer` na aplicação que **deriva** de um dataset
registrado ou de um artefato de run, num sentido só, e que carrega **apenas**
decisões de exibição: visível, ordem de desenho, opacidade, colormap, limites de
estilo, nome exibido, papel (`original`, `harmonizado`, `membership`,
`resultado`, `AOI`). Ele não guarda pixels, não guarda unidade própria, não
guarda CRS próprio — lê-os do registro. Apagar uma camada da vista não apaga
nada do projeto, e a ordem de desenho **nunca** influencia nenhum cálculo.

O gate de arquitetura precisa de um teste negativo: um `DisplayLayer` não pode
ser aceito por nenhuma função de agregação, e a ordem da pilha de exibição não
pode entrar em nenhum manifesto.

### ADR-MSP-003 — transformação de coordenadas para exibição na aplicação

Mostrar a posição do cursor em graus quando a camada está em UTM exige uma
transformação. Duas saídas:

1. **Ida e volta ao worker por movimento de cursor** — correto por contrato e
   inviável por latência (uma mensagem JSON-Lines por pixel percorrido).
2. **Um módulo `geo/coordinates.py` na aplicação, sobre pyproj, só para
   exibição** — não lê arquivos, não escreve nada, não toca em nenhum caminho
   que comita run, e é a contraparte exata do ADR-006 do workspace ("a
   reprojeção de exibição nunca modifica uma fonte").

A recomendação é (2), com o módulo nomeado em `docs/ARCHITECTURE.md` como
costura, do mesmo modo que a leitura de arquivo em `map_item.py` já é, e com um
teste negativo no gate de arquitetura: nada em `project/`, `commands/` ou no
caminho de submissão pode importá-lo.

### ADR-MSP-004 — a pré-visualização atravessa o IPC limitada e declarada

P-63 diz que a descrição não carrega arrays através do IPC. Uma prévia de
geometrias e uma prévia de pontos de um CSV **são** coordenadas.

A proposta: `io.describe_dataset` ganha um bloco `preview` opcional, com teto
declarado (proposta: 2 000 coordenadas para vetor, 5 000 pontos para tabela),
sempre acompanhado de `preview_decimated: true|false` e `source_features: N`.
É JSON, é limitado, e é rotulado na tela como prévia. Um teste de contrato fixa
o teto e um segundo garante que o bloco `preview` **nunca** é entrada de
operador. O array completo continua proibido.

## As sete etapas

A ordem é a pedida: primeira imagem, segunda imagem, terceira imagem, e depois
o que sustenta as três.

### E1 — Workflow vertical e barra de menus (primeira imagem)

O workflow substitui o `Navigator` estático. As oito etapas — Projeto, Dados,
QA/QC, Harmonização, Membership, Pesos/AHP, Agregação, Resultados — com estado
`não iniciada | disponível | em execução | concluída | alerta | bloqueada`,
**derivado** de fatos do Project Store: há projeto aberto? há dataset
importado? há veredito de QA/QC? há grid alvo definido? há critério
`NORMALIZED`? há matriz com CR abaixo do limite? há run de agregação comitada?

Cada etapa mostra entradas necessárias, resultados produzidos, o motivo quando
bloqueada e os caminhos seguintes. Clicar abre a ferramenta correspondente.

Arquivos:

- **novo** `app/geopotential_app/viewmodels/workflow_model.py` — QtCore apenas;
  o pacote existe e está vazio. Um `QAbstractListModel` de etapas cujo estado é
  função pura dos fatos do store.
- **novo** `app/geopotential_app/qml/GeoPotential/WorkflowPanel.qml`
- **novo** `app/geopotential_app/qml/GeoPotential/AppMenuBar.qml`
- `app/geopotential_app/controllers/app_controller.py` — publica
  `workflow` (`Property(QObject, constant=True)`) e emite a mudança nos
  mesmos pontos em que já emite `projectChanged` / `runCommitted`
- `app/geopotential_app/qml/Main.qml` — `menuBar:`, `Navigator` → `WorkflowPanel`
- `app/geopotential_app/qml/GeoPotential/Navigator.qml` — **removido**; a lista
  de operadores disponíveis migra para o Inspector, seção "Worker"
- `app/geopotential_app/qml/GeoPotential/Theme.qml` — token de largura e cores
  de estado de etapa

Aceitação:

- A1 Com projeto fechado, só a etapa 1 está disponível; as outras sete estão
  bloqueadas e cada uma **nomeia o que falta**.
- A2 Depois de importar `Distance_to_fault.tif`, as etapas 2 e 3 ficam
  concluídas e a 4 disponível, **sem nenhuma escrita manual de estado**: o
  teste apaga o estado em memória, relê do store e obtém o mesmo resultado.
- A3 Uma etapa bloqueada clicada não abre nada e mostra o motivo.
- A4 Todo item de menu ou está ligado a um slot real, ou está desabilitado com
  o motivo — nenhum item que aceite clique e não faça nada. Teste que percorre
  o `MenuBar` e falha em qualquer item habilitado sem handler.
- A5 Atalhos: `Ctrl+N`, `Ctrl+O`, `Ctrl+I`, `Ctrl+Z`, `Ctrl+Shift+Z`, `F11`,
  `F1` — cada um dispara o mesmo caminho que o item de menu.

### E2 — Painel de camadas, Inspector, colormap, AOI e Jobs (segunda imagem)

O maior bloco, e o que fecha B1, B2, B5, B7 e B8.

Arquivos:

- **novo** `app/geopotential_app/models/layer_model.py` — a pilha de exibição
  do ADR-MSP-002; QtCore apenas
- **novo** `app/geopotential_app/qml/GeoPotential/LayerPanel.qml`
- **novo** `app/geopotential_app/qml/GeoPotential/LayerProperties.qml` —
  propriedades, estatísticas, colormap, limites
- **novo** `app/geopotential_app/qml/GeoPotential/JobDetail.qml`
- `render/geocanvas/map_item.py` — desenhar N camadas em ordem, com opacidade;
  `toolMode`; AOI com marcadores de vértice, desfazer, cancelar, finalizar;
  colormap e limites **por camada**
- `render/colormap.py` — plasma, inferno, cividis, turbo; inversão; divergente
  com número **ímpar** de entradas centrado exatamente em zero (a regra já
  existe e passa a valer para todas as rampas)
- `models/job_model.py` — papéis novos: nome amigável, descrição, entradas,
  saídas, artefatos, início, tempo decorrido, avisos
- `controllers/job_controller.py` — guardar entradas/saídas/tempos por job;
  `retry(job_id)`
- `controllers/app_controller.py` — `status` deixa de ser o balde único; passa
  a haver estado por job e uma linha global que só fala do worker e do projeto
- `qml/GeoPotential/JobsPanel.qml` — recolher, redimensionar, filtrar, detalhe
- `qml/GeoPotential/Inspector.qml` — passa a descrever **a camada ativa**
- `qml/Main.qml` — `SplitView`, painel de camadas, remoção do `smokeInput`

Aceitação:

- A6 Três camadas carregadas desenham na ordem da pilha; inverter a ordem
  inverte o desenho; opacidade 0 some e 1 volta — provado por sondagem de
  pixels, não por olhar.
- A7 Esconder a camada ativa não muda nenhum valor lido sob o cursor a partir
  da fonte (P-70 continua verde).
- A8 A AOI **não** aparece fora do modo AOI. Entrar no modo mostra "Desenhando
  AOI", os vértices ganham marcadores, desfazer remove o último, cancelar não
  salva nada e finalizar cria versão (P-74, P-75 continuam verdes) e a AOI
  aparece no painel de camadas.
- A9 Trocar o colormap da camada ativa repinta e **não** reescreve nenhum
  arquivo: hash do artefato idêntico antes e depois.
- A10 O colormap pertence à camada: com duas camadas e colormaps diferentes,
  trocar a ativa não muda a outra.
- A11 Nodata continua transparente em toda rampa nova (P-31 estendido a
  plasma, inferno, cividis, turbo, cinza e invertidas).
- A12 Uma rampa divergente tem número ímpar de entradas e o zero recebe a
  entrada central exata.
- A13 Com um job falhado e outro bem-sucedido, a mensagem de falha aparece
  **no** job que falhou; o cabeçalho não mostra `job failed` quando o job
  selecionado teve sucesso.
- A14 Cada job mostra nome amigável, nome técnico do operador, entradas,
  saídas, artefatos, tempo decorrido; cancelar, repetir e abrir resultado
  funcionam; um job cancelado continua não registrando nada (P-36 verde).
- A15 O painel de jobs recolhe até a altura de cabeçalho e volta; a preferência
  sobrevive ao fechamento.

### E3 — Barra vertical de ferramentas do mapa (terceira imagem)

Onze ferramentas numa coluna compacta sobre o mapa, agrupadas: navegar |
camadas · identificar · AOI | medir distância · medir área | zoom in · zoom out
· extensão total · tela cheia | exportar mapa. Ferramenta ativa destacada, com
descrição.

Arquivos:

- **novo** `app/geopotential_app/qml/GeoPotential/MapToolBar.qml`
- **novo** `app/geopotential_app/qml/GeoPotential/MeasureOverlay.qml`
- `render/geocanvas/map_item.py` — `toolMode` completo, medição de distância e
  de área, cursor por modo
- `render/geocanvas/viewport.py` — se a medição precisar de conversão
  ecrã↔mapa adicional (o round-trip exato de P-69 é o alicerce e não muda)
- `qml/GeoPotential/CanvasOverlay.qml` — os três botões de zoom saem daqui
- **novo** `app/geopotential_app/qml/GeoPotential/icons/` — SVG monocromático,
  colorido por token; nada de mapa de bits

Aceitação:

- A16 Um e só um modo ativo por vez; o destaque no botão corresponde ao modo do
  `MapItem` — lido do estado da aplicação, não da imagem.
- A17 O cursor muda com o modo, e a barra de estado nomeia o modo ativo.
- A18 Medir distância entre dois pontos conhecidos bate com o cálculo
  independente dentro da tolerância declarada **antes** do teste, na unidade do
  CRS; **recusado** em CRS geográfico, com a recusa nomeando o CRS (P-14).
- A19 Medir área idem, com unidade ao quadrado correta.
- A20 Sair de um modo de medição limpa a medição da tela — o defeito B1 não se
  repete em outra ferramenta.
- A21 Exportar mapa grava PNG com barra de cor, escala, CRS e nome da camada, e
  não cria run nem artefato registrado.

### E4 — Pré-visualização completa dos formatos

Depende do ADR-MSP-004.

Arquivos:

- `worker/geopotential_worker/io/describe.py` — bloco `preview` limitado
- `worker/geopotential_worker/protocol.py` **e** `app/…/ipc/protocol.py` —
  o campo novo, **copiado byte a byte** (P-03)
- `schemas/` — regenerar com `tools/generate_ipc_schemas.py`
- `qml/GeoPotential/ImportWizard.qml` — três painéis por tipo: raster (mapa,
  histograma, CRS, resolução, extensão, NoData, unidade, bandas), vetor
  (geometrias, atributos, CRS, extensão, nº de feições, camadas de GeoPackage),
  tabela (prévia tabular, escolha de X/Y/valor, mapa de pontos, estatísticas,
  CRS, unidade)
- **novo** `qml/GeoPotential/PreviewMap.qml`

Aceitação:

- A22 Os seis formatos abrem a prévia certa (P-62 verde, com a prévia por
  cima).
- A23 O bloco `preview` respeita o teto e declara a decimação; um shapefile com
  50 000 vértices produz uma prévia limitada que **diz** que foi limitada.
- A24 Prévia **não** importa: nenhuma linha no store, nenhuma run comitada
  (P-53 verde).
- A25 Arquivo sem CRS, sem unidade, sem NoData ou sem campos reconhecíveis
  **pede a declaração**, e a declaração é registrada como asserção do usuário
  (P-57 verde). Nada é assumido em silêncio.
- A26 Um GeoPackage com várias camadas lista todas e exige a escolha.

### E5 — CRS e formatos de coordenadas

Depende do ADR-MSP-003.

Arquivos:

- **novo** `app/geopotential_app/geo/coordinates.py` — formatação UTM, graus
  decimais, GMS com hemisfério, e transformação **só de exibição**
- **novo** `qml/GeoPotential/CrsPanel.qml` — CRS do projeto, da camada, da
  vista, com as três operações distintas e rotuladas: **declarar** (arquivo sem
  referência), **reprojetar de fato** (escreve dado novo, é run), **reprojetar
  só para exibição** (não escreve nada)
- `qml/GeoPotential/StatusBar.qml` — seletor de formato de coordenada
- `docs/ARCHITECTURE.md` — a costura nomeada
- `tools/architecture_check.py` — o teste negativo do ADR-MSP-003

Aceitação:

- A27 As três operações de CRS aparecem com nomes distintos e consequências
  declaradas; a reprojeção efetiva é uma run com manifesto, a de exibição não
  escreve byte nenhum.
- A28 Os quatro formatos de coordenada mostram o mesmo ponto, e a conversão de
  ida e volta fecha dentro da tolerância declarada.
- A29 Toda coordenada exibida vem acompanhada do seu CRS.
- A30 Nenhum CRS padrão em lugar nenhum: um arquivo sem CRS continua recusado
  por nome (P-13 verde).
- A31 O gate de arquitetura falha se `project/`, `commands/` ou o caminho de
  submissão importar `geo/coordinates.py`.

### E6 — O fluxo real, sem injeções

`smokeInput` e `runSmokeOperator` saem. O Run passa a operar sobre a camada
ativa e o estado do workflow: harmonização a partir do CRS-alvo escolhido,
membership a partir do editor, pesos a partir da matriz, agregação a partir da
pilha de critérios. Cada botão Run desabilitado nomeia o que falta.

Arquivos: `qml/Main.qml`, `controllers/app_controller.py`,
`viewmodels/workflow_model.py`, `qml/GeoPotential/DecisionModel.qml`,
`qml/GeoPotential/MembershipEditor.qml`.

Aceitação:

- A32 A aplicação iniciada **sem argumento de linha de comando** percorre o
  fluxo inteiro até um mapa de prospectividade.
- A33 Nenhum caminho de execução da interface depende de um parâmetro que só o
  self-test ou o storyboard fornece — verificado por busca no código e por um
  storyboard que arranca sem argumentos.
- A34 O manifesto da run final continua reproduzindo a run (P-99 verde).

### E7 — Temas, evidência e fechamento

- `Theme.qml`: `mode` em `dark | light | highContrast | system`; **nenhum token
  métrico depende do modo** — provado comparando capturas, não a olho.
- Preferência de tema, formato de coordenada e layout dos painéis persistida
  **fora do projeto** (o projeto é dado, não preferência).
- **novo** `tools/storyboards/m55.py` — o fluxo inteiro em sequência, com
  `probes`, fatos e `expect`; a AOI antes/depois de sair do modo é um `expect`
  explícito, porque é o defeito B1.
- **novo** `docs/validation/V-M5_5-interface.md`
- `docs/PROJECT_STATE.md`, `docs/ARCHITECTURE.md`, `README.md`
- `app/geopotential_app/_version.py` → `0.2.00`

Aceitação:

- A35 Os quatro temas passam pelo mesmo storyboard; a diferença entre capturas
  é **só de cor** — posições idênticas, ao pixel.
- A36 Alto contraste atinge a razão de contraste declarada em texto e bordas,
  medida, não estimada.
- A37 `./tools/run_gate.sh` verde, com os checks novos, e **os 102 contratos
  protegidos anteriores continuam verdes**.

## Gate M5.5

| # | Etapa | Como é provada |
|---|---|---|
| G1 | O workflow diz a verdade | o estado de cada etapa é recalculado a partir do store e bate com o exibido, em três pontos do fluxo |
| G2 | Nenhum menu morto | percorrer o `MenuBar`; todo item habilitado tem handler, todo item desabilitado tem motivo |
| G3 | A pilha de exibição é exibição | ordem, visibilidade e opacidade mudam o desenho e **não** entram em nenhum manifesto |
| G4 | A AOI é um modo | fora do modo AOI, nenhum pixel de AOI na tela; dentro, vértices, desfazer, cancelar e finalizar |
| G5 | O colormap pertence à camada | duas camadas, dois colormaps, hash dos artefatos inalterado |
| G6 | O job certo mostra o erro certo | um job falha, outro tem sucesso, e a mensagem fica onde deve |
| G7 | A prévia não importa | os seis formatos previstos, nenhuma linha no store |
| G8 | Nada de CRS silencioso | as três operações distintas; arquivo sem CRS recusado por nome |
| G9 | Medição honesta | distância e área batem com cálculo independente; recusadas em CRS geográfico |
| G10 | O fluxo é real | storyboard sem argumentos, do arquivo ao mapa de prospectividade |
| G11 | Tema só repinta | capturas dos quatro temas com geometria idêntica |
| G12 | Nada regrediu | 20/20 anteriores + os checks novos |

## Contratos protegidos que este milestone acrescenta

Entram em `docs/PROJECT_STATE.md` ao fechar.

| ID | Contrato | Gate |
|---|---|---|
| P-103 | O estado de cada etapa do workflow deriva do store, nunca é escrito à mão | `--only workflow` |
| P-104 | Uma etapa bloqueada nomeia o que falta e não executa nada | `--only workflow` |
| P-105 | Todo item de menu habilitado tem ação; todo item desabilitado tem motivo | `--only menus` |
| P-106 | A pilha de exibição não entra em nenhum manifesto nem em nenhuma agregação | `--only layers`, `architecture_check.sh` |
| P-107 | Esconder ou reordenar camadas não altera nenhum valor lido da fonte | `--only layers` |
| P-108 | Remover uma camada da vista não remove nada do projeto | `--only layers` |
| P-109 | A AOI só é desenhada no modo AOI ou como camada visível declarada | `--only tools`, storyboard |
| P-110 | Cancelar um desenho de AOI não cria versão | `--only tools` |
| P-111 | Trocar colormap ou limites não reescreve nenhum artefato | `--only layers` |
| P-112 | Toda rampa mantém nodata transparente e a divergente tem entradas ímpares centradas em zero | `--only io-render` |
| P-113 | Um e só um modo de ferramenta ativo, e a barra reflete o modo do canvas | `--only tools` |
| P-114 | Medição é recusada em CRS geográfico e bate com cálculo independente | `--only tools` |
| P-115 | A mensagem de erro pertence ao job que falhou, nunca ao painel | `--only jobs` |
| P-116 | Repetir um job cria uma run filha e preserva a pai | `--only jobs`, `--only store` |
| P-117 | O bloco `preview` é limitado, declara decimação e nunca é entrada de operador | `--only describe`, `--only protocol` |
| P-118 | Pré-visualizar não cria linha no store nem comita run | `--only import` |
| P-119 | Declarar CRS, reprojetar e reprojetar para exibição são operações distintas e rotuladas | `--only coordinates` |
| P-120 | A transformação de exibição não é alcançável a partir de `project/`, `commands/` ou do caminho de submissão | `architecture_check.sh` |
| P-121 | Toda coordenada exibida vem com o seu CRS, no formato escolhido | `--only coordinates` |
| P-122 | Nenhum caminho da interface depende de entrada exclusiva de teste | `--only vertical-slice`, storyboard |
| P-123 | Uma troca de tema só repinta: geometria idêntica ao pixel | storyboard `m55` |

## Ordem de trabalho

E1 → E2 → E3 → E4 → E5 → E6 → E7, com o gate completo rodado ao fim de cada
etapa e **parada na primeira regressão**. As três ADRs são escritas e aprovadas
antes de E1 (a MSP-002 e a MSP-004 antes de E2 e E4, a MSP-003 antes de E5),
porque cada uma decide uma fronteira que o código depois não pode renegociar.

## Estado das etapas

### E1 — `DONE` em `2026-09-01`

Entregue: `viewmodels/workflow_model.py` (estado derivado, função pura),
`qml/GeoPotential/WorkflowPanel.qml`, `qml/GeoPotential/AppMenuBar.qml`,
`workflow` e `currentStep` no `AppController`, sete atalhos, quatro diálogos de
Help, e `Navigator.qml` **removido**.

Evidência: gate **22/22** — os 20 anteriores intactos, mais `--only workflow`
(16 testes) e `--only menus` (9 testes, com o motor QML real carregado).
Arquitetura: 70 módulos, 11/11 negativos. Self-test 59/59. Storyboards 14/14.

Dois defeitos apareceram no caminho, ambos fechados:

1. **`state` e `action` são propriedades FINAL de `QQuickItem` e de
   `AbstractButton`.** Os papéis do modelo com esses nomes fizeram o shell
   inteiro deixar de carregar (`Cannot override FINAL property`), e o sintoma
   foi "Type WorkflowPanel unavailable" — uma mensagem que não aponta para a
   causa. Os papéis passaram a `stepState` e `stepAction`. É o segundo defeito
   deste projeto em que uma colisão de nome do Qt se apresenta como outra
   coisa; o primeiro foi o caminho de import do módulo QML.
2. **Ordem errada dos testes na derivação.** As etapas 6 e 7 liam
   `committed("decision.membership")` enquanto a 5 lia `approved`, e o painel
   mostrou a etapa 5 bloqueada com as etapas 6 e 7 abertas ao mesmo tempo. Um
   run comitado é o fato mais forte que o store guarda sobre uma etapa e passou
   a ser testado **primeiro**; 6 e 7 encadeiam no *estado* da 5, não no mesmo
   fato lido duas vezes. O teste
   `test_a_committed_run_is_never_reported_as_impossible` guarda isso.

Uma questão aberta que o E1 expôs e que o **E7** fecha: a interface está em
duas línguas. O workflow, os menus e os diálogos novos estão em português; o
Inspector, a TopBar, o Import Wizard e as mensagens do controller estão em
inglês. Unificar é trabalho de tradução com storyboard, não de implementação, e
está fora do E1 de propósito.

### E2 — `DONE` em `2026-09-02`

Pilha de exibição (`models/layer_model.py`, ADR-MSP-002), `LayerPanel.qml`,
dez rampas com inversão e limites em `render/colormap.py`, `MapItem` desenhando
N camadas com opacidade e ordem, modo AOI explícito com marcadores de vértice,
desfazer, cancelar e finalizar, Inspector lendo a camada ativa, painel de jobs
recolhível com filtro, detalhe por job e `retry`, e o fim da mensagem
`job failed` sem dono.

### E3 — `DONE` em `2026-09-02`

`MapToolBar.qml` com onze ferramentas em quatro grupos, modo ativo destacado e
descrito, medição de distância e área em `render/geocanvas/tools.py` — recusada
em CRS geográfico — e exportação do mapa como imagem da vista, que não cria run
nem artefato.

### Idioma — `DONE` em `2026-09-02`, fora do plano original

Estava no E7 e foi antecipado a pedido. `i18n/catalog.py` com 230 chaves em
português e inglês, `Translator` publicado como `controller.tr`, e um teste que
reprova qualquer literal numa tela traduzida — a lista de exceções está vazia.

Uma consequência: o texto que o **worker** produz (mensagens de job, vereditos
de QA/QC) continua só em inglês. É outro catálogo, do outro lado do IPC, e não
foi feito.

### Rodada de depuração com dados reais — `2026-09-02`

Fora do plano, a pedido, sobre os arquivos do usuário. Sete defeitos, todos
fechados:

1. **O veredito do QA/QC não era refeito ao declarar.** Digitar o CRS deixava
   o "cannot be used" antigo na tela e o botão Importar desabilitado. Agora
   declarar revalida sozinho (450 ms depois da última tecla) e a faixa diz
   "verificando" em vez de mostrar um veredito vencido.
2. **`extent.overlap` comparava CRSs diferentes** e bloqueava qualquer camada
   de outra área — `ADR-MSP-005`. A comparação passou a ser feita num CRS
   comum, e a severidade na importação passou a `WARNING`; a recusa dura
   continua na harmonização, com teste próprio.
3. **Criar projeto dependia do seletor de pastas**, que abre atrás do modal.
   A pasta virou campo editável e a criação funciona em qualquer diretório.
4. **Recentes só abriam com duplo clique.**
5. **Duas barras de cor**, nenhuma seguindo a camada. Sobrou uma, que agora
   mostra a rampa e os limites da camada ativa.
6. **Uma camada adicionada fora da vista não aparecia** e parecia não ter sido
   adicionada. A vista passa a ir até ela quando não há interseção.
7. **Storyboards e gates escreviam nos recentes e na preferência de idioma do
   usuário** — doze projetos de `/tmp` na lista de outra pessoa.

Acrescentado junto: tabela de atributos (botão direito na camada), menu de
contexto com enquadrar/atributos/detalhes/remover, arrastar-e-soltar arquivo,
camadas de pontos desenhadas a partir da prévia, e a explicação do painel de
jobs.

**O que a rodada expôs e ainda não está feito:** sem reprojeção de exibição
(E5), duas camadas em CRSs diferentes não se sobrepõem na tela. É a mesma peça
que falta para um mapa de fundo web, que vem em Web Mercator.

### E5 — `DONE` em `2026-09-02`

`geo/coordinates.py` (ADR-MSP-003): transformações e formatação só para
exibição, com transformers em cache, e o gate de arquitetura impedindo que
`project/` ou `commands/` a alcancem. `raster/warp.py`: uma camada é reprojetada
**para a foto**, nunca no arquivo — o SHA-256 é idêntico depois de desenhar em
três CRSs. `Exibir › Formato das coordenadas` com CRS da camada, UTM com a
zona, graus decimais e GMS, todos com hemisfério; `Exibir › CRS da vista` com
seguir a camada, WGS 84 e Web Mercator.

Dois defeitos achados aqui: a zona UTM era lida do **nome** do CRS, e
`NAD83 / UTM zone 12N` tem dois números — dava zona 83; e um CRS declarado como
`26912` é aceito pelo pyproj e recusado pelo rasterio, o que estourava fundo
dentro de um warp. Ambos com teste.

### Mapa de fundo — `DONE` em `2026-09-02`, ADR-MSP-006

Tiles XYZ de fontes abertas — OpenStreetMap (ODbL), OpenTopoMap (CC-BY-SA),
Carto Positron e Dark Matter (CC-BY) — desligado por padrão, com atribuição
obrigatória na tela, cache dentro do projeto registrando fonte, licença e data.
Google, Bing, Esri e Mapbox ficam de fora por licença, e há teste que reprova
se algum entrar.

`P-07` foi **estreitado, não abandonado**: continua proibido servidor, porta em
escuta, WebView e framework web, e o cliente de tiles é o único módulo do app
que fala rede — verificado por `ast`, com `self_test.py` isento por nome porque
o trabalho dele é provar que nenhuma porta escuta.

### E4 — `DONE` em `2026-09-03`

`render/geometry.py`: silhuetas vetoriais para RGBA, vetorizado — o único laço
Python percorre a espessura do traço, nunca os vértices, e há teste que lê o
que cada laço itera. `MapItem.addGeometryLayer` e o caminho de pintura
correspondente. **Fecha a lacuna que o M4 carregava**: um shapefile importado
agora aparece no canvas, em vez de entrar no painel e deixar a tela vazia.

`PreviewMap.qml` no assistente, com as três formas de desenhar segundo a
ADR-MSP-004: o raster lido direto do arquivo pela costura nomeada, o vetor pela
silhueta limitada, a tabela pela nuvem de pontos. Fatos por tipo (bandas,
overviews/COG, pixel em dois números, feições, geometria, camadas do
GeoPackage) e histograma ao lado do mapa. Escolha obrigatória da camada num
GeoPackage multi-camada (A26), que antes lia a primeira em silêncio.

Três defeitos achados aqui, todos com teste:

1. **Dois `MapItem` na cena.** Quem procurava "o canvas" por tipo passou a
   achar o do assistente. Os storyboards e o `interaction_check` continuaram
   verdes enquanto dirigiam uma tela vazia — `m4` caiu para 4/8 e a AOI parou
   de ser desenhada assim que o defeito apareceu. Canvas nomeados, busca por
   nome, e teste que exige exatamente um `mapCanvas`.
2. **Escalares numpy na descrição.** `json.dumps` aceita `numpy.float64`
   porque herda de `float`, então o vazamento passou por todo teste de
   codificação — e chegou no QML como objeto opaco sem `toFixed`.
3. **`Insufficient arguments`.** Um slot Qt chamado do QML com menos argumentos
   do que declara devolve `undefined` em silêncio.

### E6 — `DONE` em `2026-09-03`

`smokeInput` e `runSmokeOperator` removidos; `_build_engine` recebe só o
controller. O Run da barra superior executa a etapa em que o fluxo está, lida
do modelo — e uma etapa bloqueada diz o que falta em vez de submeter.
`HarmonizeDialog.qml` dá à etapa 4 a tela que faltava: CRS alvo, pixel e
política de extensão **escolhidos** e registrados no manifesto, nenhum
assumido. O arquivo dado na linha de comando passa a entrar pelo assistente,
como qualquer outro.

As quatro entradas de menu que diziam "chega no M5.5 E2" para trabalho já
entregue foram ligadas: remover camada, colormap (submenu por rampa),
propriedades (foca o painel) e renomear (`setName`, só exibição). O `auditTable`
passou a ser reconstruído quando a pilha muda — antes era um retrato do projeto
vazio, que é como quatro entradas mortas sobreviveram um milestone com o gate
verde.

Dois defeitos achados aqui:

1. **Segmentation fault** ao rodar as classes de UI juntas: `del engine`
   deixava objetos QML com eventos pendentes, e o `processEvents` seguinte
   despachava em memória liberada. Teardown determinístico.
2. **Todo artefato virava camada rotulada `membership [0-1]`**, inclusive um
   raster harmonizado ainda em mGal — cru sob nome de normalizado, que é
   exatamente a conflação que o contrato proíbe. `artifactReady` passou a
   carregar o operador que produziu o arquivo.

Novo storyboard **`flow`**: da janela vazia ao mapa de prospectividade, sem
argumento de linha de comando e pelos próprios controles (A32).

### E7 — `DONE` em `2026-09-03`

`Theme.qml` com quatro modos e **três paletas**: alto contraste é uma paleta
própria, medida em 21:1 no texto e nas bordas, com piso declarado de 7:1
(WCAG AAA) fixado antes de qualquer medição. Nenhum token métrico lê `mode`,
`dark` ou `contrast`, e `--only theme` verifica isso na fonte.

`preferences.py`: tema, formato de coordenada, fundo do mapa e quais painéis
estão abertos, em `QSettings`, fora de todo `.gpot`. QtCore puro — ler o
esquema do sistema precisa de QtGui e é o ponto de entrada que faz isso e
empurra a resposta, o que também torna `system` testável sem depender do
desktop de quem roda. Um valor desconhecido no arquivo cai no padrão.
`PreferencesDialog.qml` reúne as quatro escolhas numa tela (§9.11).

Novo storyboard **`themes`**: os quatro temas, com o retângulo dos seis painéis
nomeados comparado **exatamente** entre eles, e o frame `system` pixel a pixel
idêntico ao claro com a área de trabalho declarada clara.

**P-116 fechado junto**, fora do escopo desta etapa mas dentro do contrato do
milestone: `retry` passou a encontrar a run do job repetido e a gravá-la como
pai. A coluna existia desde o M2 e ninguém a preenchia.

A primeira evidência de geometria comparava mapas de borda das capturas e
acusou quatro colunas de terem se movido entre o escuro e o claro. Não tinham:
um detector de bordas mede o quanto uma borda é **visível**, o que muda com a
paleta por construção. A comparação passou a ler o retângulo dos objetos vivos.

### Rodada de depuração com dados reais — `2026-09-03`

Depois do fechamento, sobre os arquivos do usuário. Três achados:

1. **O botão Importar saía da tela com um CSV.** Regressão do E4: a prévia, o
   histograma e a tabela de atributos cresceram a coluna além do diálogo, o
   conteúdo transbordou o fundo — o que se via como "a janela fica meio
   transparente na parte final" — e a decisão foi empurrada para fora. Num
   modal centrado, que não se move, isso deixa o arquivo sem caminho de
   importação. A decisão virou **rodapé** do diálogo, o conteúdo rola, e a
   altura é limitada à da janela. Teste que exige as três coisas.
2. **O campo Unidade não explicava nada.** Ele não é decorativo: a regra
   `unit.declared` avisa quando falta, e `unit.plausible` compara a unidade
   declarada com faixas de magnitude — uma unidade errada produz um mapa que
   parece certo e está errado. Mas nenhum formato guarda a unidade, então ela
   nunca é preenchida sozinha, e a tela não dizia isso. Agora diz, a primeira
   entrada do combo é "— não declarada —" em vez de vazia, e o worker devolve
   as unidades que a faixa de valores **não contradiz**, lidas da mesma tabela
   que a QA/QC usa para julgar a resposta.
3. **A lista curta às vezes não é curta.** Uma faixa estreita cabe dentro de
   toda faixa larga: densidade entre 2,2 e 2,9 não contradiz mGal. A resposta
   honesta é listar tudo, e listar tudo não informa nada — então a linha só
   aparece quando a faixa do arquivo de fato excluiu alguma unidade. Para o
   dado do usuário, 3 de 6.

## Fechamento

`PASS` em `2026-09-03`. Gate **30/30**, 524 testes, self-test 59/59,
5 storyboards / 29 frames, arquitetura 84 módulos com negativos 11/11.
Evidência: `docs/validation/V-M5_5-interface.md`.

## Riscos

| Risco | Mitigação |
|---|---|
| A pilha de exibição virar uma segunda representação do domínio | ADR-MSP-002 e o teste negativo de P-106 antes da primeira linha de `layer_model.py` |
| `map_item.py` virar um god-file (518 linhas hoje, N camadas + 5 modos + medição depois) | separar `layers.py`, `tools.py` e `paint.py` dentro de `render/geocanvas/`, com paridade provada pelo gate de canvas atual |
| A prévia abrir a porta para arrays no IPC | teto numérico no protocolo, no schema e num teste de contrato |
| O tema claro mover a interface | comparação de capturas ao pixel, não inspeção visual |
| O escopo crescer para dentro do M6 | tudo o que é cenário, explicabilidade e ranking está nomeado em "Fora" |
