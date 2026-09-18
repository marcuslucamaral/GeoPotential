# `../data/` — todo arquivo é exercitado, ou não fica

Antes desta regra, **26 dos 56 arquivos** de `../data/` não eram citados por
teste nem storyboard nenhum da árvore: doze camadas de deslizamento, dois
levantamentos do Utah FORGE, e quase tudo que o M0 gerou em `data/synthetic/`
e depois parou de usar.

Um fixture sem uso é pior que um fixture ausente. Ocupa espaço, aparece na
documentação como se provasse alguma coisa, e quando quebra nada avisa.

## A regra

**`--only data-coverage` anda no diretório, não numa lista.** Acrescentar um
arquivo em `../data/` já o põe no gate. Para ele passar, o arquivo precisa de
três coisas:

1. **Ser um formato que o produto declara ler.** `classify` tem de aceitá-lo.
   Se não aceita, não é fixture: é lixo no diretório.
2. **Ser legível por `describe`.** Um fixture defeituoso *de propósito*
   continua legível — o defeito dele é de CRS, de nodata ou de unidade, nunca
   de sintaxe. Um arquivo que o worker não abre é um arquivo que não testa
   nada.
3. **Ter procedência no diretório.** Um `README.md` para dado de terceiros,
   um `MANIFEST.json` para o que este projeto gerou. Dado sem origem não é
   evidência.

Um arquivo que não pode cumprir as três é **corrigido ou removido**, nunca
adicionado à lista de exceções. Se precisar mesmo de exceção, ela vai em
`COMPANION_SUFFIXES`/`COMPANION_NAMES` e só vale para arquivo que **pertence a
outro** — o `.prj` de um shapefile, o `.meta.json` de um CSV.

## Dado de terceiros

Vem com **DOI, licença e checksum**, e o checksum de origem é conferido no
download — não depois, não "confiando na fonte". O `README.md` do diretório
registra os quatro, mais **o que foi alterado**.

Recortar um arquivo grande é legítimo e **é uma alteração**: diga a janela e
diga por que ela é uma janela e não uma amostra. Em campo potencial a
geometria é o dado, e um subconjunto espalhado de linhas de voo tem um
espectro que o levantamento original não tem — os operadores espectrais
passariam a ser gateados contra um artefato.

## Dado gerado

Vai em `data/synthetic/`, sai de `tools/make_synthetic_data.py`, é **semeado**,
e regerar reproduz byte a byte. Um fixture que muda quando você o reconstrói é
um fixture cujo gate mede o gerador.

Cada fixture defeituoso carrega **exatamente um defeito**, e o `MANIFEST.json`
diz qual regra e qual severidade ele tem de disparar. O gate lê o manifesto:
um defeito que silenciosamente deixou de existir é um gate verde que não testa
nada.

## O que este gate **não** faz

Não duplica a ciência. Se o IDW interpola certo é `--only interpolation`; se o
QA/QC pega um CRS ausente é `--only qc`. Aqui a pergunta é mais estreita, e
vale para todo arquivo: **o produto consegue te ler, e você é o que o teu
diretório diz que és?**

## Tipos de dado, não só formatos

Uma suíte que roda vinte GeoTIFFs contínuos do mesmo levantamento testou um
caso. O conjunto em `../data/` cobre deliberadamente:

| Eixo | Coberto por |
|---|---|
| contínuo · classe · direção | `conditioning_factors/` — as três pertinências saem daí |
| métrico · geográfico | `synthetic/utm_field.tif` contra `wgs84_field.tif`; os dois levantamentos reais em `EPSG:4326` |
| raster · vetor · tabela | as três famílias de `classify` |
| shapefile · geopackage · geojson | caminhos diferentes do GDAL; um funcionar não diz nada sobre os outros |
| esparso · em grade | os `.csv` do Utah FORGE contra os `.tif` |
| gravimetria · magnetometria | `bushveld_gravity/` e `britain_magnetic/` — **reais**, porque até `0.8.06` o módulo de campos potenciais só tinha visto campo sintético |
| pequeno · 16 Mpx | `synthetic/msp/canvas/` |
| **vários tipos sobre a mesma área** | `southern_africa/` — raster contra esparso, projetado contra geográfico, regional contra local |

**Falta um eixo? O dado se busca**, de fonte confiável, com DOI e licença — não
se inventa um fixture que confirme o que o código já faz.

O eixo que mais custa e mais paga é o último: um MCDA consome **grandezas
diferentes sobre o mesmo terreno**, e um diretório onde tudo já está no mesmo
CRS e na mesma grade nunca faz a reprojeção nem a harmonização entrarem no
caminho. Quando a região existe, a sobreposição é **medida** pelo gate e não
afirmada no README: três arquivos numa pasta chamada "uma região" não são uma
região até a extensão de um conter a do outro.

## Formato que o ambiente não lê

Acontece, e a saída **não** é instalar um driver. O ambiente é o `mcda_geo`
que o contrato fixa, e um fixture que só abre com um plugin a mais é um
fixture que quebra na máquina que só tem o release. Busque o mesmo dado em
formato que o produto lê, e **registre a tentativa** — qual arquivo, qual DOI,
por que não serviu. Foi o caso do netCDF4 da topografia da África Austral.
