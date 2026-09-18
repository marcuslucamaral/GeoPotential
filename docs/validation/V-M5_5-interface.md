# V-M5.5 — Interface profissional

Data: `2026-09-03`
Versão: app `0.2.00`, worker `0.1.00`, protocolo `1.0.0`, schema `1.3.0`
Milestone: `docs/milestones/M5_5_INTERFACE.md`
Decisões: `ADR-MSP-002`, `ADR-MSP-003`, `ADR-MSP-004`, `ADR-MSP-005`,
`ADR-MSP-006`

## Resultado

`PASS`. As sete etapas E1–E7 executadas, mais o idioma e o mapa de fundo, que
entraram fora do plano original.

Reproduzir com `./tools/run_gate.sh` a partir de `geopotencial_msp/`.

| Item | Valor |
|---|---|
| Gate | **30 de 30** |
| Testes | **578** unit/contract/integration + **59** checagens de interface |
| Arquitetura | `PASS` — 84 módulos; negativos **11/11** |
| Storyboards | **5**, **29 frames**: `flow` 5, `m4` 8, `m5` 6, `m55` 6, `themes` 4 |
| Janela real | `interaction_check` 8/8, com 2 camadas ainda desenhadas ao fim |

O gate ganhou um check nesta etapa: `theme`. `preview` passou a declarar Qt
como dependência real — a metade dele que prova que um vetor chega à tela não
pode ser silenciosamente pulada.

## O que cada gate provou

| # | Etapa | Como foi provada |
|---|---|---|
| G1 | O workflow diz a verdade | `--only workflow`, `--only menus`: `derive(Facts)` é função pura, o estado é recalculado do store e bate com o exibido. |
| G2 | Nenhum menu morto | `--only menus` percorre a `auditTable` da barra real — e agora **com uma camada ativa** também, que é o estado que a auditoria nunca via. |
| G3 | A pilha de exibição é exibição | `--only layers`: o snapshot só carrega campos de exibição; reordenar não altera estilo. |
| G4 | A AOI é um modo | Storyboard `m55`: **1 062 pixels** da cor da AOI com o modo ativo, **0** depois de sair, com `expect` entre dois frames. |
| G5 | O colormap pertence à camada | `--only layers`: SHA-256 do artefato idêntico depois de dez restilizações. |
| G6 | O erro fica no job certo | `--only menus`: o desfecho vive na linha do job. |
| G7 | A prévia não importa | `--only preview` (39 testes) e `--only import`: nenhuma linha no store, e `PreviewMap.qml` não nomeia controller, submit nem store. |
| G8 | Nada de CRS silencioso | `--only coordinates`, `--only domain`: as três operações distintas; arquivo sem CRS recusado por nome. |
| G9 | Medição honesta | `--only tools`: distância e área dentro de 1e-9 de cálculo independente; CRS geográfico recusado. |
| G10 | O fluxo é real | Storyboard **`flow`**, 5/5: janela vazia → mapa de prospectividade, **sem argumento de linha de comando**, pelos próprios botões. |
| G11 | Tema só repinta | Storyboard **`themes`**, 4/4: os seis painéis nomeados com retângulo idêntico nas quatro paletas, comparação exata. |
| G12 | Nada regrediu | 29 checagens anteriores verdes, self-test 59/59, storyboards `m4` e `m5` intactos. |

## E4 — a prévia dos formatos

`render/geometry.py` transforma a silhueta que o worker amostrou em RGBA. Todo
segmento é rasterizado de uma vez por uma construção `repeat`/`arange`; o único
laço Python percorre a espessura do traço, e há teste que lê **o que cada laço
itera**, não como está escrito.

Isso fechou a lacuna que o M4 nomeou e carregou: até aqui um shapefile
importado entrava no painel de camadas e não desenhava nada, porque ia para
`addLayer`, que abre arquivos com rasterio.

`PreviewMap.qml` desenha os três casos pelo caminho que a `ADR-MSP-004` manda:
o raster lido direto do arquivo pela costura nomeada — a ADR é explícita que
raster **não** viaja como prévia —, o vetor pela silhueta limitada, a tabela
pela nuvem de pontos. Verificado nos quatro arquivos reais do repositório
(`.tif`, `.shp`, `.gpkg`, `.csv`), e a correspondência dos seis formatos do
MSP-03 para os três tipos desenháveis é asserção, não suposição.

**A26** está fechado: um GeoPackage com mais de uma camada exige a escolha, e
a escolha viaja como declaração do operador — testado com um arquivo de duas
camadas construído no próprio teste.

## E6 — o fluxo real

`smokeInput` e `runSmokeOperator` saíram; `_build_engine` recebe só o
controller, verificado por assinatura. O Run executa a etapa em que o fluxo
está, lida do modelo; uma etapa bloqueada nomeia o que falta em vez de
submeter. `HarmonizeDialog.qml` deu à etapa 4 a tela que faltava: CRS alvo,
pixel e política de extensão escolhidos e registrados no manifesto — não existe
CRS padrão (ADR-004) e interseção e união são mapas diferentes (P-82).

