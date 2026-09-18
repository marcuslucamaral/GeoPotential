# Changelog — GeoPotential Professional (MSP)

Every update to this tree, numbered. The scheme is the workspace's:
`../docs/VERSIONING.md`. `MAJOR` stays at `0` until the application does the
thing it exists to do end to end.

Two packages, two version sources — `app/geopotential_app/_version.py` and
`worker/geopotential_worker/_version.py` — because they ship as two processes
and a mismatched pair has to be visible rather than inferred. An entry names
both.

Each entry says what the update delivers **and what it does not**, because a
changelog that only lists gains is how a project loses track of its own gaps.

---

## app `0.8.10` — 2026-09-18 · Abrir um projeto traz o projeto de volta

Quatro relatos de quem usou o produto. Um deles produzia **mapa
cientificamente errado**, em silêncio.

### Abrir um projeto vinha com a tela vazia

O `.gpot` guardava tudo desde sempre — no projeto relatado, 2 datasets, 7
runs, 7 artefatos, 28 jobs e 13 eventos de procedência. **Nada estava
perdido.** O que faltava era repor: `_after_open` abria a sessão, recuperava e
ligava os controladores, e nunca reconstruía a pilha de camadas.

Agora repõe, em duas passadas — os dados importados, depois o que foi
computado deles —, com o papel que cada operador declara. No projeto relatado:
**9 camadas** onde antes vinham zero. Arquivo movido ou apagado é pulado em
vez de entrar como linha quebrada; quem reporta isso é a recuperação (`P-206`).

### As âncoras da camada anterior contaminavam a seguinte

O pior dos quatro. Elas eram preenchidas `if (xMin.length === 0)`, então uma
vez postas sobreviviam a toda troca de camada. Aberto numa camada de 2,25 a
2,86 e reaberto num MDE de **120 a 1005**, o `x_max` continuava 100 — todo
pixel saturava, e o mapa saía com faixa `1,0000 a 1,0000`, média `1,0000`. O
sigmoidal, com centro 2,5 sobre a mesma faixa, dava curva plana.

Nada na tela dizia por quê, e o número estava lá para ser lido. Agora trocar
de camada limpa as âncoras e elas são rederivadas; a descrição que chega
depois — o pedido é read-only e a resposta vem por sinal — **não** sobrescreve
o que foi digitado (`P-207`).

### Tudo era pedido duas vezes

`describeLayer` guardava contra repetir com `if layer_id in
self._layer_description` — e esse dicionário só é preenchido **quando a
resposta chega**. O painel seguindo a camada ativa e a tela de pertinência
abrindo pediam antes dela, e saíam dois jobs para o mesmo arquivo. Era o
`described dem.tif` duplicado na lista (`P-208`).

### Reaplicar a curva empilhava rasters

Três tentativas de curva deixavam três camadas quase com o mesmo nome e nada
dizia qual era a da vez. Reaplicar passa a **substituir** a pertinência
anterior daquela camada de origem. O nome ganhou o sufixo `_membership`, para
que a camada diga o que é além de de onde veio.

### O seletor de camada estava vazio

Uma chamada de função numa ligação de propriedade QML é avaliada **uma vez**,
na carga do shell — quando ainda não há camada nenhuma. Passa a ser preenchido
ao abrir a tela.

Evidência: gate 37/37, 1000 testes, o quadro `flow/04` medindo
`membership_layers=2 membership_names=2 unique_paths=2`, e o projeto real
`teste_2.gpot` restaurando 9 camadas.

**O que não entrega:**

- **A vista não é persistida.** A ordem da pilha, a visibilidade, a opacidade
  e o colormap não são guardados: reabrir traz as camadas, não o arranjo.
- **Não há exportação.** Os GeoTIFF estão em `<projeto>/artifacts/` e abrem no
  QGIS como estão; o que falta é um "Exportar" que os copie para onde a pessoa
  quer, com um nome que ela escolha.
- **Reabrir um projeto anterior a esta versão traz as duplicatas que ele já
  tinha.** Elas são históricas; o código novo não cria mais.
- **O AHP continua sem caminho na interface.**

---

## app `0.8.09` · worker `0.5.06` — 2026-09-18 · A etapa 5 passa a produzir mapa

Quatro defeitos relatados por quem usou o produto, numa sessão só. Nenhum era
visível de dentro, e o fio comum é o mesmo: **telas que anunciavam um
resultado sem produzi-lo**.

### A pertinência não gerava mapa nenhum

A etapa 5 promete, na própria tela, *"PRODUZ: critério NORMALIZED em [0,1]"*.
Ela não produzia: `decision.membership` existe, é testado, e **ninguém o
chamava**. Aplicar registrava uma linha numa lista e mais nada — a agregação
recalculava a pertinência por dentro e o mapa normalizado nunca existia.

Ninguém conseguia conferir uma curva antes de combiná-la, que é exatamente
onde uma curva mal escolhida se reconhece.

Agora Aplicar produz a camada. `membership [0-1]`, e numa linear ancorada no
mínimo e no máximo ela varre **0,0000 a 1,0000** — medido no quadro.

### Reaplicar duplicava o critério

`criteria` era montado com `concat`: aplicar de novo na mesma camada
**acrescentava** um segundo critério sobre o mesmo raster, a lista mostrava o
mesmo nome duas vezes e a agregação o contava duas vezes. Passa a substituir,
com o caminho do arquivo como chave — dois arquivos podem ter o mesmo nome e
continuar sendo dois dados.

### Não havia como escolher a camada, nem tirar critério da análise

- **Seletor de camada no editor de pertinência.** Antes era preciso fechar o
  diálogo, clicar na camada certa no painel e reabrir: a tela agia sobre a
  camada ativa, não dizia que agia, e não deixava trocar.
- **Caixa por critério na agregação.** A tela anunciava o que ia fazer e não
  deixava mudar de ideia sem refazer a pertinência de tudo.

### Tudo se chamava `prospectivity`

Três execuções deixavam três arquivos com o mesmo nome e nada os distinguia.
O resultado passa a se chamar pelo que foi feito —
`suitability_gamma70_3crit`, `suitability_wlc_2crit` — e o critério pela
camada **e pela curva**: `density_500m_sigmoidal`. Duas curvas diferentes
sobre o mesmo raster são dois critérios diferentes, e chamá-los pelo nome do
arquivo escondia justamente a diferença.

### O vocabulário de pertinência estava partido em dois

`decision.membership` aceitava seis funções e `decision.aggregate` aceitava
oito: `circular` e `categorical` eram utilizáveis na agregação e **recusadas**
no operador que produz o mapa. Unificado — e as duas trazem âncora declarada,
não derivada da população, porque resolver percentil sobre código de classe
trataria `3` como magnitude três vezes `1`.

### A conta do gamma foi conferida, e está certa

