# V-M5.7 — O interpolador é medido, não suposto

Data: `2026-09-03`
Versão: app `0.3.00`, worker `0.2.00`, protocolo `1.0.0`, schema `1.3.0`
Decisão: `docs/decisions/ADR-MSP-007-escolha-do-interpolador.md`
Fonte normativa: `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` MSP-06, §16

## Resultado

`PASS`.

Reproduzir com `./tools/run_gate.sh` a partir de `geopotencial_msp/`.

| Item | Valor |
|---|---|
| Gate | **32 de 32** |
| Testes | **683** unit/contract/integration + 59 checagens de interface |
| Storyboards | **7**, **37 frames**: `flow` 5, `gridding` 3, `interpolation` 5, `m4` 8, `m5` 6, `m55` 6, `themes` 4 |
| Operadores | **13 registrados** (eram 10) |
| Janela real | `tools/interaction_check.py` 8/8 |

O gate ganhou um check: `interpolation`, com 26 testes.

## O problema que este milestone fecha

Encontrado usando a aplicação, como o anterior. O M5.6 entregou **um**
interpolador, IDW, e a tela de gerar grade não oferecia outro. O relato foi
direto: *"tá bem ruim, parece que ele tá pegando a imagem e tentando
interpolar, sendo que o correto é o valor"*, com o pedido de fazer conforme o
QGIS.

O IDW não estava com defeito. `worker/geopotential_worker/grid/idw.py` é
Shepard (1968) correto, vetorizado, com o raio e o `min_points` que documenta.
O defeito era **não haver escolha**, e o IDW ser o pior método possível para o
dado que estava sendo testado.

IDW é uma média ponderada. Toda estimativa é puxada para a média local, e por
construção o método não devolve um valor que não viu. Numa malha regular de
amostras isso aparece de duas formas ao mesmo tempo: a textura manchada em
torno de cada amostra, e a faixa comprimida — o mapa nunca alcança nem o
mínimo nem o máximo do dado.

E o dado do projeto é, em boa parte, malha regular gravada como tabela.
Medido em `../data/utah_forge/`:

| Arquivo | amostras | X | Y | geometria |
|---|---|---|---|---|
| `vp_500_m.csv` | 1 626 | 125 m | 125 m | malha regular, 96,7 % completa |
| `density_modified_500m.csv` | 4 273 | 100 m | 100 m | malha regular com linhas extras |
| `top_basement_500m.csv` | 333 | 50 m | 50 m | linhas de 50 m |
| `anomaly_bouger…csv` | 3 735 | — | — | disperso, vizinho mediano 203 m |
| `magtellu_min_depth_500m.csv` | 6 898 | — | — | disperso, vizinho mediano 230 m |

Três de cinco são malhas regulares. Em `vp` o método oferecido era o que erra
mais; em `density` era o que erra menos. Isso só se sabe medindo, e não havia
como medir.

## A medição que decide

Produzida pelo código que foi entregue — `crossval.compare`, 5 partições,
semente `20260903`, raio igual ao triplo do espaçamento mediano, que é o que a
tela propõe. RMSE na unidade de cada arquivo, sobre as amostras que **todo**
método respondeu; menor é melhor.

| Dado | n | IDW p=2 | TIN linear | TIN cúbico | recomendado |
|---|---|---|---|---|---|
| `vp_500_m` (malha 125 m) | 1 626 | 0,0766 | 0,0567 | **0,0411** | cúbico |
| `density_modified_500m` (malha 100 m) | 4 273 | **0,0165** | 0,0171 | 0,0177 | IDW |
| `anomaly_bouger` (disperso) | 3 735 | 0,954 | **0,857** | 1,460 | linear |
| `magtellu_min_depth` (disperso) | 6 898 | 327 | 337 | **312** | cúbico |

**Os três métodos ganham em algum dos quatro arquivos, e a geometria das
amostras não prevê qual.** Duas malhas regulares e vencedores diferentes; dois
levantamentos irregulares e vencedores diferentes. Em `vp` o cúbico erra 1,9
vez menos que o IDW; em `bouguer` o cúbico erra 1,7 vez mais que o linear;
em `density` os três ficam a 7 % um do outro e o IDW ganha.

Isso é mais forte do que a hipótese com que este trabalho começou. A primeira
exploração usou uma separação única de 20 % em vez de 5 partições e produziu
uma história arrumada — "malha regular favorece o cúbico, disperso favorece o
IDW" — que **não sobrevive** ao protocolo mais robusto: sob 5-fold o vencedor
muda em dois dos quatro arquivos. A tabela acima é a que vale, e ela não
sustenta nenhuma regra prática do tipo "use X para dado do tipo Y".

Nenhum padrão escolhido no código estaria certo. É exatamente por isso que a
entrega é *medir*, e não trocar o padrão.

A metade visível do mesmo efeito, em `vp`, cujas amostras vão de 3,168 a
5,985 km/s:

| Método | faixa produzida | alcance |
|---|---|---|
| IDW | 3,201 – 5,970 | 2,626 |
| TIN linear | 3,197 – 5,983 | 2,786 |
| TIN cúbico | 3,161 – 6,048 | 2,887 |

O IDW não chega às pontas, porque uma média ponderada não pode.

## O que foi entregue

