# M4 — GeoCanvas nativo

Status: `PASS`
Entry gate: `OPEN` — M3 verde, 15/15
Exit gate: `PASS` — 17/17, `../validation/V-M4-geocanvas.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §20 M4, §10, MSP-05,
MSP-09, §9.1, §9.3

## Objetivo

**Ver o dado sem mentir sobre ele.** O M3 decidiu se um dado pode ser usado; o
M4 mostra-o — em qualquer escala, com a coordenada e o valor corretos sob o
cursor, e sem travar a interface enquanto carrega.

A frase que governa o milestone é do §10.1: **"Evite carregar raster inteiro na
memória gráfica sem necessidade."** Um canvas que lê 4 GB para desenhar 800 ×
600 pixels não é lento — é errado, e falha exatamente quando o dado deixa de
ser um exemplo.

E a armadilha que o gate existe para pegar: **o valor sob o cursor tem de vir
da fonte, não do tile decimado que está na tela.** Um LOD que também responde
"qual é o valor aqui" devolve a média de 64 pixels e chama isso de medição.

## Escopo

Dentro:

| Item | O que significa aqui |
|---|---|
| pirâmides e overviews | escolher o nível pelo zoom; usar os overviews do arquivo quando existem |
| tiles e cache LRU | ler em janelas, guardar as janelas lidas, descartar as antigas por tamanho |
| LOD | o nível de decimação é função da escala, e é registrado no readout |
| preview progressivo | um nível grosseiro aparece antes do fino; a UI nunca espera |
| pan e zoom | o canvas hoje só encaixa a extensão; passa a navegar |
| readout | coordenada e valor sob o cursor, **amostrados da fonte em resolução plena** |
| escala | barra de escala em unidade do CRS, com o número |
| legenda | rampa, faixa e unidade, por camada |
| vetores | desenho com simplificação por LOD, índice espacial, seleção e picking |
| AOI | desenhar, editar, salvar, reutilizar, versionar, com provenance (MSP-09) |
| split view | duas camadas lado a lado, mesma extensão e mesma escala |
| difference map | `A − B` sobre o grid comum, como operador do worker |
| Project Hub | as superfícies do §9.1, carregadas do M2 e do M3 |
| Data Inspector | o painel do §9.3, com o histograma desenhado |

Fora (nomeado para que a ausência seja escolha):

- `QQuickRhiItem`, `QSGRenderNode`, shaders — o §10 os permite *quando
  necessário*; a necessidade é uma medição, e ela ainda não existe. O caminho
  é `QQuickPaintedItem` até que um profiling diga o contrário, e essa decisão
  fica registrada com o número que a sustenta.
- hillshade — §10.1 o lista; depende de um DEM e de uma convenção de
  iluminação que ninguém declarou ainda. **M5**, com o operador que o produz.
- lineamentos e polígonos de target — §10.2 os lista; são produtos de M6/M7,
  e desenhar uma camada que nada produz seria desenhar um exemplo.
- AHP, Fuzzy, WLC — **M5**
- cenários, sensibilidade, ranking — **M6**
- gravity, magnetics — **M7**
- empacotamento — **M8**

## Gate M4

As cinco exigências do §20, cada uma um check executável.

| # | Exigência | Como é provado |
|---|---|---|
| G1 | raster grande abre sem bloquear UI | um raster muito maior que a janela é aberto e desenhado lendo **uma fração** dos pixels; o número lido é medido e comparado com o total |
| G2 | coordenada sob cursor correta | ida e volta tela↔mapa exata, sob pan e sob zoom, em vários níveis de LOD |
| G3 | valor sob cursor correto | o valor amostrado bate com o pixel **da fonte**, não com o do tile decimado — testado num nível de LOD onde os dois diferem |
| G4 | AOI persistente | uma AOI desenhada sobrevive a fechar e reabrir o projeto, com sua versão e sua provenance |
| G5 | comparação operacional | split view alinhado, e um difference map calculado pelo worker sobre o grid comum |

Testes do §10.4, todos os seis:

| Teste | O que prova |
|---|---|
| snapshots | a mesma entrada desenha a mesma imagem |
| coordenadas numéricas | ida e volta exata, e norte para cima |
| amostragem numérica | o valor vem da fonte, em qualquer LOD |
| picking | o vértice/feição escolhido é o mais próximo do cursor |
| LOD | o nível escolhido é função da escala, e é o mesmo para a mesma escala |
| exportação visual | o PNG exportado tem a extensão e a escala que a tela tem |

## Invariantes que o M4 acrescenta

- **O LOD é de exibição. A amostragem é da fonte.** Nenhum readout, nenhuma
  estatística e nenhuma AOI pode ser calculada a partir de um tile decimado.
- **Um tile é cache, nunca resultado.** O cache é descartável, endereçado por
  (camada, nível, janela), e apagá-lo não muda nada além do tempo.
- **O canvas não lê arquivo.** A leitura vive numa camada de I/O própria
  (`raster/`), e `render/` continua sendo numpy → pixels. Isso mantém o gate
  numérico sem janela e fecha a costura aberta no M1.
- **Uma AOI é um objeto versionado com proveniência**, não um retângulo
  guardado numa propriedade da view.
- **Pan e zoom nunca alteram a fonte.** Só a janela de leitura muda.

## Ordem de trabalho

1. `raster/`: leitor por janela, escolha de nível, cache LRU.
2. Canvas: pan, zoom, LOD, preview progressivo, escala, legenda.
3. Readout amostrado da fonte, provado contra o tile decimado.
4. Vetores: simplificação por LOD, índice espacial, picking.
5. AOI: desenho, edição, persistência, versão, provenance.
6. Split view e o operador `grid.difference`.
7. Project Hub e Data Inspector.
8. Testes do §10.4, checks no `--self-test`, relatório e `PROJECT_STATE.md`.

Nenhum item avança com o gate do anterior vermelho.

## Fechamento

Fechado em `2026-09-01` com **17/17** no gate e **51/51** no `--self-test`,
estável em três execuções. Evidência: `../validation/V-M4-geocanvas.md`.

Os cinco itens do gate G1–G5 estão verdes, e os seis tipos de teste do §10.4
existem. A costura que o M1 abriu — `render/` autorizado a ler arquivo — está
fechada: a leitura mudou para `raster/`, e o gate de arquitetura passou a ter
onze classes de violação testadas negativamente em vez de dez.

**Dois itens do escopo carregados do M2 e do M3 foram entregues aqui**, e não
carregados uma terceira vez:

| Item | Entregue |
|---|---|
| Project Hub (§9.1) | criar, abrir, duplicar e recentes, com o relatório de recuperação mostrado na abertura |
| Data Inspector (§9.3) | o painel dividido em THE DATA e THE VIEW, com o histograma desenhado |

Relink continua sendo comando sem tela — é a única superfície do §9.1 que
falta, e ela pertence ao Data Manager mais do que ao Hub.

**O que ficou de fora do M4, nomeado:** vetores no canvas (§10.2), hillshade e
preview progressivo (§10.1), `QQuickRhiItem` e shaders (§10, "quando
necessário" — e a necessidade é uma medição que ninguém tomou). Os três estão
em `PROJECT_STATE.md` com o milestone que os recebe.