Relatado que um resultado com fuzzy não varria 0 a 1. **Não é defeito.** Os
casos que fixam a convenção fecham:

```
todos 0.0 -> 0.0000     um zero -> 0.0000     todos 0.5 -> 0.3307
todos 1.0 -> 1.0000     um um   -> 0.5000
```

E com pertinências **sigmoidais** — que se aproximam de 0 e 1 sem tocá-los —
a entrada vai de 0,0038 a 0,9752 e a saída de 0,0010 a 0,9561. A saída não
varre o intervalo porque a entrada não varre; a implementação é Zimmermann e
Zysno (1980) literal. Uma pertinência **linear** ancorada no mínimo e no
máximo varre, e é o que o quadro novo mostra.

### Um erro meu no caminho, e como apareceu

A primeira versão de `runMembership` mandava `result_name`, que
`decision.membership` **não declara**. O job era recusado por parâmetro
desconhecido, nenhuma camada aparecia, e o quadro media `membership_layers=0`
enquanto o resto passava — foi a asserção nova que o pegou, não o olho.

Evidência: gate 37/37, o quadro `flow/04` medindo
`unique_paths=2 reapplied_function=linear_decreasing membership_layers=3`, e o
`flow/05` seguindo verde.

**O que não entrega:**

- **O AHP continua sem caminho na interface**, e com ele a razão de
  consistência — recusa bloqueante por contrato.
- **O nome do resultado não é editável na tela**: é derivado, e quem quiser
  outro ainda não tem onde escrever.
- **Reaplicar a pertinência deixa o raster anterior no projeto.** A camada
  nova entra, a velha continua lá, e ninguém as reconcilia.
- **A tela não explica por que o resultado não varre 0 a 1.** A conta está
  certa e a expectativa é legítima; falta a frase que liga uma coisa à outra.

---

## app `0.8.08` — 2026-09-18 · A combinação ponderada produz um mapa

Encontrado por quem usou o produto, como o editor de pertinência foi:
normalizar, pedir o MCDA, e **nenhum mapa aparecer**. A causa são três coisas
que se somam, e nenhuma delas era visível de dentro.

1. **`runDecision` montava o pedido sem pesos.** Método, gamma, nome do
   resultado e critérios — e nada mais. `decision.aggregate` recusa a
   combinação ponderada sem eles, com a mensagem certa: *"sem pesos não há
   combinação, só uma média que ninguém escolheu"*. Quem escolhia o método
   ponderado recebia um job vermelho no lugar do mapa.
2. **`lastAhp` era declarado `({})` e nunca atribuído.** A coluna de peso
   mostrava `—` para todo critério, sempre.
3. **A aplicação nunca chamava `decision.ahp_weights`.** O operador existe,
   é testado, e não tinha chamador nenhum na interface.

**Por que nenhum gate pegava:** a storyboard `flow` montava o pedido no próprio
driver e chamava `runDecision` com `fuzzy_gamma` — que **não usa peso**. Um
quadro que roda gamma não consegue notar peso faltando, e o caminho ponderado
nunca tinha sido percorrido pela interface em rodada nenhuma.

### O conserto

- **O pedido é montado num lugar só**, `DecisionModel.request()`, e a tela
  passa a expô-lo. O funil `runDecision` repassa o que o operador declara;
  uma chave que a tela monta e ele deixa cair é uma decisão perdida em
  silêncio, que é literalmente o que acontecia.
- **`weights` acompanha só o método que os usa.** Mandá-los para o gamma
  registraria na procedência uma escolha que não afetou o resultado.
- **Peso editável por critério** quando não há AHP, com **peso igual como
  ponto de partida declarado** — um default silencioso aqui seria uma escolha
  científica que ninguém fez. Normalizado para somar 1: pesos que não somam 1
  não são pesos, são uma escala arbitrária que muda o mapa sem dizer.
- **De onde os pesos vieram** vai junto (`weight_source`: `ahp` ou `manual`).
  Um peso afirma uma prioridade, e a origem da afirmação entra na procedência
  com ela.
- Tudo zerado volta ao igual: peso zero em tudo não é uma ponderação, é a
  ausência de uma.

### A storyboard passa a apertar o botão

O quadro `05 prospectivity` deixou de montar o pedido e passou a **pressionar o
`decisionRun` de verdade**, com o método **ponderado** de propósito. E afirma a
pergunta que quem usou o produto fez — *o mapa apareceu?*:

```
pressed=True  outcome=Succeeded  method=weighted_linear_combination
weighted=2    artifacts=1        layers_before=4 -> layers_after=5
```

`layers_before` contra `layers_after` é a asserção que faltava em toda a
árvore: uma run que termina e não põe camada nenhuma na pilha produz um mapa
que existe em disco e não aparece na tela.

Evidência: 6 testes em `--only menus`, o quadro `flow/05`, gate 37/37.
Negativados: contra o código anterior, 2 falham e 2 dão erro, e o traceback
mostra o `runDecision` sem `weights` literalmente.

**O que não entrega:**

- **O AHP continua sem caminho na interface.** `decision.ahp_weights` é
  chamável e não é chamado: falta a tela da matriz de comparação par a par. A
  razão de consistência, que é uma recusa bloqueante por contrato, não tem
  como ser calculada de dentro do produto.
- **`overrideReason` continua sem destino.** A tela coleta a justificativa
  para uma matriz inconsistente e ela não vai a lugar nenhum — porque o
  parâmetro pertence ao `ahp_weights`, que ninguém chama.
- **As correlações não chegam à tela.** `lastCorrelations` é declarado e nunca
  atribuído, pelo mesmo motivo: o resultado da agregação traz
  `correlation_findings` e ninguém os lê de volta.
- O peso é um número e não um comparativo. Quem quer dizer "A é três vezes
  mais importante que B" ainda tem de traduzir isso em 0,75 e 0,25 na mão.

---

## app `0.8.07` — 2026-09-15 · Uma região, vários tipos de medida

O caso que o produto existe para consumir — **várias grandezas sobre o mesmo
terreno** — não tinha onde ser exercitado do jeito difícil. Utah FORGE são seis
tabelas esparsas e um raster, tudo num CRS só. O dataset de deslizamento são
vinte camadas, todas raster, todas já numa grade. Nenhum dos dois faz o produto
atravessar **um raster contra um levantamento esparso em dois CRS diferentes**,
que é o caso comum.

`../data/southern_africa/`, sobre o Bushveld — a maior intrusão máfica
acamadada conhecida:

| Camada | Tipo | Formato | CRS | Grandeza |
|---|---|---|---|---|
| `southern_africa_topography.tif` | raster 2048² com pirâmide | GeoTIFF | `EPSG:3857` | elevação, m |
| `southern_africa_gravity.csv` | esparso, 14 359 pontos | CSV + sidecar | `EPSG:4326` | gravidade **observada**, mGal |
| `../bushveld_gravity/` | esparso, 3 877 estações | CSV + sidecar | `EPSG:4326` | Bouguer e perturbação, mGal |

