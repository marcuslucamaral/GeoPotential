# ADR-MSP-002 — A pilha de exibição deriva do registro e não é uma representação do domínio

Status: `ACCEPTED`
Data: `2026-09-01`
Decidido por: Marcus, sobre o plano do M5.5
Relacionado: ADR-005 do workspace (derivação de sentido único entre `Layer` e
`Criterion`), `docs/ARCHITECTURE.md` — "não crie uma segunda representação do objeto de
domínio"

## Contexto

O M5.5 acrescenta um painel de camadas ao estilo QGIS: várias camadas abertas
no mesmo projeto, com visibilidade, ordem de desenho, opacidade, camada ativa,
colormap, zoom para a camada, propriedades e remoção da vista.

Isto colide de frente com a regra mais dura do contrato. Hoje o `MapItem`
guarda **uma** fonte e **uma** comparação, e a ausência de pilha é justamente o
que garante que não há duas ideias de "camada" no produto. A representação
científica é `Criterion` sobre um `TargetGrid`, ela vive no worker, e
`CriterionStack.names` é a **única** ordem a que os pesos se amarram.

Um painel de camadas mal desenhado cria a segunda representação em uma semana:
basta que a ordem de desenho comece a significar alguma coisa, ou que a camada
guarde a sua própria unidade, ou que alguém agregue "as camadas visíveis".

## Decisão

**A aplicação ganha um `DisplayLayer`, e ele é estritamente uma decisão de
exibição derivada, num sentido só, de algo que já está registrado.**

Um `DisplayLayer` referencia um `dataset_id` importado ou um artefato de uma
run comitada, e carrega **apenas**:

- `visible`, `opacity`, posição na ordem de desenho;
- `colormap`, limites de estilo (`vmin`, `vmax`), inversão;
- nome exibido;
- papel: `original`, `harmonizado`, `membership`, `resultado`, `aoi`.

E **não** carrega:

- pixels ou geometrias próprias — lê-os pela referência;
- unidade, CRS, nodata ou estatísticas próprias — todos vêm do registro;
- qualquer parâmetro que entre em cálculo.

Três consequências obrigatórias:

1. **A ordem da pilha de exibição não entra em nenhum manifesto e não define
   nenhuma ordem científica.** A ordem que os pesos amarram continua sendo
   `CriterionStack.names`, produzida pelo worker.
2. **Nenhuma função de agregação aceita um `DisplayLayer`.** Agregar continua
   exigindo critérios `NORMALIZED` no mesmo grid, vindos do worker.
3. **Remover uma camada da vista não remove nada do projeto.** É uma operação
   de exibição, é reversível, e não é undo de comando nem toca em run comitada.

O `DisplayLayer` vive em `app/geopotential_app/models/layer_model.py`, é
QtCore-only como todo `models/`, e o `MapItem` desenha a pilha na ordem que ela
declara.

## Alternativas consideradas

**Deixar a pilha dentro do `MapItem`, como lista de fontes.** É o caminho de
menor esforço e o mais perigoso: as decisões de exibição ficariam misturadas com
o cache de tiles e o LOD, e `render/` — que hoje é numpy entra, pixels saem —
passaria a guardar estado de projeto. Rejeitada.

**Fazer o worker dono da pilha.** Tornaria a ordem de desenho um fato
científico, que é exatamente o erro que esta ADR existe para impedir. Além
disso, mudar a opacidade de uma camada passaria a ser uma mensagem IPC.
Rejeitada.

## Como isto é verificado

- `P-106` — a pilha de exibição não aparece em nenhum manifesto e nenhuma
  função de agregação a aceita. Teste negativo no gate de arquitetura, mais um
  teste de contrato que passa um `DisplayLayer` a `aggregate` e exige a recusa.
- `P-107` — esconder ou reordenar camadas não altera nenhum valor lido da
  fonte; o valor sob o cursor continua vindo do dado, não do tile (P-70).
- `P-108` — remover uma camada da vista deixa o dataset e as runs intactos.

## Consequências

O painel de camadas fica útil e inerte ao mesmo tempo: mexe no que se vê e em
nada do que se calcula. O custo é uma indireção — para saber a unidade de uma
camada é preciso resolver a referência — e é esse custo que impede a cópia
divergir do original.
