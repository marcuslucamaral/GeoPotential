# Instalar o GeoPotential Professional no Ubuntu

Este arquivo viaja dentro do `.tar.gz`. Se você o está lendo depois de
descompactar, está no lugar certo.

## O que você recebeu

```
geopotential-<versão>-linux-x86_64-<data>.tar.gz
├── geopotential/     a aplicação inteira: Python, Qt, GDAL, PROJ, tudo dentro
├── install.sh        põe no lugar, cria o comando e a entrada de menu
└── INSTALL.md        este arquivo
```

**Não há nada para instalar antes.** O pacote carrega o próprio interpretador
Python, o próprio Qt e a própria pilha geoespacial (GDAL, PROJ, rasterio,
geopandas). Uma máquina Ubuntu limpa, sem Python de desenvolvimento, sem conda
e sem internet, roda isto.

## Instalar

```bash
tar -xzf geopotential-<versão>-linux-x86_64-<data>.tar.gz
cd geopotential-<versão>-linux-x86_64-<data>    # ou onde extraiu
./install.sh
```

Isso põe a aplicação em `~/.local/share/geopotential`, cria o comando
`~/.local/bin/geopotential` e uma entrada no menu do sistema. **Não precisa de
root.**

Para instalar para todos os usuários da máquina:

```bash
sudo ./install.sh --system
```

que usa `/opt/geopotential` e `/usr/local/bin/geopotential`.

Para remover:

```bash
./install.sh --uninstall          # ou: sudo ./install.sh --system --uninstall
```

Seus projetos não são tocados: eles estão onde você os salvou.

## Confirmar que funcionou

```bash
geopotential --self-test
```

Deve terminar com `59/59 checks passed`. Esse teste exercita o que quebra num
pacote mal feito: PROJ achando o `proj.db`, o QML carregando, o worker subindo
como processo separado, o GeoTIFF sendo lido, o canvas desenhando. Se ele passa,
a instalação está boa.

Sem display (por SSH, por exemplo), rode assim:

```bash
QT_QPA_PLATFORM=offscreen geopotential --self-test
```

## Usar

```bash
geopotential                       # abre no dado de exemplo que vem junto
geopotential /caminho/para/um.tif  # abre num raster seu
```

Ou pelo menu do sistema, em Ciência / Educação.

## Se não funcionar

**`geopotential: command not found`** — `~/.local/bin` não está no seu `PATH`.
O `install.sh` avisa quando isso acontece e diz o caminho completo. Para
resolver de vez:

```bash
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc && source ~/.bashrc
```

**A janela não abre, ou o Qt reclama de plugin** — falta a biblioteca do
sistema que o Qt usa para falar com o servidor gráfico. No Ubuntu:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0
```

É a única dependência de sistema que este pacote não pode carregar consigo,
porque ela conversa com o servidor gráfico da máquina.

**Qualquer outro erro** — rode `geopotential --self-test` e mande a saída. Ela
diz qual das 59 checagens falhou, e cada uma nomeia o que ela testa.

## O que este pacote é, e o que não é

- **É** Linux x86_64, construído a partir de um ambiente, verificado rodando o
  binário num ambiente despido (`env -i`, sem `PATH` para o ambiente de
  desenvolvimento).
- **Não é** Windows nem macOS. Cada um precisa da sua própria construção, e
  nenhuma foi feita nem testada.
- **Não é** assinado, não tem repositório `apt`, não tem ícone próprio de
  aplicação e não passa por CI. Isso é o M8.
- O pacote inclui **as fixtures de teste** (~72 MB dos ~617 MB instalados), que
  é o que permite ao binário rodar o próprio gate na máquina de destino. É uma
  escolha: sem elas o pacote seria bem menor e você não teria como verificar a
  instalação.

## Reconstruir

Da raiz do repositório, em `geopotencial_msp/`:

```bash
tools/build_app.sh --clean
```

O script gera as fixtures, roda o gate da árvore, empacota e **verifica o
binário que saiu** — `--help`, o worker respondendo, `--self-test` e uma captura
de tela real, as duas últimas com `env -i`. Um build cujo binário não passa não
produz arquivo.
