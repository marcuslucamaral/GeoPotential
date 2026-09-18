# ADR-MSP-003 — A transformação de coordenadas para exibição vive na aplicação, atrás de uma costura nomeada

Status: `ACCEPTED`
Data: `2026-09-01`
Decidido por: Marcus, sobre o plano do M5.5
Relacionado: ADR-006 do workspace ("a reprojeção de exibição nunca modifica uma
fonte"), `docs/ARCHITECTURE.md` — costuras nomeadas

## Contexto

O M5.5 pede quatro formatos de coordenada na barra de estado: UTM, graus
decimais, graus/minutos/segundos com hemisfério, e o CRS original da camada.
Com uma camada em `EPSG:26912` e o formato "graus decimais" escolhido, mostrar
a posição do cursor exige uma transformação de coordenadas.

A regra do produto é que a ciência vive no worker e a aplicação não calcula.
Uma transformação de coordenadas é, sem dúvida, um cálculo geodésico.

O problema é a frequência: a posição do cursor muda a cada evento de mouse.
Uma ida e volta JSON-Lines por evento transforma um readout em tráfego de IPC
proporcional ao movimento da mão.

## Decisão

**A aplicação ganha `app/geopotential_app/geo/coordinates.py`, sobre pyproj,
exclusivamente para exibição.** É uma costura, é nomeada em
`docs/ARCHITECTURE.md`, e o gate de arquitetura a mantém no lugar.

O módulo:

- transforma coordenadas **para mostrar**, e formata em UTM, graus decimais e
  GMS com hemisfério;
- **não lê arquivos**, não escreve arquivos, não registra nada, não cria run;
- **não é alcançável** a partir de `project/`, `commands/`, nem do caminho que
  submete um job. O gate falha se algum deles o importar, direta ou
  indiretamente;
- nunca altera um valor armazenado, um manifesto ou um artefato.

**Reprojetar de fato continua sendo uma run do worker**, com manifesto, hash e
artefato — e a interface do M5.5 é obrigada a nomear as três operações como
coisas distintas: *declarar* o CRS de um arquivo sem referência, *reprojetar*
os dados, e *reprojetar só para exibição*.

Isto é exatamente a forma que o ADR-006 do workspace já deu ao problema: uma
camada lida em UTM permanece em UTM; só a grade de exibição é deformada.

## Alternativas consideradas

**Sempre pelo worker.** Correto por contrato e inviável na prática: uma
mensagem por pixel percorrido. Rejeitada por medida de latência, não por
preferência.

**Só o CRS nativo da camada, sem transformação nenhuma.** Elimina a decisão e
remove UTM, graus decimais e GMS do escopo. Foi considerada e rejeitada: a
leitura de coordenada em dois sistemas é parte do que a MSP-05 pede de um
canvas profissional, e o custo da alternativa é o produto ficar pior.

## Como isto é verificado

- `P-119` — declarar, reprojetar e reprojetar para exibição aparecem como
  operações distintas e rotuladas; a de exibição não escreve byte nenhum.
- `P-120` — `project/`, `commands/` e o caminho de submissão não alcançam
  `geo/coordinates.py`. Teste negativo no gate de arquitetura.
- `P-121` — toda coordenada exibida vem com o seu CRS, no formato escolhido, e
  a conversão de ida e volta fecha dentro da tolerância declarada antes do
  teste.
- `P-13` continua verde: não existe CRS padrão. Uma camada sem CRS não ganha
  um por causa da barra de estado — ela é recusada por nome, como já era.

## Consequências

A aplicação passa a depender de pyproj, que já é dependência do ambiente
`mcda_geo` e já é usado pelo worker. A fronteira "o app não calcula ciência"
ganha uma exceção, e é por isso que ela é **nomeada, testada negativamente e
restrita a exibição** — uma exceção invisível seria o começo do fim da
separação.
