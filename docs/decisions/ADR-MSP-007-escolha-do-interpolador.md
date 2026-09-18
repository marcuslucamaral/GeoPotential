# ADR-MSP-007 — Três interpoladores, e a escolha entre eles é medida

Status: `ACCEPTED`
Data: `2026-09-03`
Decidido por: Marcus, depois de testar o M5.6 na aplicação e reportar que o
resultado "tá bem ruim… o correto é o valor… implemente conforme o QGIS"
Altera: `P-148` deixa de ser a única regra sobre extrapolação — passa a valer
para `grid.idw`, e o comportamento dos métodos triangulados é declarado aqui.

## Contexto

O M5.6 entregou um interpolador, IDW, e a tela de gerar grade não oferecia
outro. IDW é uma média ponderada: cada estimativa é puxada para a média local,
e por construção o método **não consegue devolver um valor que não viu**. Numa
malha regular de amostras — que é o que uma seção modelada ou um levantamento
já reamostrado quase sempre é — isso aparece como a textura manchada em torno
de cada amostra e como faixa comprimida no mapa.

Não era impressão. Medido por validação cruzada de 5 partições nos dados reais
do projeto, com o raio que a tela propõe:

| Dado | amostras | geometria | IDW | TIN linear | TIN cúbico |
|---|---|---|---|---|---|
| `vp_500_m.csv` | 1 626 | malha 125 m | 0,0766 | 0,0567 | **0,0411** |
| `density_modified_500m.csv` | 4 273 | malha 100 m | **0,0165** | 0,0171 | 0,0177 |
| `anomaly_bouger…csv` | 3 735 | disperso | 0,954 | **0,857** | 1,460 |
| `magtellu_min_depth_500m.csv` | 6 898 | disperso | 327 | 337 | **312** |

RMSE na unidade de cada dado, sobre as amostras que todo método respondeu. A
leitura é a única que importa: **cada um dos três ganha em algum arquivo, e a
geometria das amostras não prevê qual.** Duas malhas regulares, dois
vencedores diferentes. Dois levantamentos irregulares, dois vencedores
diferentes. Em `vp` o cúbico erra 1,9 vez menos que o IDW; em `bouguer` erra
1,7 vez mais que o linear.

Uma observação honesta sobre como esta decisão foi tomada: a exploração
inicial usou uma separação única de 20 % e produziu uma regra arrumada —
"malha favorece o cúbico, disperso favorece o IDW". Sob 5 partições essa regra
**cai**: o vencedor muda em dois dos quatro arquivos. A conclusão que sobra é
mais fraca como regra e mais forte como argumento — não há heurística de
geometria que substitua a medição.

Três dos cinco arquivos em `../data/utah_forge/` são malhas regulares gravadas
como tabela, e o método oferecido era um só.

## Decisão

**Três interpoladores, que são os três que o QGIS oferece, e a escolha entre
eles é medida no próprio levantamento.**

1. **`grid.tin_linear`** — interpolação baricêntrica dentro de cada triângulo
   de Delaunay. É o *TIN interpolation, Linear* do QGIS, sobre
   `scipy.interpolate.LinearNDInterpolator`.
2. **`grid.tin_cubic`** — Clough-Tocher, um retalho cúbico por triângulo, C1
   em cada aresta. É o *TIN interpolation, Clough-Toucher* do QGIS, sobre
   `scipy.interpolate.CloughTocher2DInterpolator`.
3. **`grid.idw`** permanece exatamente como está. Nada nele muda.
4. **`grid.cross_validate`** separa um quinto das amostras, prevê com cada
   método e reporta o erro na unidade do dado. É **read-only**: não grava
   artefato, não commita run, não cria linhagem (`P-53`).

Cinco condições, e nenhuma é opcional:

**a) Fora do casco convexo a resposta é nula.** Nunca a amostra mais próxima,
por mais perto que esteja. A triangulação só está definida onde as amostras
cercam a célula; além disso não há levantamento — a mesma regra que o
`idw.py` enuncia sobre o raio, pelo mesmo motivo. `max_distance` é um limite
extra opcional, para o caso de um triângulo largo atravessar um vazio que
ninguém mediu; ausente, o casco é o único limite, que é o que o QGIS faz.