O arquivo dado na linha de comando entra pelo assistente, com QA/QC, como
qualquer outro: continua sendo conveniência, deixou de ser um segundo caminho.

Quatro entradas de menu que diziam *"chega em M5.5 E2"* para trabalho já
entregue foram ligadas. O `auditTable` passou a ser reconstruído quando a pilha
muda: antes era um retrato do projeto vazio, que é como quatro entradas mortas
sobreviveram um milestone inteiro com o gate verde.

**P-116** fechou junto: `retry` agora encontra a run do job repetido e a passa
como pai, do comando ao `commit_run`. A coluna `parent_run_id` existia desde o
M2, com índice, e ninguém a preenchia — o docstring do `retry` já reivindicava
a linhagem que o código não gravava.

## E7 — temas, e o que um tema pode fazer

Quatro modos: `dark`, `light`, `highContrast`, `system`. O alto contraste é uma
**terceira paleta**, não a escura aumentada, e as razões são medidas:

| Token sobre o fundo | Razão |
|---|---|
| `text` | **21,00:1** |
| `border` | **21,00:1** |
| `textMuted` | 17,14:1 |
| `warn` | 15,33:1 |
| `ok` | 15,30:1 |
| `accent` | 12,80:1 |
| `error` | 10,50:1 |

O piso declarado é **7:1**, WCAG AAA para texto corrido, fixado no teste antes
de qualquer medição e não ajustado depois. As paletas escura e clara são
mantidas em 4,5:1 (AA) para texto. A fórmula de contraste é ela própria
verificada contra os extremos conhecidos — branco sobre preto dá 21:1, uma cor
sobre si mesma dá 1:1 — porque uma fórmula errada aprovaria qualquer paleta.

**Geometria idêntica**, e é aqui que a evidência mudou de forma. A primeira
tentativa comparou mapas de borda extraídos das capturas e acusou quatro
colunas de terem se movido entre o tema escuro e o claro. Não tinham: um
detector de bordas mede o quanto uma borda é **visível**, o que muda com a
paleta por construção, e ele não sabe distinguir "o painel se moveu" de "a
borda ficou mais fraca". O storyboard passou a ler o retângulo dos seis painéis
nomeados dos objetos vivos e a compará-los **exatamente**, sem tolerância — e
`--only theme` verifica na origem que nenhum token métrico de `Theme.qml` lê
`mode`, `dark` ou `contrast`.

`system` é testado sendo empurrado, não lido: o storyboard declara a área de
trabalho como clara e o frame resultante é **pixel a pixel idêntico** ao do
tema claro — 0 pixels diferentes. Um gate que dependesse do desktop do
desenvolvedor estar no modo certo não provaria nada.

`preferences.py` guarda tema, formato de coordenada, fundo do mapa e quais
painéis estão abertos, em `QSettings`, **fora de todo `.gpot`** — um projeto é
dado, e layout não é. Um valor desconhecido no arquivo cai no padrão em vez de
deixar a interface num estado sem paleta. O módulo é QtCore puro; ler o esquema
do sistema precisa de QtGui e é o ponto de entrada que faz isso e empurra a
resposta, o que também é o que torna o comportamento testável.

## Defeitos encontrados no caminho

Todos fechados, todos com teste. Nenhum foi encontrado por leitura de código.

1. **Dois `MapItem` na cena.** `PreviewMap` trouxe um segundo canvas, e tudo
   que procurava "o canvas" pelo tipo passou a achar o do assistente. Os
   storyboards e o `interaction_check` **continuaram verdes dirigindo uma tela
   vazia** até o `m4` cair para 4/8. Canvas nomeados, busca por nome, e teste
   que exige exatamente um `mapCanvas` e nenhum anônimo.
2. **Segmentation fault** ao rodar as classes de UI juntas. `del engine`
   soltava a referência Python e deixava objetos QML com eventos na fila; o
   `processEvents` seguinte despachava em memória liberada, e a falha aparecia
   numa classe de teste depois, sem nada apontando para a causa. Teardown
   determinístico: `deleteLater` nas raízes e a fila drenada antes de soltar.
3. **Todo artefato virava camada rotulada `membership [0-1]`** — inclusive um
   raster harmonizado ainda em mGal. Cru sob nome de normalizado, que o
   contrato proíbe explicitamente. `artifact_type` no protocolo é o formato do
   arquivo (`GeoTIFF`) e não diz o que os valores são; `artifactReady` passou a
   carregar o operador que produziu o arquivo.
4. **Escalares numpy atravessando a descrição.** `json.dumps` aceita
   `numpy.float64` porque ele herda de `float`, então o vazamento passou por
   todo teste de codificação — e chegou ao QML como objeto opaco sem `toFixed`.
   Teste novo compara `type(...)`, não `isinstance`, que é exatamente por que
   isto era invisível.
