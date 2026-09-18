# ADR-MSP-005 — Sobreposição é comparada no mesmo CRS, e não bloqueia a importação

Status: `ACCEPTED`
Data: `2026-09-02`
Decidido por: Marcus, sobre um defeito observado com dados reais
Altera: a severidade da regra `extent.overlap` (MSP-04) e o modo como ela
compara extensões. Corresponde à exigência do contrato de que mudar uma
severidade é decisão científica registrada.

## Contexto

Duas camadas reais foram carregadas no mesmo projeto:

- `Distance_to_fault.tif` — `EPSG:26912`, Utah, coordenadas na casa de
  330 000 / 4 260 000;
- `forest_type.tif` — `EPSG:5186`, Coreia, coordenadas em outra ordem de
  grandeza.

A regra `extent.overlap` comparou os quatro números de uma com os quatro da
outra **sem reprojetar**, concluiu que não se tocam, e emitiu um `BLOCKER`. A
importação foi recusada.

Dois problemas, não um:

1. **A comparação não significa nada.** Extensões em CRSs diferentes são
   quatro números em sistemas diferentes; compará-las diretamente responde a
   uma pergunta que ninguém fez. Duas camadas *podem* se sobrepor no terreno e
   parecer disjuntas nessa conta, e o inverso também.
2. **A severidade estava no lugar errado.** Uma camada disjunta quebra a
   **harmonização** — lá a interseção fica vazia e o mapa de prospectividade
   diria "nenhum lugar é favorável" no lugar de dizer que houve erro. No
   momento da *importação* ela não quebra nada: pode ser dado de referência,
   pode ser a primeira de outra área, pode ser exatamente o que a pessoa quer
   olhar.

## Decisão

**A comparação passa a ser feita num CRS comum.** Quando as duas camadas
declaram CRS e eles diferem, a extensão da candidata é reprojetada para o CRS
da camada existente antes do teste. Quando algum dos dois não tem CRS, não há
comparação a fazer: a ausência de CRS já é o `BLOCKER` da regra `crs.present`,
que é o problema real.

**A severidade de `extent.overlap` na importação passa de `BLOCKER` para
`WARNING`.** O texto do achado passa a dizer o que a sobreposição afeta —
harmonização e agregação — e não que o arquivo é inutilizável.

**A recusa dura permanece onde o dano existe.** `grid/harmonize.py` já recusa
uma interseção vazia com mensagem própria, e essa recusa não é afrouxada: um
`ValueError` nomeando as camadas e mandando conferir o CRS. Um teste passa a
guardar isso explicitamente, para que mover o aviso não vire mover a proteção.

## O que isto não afrouxa

- `crs.present` continua `BLOCKER`: sem CRS, nada é comparável e a run para.
- `crs.metric_required` continua `BLOCKER` onde a operação mede em metros.
- A harmonização continua recusando interseção vazia.
- Nenhuma tolerância numérica muda.

## Consequências

Uma camada em outro CRS **entra no projeto** e pode ser vista. Ela chega à
harmonização como qualquer outra, e lá — onde a interseção vazia produziria um
mapa errado — a recusa acontece com o nome das camadas envolvidas.

`../data/synthetic/msp/broken/MANIFEST.json` passa a esperar `WARNING` para
`disjoint.tif`, e os testes que afirmavam `BLOCKER` foram atualizados junto
com esta decisão, não antes dela.

## Como é verificado

- `--only qc` — `disjoint.tif` produz `extent.overlap` com severidade
  `WARNING`, e o dataset fica utilizável.
- `--only import` — uma camada disjunta é importável, e o veredito registra o
  aviso.
- `--only pipeline` — a harmonização de camadas disjuntas continua recusada,
  nomeando as camadas.
- `--only qc` — duas camadas que **se sobrepõem no terreno** mas estão em CRSs
  diferentes não produzem mais o aviso.
