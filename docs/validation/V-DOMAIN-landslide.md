# V-DOMAIN — A aplicação fora do domínio geotérmico

Data: `2026-09-05`
Versão: app `0.8.00`, worker `0.5.00`
Reproduzir: `./tools/run_gate.sh --only other-domain` e
`tools/capture_sequence.py other_domain`

## Resultado

`PASS`, e **dois defeitos encontrados**.

| Item | Valor |
|---|---|
| Gate | **35 de 35** |
| Testes | **825** unit/contract/integration + 59 checagens de interface |
| Storyboards | **11**, **54 quadros**; `other_domain` é o novo, com 4 |
| Suíte nova | `--only other-domain`, 17 testes |

## A lacuna que isto fecha

A aplicação sempre foi agnóstica de domínio **por desenho**: importar, QA/QC,
harmonizar, pertinência, AHP, agregação e cenários recebem qualquer raster
como critério, e campos potenciais é o único módulo específico de geofísica —
8 dos 26 operadores.

Mas isso nunca tinha sido **provado**. Todo gate e toda storyboard rodavam
sobre o dataset geotérmico de Utah, e a única menção a
`../data/conditioning_factors/` em toda a árvore era uma linha do relatório do
M0 dizendo que nada o usava. Agnóstico por desenho e não verificado é uma
afirmação, não uma propriedade.

`conditioning_factors` são 20 camadas de suscetibilidade a deslizamento — MDE,
declividade, TWI, curvatura, uso do solo, geologia, solo, floresta — de uma
bacia na Coreia, em `EPSG:5186`, todas na mesma grade de 997 × 863.

## Os dois defeitos que só este dado podia achar

Utah tem um tipo de camada: contínua. Este tem três, e cada um dos que faltava
expôs um defeito.

### 1. `categorical` estava declarada e não estava ligada

`decision.membership.categorical` existe desde o M5, está em `FAMILY`, é
testada, e **o operador de agregação não a chamava**. Pedi-la dava:

```
criterion 'geologia': membership 'categorical' is not known;
use one of categorical, gaussian, large, linear_decreasing,
linear_increasing, sigmoidal, small
```

Uma mensagem que se contradiz na própria frase — lista `categorical` entre as
opções válidas enquanto a recusa. Utah não tem camada de classes; aqui
geologia, uso do solo e os quatro de solo são todas classes, e sem isso metade
do dataset não pode ser critério.

Ligada, com a tabela de classes indo para a procedência: sem ela ninguém
reproduz a análise, porque **a nota de cada classe é a decisão inteira**.

### 2. Direção não tinha pertinência nenhuma

`aspect` é azimute. 359° e 1° estão a dois graus um do outro, e toda função
deste projeto os punha nas pontas opostas da faixa. Medido:

| ângulo | `linear_increasing` | `circular` (preferindo o norte) |
|---|---|---|
| 1° | 0,0028 | 0,9999 |
| 359° | 0,9989 | 0,9999 |
| 180° | 0,5008 | 0,0000 |

Num mapa de aspecto isso não é erro de arredondamento: é dizer que uma encosta
voltada para o norte é o oposto de uma encosta voltada para o norte.

Entrou `circular`: cosseno levantado sobre a distância angular pelo caminho
curto, com o azimute preferido e a distância de meia-pertinência como
parâmetros. Verificada em 0°, 90°, 180° e 270°, e a simetria em torno do
preferido para quatro azimutes.

**E ela recusa azimute negativo.** Ferramentas de terreno escrevem `-1` para
célula plana — 6 053 delas neste dataset, 0,71 % — e `-1` não é um azimute
perto de zero: é "esta pergunta não se aplica aqui". Embrulhá-lo para 359°
daria quase pertinência cheia a uma célula sem direção nenhuma. Como um
negativo também pode ser um ângulo escrito do outro lado, embrulhar em
silêncio escolheria uma das duas leituras e estaria errado na outra — então a
recusa nomeia as duas e diz o que fazer em cada caso.

## Contratos novos