| | |
|---|---|
| `grid/triangulated.py` | Delaunay linear e Clough-Tocher, sobre `scipy.interpolate.LinearNDInterpolator` e `CloughTocher2DInterpolator` — os dois métodos do *TIN interpolation* do QGIS |
| `grid/crossval.py` | k-fold sobre os três métodos, pontuando todos nas mesmas amostras |
| `grid.tin_linear`, `grid.tin_cubic` | operadores, com manifesto, artefato e planner como os demais |
| `grid.cross_validate` | operador **read-only**: mede e não grava nada |
| `GriddingDialog.qml` | seletor com os quatro métodos, botão de medir, ranking, aviso do cúbico, campo de distância máxima; raio e potência somem quando o método não os tem |
| `catalog.py` | 12 chaves novas, PT e EN |

`grid.idw` não foi tocado. Nenhum parâmetro, nenhum default, nenhum resultado.

## Contratos novos

| ID | Contrato | Gate |
|---|---|---|
| P-155 | Um interpolante linear reproduz um campo linear exatamente | `--only interpolation` |
| P-156 | Fora do casco convexo o resultado é nulo, nunca a amostra mais próxima | `--only interpolation`, storyboard `interpolation` |
| P-157 | O overshoot do cúbico é medido e registrado, nunca cortado (ADR-MSP-007) | `--only interpolation`, storyboard `interpolation` |
| P-158 | Amostras colineares são recusadas por nome, indicando o método que funciona | `--only interpolation` |
| P-159 | A comparação pontua todo método nas mesmas amostras, e é determinística | `--only interpolation` |
| P-160 | Comparar métodos não commita run nem registra artefato | `--only interpolation`, storyboard `interpolation` |

`P-148` — "IDW não extrapola" — continua valendo, e agora vale **para o IDW**.
`tin_linear` também a satisfaz e é testado; `tin_cubic` não a satisfaz, e é
por isso que o `P-157` existe.

## Como foi provado

**A suíte falha contra o código quebrado.** Dois defeitos plantados, um de
cada vez, com o resto da árvore intacta:

| Defeito plantado | Resultado |
|---|---|
| Preencher fora do casco convexo com a amostra mais próxima | `FAIL`, 2 falhas |
| Zerar o overshoot reportado pelo cúbico | `FAIL`, 1 falha |
| Árvore restaurada | `PASS`, 26 testes |

Um gate verde tanto na versão quebrada quanto na consertada não prova nada, e
esses dois não são.

**A janela real.** Storyboard `interpolation`, 5 quadros, cada um com asserção
numérica sobre o estado da aplicação e não sobre a existência de um controle:

| Quadro | O que ficou provado |
|---|---|
| `01 imported` | a tabela entra e passa a receber 4 métodos, incluindo os triangulados |
| `02 measured` | o worker mediu: cúbico 0,04109, linear 0,05670, IDW 0,07658 — e **0 runs commitados** |
| `03 controls` | trocar para um método triangulado esconde o raio e mostra a distância máxima; a tela fica pronta sem raio |
| `04 recommended` | o método escolhido é o que rodou; o manifesto registra `bounded_by` e o overshoot |
| `05 idw_contrast` | IDW na mesma grade alcança 2,626 contra 2,776 do recomendado |

`tools/interaction_check.py`: 8/8, exit 0.

Contact sheet: `docs/validation/images/interpolation/contact_sheet.png`.
Relatório: `docs/validation/images/interpolation/STORYBOARD.md`.

## O que este milestone NÃO entrega

- **Kriging.** É o próximo método que um geocientista pede, e o único comum
  que estima incerteza junto com o valor. Fica fora porque o QGIS não o traz
  no core e porque kriging sem ajuste de variograma na tela é kriging com
  parâmetros inventados. Registrado, não esquecido.
- **Spline de placa fina.** Mediu melhor que tudo em `vp` e em `magtellu` e
  ficou fora mesmo assim: não está no QGIS core, e **quebrou** com matriz
  singular no dado gravimétrico, que tem pontos coincidentes. Entra quando o
  tratamento de duplicatas for decidido, não antes.
- **Sugestão automática do raio a partir da medição.** A comparação usa o raio
  que está na tela; ela não procura o melhor raio. Varrer raio e potência é
  uma segunda medição, e mais cara.
- **A comparação não roda sozinha ao abrir a tela.** É um botão. Rodar uma
  validação cruzada a cada abertura gastaria segundos que ninguém pediu.
- **Nada disso alcança vetor.** Os métodos triangulados são oferecidos para
  tabela. Um vetor de polígonos continua com `grid.rasterize` e distância.
- **O overshoot do cúbico não é mostrado depois da execução.** Está no
  manifesto e o aviso aparece antes de rodar; a tela não lê o número de volta
  no Inspector.

## Defeito observado e não corrigido

`tools/interaction_check.py` termina com exit 0 e as 8 checagens `ok`, e
imprime no encerramento um traceback da thread `basemap-fetch`:
`RuntimeError: Signal source has been deleted`, em `map_item.py:1207`. É uma
corrida de desligamento entre a thread de tiles e a destruição do item — não
falha nenhuma checagem, é anterior a este milestone e não tem relação com
interpolação. Registrado aqui para não se perder.
