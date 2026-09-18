# ADR-MSP-006 — Mapa de fundo de tiles abertos, desligado por padrão

Status: `ACCEPTED`
Data: `2026-09-02`
Decidido por: Marcus, explicitamente, depois de a objeção ter sido levantada
duas vezes
Altera: `P-07` — "nenhum módulo web em lugar nenhum; nenhuma porta TCP aberta
em runtime". Esta é a única mudança de contrato que o M5.5 faz.

## Contexto

O produto nasceu offline por decisão: sem HTTP, sem localhost, sem WebView,
sem servidor embutido. A barra de estado diz "offline · tudo local", e o gate
falha se `flask`, `fastapi`, `requests`, `httpx` e afins aparecerem em qualquer
lugar. Isso protege duas coisas reais: um resultado científico que não depende
de um serviço de terceiro para ser reproduzido, e um produto que roda numa
máquina sem rede.

O pedido, repetido, é o do QGIS com o QuickMapServices: um mapa de fundo sobre
o qual os dados se situam. Sem ele, um ponto de gravimetria flutua num fundo
preto e ninguém sabe se está no lugar certo — que é exatamente o que aconteceu
com o CSV do Utah.

## Decisão

**Um mapa de fundo de tiles XYZ, de fontes abertas, desligado por padrão.**

Cinco condições, e nenhuma é opcional:

1. **Só fontes abertas, com atribuição visível.**
   - **OpenStreetMap** — ODbL. Atribuição obrigatória: "© OpenStreetMap
     contributors".
   - **OpenTopoMap** — CC-BY-SA 3.0, sobre dados OSM e SRTM.
   A atribuição da fonte ativa fica **no canto do mapa** e vai junto no mapa
   exportado. Um mapa impresso sem a atribuição viola a licença.

   **Carto Positron e Dark Matter foram incluídos e removidos.** O estilo é
   CC-BY, mas o CDN que o serve responde a um cliente anônimo com um tile
   escrito `API KEY REQUIRED` — HTTP 200, PNG válido, e uma recusa. Apareceu
   na tela, escrito sobre o mapa. Uma fonte que exige chave exige conta, e
   isso não entra no produto.

   A lição virou ferramenta: `tools/verify_sources.py` busca um tile de um
   lugar denso, decodifica e conta as cores. Um mapa de verdade tem centenas;
   uma marca d'água tem uma dúzia. Uma fonte se verifica olhando o que ela
   devolve, não lendo a página de licença dela.

2. **Google, Bing, Esri e Mapbox ficam de fora.** Os termos de uso deles
   proíbem consumir os tiles fora dos seus próprios aplicativos ou exigem
   contrato e chave. Não há como embutir isso sem transferir um problema
   jurídico para quem usa o produto, e não se embute.

3. **Desligado por padrão, e ligado por ato explícito.** Sem projeto nenhum
   configurado, a aplicação continua sem tocar na rede. Ligar é uma escolha por
   projeto, e a barra de estado passa a dizer o que está ligado, no lugar de
   "offline · tudo local".

4. **A fonte entra no manifesto da run e nos metadados do mapa exportado.** Um
   mapa com imagem de terceiro por baixo e sem procedência é um mapa que não se
   pode auditar. O manifesto registra a URL do template, o nome da fonte, a
   licença e a data.

5. **O fundo nunca entra em cálculo.** Não é camada de critério, não é entrada
   de operador, não tem valor sob o cursor, não participa de harmonização,
   membership, AHP ou agregação. É pintura sob os dados, e o gate impede que
   vire outra coisa.

## O que `P-07` passa a dizer

De: *nenhum módulo web em lugar nenhum; nenhuma porta TCP aberta em runtime.*

Para: **nenhum servidor, nenhuma porta TCP escutando, nenhum WebView e nenhum
framework web.** A rede é usada apenas para buscar tiles de uma fonte declarada
de mapa de fundo, por HTTPS, e só quando o usuário liga.

Continua proibido, e o gate continua verificando: `flask`, `fastapi`,
`uvicorn`, `aiohttp`, `tornado`, `starlette`, `django`, qualquer WebView ou
QtWebEngine, e qualquer porta em escuta. O buscador de tiles é um cliente HTTPS
e nada mais.

## Consequências

- **Depende do E5.** Os tiles são servidos em Web Mercator (`EPSG:3857`); sem
  reprojeção de exibição eles não se alinham a nada em UTM. Por isso o E5 vem
  primeiro, e já veio.
- **Cache em disco, dentro do projeto.** Um tile buscado é guardado, com a data
  e a fonte. Assim o mesmo mapa reabre sem rede, e a imagem que sustentou uma
  decisão continua disponível.
- **Falha de rede não é falha do projeto.** Sem rede, o fundo simplesmente não
  aparece e a barra diz por quê. Nada do fluxo científico depende dele.
- **Uso respeitoso da fonte.** Um `User-Agent` que identifica o produto, um
  limite de requisições simultâneas, e nenhum download em massa: as políticas
  do OSM proíbem raspagem de área.

## Como é verificado

- `--only basemap` — a fonte é uma das declaradas; a atribuição é obrigatória e
  não vazia; o cache guarda fonte e data; a camada de fundo aparece no painel,
  fica sempre por baixo e nunca vira camada ativa.
- `tools/verify_sources.py` — cada fonte devolve um tile de verdade. Precisa de
  rede, então reporta `BLOCKED` sem ela; não faz parte do gate por isso.
- `architecture_check.sh` — nenhum framework web, nenhum WebView, nenhuma porta
  em escuta; o cliente de tiles é o único ponto que fala rede, e é nomeado.
- `--only basemap` — o mapa de fundo não é aceito por nenhum operador e não
  aparece em nenhum manifesto como entrada científica.
- `--self-test` — com o fundo desligado, nenhuma conexão é aberta.