5. **`Insufficient arguments`.** Um slot Qt chamado do QML com menos argumentos
   do que declara devolve `undefined` em silêncio; a prévia do vetor não
   desenhava e nada dizia por quê.
6. **Chave duplicada no catálogo.** Python constrói o dicionário sem reclamar e
   fica com a última. Teste que reprova qualquer chave escrita duas vezes.
7. **Esperar por um binding QML.** Um driver que espera `validated` virar
   verdadeiro retorna na hora, porque o binding ainda não reavaliou e ainda
   carrega o veredito do arquivo anterior. O `flow` espera pelo **store**, que
   é o que o import de fato consulta.

## Correções depois do fechamento — `2026-09-03`

Encontradas pelo usuário, sobre os arquivos dele, e é o tipo de defeito que
nenhum gate deste milestone teria pego: o `import_preview` do storyboard `m55`
usa um shapefile de seis polígonos, cuja prévia é curta. Um CSV de 3 735 linhas
traz mapa, histograma e tabela, e a coluna passou da altura do diálogo.

1. **Importar saía da tela num CSV.** A decisão virou rodapé do diálogo, o
   conteúdo rola, e a altura é limitada à da janela. Três testes: o diálogo
   nunca excede a janela, o botão está dentro do `footer`, e o conteúdo é um
   `ScrollView`.
2. **A unidade não se explicava.** Passou a dizer por que é perguntada, o que
   acontece se ficar em branco, e quais unidades a faixa do próprio arquivo
   não contradiz — da mesma tabela que a QA/QC julga a resposta, para que a
   sugestão e o veredito não possam divergir. Continua sem adivinhar: um
   arquivo não tem onde guardar a sua unidade, então ela é sempre asserção.
   Para o dado do usuário: `mGal, nT, m`, 3 de 6.

Gate depois das correções: **30/30**, 578 testes.

### Segunda rodada com dados reais — `2026-09-03`

3. **O catálogo duplicava.** `add_dataset` fazia `INSERT` com um `uuid4()` novo
   a cada chamada, então importar o mesmo arquivo outra vez — o que acontece
   naturalmente ao reabrir um projeto — criava uma segunda linha com o mesmo
   caminho e o mesmo hash. O diálogo de harmonização oferecia `dem.tif` três
   vezes e `Distance_to_fault.tif` quatro. Não era defeito de tela: era esta
   linha. Mesmo caminho e mesmo conteúdo passam a devolver o id existente;
   mesmo caminho com **conteúdo diferente** continua sendo dataset novo,
   porque o arquivo mudou sob o projeto e as runs que usaram os bytes antigos
   gravaram o hash antigo.
4. **A harmonização levava o catálogo inteiro.** Uma análise é um subconjunto
   do que o projeto guarda, não tudo. Cada camada ganhou uma caixa de seleção,
   e o diálogo avisa quando as camadas escolhidas estão em mais de um CRS —
   que é para o que a etapa serve, e também é como uma interseção sai vazia.
5. **Três botões cinzas sem explicação** no painel de jobs. `Cancelar` e
   `Abrir resultado` estavam corretamente desabilitados para um job concluído
   de `qc.validate_dataset` — que não tem o que cancelar nem artefato para
   abrir — mas nada dizia isso, e um ToolTip nunca dispara num controle
   desabilitado. O motivo virou texto. `Repetir` sempre funcionou.

## Contratos protegidos que entram

`P-103` a `P-115`, `P-116` a `P-123`, e `P-124` a `P-138`, que este trabalho
acrescentou ao plano. Todos estão em `docs/PROJECT_STATE.md` com o gate que os
verifica.

## O que este milestone não entregou

Nomeado para que a ausência seja escolha registrada.

- **Renomear e propriedades de camada não têm tela própria.** Renomear é um
  diálogo de um campo; "propriedades" foca o painel de camadas, que **é** as
  propriedades. Uma segunda superfície com os mesmos controles seriam dois
  estados de uma coisa só.
- **A persistência de layout guarda visibilidade, não proporções.** Quais
  painéis estão abertos é lembrado; a posição dos divisores do `SplitView` não.
- **`system` não distingue "desconhecido" de "escuro".** Qt reporta `Unknown`
  em plataformas que não sabem responder, e o padrão desta aplicação é escuro,
  então só um `Light` explícito muda o que é pintado.
- **Vetor no canvas é a silhueta da prévia, não o dado.** Limitada a 2 000
  vértices pela `ADR-MSP-004`, sem seleção, sem picking e sem tabela de
  atributos ligada ao mapa. §10.2 continua aberto e é onde o M6 encosta.
- **O worker fala inglês.** As mensagens que ele produz não passam pelo
  catálogo; só a aplicação é bilíngue.
- **`grid.idw` e `grid.euclidean_distance`** continuam planejados, marcados
  para um M5 que já fechou. MSP-06 pede os dois.
