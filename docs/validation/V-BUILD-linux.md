# V-BUILD — Executável Linux x86_64, verificado

Data: `2026-09-03`, reconstruído em `2026-09-17`
Versão: app `0.8.07`, worker `0.5.05`
Reproduzir: `tools/build_app.sh --clean` a partir de `geopotencial_msp/`

## Resultado

`PASS`.

| Item | Valor |
|---|---|
| Forma | um diretório (`--onedir`), não um arquivo único |
| Instalado | **617 MB** |
| Arquivo | **258 MB** (`.tar.gz`) |
| Plataforma | Linux x86_64, PyInstaller 6.22.2, Python 3.11.14 |
| Gate da árvore, antes de empacotar | **37 de 37** |
| **Gate do binário entregue** | **59 de 59**, em `env -i` |
| Operadores anunciados pelo worker de dentro do bundle | **27** |
| Captura de verificação | 1440×880, 1166 cores distintas |
| Arquivo entregue | `geopotential-0.8.07-linux-x86_64-20260917.tar.gz` |
| SHA256 | `6b37ac274478493e5be5d83c32cbc8ac799c097a8288087b214cc9e8a6d378e0` |

## O problema que este build teve de resolver primeiro

**Esta aplicação são dois processos.** O app e o worker são pacotes que nunca se
importam (`P-02`), e em execução são dois PIDs conversando por JSON Lines. Num
checkout o supervisor lança `sys.executable -m geopotential_worker`.

Num bundle isso não existe: `sys.executable` **é o binário**, não um
interpretador. `-m geopotential_worker` abriria uma segunda cópia da interface.

A saída foi dar ao binário a capacidade de ser qualquer um dos dois:

- `tools/frozen_entry.py` é o ponto de entrada do bundle e despacha por argv —
  `--worker` importa o worker, qualquer outra coisa importa o app. Ele fica em
  `tools/`, **fora de `app/geopotential_app/`**, então não é código de aplicação
  e o gate de arquitetura continua reprovando qualquer import do worker feito de
  dentro do app. Nenhum módulo dos dois pacotes aprende que o outro existe.
- `WorkerSupervisor._command()` escolhe entre `-m geopotential_worker` e
  `--worker` conforme `sys.frozen`.

Os dois processos continuam dois: PIDs distintos, memórias distintas, stdout
como protocolo e stderr como log. O que passou a ser compartilhado é um arquivo
em disco, que é o que `--onedir` dá de qualquer forma.

**Um defeito vizinho, corrigido no caminho:** `proc.processEnvironment()` volta
vazio, então o worker filho recebia **apenas** `PYTHONPATH` e
`PYTHONUNBUFFERED` — sem `PATH`, sem `LD_LIBRARY_PATH`. Funcionava porque o
Python do conda se resolve sozinho; num bundle o filho não acharia as
bibliotecas ao lado dele. Agora a base é `QProcessEnvironment.systemEnvironment()`.

## O que o pacote carrega

| | |
|---|---|
| A interface Qt Quick | `qml/`, o `qmldir` e os **35 ícones SVG** — PyInstaller segue imports e não sabe que `Main.qml` nomeia `ActivityBar`, nem que `ActivityBar` nomeia `icons/app/import.svg` |
| Os dois pacotes | `geopotential_app` e `geopotential_worker`, o segundo nomeado explicitamente porque nada no grafo leva até ele |
| PROJ e GDAL | `share/proj` e `share/gdal`, achados do ambiente vivo e apontados por um **runtime hook** — pyproj e rasterio resolvem os diretórios no import, antes de qualquer módulo da aplicação rodar |
| As fixtures | o raster de exemplo, os 14 datasets defeituosos da QA/QC e os dois rasters 4096×4096 do canvas — 72 MB, e é o que faz o `--self-test` do binário significar alguma coisa numa máquina sem checkout |
| `libssl`, `libcrypto`, `libcurl` | fixados do ambiente. O loader prefere a cópia do sistema, e misturar um `libcurl` do conda com um `libssl` do `/usr/lib` produz um binário que compila limpo e morre no primeiro import |

## O que ficou de fora, verificado e não chutado

`grep -rn <nome> app/ worker/` para cada um. A única menção a matplotlib nesta
árvore é um comentário em `render/colormap.py` dizendo que as rampas são
definidas à mão **porque** `render/` não pode importar biblioteca de plotagem.

matplotlib, plotly, seaborn, bokeh, sklearn, tkinter, IPython, jupyter,
notebook, pytest, PyInstaller, e os módulos Qt de web, 3D, gráficos,
multimídia, bluetooth, NFC, posicionamento, porta serial, teste e designer.

**scipy ficou**, e é carregado: `cKDTree` para o IDW e a distância euclidiana,
Qhull para os dois interpoladores triangulados, `ndimage` para a transformada
de distância. São 34 MB e todos os três chegam por `from scipy... import` dentro
de função, então entraram como hidden imports.

## Como foi verificado

Rodando o binário, não lendo o log do build. As duas últimas checagens com
`env -i HOME=/tmp PATH=/usr/bin:/bin` — rodar com o ambiente de desenvolvimento
ainda no `PATH` não prova nada, porque é exatamente o ambiente que o binário
existe para não precisar.

| Checagem | O que ela pega | Resultado |
|---|---|---|
| `--help` | o bootloader descompactou e o Python subiu | `ok` |
| `--worker --capabilities` | **o binário consegue ser o outro processo** | 13 operadores |
| `--self-test` em `env -i` | PROJ achou o `proj.db`, o QML carregou, o worker subiu como filho, o GeoTIFF foi lido, o canvas desenhou, o processo encerrou limpo | **59/59** |
| `--screenshot` em `env -i` | GDAL lê e a tela compõe | 1440×880, **1167 cores** |

A última checagem não se contenta com "o arquivo existe": uma janela que falha
em compor escreve um PNG perfeitamente válido de uma cor só. O script conta as
cores distintas e reprova abaixo de 50.

## A instalação, testada de ponta a ponta

Numa máquina simulada — `HOME` falso, `env -i`, sem `PATH` para o conda:

```
tar -xzf geopotential-0.4.00-linux-x86_64-20260903.tar.gz
./install.sh                    -> ~/.local/share/geopotential
                                   ~/.local/bin/geopotential
                                   ~/.local/share/applications/geopotential.desktop
geopotential --self-test        -> 59/59 checks passed
./install.sh --uninstall        -> removeu os três, sem deixar resto
```

`sudo ./install.sh --system` faz o mesmo em `/opt/geopotential` e
`/usr/local/bin`. O manual viaja dentro do arquivo (`INSTALL.md`).

## O que este artefato não é

- **Não é Windows nem macOS.** Cada um precisa da sua própria construção, a
  partir do seu próprio ambiente. Nenhuma foi feita, nenhuma foi testada.
- **Não é assinado**, não tem repositório `apt`, não tem `.deb`, não tem ícone
  próprio de aplicação e não passa por CI. Isso é o M8.
- **Não é pequeno.** 617 MB instalados, dominados por: fixtures 72 MB, PySide6
  56 MB, OpenBLAS 40 MB, GDAL 35 MB, scipy 34 MB, ICU 32 MB. Tirar as fixtures
  economizaria 72 MB e custaria a capacidade de o binário se verificar na
  máquina de destino — a troca está registrada aqui e não foi feita.
- **Uma dependência de sistema não é carregada**: `libxcb-cursor0` e
  `libxkbcommon-x11-0`, que conversam com o servidor gráfico. `INSTALL.md` diz
  como instalar.