As estações do Bushveld caem **100 % dentro** do raster de topografia, e isso é
medido pelo gate, não afirmado no README (`P-201`).

- **A corrente inteira roda sobre a região**: o esparso vira grade, os dois vão
  para uma grade só e a agregação sai. Medido: interseção de **140 × 89 a 5 km**
  = 12 460 células, **88,2 %** com score. Os dois números estão fixados no
  teste — uma grade que encolhesse para meia dúzia de células faria o resto das
  asserções passar sem nada ter sido harmonizado.
- **Observada contra anomalia.** O regional traz gravidade observada, perto de
  978 000 mGal; o Bushveld traz a anomalia, perto de zero. Tratar uma como a
  outra dá um mapa diferente sem dizer nada, e é por isso que as duas estão
  aqui.
- Um **terceiro domínio**, gateado como tal: nem geotermia em Utah, nem
  deslizamento na Coreia.

### Procedência

| | |
|---|---|
| Gravimetria | NOAA NCEI, via `fatiando-data`, DOI `10.5281/zenodo.5882430`, CC-BY |
| SHA256 de origem | `f5f8e5eb…2cac`, **conferido no download** |
| Topografia | AWS Terrain Tiles (Mapzen), zoom 6, 16 tiles `6/34..37/35..38` |

**A topografia não veio da fonte óbvia, e o motivo está registrado.**
`fatiando-data/southern-africa-topography` (DOI `10.5281/zenodo.6481379`) foi
baixado e teve o SHA256 conferido — `3e3878a4…1bef` — e é **netCDF4, que é HDF5
por baixo**. Nada no ambiente que este projeto fixa lê isso: o GDAL do rasterio
não tem o plugin HDF5, o `osgeo` não expõe driver netCDF, e `scipy.io.netcdf` lê
netCDF3 apenas. Instalar um driver mudaria o ambiente que o contrato fixa, então
o arquivo **não está aqui** e a topografia veio de uma fonte em GeoTIFF.

O mosaico foi montado com `rasterio.merge` sem reamostragem, escrito em tiles
256×256 com deflate e pirâmide `2, 4, 8`, e **sem nodata declarado** — os
valores negativos são batimetria, e declarar uma sentinela abriria um buraco que
o dado não tem.

**O que não entrega:**

- **Nenhuma geologia nesta região.** A pergunta de prospecção montada no teste é
  elevação contra anomalia; um mapa litológico faria dela uma pergunta de
  verdade, e não há um em formato que o produto leia.
- **A topografia é de tile de visualização, não de produto científico citável.**
  As AWS Terrain Tiles agregam SRTM, GMTED e ETOPO1 sem um DOI único, então a
  procedência aqui é mais fraca que a dos outros diretórios — e está dito.
- **A região não tem storyboard.** A corrente roda num teste; não há quadro
  mostrando o mapa dela na tela.
- `../data/` passou de 99 MB para 105 MB.

---

## app `0.8.06` · worker `0.5.05` — 2026-09-15 · Todo arquivo de `../data/` é exercitado

Medido antes de consertar: **26 dos 56 arquivos** de `../data/` não eram
citados por teste nem storyboard nenhum da árvore. Doze camadas de
deslizamento, dois levantamentos do Utah FORGE, e quase tudo que o M0 gerou em
`data/synthetic/` e depois parou de usar.

Um fixture sem uso é pior que um fixture ausente: ocupa espaço, aparece na
documentação como se provasse alguma coisa, e quando quebra nada avisa.

- **`--only data-coverage`** (`P-199`) anda no diretório em vez de nomear
  arquivos, então acrescentar um fixture já o põe no gate. Três exigências:
  ser um formato que o produto declara ler, ser legível por `describe`, e ter
  procedência no diretório — `README.md` para dado de terceiros,
  `MANIFEST.json` para o gerado. Verificado que recusa: um arquivo intruso faz
  o gate falhar.
- **A ciência roda sobre os órfãos** (`P-200`), não só a leitura. As 19
  camadas de deslizamento numa agregação só; os dois levantamentos do Utah que
  ninguém tinha aberto viram grade; a magnetometria real atravessa derivada
  vertical e sinal analítico.
- **Os fixtures defeituosos são conferidos contra o próprio manifesto**, regra
  **e severidade**. Um BLOCKER que virou aviso continua sendo acusado e deixa
  de parar a run, que é o que ele existe para fazer.
- `data/synthetic/` e `data/utah_forge/` ganharam o `README.md` que não
  tinham; foi o gate novo que apontou os dois.
- **Regra nova**: `docs/conventions/test-data.md`.

### Dado buscado, com procedência conferida

Três lacunas que o produto declarava cobrir e nenhum arquivo comprovava:

| Diretório | O que é | Fonte | Licença |
|---|---|---|---|
| `britain_magnetic/` | **aeromagnetometria real**, 4 102 pontos em 99 linhas de voo | British Geological Survey, via `fatiando-data`, DOI `10.5281/zenodo.5879260` | CC-BY |
| `bushveld_gravity/` | **gravimetria real**, 3 877 estações, Bouguer de -178 a +75 mGal | NOAA NCEI + ETOPO1, DOI `10.5281/zenodo.6511942` | CC-BY |
| `natural_earth/` | o primeiro **`.geojson`** da árvore, 127 polígonos | Natural Earth | domínio público |

**Os SHA256 de origem foram conferidos no download**, contra os que a fonte
publica — não depois, não confiando na fonte.

Até aqui **todo gate de campos potenciais rodava sobre um campo sintético que
este projeto gerava**: FIS-01 a FIS-08 testavam a aritmética, não o dado. E os
dois levantamentos são **geográficos**, então também é neles que a recusa de
operação métrica em graus passa a ser provada contra dado real em vez de
contra um fixture escrito para disparar a recusa.

O aeromagnético foi **recortado** numa janela — `-3.2..-1.6`, `53.2..54.2` —
porque o arquivo de origem tem 21 MB e 541 509 pontos. Recorte retangular e
não amostragem: em campo potencial a geometria é o dado, e um subconjunto
espalhado de linhas de voo teria um espectro que o levantamento original não
tem.

### Um defeito que a cobertura encontrou

**`describe` morria lendo um CSV com coluna de identificador.**
`data/synthetic/stations.csv` começa com `station`, que traz `ST0000`, e o
palpite de coluna de valor pegava a primeira não-coordenada — a de texto — e a
leitura estourava com `ValueError: could not convert string to float: 'ST0000'`,
sem nomear coluna nenhuma. Uma tabela de levantamento com coluna de
identificador é comum.

