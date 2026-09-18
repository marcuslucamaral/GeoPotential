# Empacotar o MSP

O workspace já tem `../docs/conventions/packaging.md`, e tudo lá continua valendo:
bibliotecas fixadas do ambiente, dados de PROJ e GDAL por runtime hook, QML como
dado, `--onedir`, UPX desligado, `console=True`, `build/` não é entrada.

Isto acrescenta o que é desta árvore e não daquela.

## A regra que as outras servem

**Um build que não foi exercitado não é evidência de que funciona.**
`tools/build_app.sh` roda o gate **do binário entregue** e reprova o build se
ele não passar. Não existe chave para pular. `--fast` pula o gate *da árvore*
antes de empacotar, para iteração local, e o próprio script avisa que o
artefato daí não se publica.

Rodar a verificação com o ambiente de desenvolvimento no `PATH` não prova nada.
As duas checagens que importam rodam com
`env -i HOME=/tmp PATH=/usr/bin:/bin`.

## Esta aplicação são dois processos num arquivo

O app e o worker nunca se importam (`P-02`) e em execução são dois PIDs. Num
bundle **não há interpretador para receber `-m`**: `sys.executable` é o próprio
binário, e `-m geopotential_worker` abriria uma segunda interface.

- `tools/frozen_entry.py` é o ponto de entrada e despacha por argv. Ele fica em
  `tools/` **de propósito**: o gate de arquitetura varre
  `app/geopotential_app/`, e um lançador que sabe dos dois pacotes não pode ser
  código de aplicação. Ele importa um **ou** o outro, nunca os dois no mesmo
  processo.
- `WorkerSupervisor._command()` é o único lugar que escolhe entre `-m` e
  `--worker`. Se você precisar de um terceiro modo, ele vai aí, não espalhado.
- **Nunca faça o app importar o worker para "simplificar o bundle".** Isso
  desfaz a separação de processos, e "matar o worker e reiniciar" deixa de
  significar alguma coisa.

## O ambiente do filho

`QProcess.processEnvironment()` volta **vazio**. Um filho lançado a partir dele
recebe só o que você inserir — sem `PATH`, sem `LD_LIBRARY_PATH`. Num checkout
passa despercebido, porque o Python do conda se resolve sozinho; num bundle o
filho não acha as bibliotecas ao lado dele.

A base é `QProcessEnvironment.systemEnvironment()`, sempre.

## Uma captura que existe não é uma captura que desenhou

Uma janela que falha em compor escreve um PNG perfeitamente válido de uma cor
só, e `[ -s "$arquivo" ]` aprova. O script conta cores distintas e reprova
abaixo de 50.

O mesmo raciocínio já tinha aparecido nos ícones: um efeito de shader não
desenha nada sob `offscreen`, e um quadro em branco é um quadro válido
(`app/geopotential_app/icons.py`). **Toda evidência visual precisa de um número
junto.**

## As fixtures vão no pacote

72 MB dos 617 MB instalados. É deliberado: sem elas o `--self-test` do binário
pula sete checagens e a verificação que aprova o build fica mais fraca na
máquina de destino. `repository_root()` volta a raiz do bundle quando congelado,
que é onde `--self-test` já procura.

Se um dia isso for cortado, corte **com a medição na mão** e registre o que a
verificação passa a não cobrir.

## O que ainda não existe

Não há `.deb`, não há assinatura, não há repositório `apt`, não há ícone de
aplicação e não há CI. `tools/install.sh` põe o pacote em `~/.local` ou `/opt`,
cria o comando e a entrada de menu, e desinstala. Isso é o mínimo para instalar
noutra máquina, não é uma release — e o M8 é onde o resto entra.

`libxcb-cursor0` e `libxkbcommon-x11-0` são a única dependência de sistema que
o pacote não carrega, porque conversam com o servidor gráfico da máquina.