| ID | Contrato | Gate |
|---|---|---|
| P-187 | Uma camada de classes pode ser critério, e a tabela de classes entra na procedência | `--only other-domain`, storyboard `other_domain` |
| P-188 | Uma direção usa pertinência circular; um azimute negativo é recusado, nunca embrulhado | `--only other-domain`, storyboard `other_domain` |
| P-193 | Os códigos de classe de um raster são lidos do arquivo e listados com a fração de pixels válidos que cada um ocupa; um campo contínuo é reportado como não tendo nenhum | `--only describe` |
| P-194 | `categorical` não pode ser aplicada enquanto alguma classe estiver sem nota, e a tela diz quantas faltam; uma nota fora de `[0, 1]` não conta como nota | `--only menus`, storyboard `other_domain` |

## O que foi verificado, e com que números

Storyboard `other_domain`, 5 quadros na aplicação:

| Quadro | O que ficou provado |
|---|---|
| `01 layers` | três camadas em **EPSG:5186** atravessam o caminho; nenhum gate anterior tinha saído do EPSG:26912 |
| `02 circular` | o editor desenha a curva circular, diz em palavras o que ela faz, e o alcance angular **não** é a mesma propriedade do alcance de valores |
| `03 classes` | a tabela de classes pela cadeia real — camada ativa, `openMembership`, descrição pelo IPC: **4 códigos** lidos de `geology.tif`, `missing_before=4` com aplicar desligado, `missing_after=0` com aplicar ligado |
| `04 mixed` | contínuo e categórico na mesma agregação: 3 critérios, `categorical, linear_increasing`, **99,6 %** de células válidas, tabela de 4 classes na procedência, grade de saída em EPSG:5186 |
| `05 sensitivity` | o leave-one-out do M6 sobre esta análise, 3 linhas, **856 695** células comparadas |

O quadro 5 é o que responde se os cenários são do produto ou do dataset: eles
rodam aqui sem nada específico de geofísica.

O quadro 3 não atribui `criterion`: torna a camada ativa e deixa a descrição
chegar pelo sinal. Um quadro que atribuísse a propriedade não testaria quem a
preenche, que é exatamente como o editor ficou sem a camada no `0.8.02`.

## Fechado desde a primeira versão deste relatório

- **A tabela de classes tem tela** (`0.8.03`). `describe` passa a expor os
  códigos — em dado real, `geology.tif` 4, `landcover.tif` 9,
  `soil_drainage.tif` 5, enquanto `slope.tif` e `aspect.tif` não são
  oferecidas — e o editor lista um código por linha com a área que ocupa e a
  nota que recebe. Aplicar espera a tabela inteira: o worker recusaria o
  código sem nota de qualquer forma, e recusar na tela diz **onde** está a
  lacuna. `dem.tif`, que é integral e não é camada de classes, volta com 885
  distintos e nenhum listado — a tela diz quantos são e manda reclassificar.

## O que continua não entregue

- **O código de classe continua sendo um número.** A tabela pontua `1`, `2`,
  `3`, e nada lê a tabela de atributos (`.dbf`, `.vat`, RAT do GDAL) que diria
  qual é granito. Quem pontua precisa saber por fora o que cada código é.
- **Nada sugere uma nota**, o que é o certo — a nota de cada classe é a decisão
  científica inteira — mas significa que uma camada de 40 classes ainda são 40
  campos à mão.
- **A importação não detecta uma camada de classes.** O wizard trata todas como
  contínuas; o editor é o único lugar da aplicação que sabe a diferença.
- **Nada reclassifica um contínuo em classes.** Aspecto em oito setores, por
  exemplo, é o que boa parte da literatura de deslizamento faz; aqui a
  alternativa é a pertinência circular, que é contínua.
- **Nenhuma checagem de que uma camada declarada como classe é discreta.** Uma
  camada contínua com `categorical` seria recusada por classe não mapeada,
  mas por acidente e não por regra.
- **A célula plana continua sendo decisão de quem opera.** A recusa diz o que
  fazer; a aplicação não oferece um botão para fazê-lo.
- **Os outros 16 arquivos do dataset não foram exercitados** — só declividade,
  TWI, LS, MDE, geologia, drenagem e aspecto. Os de floresta e as curvaturas
  entram no mesmo caminho e não foram medidos.