Agora o palpite **exclui coluna de texto** — não é um palpite melhor, é uma
exclusão: texto não pode ser medida em leitura nenhuma. E declarar uma coluna
de texto como `value_field` é recusado por nome, listando as numéricas.

**O que não entrega:**

- **`../data/` passou de 73 MB para 99 MB.** O aeromagnético recortado são
  152 KB, mas o repositório continua carregando 69 MB de fixtures sintéticos
  que nada mede — `msp/canvas/` sozinho são dois rasters de 16 Mpx.
- **A magnetometria real não tem storyboard.** Ela atravessa os operadores num
  teste; não há quadro mostrando o sinal analítico dela na tela.
- **RTP, tilt, continuação e espectro radial continuam só em sintético.** O
  dado real entrou em dois dos oito operadores.
- **`.vat.dbf`, `.gml` e `.kml` continuam declarados legíveis sem um arquivo
  que o comprove** — o gate exige que cada *família* tenha arquivo, não cada
  extensão.
- **Nenhum raster multibanda.** `band` é parâmetro de vários operadores e todo
  fixture aqui tem uma banda só.

---

## app `0.8.05` · worker `0.5.04` — 2026-09-15 · O que o código de classe significa

A tabela pontuava `1`, `2`, `3` e não sabia dizer qual era granito. Quem
pontuava tinha de segurar a legenda na cabeça ou em outra janela — e a nota de
cada classe é a decisão científica inteira.

- **Três lugares carregam a legenda, e os três são lidos** (`P-197`), na ordem
  `.meta.json` → RAT do `.aux.xml` → `CategoryNames`. O sidecar é o que alguém
  escreveu para este projeto de propósito, então ganha de uma tabela que pode
  ter viajado com o arquivo de outro estudo; a RAT ganha de `CategoryNames`
  porque **nomeia** o código que rotula, enquanto `CategoryNames` só o implica
  pela posição.
- **De onde a legenda veio aparece na tela** (`P-198`). Um rótulo afirma o que
  um código significa, e uma afirmação sem origem não é conferível.
- **Um código que a legenda não menciona fica visivelmente sem nome** — `—` na
  célula, e a contagem do que falta abaixo da tabela. Inventar "classe 3"
  faria uma legenda ausente parecer presente. Ele continua pontuável: quem
  decide se sabe o bastante é quem pontua, não o arquivo.
- Uma legenda que não nomeia **nenhum** dos códigos presentes é a legenda de
  outro raster, e não é mostrada.
- Uma legenda ilegível é uma legenda ausente: nunca impede o raster de ser
  usado.
- Sem legenda a coluna não existe. Uma coluna vazia em toda linha seria a tela
  prometendo o que não tem.

**Os formatos não foram supostos.** Os dois XML foram confirmados contra o GDAL
3.12 antes de serem parseados: uma RAT escrita à mão volta por
`GetDefaultRAT()` com os mesmos códigos e nomes, e `SetCategoryNames` escreve
exatamente o bloco `<CategoryNames>` que o leitor entende.

**Lido com a biblioteca padrão.** `osgeo.gdal` leria os três numa chamada e
está no ambiente de desenvolvimento, mas não é dependência declarada de nenhum
dos dois pacotes e teria de entrar no bundle congelado para funcionar numa
máquina que só tem o release.

Evidência: 10 testes em `--only describe`, 5 em `--only menus`, e o quadro
`03_classes` da storyboard `other_domain`, que passa a medir `named=3
unnamed=1 legend=sidecar`. Negativados: sem o módulo, 9 dos 10 testes de
unidade dão erro e 4 dos de interface falham.

**Um limite do ambiente de teste, contornado e não escondido:** sob
`offscreen` a `ListView` não recebe altura e não instancia delegate nenhum,
então `findChild` sobre uma linha da tabela acha `None` mesmo com a tabela
correta. O teste afirma o **valor a que a célula se liga**; que a linha desenha
é o que o quadro de storyboard prova, com a imagem.

**O que não entrega:**

- **`.vat.dbf` não é lido.** O ArcGIS escreve a legenda nesse formato, que é um
  dBASE binário e não um XML — outro parser, e nenhum arquivo aqui tem um para
  testar contra.
- **O RAT embutido no próprio GeoTIFF não é lido.** O GDAL 3.x grava no tag
  `GDALMetadata`, sob `<Item name="DEFAULT_RASTER_ATTRIBUTE_TABLE" role="rat">`,
  e o rasterio não o alcança — `tags()`, `tags(ns=...)` e `get_tag_item` voltam
  vazios. Alcançá-lo exige ler o tag TIFF na mão ou acrescentar `osgeo`.
- **Nada escreve uma legenda.** O produto lê a de quem tem e não oferece criar
  uma; quem não tem continua digitando nome nenhum.
- **A legenda não entra no manifesto.** O `mapping` que vai para a procedência
  continua sendo `{código: nota}`, sem os nomes — quem reproduz a run vê 4 e
  não "aluvião".
- **Nenhum arquivo do repositório traz legenda**, então a evidência é uma cópia
  da geologia real com um `.meta.json` declarado ao lado. Os códigos e as
  contagens são do arquivo de verdade; só a legenda é montada.

---

## app `0.8.04` · worker `0.5.03` — 2026-09-15 · As duas extensões, antes de escolher

A política de extensão decide o resultado inteiro, e era escolhida às cegas: a
tela pedia interseção ou união antes de qualquer número existir. Os dois
números estavam medidos na suíte `mixed-sources` desde o `0.8.01` — 100 %
contra 27,7 % de células com score — mas quem operava só os via depois de
rodar, uma vez cada, comparando de cabeça.

- **`grid.compare_policies`** (`P-195`), read-only: mede as duas sem
  harmonizar, sem registrar run e sem escrever artefato. A estimativa é
  produzida chamando `harmonize` numa grade decimada, de modo que **não pode
  divergir** do operador cujo resultado ela prevê.
- **O número que a prévia revelou e os dois anteriores não davam** (`P-196`): a
  área **com score** é a mesma nas duas políticas. Um score precisa de todos os
  critérios (ADR-MSP-004), então as células pontuadas são a interseção das
  máscaras qualquer que seja a extensão da grade — a união só acrescenta área
  vazia. Medido no Utah FORGE: 13 875 células nas duas, contra 50 020 no total
  da união. Medido na storyboard `gridding`, onde o contraste é maior ainda:
  **1 661 nas duas**, com a união entregando um mapa 56× maior, 98,5 % dele em
  branco.
- Cada camada reporta a própria fração, que é o que diz **qual** delas encolhe
  a interseção — no Utah, Vp com 31,2 % contra falha com 84,6 %.
- Uma interseção vazia volta como resposta, não como falha: é precisamente o
  que se precisa saber antes de escolhê-la, e é o que faria a harmonização
  falhar depois.
