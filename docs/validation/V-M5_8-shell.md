# V-M5.8 — A interface repaginada

Data: `2026-09-03`
Versão: app `0.4.00`, worker `0.2.00`, protocolo `1.0.0`, schema `1.3.0`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §8; pedido do operador

## Resultado

`PASS`.

| Item | Valor |
|---|---|
| Gate | **32 de 32** |
| Testes | **692** unit/contract/integration + 59 checagens de interface |
| Storyboards | **8**, **41 frames**; `shell` é o novo, com 4 |
| Ícones | **35**, gerados por `tools/make_icons.py` |
| Botões de ícone na tela | **25**, todos com dica — medido, não afirmado |
| Worker | **não tocado**; a sua versão não muda |

## O que mudou

Só o visual. Nenhum operador, nenhum parâmetro, nenhum resultado.

| | |
|---|---|
| `tools/make_icons.py` | 35 SVGs, 24 × 24, desenho em 20 × 20, traço 1,5, uma cor. Um gerador para que o conjunto continue sendo uma família |
| `app/geopotential_app/icons.py` | image provider: renderiza o SVG e o pinta na cor que o tema pede |
| `ThemedIcon.qml`, `IconButton.qml` | um ícone que segue o tema; um botão que é ícone e diz o que é |
| `ActivityBar.qml` | a trilha da esquerda: as oito etapas, carregar arquivo, gerar grade, os quatro painéis, preferências |
| `TopBar.qml` | ações em ícones; o que está carregado em chips — projeto, CRS, camadas |
| `MapToolBar.qml` | os onze glifos viraram os onze ícones |
| `WorkflowPanel.qml` | uma linha por etapa; o parágrafo foi para a dica |
| `AppMenuBar.qml` | menu **Processamento**: as oito etapas e as cinco telas |
| `catalog.py` | 13 chaves novas, PT e EN |

## A decisão que a medição forçou

O jeito óbvio de recolorir um ícone é um shader — `ColorOverlay`, que o próprio
README dos ícones sugeria, ou `MultiEffect`. **Os dois foram testados e nenhum
desenha coisa alguma sob `QT_QPA_PLATFORM=offscreen`**, com um `Image` comum ao
lado renderizando corretamente:

| Caminho | Pixels não-fundo numa área de 48 × 48 |
|---|---|
| `Image` simples | 236 |
| `MultiEffect` colorization | **0** |
| `Qt5Compat` `ColorOverlay` | **0** |

Toda storyboard deste projeto é capturada offscreen. Um ícone tingido por
shader seria um **quadrado em branco em toda a evidência visual do gate**, e o
gate passaria, porque um quadrado em branco é um quadro válido. Por isso o
tingimento é feito na CPU, com `QPainter`, onde a resposta não depende de qual
loop de render está rodando.

É o mesmo tipo de armadilha que o `docs/conventions/visual-evidence.md` já
descreve, encontrada de novo e agora registrada em `icons.py`.

## Contratos novos

| ID | Contrato | Gate |
|---|---|---|
| P-161 | Todo botão de ícone carrega uma dica; uma dica vazia reprova | `--only tools`, storyboard `shell` |
| P-162 | Todo ícone nomeado na interface é um arquivo que existe | `--only tools` |
| P-163 | O conjunto de ícones bate com o seu gerador; nenhum é editado à mão | `--only tools` |
| P-164 | Um ícone é tingido na CPU, então desenha sob a plataforma offscreen | `--only tools`, storyboard `shell` |
| P-165 | A trilha é um painel: some, é lembrada, e volta idêntica | storyboard `shell` |

`P-125` — "um glifo que a fonte não desenha reprova o gate" — foi **substituído**
por `P-162`, que é o mesmo contrato mais forte: uma fonte tem ou não tem um
codepoint, mas um arquivo está ou não está lá. `--only tools` passou de 19 para
28 testes.

## Como foi provado

**A dica é obrigatória, e isso é um gate.** Negativado: uma `tip: ""` em
`TopBar.qml` derruba `--only tools` com 1 falha; restaurada, 28 testes `OK`.
Sem isso, "a palavra foi para a dica" seria uma frase num comentário.

**A janela real.** Storyboard `shell`, 4 quadros:

| Quadro | O que ficou provado |
|---|---|
| `01 opened` | 25 botões de ícone, **25 com dica**, 0 ícones nomeados sem arquivo |
| `02 rail_hidden` | a trilha some e a escolha é guardada nas preferências |
| `03 rail_back` | volta com os mesmos 44 px |
| `04 light` | tema claro, 25 botões ainda lá, a trilha com a mesma largura (P-123) |

Storyboard `themes` (4 quadros) continua verde: os quatro temas repintam sem
mover nada, agora com os ícones dentro.

`--self-test` 59/59. `interaction_check.py` 8/8, exit 0.

Contact sheet: `docs/validation/images/shell/contact_sheet.png`.

## O que este milestone NÃO entrega

- **`icons/jobs/` e `icons/layers/` continuam vazias.** O painel de jobs e o de
  camadas carregam o seu estado em texto e cor, não em ícone.
- **A trilha não é configurável.** O que está nela, e em que ordem, está em
  `ActivityBar.qml`.
- **Nenhum atalho de teclado novo.** A trilha e o menu Processamento chegam às
  etapas; nenhum dos dois tem acelerador.
- **O ícone da aplicação não foi desenhado.** `icons/app/` tem ícones de
  interface; o ícone de janela e de lançador que o M8 precisa não está lá.
- **A dica é a do Qt.** Sem formatação, sem atraso ajustado por controle, e um
  controle desabilitado não recebe hover — que é por que toda entrada de *menu*
  desabilitada continua com a razão no rótulo.
- **A largura da trilha é fixa.** 44 px, do `Theme`, e não arrastável.
