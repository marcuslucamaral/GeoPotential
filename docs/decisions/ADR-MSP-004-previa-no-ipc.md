# ADR-MSP-004 — A pré-visualização atravessa o IPC limitada, decimada e declarada

Status: `ACCEPTED`
Data: `2026-09-01`
Decidido por: Marcus, sobre o plano do M5.5
Relacionado: `P-63` — a descrição não carrega arrays através do IPC

## Contexto

A MSP-03 pede que, antes de importar, o usuário veja o que o arquivo contém:
para um raster, mapa, histograma, CRS, resolução, extensão, NoData, unidade e
bandas; para um vetor, uma prévia das geometrias, atributos, CRS, extensão e
número de feições; para uma tabela, prévia tabular, escolha das colunas X, Y e
valor, mapa dos pontos e estatísticas.

Duas dessas prévias são coordenadas: as geometrias de um vetor e os pontos de
uma tabela. E `P-63` diz que a descrição não carrega arrays através do IPC —
uma regra que existe porque um shapefile de 50 000 vértices ou um CSV de um
milhão de linhas transformaria uma descrição em transferência de dados.

O raster não tem esse problema: o canvas já lê o arquivo diretamente pela
costura nomeada em `map_item.py`, sem passar pelo IPC.

## Decisão

**`io.describe_dataset` ganha um bloco `preview` opcional, com teto numérico
declarado no protocolo.**

- Vetor: no máximo **2 000 coordenadas** no total, distribuídas entre as
  feições, com as geometrias simplificadas para caber.
- Tabela: no máximo **5 000 pontos**, amostrados.
- Todo bloco `preview` carrega `preview_decimated: true|false` e
  `source_features` (ou `source_rows`), para que a tela possa dizer que está
  mostrando uma parte.
- O teto vive no protocolo e no schema, não no bom senso de quem chama.

E duas proibições:

1. **O bloco `preview` nunca é entrada de operador.** Ele existe para desenhar
   uma prévia e para nada mais. Nenhum cálculo, nenhuma estatística, nenhuma
   decisão de QA/QC deriva dele — as estatísticas continuam vindo da leitura
   completa que o worker já faz.
2. **Pré-visualizar não é importar.** Nenhuma linha no store, nenhuma run
   comitada, nenhum artefato registrado — `P-53` já diz isso e continua valendo
   com a prévia por cima.

O array completo continua proibido. `P-63` não é afrouxado: ele passa a dizer
"nenhum array **ilimitado**", e o teste de contrato fixa o teto.

## Alternativas consideradas

**O app lê o vetor diretamente, como já faz com o raster.** Simétrico e
tentador. Rejeitado: a costura de leitura de arquivo em `map_item.py` é uma
exceção nomeada e cara, criada para o canvas de raster com LOD; abri-la para
geopandas na aplicação traria GDAL e leitura de atributos para o lado errado
da fronteira, e a MSP-04 exige que quem lê o arquivo pela primeira vez seja
quem o valida.

**O worker escrever um arquivo de prévia que o app lê.** Cria um artefato que
não pertence a run nenhuma, o que colide com `P-25` — um artefato não existe
sem run. Rejeitado.

## Como isto é verificado

- `P-117` — o bloco `preview` respeita o teto, declara a decimação, e nunca é
  entrada de operador. Testado nos dois lados do protocolo, que continuam
  byte-idênticos (`P-03`).
- `P-118` — pré-visualizar não cria linha no store nem comita run.
- `P-63` — a descrição continua serializável e sem arrays ilimitados; o teste
  existente permanece, com o teto acrescentado.

## Consequências

A prévia de um shapefile grande é uma silhueta, não o dado. É a resposta certa
para a pergunta "é este o arquivo que eu quero?", e é a resposta errada para
qualquer outra pergunta — razão pela qual a tela a rotula como prévia e o teste
impede que ela alimente um operador.