- A estimativa **diz em que grade foi estimada**. Uma fração sem isso é lida
  como exata.
- Trocar o CRS, o pixel ou as camadas invalida a medida na tela: números de uma
  grade ao lado dos controles de outra seriam lidos como sendo desta.

**Um contrato pegou o nome do parâmetro.** A primeira versão chamava o
orçamento da grade de estimativa de `preview_cells`, e o `P-117` recusou: neste
projeto *preview* é o arranjo decimado que cruza o IPC para desenhar
(ADR-MSP-004), e nenhum operador pode tomar um como entrada. Grandeza diferente,
nome diferente — `estimate_cells`, pela mesma regra que separou `spread` de
`angularSpread`.

**E o `P-24` pegou o próprio teste**, como já tinha feito no `0.8.01`: comparar
duas vezes num teste só reescrevia a grade da primeira.

Evidência: 7 testes em `--only mixed-sources`, o quadro `04_policies` da
storyboard `gridding`, e o gate 36/36. Negativados: sem o operador, os 7
falham.

**O que não entrega:**

- **A prévia não desenha.** Diz quantas células e que fração, e não mostra
  *onde* — a mancha que a união acrescenta não aparece no canvas.
- **Nada recomenda uma política.** É deliberado: elas respondem a perguntas
  diferentes e a escolha é científica. Mas significa que a tela informa e não
  orienta.
- **A estimativa custa uma reprojeção grossa por camada por política.** Com 20
  camadas isso é 40 reprojeções, e o botão é manual por causa disso — não mede
  sozinho a cada tecla digitada.
- **A fração por camada não entra no manifesto da harmonização**, só no
  resultado da sonda, que é read-only e não é gravada.

---

## app `0.8.03` · worker `0.5.02` — 2026-09-15 · A tabela de classes

Geologia, uso do solo e solo eram inalcançáveis pela interface, e o motivo era
uma volta fechada: `membership.categorical` recusa qualquer código sem nota — a
recusa está certa, pontuar zero uma classe desconhecida transforma uma lacuna
de dado em afirmação científica — mas o editor não sabia listar os códigos.
Satisfazer a recusa exigia **já saber** quais eram. É onde quem usou o produto
parou, e era o primeiro dos próximos passos.

- **O worker passa a expor os códigos** (`P-193`). `describe` reconhece uma
  camada de classes por ela ser integral e ter poucos valores distintos, e
  devolve cada código com a contagem. Em dado real: `geology.tif` 4 classes,
  `landcover.tif` 9, `soil_drainage.tif` 5; `slope.tif` e `aspect.tif` não são
  oferecidas. O `dem.tif`, que é integral e **não** é camada de classes, volta
  com 885 distintos e nenhum código listado — a tela diz quantos são e manda
  reclassificar, em vez de só recusar.
- Custo limitado por aritmética, não por ordenação: um raster cujo intervalo
  passa de 100 000 é descartado antes de qualquer conta por pixel, e a
  contagem é `bincount` sobre o intervalo deslocado, não um `unique` que
  ordenaria 16 milhões de valores a cada descrição.
- **A tabela na tela**: um código por linha, com a fração de área que ocupa e
  a nota que recebe. A área está lá porque uma classe que cobre 0,1 % do mapa
  e uma que cobre 97,2 % não merecem o mesmo cuidado — os dois números são de
  `geology.tif`.
- **Aplicar espera a tabela inteira** (`P-194`), dizendo quantas classes
  faltam. O worker recusaria o código sem nota de qualquer forma; recusar aqui
  diz *onde* está a lacuna em vez de devolver um job vermelho. Uma nota fora
  de `[0, 1]` não conta como nota.
- A curva **não** é desenhada sobre classes: entre geologia 2 e geologia 3 não
  há "mais", e uma curva ali desenharia uma ordem que não existe.
- Trocar de camada zera as notas; a descrição da **mesma** camada chegando
  depois não zera, ou o que já foi digitado se perderia quando o worker
  responde.

Evidência: 8 testes em `--only describe`, 7 em `--only menus` e o quadro
`03_classes` da storyboard `other_domain`, que dirige a cadeia inteira — camada
ativa, `openMembership`, descrição pelo IPC, tabela preenchida — e mede
`codes=4 described=True missing_before=4 apply_before=False missing_after=0
apply_after=True`. Negativados: contra o código anterior os 7 testes de
interface falham e a suíte `describe` não importa.

**O que não entrega:**

- **O código continua sendo um número.** A tabela mostra `1`, `2`, `3`, `4`, e
  não "granito", "xisto". Um raster de classes pode trazer uma tabela de
  atributos (`.dbf`, `.vat`, RAT do GDAL) com o rótulo de cada código, e nada
  aqui a lê. Quem pontua precisa saber por fora o que cada código significa.
- **Nada sugere uma nota.** É o certo — a nota de cada classe é a decisão
  científica inteira — mas significa que uma camada de 40 classes ainda são 40
  campos a preencher à mão.
- **Uma camada de classes não é detectada como tal na importação.** O wizard
  continua tratando todas como contínuas; o editor é o único lugar que sabe.
- O limite de 64 classes não é configurável, e acima dele o produto só sabe
  mandar reclassificar — não sabe reclassificar.

---

## app `0.8.02` — 2026-09-05 · O editor de pertinência recebe a camada

Encontrado por quem usou o produto, não por um gate: abrir o passo 5 mostrava
**"sem distribuição"**, âncoras vazias e nenhuma curva — com o Inspector logo
ao lado exibindo a faixa e o histograma da mesma camada.

O `MembershipEditor` era instanciado com o controller e o manipulador do sinal,
e `criterion` ficava `{}`. Ele nunca recebia a camada.

- A pertinência agora abre sobre a **camada ativa**, lendo `layerDescription` —
  a mesma fonte que o Inspector lê, e não a última coisa que o wizard
  descreveu, que é uma camada diferente sempre que algo foi calculado.
- Quando a descrição ainda não chegou, o pedido read-only é feito e a resposta
  preenche o editor já aberto.
- Sem camada ativa, diz o que falta em vez de abrir um diálogo vazio.
- `P-192`, negativado: contra o código anterior o teste falha em três
  asserções.

**Por que nenhum gate pegava:** nenhum abria o editor. As storyboards atribuíam
`functionName` direto e nunca liam `ready`, então a curva era exercitada e o
caminho que a alimenta, não.

**Um defeito meu, pego pelo próprio teste novo:** `activeLayer()` devolve
`layerId`, não `id`. A primeira versão lia a chave errada e trocava um editor
vazio por uma recusa — outro defeito, no lugar do primeiro.

---

## app `0.8.01` · worker `0.5.01` — 2026-09-05 · A corrente `.csv` + `.tif`