**b) O cúbico pode passar do intervalo das amostras, e isso não é cortado.**
Uma superfície C1 precisa se curvar para encontrar a derivada dos vizinhos, e
num degrau abrupto a cúbica ultrapassa. Isso é propriedade do método, não
defeito. Um cúbico cortado não é Clough-Tocher e não reproduz o QGIS — deixa
de ser comparável com a ferramenta que o usuário conhece, que é a razão de o
método existir aqui. Então **é medido e registrado**, não silenciado:
`statistics` devolve `overshoot` com quanto passou acima e abaixo e que fração
da faixa amostrada isso representa, o manifesto carrega, e a tela avisa antes
de rodar. Em `vp_500_m.csv` foi 2,47 % da faixa.

**c) `P-148` continua valendo para o IDW.** "IDW não extrapola: o resultado
fica dentro do intervalo das amostras" é uma propriedade da média ponderada e
segue sendo testada. O que muda é que ela deixa de ser lida como regra de
todo interpolador — `tin_linear` também a satisfaz, por construção, e é
testado; `tin_cubic` não a satisfaz e diz por quê.

**d) A recomendação é conselho, nunca ação.** A tela mostra o ranking e marca
o menor erro. Não troca o método escolhido, não roda nada, não desabilita as
outras opções. Quem opera decide, e a decisão fica no manifesto.

**e) A comparação é sobre as mesmas amostras.** O raio do IDW deixa amostras
separadas sem resposta onde um método triangulado, limitado só pelo casco,
ainda responde. Pontuar cada método no seu próprio subconjunto premiaria o que
respondeu menos, porque os pontos com mais vizinhos são os fáceis. Então o
RMSE é sobre a interseção, e a cobertura de cada método é reportada à parte —
as duas coisas, porque um método que ganha em 60 % dos pontos não ganhou.

## Alternativas consideradas

**Trocar o padrão para Clough-Tocher.** Rejeitada pela tabela acima: ele
perde em dois dos quatro arquivos, um deles uma malha regular. O problema
nunca foi qual é o padrão, foi haver um só.

**Kriging.** É o que um geocientista pediria em seguida, e é o único dos
métodos comuns que estima incerteza junto com o valor. Fica de fora aqui por
uma razão de escopo e uma de honestidade: o QGIS não traz kriging no core (vem
de SAGA/GRASS), e kriging sem ajuste de variograma na tela é kriging com
parâmetros inventados — pior que não ter. Anotado como não entregue.

**Spline de placa fina (RBF).** Mediu bem na exploração inicial — melhor que
tudo em `vp` e em `magtellu` — e foi deixada de fora mesmo assim. Não está no QGIS core, o
pedido era "conforme o QGIS", e ela **falhou** com matriz singular no dado
gravimétrico, que tem pontos coincidentes. Um método que quebra num dos quatro
arquivos do projeto não entra sem tratamento de duplicatas decidido antes.

**Cortar o overshoot do cúbico em silêncio.** Rejeitada em (b).

## Consequências

- A tela de gerar grade cresce: um seletor com quatro métodos para tabela, o
  botão de medir, o ranking, o aviso do cúbico e o campo de distância máxima.
  O raio e a potência somem quando o método não os tem — um controle que não
  faz nada é pior que um controle ausente.
- `grid.cross_validate` roda no worker e leva alguns segundos em levantamentos
  grandes. Acima de 20 000 amostras ele subamostra, com semente fixa, e diz que
  subamostrou: é apoio à decisão e precisa responder com a tela aberta.
- A semente é fixa (`20260903`). Uma recomendação que muda entre duas execuções
  no mesmo dado não é medição e ninguém poderia agir sobre ela.
- Contratos novos: `P-155` a `P-160`.

## Evidência

`docs/validation/V-M5_7-interpolation.md`; suíte `--only interpolation`
(26 testes, negativada em dois defeitos plantados); storyboard `interpolation`
(5 quadros) na janela real.

## Fontes

- QGIS Processing, *Interpolation*: IDW Interpolation e TIN Interpolation com
  os métodos Linear e Clough-Toucher —
  <https://docs.qgis.org/3.44/en/docs/user_manual/processing_algs/qgis/interpolation.html>
- GDAL `gdal_grid`, para os nomes e o comportamento de `invdistnn`, `linear`,
  `nearest` e `average` — <https://gdal.org/en/stable/programs/gdal_grid.html>
- Clough, R. & Tocher, J. (1965), *Finite element stiffness matrices for
  analysis of plates in bending*.
- Alfeld, P. (1984), *A trivariate Clough-Tocher scheme for tetrahedral data*,
  CAGD 1(2).
- Stone, M. (1974), *Cross-validatory choice and assessment of statistical
  predictions*, J. R. Stat. Soc. B 36(2), 111-147.
- Shepard, D. (1968), para o IDW que já estava aqui.
