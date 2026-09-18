# V-M5.6 — Gridding: dado esparso vira critério

Data: `2026-09-03`
Versão: app `0.2.00`, worker `0.1.00`, protocolo `1.0.0`, schema `1.3.0`
Milestone: `docs/milestones/M5_6_GRIDDING.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-06, §18.1, §16

## Resultado

`PASS`. As seis etapas E1–E6.

Reproduzir com `./tools/run_gate.sh` a partir de `geopotencial_msp/`.

| Item | Valor |
|---|---|
| Gate | **31 de 31** |
| Testes | **657** unit/contract/integration + 59 checagens de interface |
| Storyboards | **6**, **32 frames**: `flow` 5, `gridding` 3, `m4` 8, `m5` 6, `m55` 6, `themes` 4 |
| Operadores | **10 registrados** (eram 7); nenhum planejado aponta para milestone fechado |

O gate ganhou um check: `gridding`, com 45 testes.

## O problema que este milestone fecha

Encontrado usando a aplicação, não lendo o código. `grid.harmonize` chama
`read_raster()` e a aplicação filtrava `kind != "raster"`. Um CSV importava,
passava pela QA/QC, era desenhado — e parava ali. Na prática
`../data/utah_forge/anomaly_bouger_easting_northin_bouger.csv`, uma anomalia
Bouguer com 3 735 pontos, **não conseguia entrar na MCDA**. E o
`Distance_to_fault.tif` que o projeto usa como critério é o produto de uma
transformada de distância feita **fora** desta aplicação.

O registro ainda prometia os operadores que faltavam para um milestone que já
tinha fechado: `grid.idw` e `grid.euclidean_distance` marcados `M5`, e
`io.import_dataset` marcado `M3` embora importar seja um comando desde o M3. A
aplicação respondia *"planejado para o milestone M5"* a quem estava no M5.5.

## Os três operadores, e a linha entre eles

| Operador | Estima? | Como foi provado |
|---|---|---|
| `grid.idw` | **sim** | célula sobre a amostra devolve o valor exato; centro de quatro cantos dá a média por simetria a 1e-9; `power=30` tende ao vizinho mais próximo, `power≈0` à média |
| `grid.euclidean_distance` | não | zero sobre a feição; 3 células × 10 m = 30 m; a diagonal 3-4-5 dá exatamente 50 m |
| `grid.rasterize` | não | o valor dentro do polígono é o do atributo; fora é nulo, nunca zero |

A distinção não é vocabulário: o manifesto de cada run grava
`gridding.interpolates`, e um campo de distância descrito como interpolação
colocaria uma estimativa numa linhagem que não tem nenhuma.

**IDW não extrapola** (P-148), verificado com 2 000 células aleatórias: o
resultado fica dentro do intervalo das amostras. Sobre o dado real, amostras de
−243,43 a −169,81 mGal produziram um campo de −243,42 a −169,86.

**Célula sem amostra suficiente fica nula** (P-149). Sobre o CSV real, a
cobertura obedece ao raio, medida:

| Raio | `min_points` | Cobertura | Faixa do resultado |
|---|---|---|---|
| 250 m | 1 | 11,2 % | −243,43 a −169,81 |
| 500 m | 3 | 7,3 % | −242,34 a −170,04 |
| 1 000 m | 3 | 37,3 % | −243,42 a −169,86 |
| 2 000 m | 3 | 89,3 % | −243,42 a −169,85 |

Os buracos são o levantamento, não um defeito. Preencher com o vizinho mais
próximo por mais longe que esteja daria um mapa sem buracos e sem dado por
trás deles.

## Pixel, área e memória

Os três recebem a mesma especificação (`grid/spec.py`), e nada dela é inferido.

- **Pixel** obrigatório, na unidade do CRS.
- **Área** opcional: ausente é a extensão do dado, presente é a área escolhida.
  Sobre o CSV real, `bounds` de 5 × 5 km reduziu a grade de **738 × 594** para
  **50 × 50** células — e é o meio mais barato de fazer uma grade caber.
- **Custo estimado antes de alocar.** Um pixel de 0,001 m sobre a mesma
  extensão é recusado com a conta na mensagem, e a recusa diz o que reduzir:

  > `73866000 x 59464000 pixels at 0.001 x 0.001: the output needs
  > 16755553528 MB and only 98589 MB is free.`

  Isso acontece em `grid_spec.build`, antes de qualquer `np.full`.
- Quando o plano não cabe em memória mas é viável, o `Policy.BLOCKED` do
  planner dá o número de linhas por bloco e o IDW processa em janelas — §18.1
  na ordem que ele mesmo define. Um teste percorre os dois regimes e exige que
  toda linha da grade seja visitada exatamente uma vez.

**Sem laço Python por célula nem por amostra** (P-153): a busca de vizinhos é
uma consulta `cKDTree` por bloco inteiro, e o teste lê **o que cada laço
itera** nos quatro módulos de gridding, não como está escrito.

## O fluxo, ponta a ponta

Storyboard **`gridding`**, 3/3, sobre o dado real e pela interface:

| Frame | O que ficou provado |
|---|---|
| `imported` | 1 dataset, 1 camada desenhada, **0 harmonizáveis**, 1 griddable — uma tabela não é harmonizável, e isso não é defeito |
| `chosen` | a tela oferece `grid.idw` primeiro para uma tabela, declara que **estima**, e fica pronta com CRS, pixel e raio |
| `gridded` | run `grid.idw`, grade **369 × 297 @ 200 m**, 37,3 % válidos, 1 artefato, e **1 harmonizável** — o raster produzido volta ao fluxo |

O último número é o que fecha o ciclo: `harmonizableDatasets` passou a oferecer
também os rasters que o próprio projeto calculou. Sem isso, um CSV chegava à
grade e parava ali.

## Defeitos encontrados no caminho

1. **O diálogo submetia sem o arquivo de entrada.** `grid.idw: expects exactly
   one input file; got 0`. O arquivo é *input* do job e não parâmetro: o store
   grava os inputs de uma run dessa lista, e uma run sem inputs não tem
   linhagem até o dado de onde saiu.
2. **O Inspector mostrava os números do dado errado.** É o defeito `B8` que o
   M5.5 listou na sua linha de base e não fechou: o painel lia
   `lastDescription`, *o último dataset descrito*, e não a camada ativa.
   Depois de interpolar, ele mostrava `Válidos 100 %` e a faixa do CSV sob o
   nome do raster — números de um dado sob o nome de outro. Cada camada passou
   a ter a sua própria descrição, pedida uma vez por uma sonda somente-leitura
   que não comita run. Verificado na captura: agora diz `369 x 297 px`,
   `37.3 % dos pixels`, e a faixa da interpolação.
3. **Um frame do storyboard `flow` deixou de mudar pixels.** Não porque o
   passo parou de fazer algo — `applied=2, criteria=2` — mas porque o Inspector
   passou a se atualizar antes, e a diferença incidental sumiu. O guarda de
   pixels pega um passo que não fez nada; o `expect` deste diz o que ele fez,
   e é a asserção mais forte que fica.

4. **Um `Dialog` sumia da árvore uma execução em cinco.** Quatro classes de
   teste liam a interface carregada, e cada uma construía o seu próprio engine
   QML e o destruía. Vários engines num processo compartilham o registro de
   tipos e os singletons; num run em cinco um `Dialog` simplesmente não existia
   na janela de uma classe posterior, e `findChild` devolvia `None` sem nenhum
   erro em lugar nenhum. A classe base já dizia "um engine para a suíte
   inteira" — passou a ser verdade. **0 falhas em 15 execuções** depois, contra
   3 em 15 antes.
5. **Uma sonda de descrição abria um modal de erro.** `describeLayer` segue a
   camada ativa, então dispara enquanto o projeto ainda está abrindo; com o
   worker ainda subindo, o `_fail` levantava um diálogo de erro por um detalhe
   de painel. Agora ela desiste em silêncio e pergunta de novo depois.

6. **O assistente lia o arquivo duas vezes.** `onDatasetDescribed` copia o CRS
   e a unidade do arquivo para os campos de declaração, para que a pessoa
   corrija em vez de digitar. São os mesmos campos em que ela digita, então o
   preenchimento disparava a re-checagem que acabara de produzi-lo. Um raster
   traz o próprio CRS, então **abrir o assistente sobre um raster lia o arquivo
   duas vezes** e mostrava cada job repetido no painel: medido em 4 jobs onde
   deviam ser 2. Um guarda durante o preenchimento; 2 jobs agora.

7. **O raio de busca vinha vazio.** Ninguém pode escolher um raio olhando o
   nome do arquivo, e um raio abaixo do espaçamento das amostras deixa quase
   toda célula nula — que é o que uma pessoa vê como "não gerou nada". A
   descrição de uma tabela passou a trazer o **espaçamento mediano** entre
   amostras vizinhas (um fato do levantamento, calculado com `cKDTree`), e a
   tela propõe pixel = espaçamento e raio = 3 × espaçamento, dizendo de onde
   o número veio. Para o dado do usuário: 203 m de espaçamento, 609 m de raio.
8. **A tela mandava um default que o operador não documenta.** `min_points`
   era `3` na interface e `1` no operador — uma análise mais estrita do que a
   que o contrato descreve, escolhida por ninguém. Num levantamento em linhas
   isso levou a cobertura de **45,1 % para 11,7 %** com nada na tela dizendo
   que um default diferente tinha sido usado. É exatamente o default silencioso
   que o §16 proíbe. Teste novo compara os defaults da tela com os do operador.

### Segunda rodada com dados reais — `2026-09-03`

Sobre `../data/utah_forge/density_modified_500m.csv`, cujo nome diz 500 m e
cujas amostras estão a **100 m** umas das outras — a sugestão vem do dado, não
do nome.

9. **A grade proposta não tinha nuance nenhuma.** Pixel = espaçamento dá **uma
   célula por amostra**, e uma interpolação com uma célula por amostra não tem
   onde variar: o resultado era 82 × 52 e parecia degraus. O pixel passou a
   dividir o espaçamento, com três níveis nomeados e **o tamanho da grade
   mostrado antes de rodar** — 82 × 52, 250 × 157 ou 412 × 260, com os MB ao
   lado. No "Equilibrada": 250 × 157 a 33 m, **100 % de cobertura**, faixa
   2,240 a 2,860 (a das amostras, sem extrapolar).
10. **O nome do método estava incompleto.** "Distância até a feição mais
    próxima" não diz *qual* distância; passou a ser **"Distância euclidiana
    até a feição mais próxima"**, que é o que o operador calcula (linha reta,
    não geodésica nem de custo). E escolher distância sobre uma **tabela** é
    legítimo mas quase nunca é o que se quer: as "feições" ali são as próprias
    amostras, então o resultado mede a **cobertura do levantamento** e não uma
    propriedade do terreno. A tela agora diz isso, em amarelo.
11. **Clicar não dizia nada.** A ferramenta de identificar existia e escrevia
    um número na barra de estado. Agora abre um painel que responde por
    **todas as camadas visíveis** — que é a razão de existir uma pilha —, cada
    valor lido da fonte da sua camada em resolução plena e no CRS dela, com a
    célula de origem: `2.64000 g/cm3   col 125, lin 78`. Uma camada de pontos
    responde "amostras, não um campo contínuo", porque o valor "em" uma
    coordenada que ela não ocupa não existe.
12. **Um raster produzido não sabia a sua unidade.** Todo artefato carimba
    `GEOPOTENTIAL_UNIT` e ninguém lia de volta, então o valor aparecia sem
    unidade ao lado. Lido agora tanto na descrição quanto ao abrir a camada no
    canvas; uma declaração explícita continua vencendo a tag.
13. **`26912` e `EPSG:26912` apareciam como CRSs diferentes.** Normalizado
    onde o catálogo é oferecido.

### Quadro acrescentado em `0.8.04` — a escolha da extensão deixa de ser cega

`04_policies` usa o que os três quadros anteriores deixaram no projeto — a
grade que saiu do CSV — mais `Distance_to_fault.tif`, que cobre outra área. Com
uma camada só as duas políticas coincidem; com duas, elas deixam de ser duas
grafias de uma coisa só, e o `expect` deste quadro recusa o caso trivial.

Medido pela tela, com o botão **Comparar as duas**:

| Política | Grade | Células | Com score | Células com score |
|---|---|---|---|---|
| Interseção | 48 × 41 | 1 968 | 84,4 % | **1 661** |
| União | 369 × 297 | 109 593 | 1,5 % | **1 661** |

As duas colunas da direita são o achado. A união entrega um mapa **56× maior** e
**a mesma área pontuada**: um score precisa de todos os critérios
(`ADR-MSP-004`), então as células com score são a interseção das máscaras
qualquer que seja a extensão da grade. 98,5 % do mapa da união fica em branco.

O quadro também mede `runs_before=1` e `runs_after=1` no mesmo frame: a sonda é
read-only e não entra na linhagem do projeto (`P-53`).

`P-195` e `P-196`. Os mesmos contratos são medidos com números independentes no
Utah FORGE por `--only mixed-sources`, onde a diferença é 13 875 contra 50 020.

## O que este milestone não entregou

- **Krigagem, mínima curvatura, spline.** O MSP-06 nomeia IDW; um segundo
  interpolador sem um caso que o exija é escopo que ninguém pediu.
- **Blocos em disco e memory mapping.** O `Policy.BLOCKED` processa em janelas
  de linhas, que é o que o §18.1 pede primeiro. Uma grade que não cabe nem em
  janelas é recusada, não paginada.
- **Rasterização categórica com tabela de classes.** Queimar um valor numérico
  entra; o mapeamento classe → código é do editor de critérios.
- **`bounds` desenhado no mapa.** A área é digitada. Usar a AOI já existente
  como área de gridding é ligação óbvia e não foi feita.
- **Encadeamento automático.** Gerar a grade e harmonizar são dois passos e
  dois cliques. Um CSV não vira critério sozinho, e nem deveria: o método é
  uma decisão científica.
- **A prévia das políticas não desenha** (`0.8.04`). Diz quantas células e que
  fração cada extensão daria, e não mostra **onde**: a faixa que a união
  acrescenta, e que nunca recebe score, não aparece no canvas. Ver a mancha é o
  que separaria informar de orientar.