O caminho que o produto existe para percorrer — dois CSV que precisam virar
grade, mais um raster que já existe, numa análise só — **nunca tinha sido
testado de ponta a ponta.** As peças eram gateadas; a corrente que as liga,
não.

Rodada, ela fecha, e mede o seguinte no Utah FORGE:

- As três fontes ficam em **três grades diferentes** (206×130, 125×125 e
  821×979 a 10 m). Agregar sem harmonizar é recusado nomeando a camada.
- A **política de extensão decide o resultado inteiro**: `intersection` dá
  100 % de células com score, `union` dá 27,7 % — porque um score precisa de
  todos os critérios (ADR-004) e a união inclui onde só um mediu. Nenhuma está
  errada; elas respondem a perguntas diferentes.
- Em ambas, a fração válida do agregado **bate exatamente com a interseção das
  máscaras**. Se divergisse, algum operador estaria inventando ou perdendo
  célula.
- Qual coluna do CSV vira critério é declarado: `vp_500_m.csv` tem Vp e Vs, e
  escolher uma produz um raster diferente da outra.

**Um defeito encontrado no caminho:** `write_geotiff` **sobrescrevia em
silêncio**. O `P-24` — uma saída nunca é sobrescrita em silêncio — era imposto
só no Project Store, pelo UNIQUE de `artifact.path`. Na aplicação os dois nunca
se encontram, porque cada run escreve no seu diretório; o buraco só apareceu
quando um harness rodou duas operações no mesmo diretório e mediu a saída da
segunda acreditando ser a da primeira. Agora o escritor recusa, a recusa
preserva o arquivo que protege e não deixa `.tmp`, e `overwrite=True` existe
para quem quiser mesmo.

Três contratos novos, `P-189` a `P-191`; suíte `mixed-sources` com 14 testes.

**Não entrega**: a corrente não é um comando só — são três runs e três cliques,
o que é deliberado mas não é oferecido como receita; a política de extensão não
tem prévia, e a pessoa escolhe antes de ver os dois números; e `overwrite=True`
ainda não tem nenhum chamador.

---

## app `0.8.00` · worker `0.5.00` — 2026-09-05 · A aplicação fora da geofísica

A aplicação sempre foi agnóstica de domínio **por desenho** — só 8 dos 26
operadores são de geofísica. Mas isso nunca tinha sido **provado**: todo gate e
toda storyboard rodavam sobre o dataset geotérmico de Utah.

Rodar o caminho MCDA sobre `../data/conditioning_factors/` — 20 camadas de
suscetibilidade a deslizamento, EPSG:5186, Coreia — **achou dois defeitos**,
porque Utah tem um tipo de camada e este tem três.

- **`categorical` estava declarada e não estava ligada.** Existe no módulo de
  pertinência desde o M5, está em `FAMILY`, é testada — e o operador de
  agregação não a chamava. Pedi-la dava `membership 'categorical' is not
  known; use one of categorical, ...`, uma mensagem que se contradiz na
  própria frase. Sem ela, geologia, uso do solo e os quatro de solo não podiam
  ser critério.
- **Direção não tinha pertinência nenhuma.** `aspect` é azimute: 359° e 1°
  estão a dois graus um do outro, e toda função punha os dois nas pontas
  opostas — medido, 0,9989 contra 0,0028. Entrou `circular`, cosseno levantado
  sobre a distância angular pelo caminho curto.
- **E `circular` recusa azimute negativo.** Ferramentas de terreno escrevem
  `-1` para célula plana — 6 053 delas neste dataset — e `-1` não é um azimute
  perto de zero. Como um negativo também pode ser um ângulo escrito do outro
  lado, embrulhar em silêncio escolheria uma leitura e estaria errado na
  outra; a recusa nomeia as duas.
- Suíte `other-domain` com 17 testes; storyboard `other_domain` com 4 quadros,
  provando EPSG:5186 no caminho inteiro, 99,6 % de células válidas numa
  agregação que mistura contínuo e categórico, e o leave-one-out do M6 sobre
  856 695 células.
- Dois contratos novos, `P-187` e `P-188`. `docs/validation/V-DOMAIN-landslide.md`.

**Não entrega**: a tabela de classes não tem tela (funciona por parâmetro);
nada reclassifica um contínuo em classes; nada verifica que uma camada
declarada como classe é discreta; a célula plana continua sendo decisão de
quem opera; e 16 das 20 camadas do dataset não foram exercitadas.

---

## app `0.7.01` · worker `0.4.01` — 2026-09-05 · O que o dado é passa a ser declarado

Uma lacuna do M7, encontrada por uma pergunta e não por um gate: **os
operadores de campos potenciais aceitavam qualquer raster métrico.** Eles
rodavam uma continuação para cima num MDE sem dizer nada. O manifesto
registrava a convenção e a borda, e não registrava a suposição mais forte de
todas — que o campo é harmônico.

- **A bancada pergunta o que o dado é**: gravimétrico, magnético, ou outro. Não
  há default: adivinhar "isto parece gravimetria" a partir de uma faixa de
  valores é o tipo de suposição que este projeto não faz.
- **Cinco transformações passam a ser recusadas** num campo declarado como não
  potencial: derivada vertical, sinal analítico, tilt, continuação para cima e
  regional/residual. Todas dependem de `d/dz`, que num campo potencial é
  **inferido do dado horizontal** pelo operador `|k|` — e esse `|k|` sai da
  equação de Laplace. Num MDE isso infere uma dimensão que o dado não tem.
- **A RTP passa a exigir campo magnético**: ela depende da natureza dipolar.
- **O que continua valendo em qualquer campo contínuo** é dito na recusa:
  derivadas horizontais, gradiente horizontal total e o espectro radial são
  matemática de grade, não física de potencial. Um THG num MDE é realce de
  borda legítimo.
- A razão vai **no rótulo** do item indisponível, não numa dica — um item
  desabilitado não recebe hover. Mesma regra dos menus desde o M5.5.
- O tipo declarado entra no manifesto ao lado da convenção.
- Dois contratos novos, `P-185` e `P-186`; 13 testes novos; um quadro novo na
  storyboard `potential_fields`.

**Não entrega**: nada verifica que um campo *declarado* como gravimétrico de
fato é um. A declaração é de quem opera, registrada e imposta; a aplicação não
a audita contra o dado. Uma declaração errada produz um mapa errado com
procedência correta.

---

## app `0.7.00` · worker `0.4.00` — 2026-09-04 · Campos potenciais

Gravimetria e magnetometria. O M7 manda implementar a suíte sintética
**primeiro**, e a razão apareceu em execução: **dois defeitos reais foram
encontrados por ela**, e nenhum seria visto por um filtro comparado consigo
mesmo.

- **Oito operadores**: derivadas direcionais, gradiente horizontal total,
  sinal analítico, tilt, continuação para cima, regional/residual, redução ao
  polo, e o espectro radial. O `PLANNED` do registro caiu de sete nomes para
  um.
- **A suíte sintética**: a esfera enterrada de Blakely §3.1, com as três
  derivadas e a continuação **em forma fechada**. Cada operador é medido
  contra ela, nunca contra outra FFT (FIS-04).
- **A convenção viaja com o resultado** (FIS-02): z para baixo, altura para
  cima, x leste e y norte, a unidade por transformação. Está em todo manifesto
  e na tela, não só num docstring.
- **A borda é um parâmetro** (FIS-03): reflexão, taper, recorte, e os cinco
  números no manifesto de toda execução.
- **A bancada do §9.4**, no menu Processamento, com os sete requisitos da
  seção — incluindo o alerta de instabilidade da RTP, que acende **antes** de
  executar.

**Os dois defeitos que a suíte pegou:**

O taper decaía para a **média** da grade em vez de para a **borda**. Numa
anomalia toda positiva e concentrada isso constrói um degrau logo fora do
dado, e o erro de borda ia de 1,85e-4 (padding sem taper) para 5,74e-4 — pior
que não ter taper. Contra a borda: 1,56e-4, o melhor dos quatro.

O **coeficiente de Nyquist** não tem par conjugado numa grade de lado par, e
toda derivada horizontal de ordem ímpar deixa de ser hermitiana ali. A suíte
sintética roda em 201 × 201, ímpar, e passava; foi o campo real 4096 × 4096
que acendeu a checagem de hermitianidade — a checagem que existe justamente
porque um `.real` esconderia um erro de convenção.

Dez contratos novos, `P-175` a `P-184`; suíte `potential-fields` com 53
testes; storyboard `potential_fields` com 4 quadros.
`docs/validation/V-M7-potential-fields.md`.

**Não entrega**: ingestão de line data e XYZ com histórico de reduções; IGRF
(MSP-15 o condiciona a metadados que a aplicação não coleta); RTE; extração de
lineamentos (MSP-15 a quer com edição e confirmação humana, e sem as duas ela
é interpretação automática, que o §23 proíbe); minimum curvature; um modo de
comparação lado a lado dedicado; e uma tela para o espectro radial. FIS-07,
paridade Python/C++, **não se aplica**: não há C++, por ADR-007.

---

## app `0.6.00` · worker `0.3.00` — 2026-09-04 · Cenários e sensibilidade

O M5 responde "onde". Este responde as duas perguntas que decidem se alguém age
sobre aquilo: **por que este pixel, e o que muda se a escolha tivesse sido
outra.** Sete das onze perguntas do §17 não tinham resposta; agora têm.

- **Cinco operadores**: `scenarios.leave_one_out` (tira um critério por vez e
  mede o que o mapa perde), `scenarios.sensitivity` (varre gamma ou o peso de
  um critério), `scenarios.explain` (decompõe o score de uma célula),
  `scenarios.rank_targets` (os melhores lugares, como lugares e não pixels) e
  `reporting.manifest` (o manifesto da run, como arquivo que se entrega a
  alguém).
- **Uma tela de cenários**, no menu Processamento, com as duas tabelas. Ela
  **mede e não decide**: não troca peso, não re-roda a agregação e não esconde
  critério.
- **Todo número vem com o tamanho da amostra.** Um rho sobre 300 células e um
  sobre 300 000 não são a mesma evidência.
- **A decomposição diz o que é.** Para WLC, `w·m` é exato e as parcelas somam o
  score. Para os operadores fuzzy não existe decomposição aditiva de um
  produto: reporta-se a parcela do logaritmo, e o resultado carrega o nome
  disso para o número nunca ser lido sob o significado errado. Um critério em
  zero é nomeado como veto, em vez de virar parcelas de `-inf`.
- **Os quatro `scenarios.*` são read-only.** `leave_one_out` chegou a escrever
  um raster de diferença por critério e isso saiu: `grid.difference` é o
  operador para isso desde o M4.
- **Um defeito que o teste pegou**: `np.argsort` põe NaN no fim, então
  invertida a ordem os nulos vêm primeiro e `rank_targets` devolvia zero alvos
  num mapa com nulos.
- Nove contratos novos, `P-166` a `P-174`; suíte `scenarios` com 50 testes;
  storyboard `scenarios` com 4 quadros, medindo sobre 16 587 485 células.
- `docs/milestones/M6_SCENARIOS.md`, `docs/validation/V-M6-scenarios.md`.

**Não entrega**: sensibilidade a resolução (§17.7); otimização de pesos; Monte
Carlo (a varredura é determinística, um parâmetro por vez, e a limitação viaja
com o resultado); relatório em PDF (M8); cenários salvos entre projetos; a
explicação clicável no mapa — os operadores existem e são testados, a tela usa
só os dois de sensibilidade; e a linha da limitação aparece em inglês, porque
vem do worker.

---

## app `0.5.00` · worker `0.2.00` — 2026-09-03 · Um executável para Ubuntu

O produto passa a ter build. `tools/build_app.sh --clean` gera as fixtures,
roda o gate da árvore, empacota com PyInstaller e **verifica o binário que
saiu** — e um binário que não passa não vira arquivo.

- **Dois processos num arquivo.** O supervisor lançava
  `sys.executable -m geopotential_worker`; num bundle `sys.executable` é o
  próprio binário, e isso abriria uma segunda interface. `tools/frozen_entry.py`
  despacha por argv, e o binário sabe ser qualquer um dos dois. Ele fica em
  `tools/`, fora de `app/`, então `P-02` continua valendo: nenhum módulo dos
  dois pacotes aprende que o outro existe.
- **Defeito corrigido no caminho:** `QProcess.processEnvironment()` volta
  vazio, então o worker filho recebia só `PYTHONPATH` e `PYTHONUNBUFFERED` —
  sem `PATH`, sem `LD_LIBRARY_PATH`. Passa despercebido num checkout e quebraria
  num bundle. A base agora é `systemEnvironment()`.
- **Verificado rodando, não lendo log**: `--help`, o worker respondendo de
  dentro do bundle (13 operadores), e — em `env -i`, sem `PATH` para o ambiente
  de desenvolvimento — `--self-test` **59/59** e uma captura de 1440×880 com
  1167 cores distintas. Um PNG de uma cor só é uma janela que não compôs, e o
  script reprova abaixo de 50.
- **`tools/install.sh` viaja dentro do arquivo**: instala em `~/.local` sem
  root, ou em `/opt` com `--system`, cria o comando e a entrada de menu, e
  desinstala. Testado de ponta a ponta numa máquina simulada — extrair,
  instalar, 59/59, desinstalar sem deixar resto.
- `docs/INSTALL.md`, `docs/validation/V-BUILD-linux.md`,
  `docs/conventions/packaging.md`.

617 MB instalados, 258 MB comprimidos.

**Não entrega**: Windows e macOS (cada um precisa da sua construção, nenhuma
foi feita); `.deb`, assinatura, repositório `apt`, ícone de aplicação e CI —
isso é o M8. `libxcb-cursor0` e `libxkbcommon-x11-0` continuam sendo
dependência de sistema, porque conversam com o servidor gráfico. E as fixtures
vão no pacote (72 MB), o que é uma escolha registrada: sem elas o binário não
consegue se verificar na máquina de destino.

---

## app `0.4.00` · worker `0.2.00` — 2026-09-03 · A interface repaginada

Só o visual. Nenhum operador, nenhum parâmetro, nenhum resultado: o worker não
foi tocado e a sua versão não muda.

- **Os botões viraram ícones, e a palavra foi para a dica.** 35 SVGs
  desenhados por um gerador (`tools/make_icons.py`), 24 × 24, traço 1,5,
  monocromáticos e recoloridos pelo tema. `IconButton` exige `tip`, e o gate
  reprova um botão que deixe a dica vazia — a palavra não sumiu, mudou de
  lugar, e isso é verificado.
- **Uma trilha de ícones à esquerda**, com as oito etapas do fluxo, carregar
  arquivo e gerar grade sempre a um clique. Ela é um painel como os outros:
  Exibir › Trilha de ícones a esconde, e a escolha fica guardada.
- **Menu Processamento**, ao lado de Arquivo, Editar, Exibir e Ajuda, com as
  oito etapas e as cinco telas de processamento. As três superfícies — menu,
  trilha e painel — leem o mesmo modelo e roteiam o mesmo token, então uma
  etapa bloqueada é bloqueada nas três, com a mesma razão.
- **O painel de fluxo é uma linha por etapa**: número, ícone e nome. O
  parágrafo que ficava aberto embaixo de uma delas foi para a dica; os fatos
  (precisa de / produz / leva a) continuam a um clique.
- **A barra superior mostra o que está carregado** — projeto, CRS, camadas —
  em chips, ao lado do que dá para fazer.
- **O recolorimento é feito na CPU**, não por shader. `ColorOverlay` e
  `MultiEffect` foram testados e **não desenham nada no modo offscreen**, que
  é como toda storyboard deste projeto é capturada: um ícone tingido por
  shader seria um quadrado em branco em toda a evidência, e o gate passaria.
  Está medido em `app/geopotential_app/icons.py`.
- Storyboard `shell` com 4 quadros; `--only tools` passou de 19 para 28
  testes, negativado com uma dica vazia.

**Não entrega**: as pastas `icons/jobs/` e `icons/layers/` continuam vazias —
o painel de jobs e o de camadas ainda usam texto e cor; a trilha não é
reordenável nem configurável; não há atalho de teclado novo; e o ícone da
aplicação (`icons/app/` para o empacotamento do M8) não foi desenhado.

---

## app `0.3.00` · worker `0.2.00` — 2026-09-03 · O interpolador é medido

O M5.6 entregou um interpolador e nenhuma escolha. Testado na aplicação, o
resultado em malha regular saiu manchado e com a faixa comprimida — e o IDW,
que estava correto, é o pior dos métodos comuns exatamente nesse caso.

- **Dois interpoladores novos, que são os do QGIS**: `grid.tin_linear`
  (baricêntrico em cada triângulo de Delaunay) e `grid.tin_cubic`
  (Clough-Tocher, C1 entre arestas), sobre `scipy.interpolate`. São o *TIN
  interpolation, Linear* e *Clough-Toucher* do QGIS, para que quem conhece um
  reconheça o outro.
- **`grid.cross_validate`**: separa um quinto das amostras, prevê com os três
  métodos e reporta o erro na unidade do dado. É read-only — não grava
  artefato, não commita run. A tela mostra o ranking e marca o menor erro, e
  **não troca nada sozinha**.
- **Medido, não achado**: em `vp_500_m.csv` o cúbico erra 1,9 vez menos que
  o IDW; em `density_modified_500m.csv`, que também é malha regular, quem
  ganha é o IDW; na anomalia Bouguer ganha o linear. **Cada um dos três ganha
  em algum dos quatro arquivos, e a geometria das amostras não prevê qual** —
  por isso os três ficam disponíveis em vez de um virar padrão.
- **O overshoot do cúbico é medido e registrado, nunca cortado**
  (`ADR-MSP-007`): um Clough-Tocher cortado não é Clough-Tocher e não
  reproduz o QGIS. O manifesto carrega quanto passou; a tela avisa antes.
- **Fora do casco convexo o resultado é nulo**, nunca a amostra mais próxima.
  `max_distance` é um limite extra opcional para um triângulo largo que
  atravessa um vazio que ninguém mediu.
- A tela esconde raio e potência quando o método não os tem, e mostra a
  distância máxima quando ele a aceita.
- Seis contratos novos, `P-155` a `P-160`; suíte `interpolation` com 26 testes,
  **negativada em dois defeitos plantados**; storyboard `interpolation` com 5
  quadros na janela real.
- `grid.idw` não foi tocado: nenhum parâmetro, nenhum default, nenhum
  resultado.
- `docs/validation/V-M5_7-interpolation.md`,
  `docs/decisions/ADR-MSP-007-escolha-do-interpolador.md`.

**Não entrega**: kriging (o QGIS não traz no core, e sem ajuste de variograma
na tela seriam parâmetros inventados); spline de placa fina (mediu melhor em
dois dos quatro arquivos e **quebrou** com matriz singular no terceiro);
sugestão automática de raio; comparação automática ao abrir a tela; nada disso
para dado vetorial; e o overshoot não é lido de volta no Inspector depois da
execução.

---

## app `0.2.00` · worker `0.1.00` — 2026-09-03 · M5.5 e M5.6

Registrado retroativamente: este arquivo não existia quando os dois fecharam,
que é a lacuna que ele passa a cobrir. A narrativa está nos relatórios.

- **M5.6** — dado esparso vira critério: `grid.idw`,
  `grid.euclidean_distance` e `grid.rasterize`, com a grade declarada — CRS,
  pixel e área — e o planner consultado antes de qualquer alocação.
  `docs/validation/V-M5_6-gridding.md`.
- **M5.5** — interface profissional: fluxo de oito passos derivado do Project
  Store, painel de camadas, modo AOI explícito, painel de jobs, PT/EN,
  prévias que desenham o arquivo, reprojeção de exibição, mapa de fundo
  aberto e desligado por padrão, quatro temas.
  `docs/validation/V-M5_5-interface.md`.

**Não entrega**: o que cada um deixou aberto está em
`docs/PROJECT_STATE.md`, nas seções "What M5.5/M5.6 did not deliver".
