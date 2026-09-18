# `build/` e `dist/` — nunca ler, nunca editar, nunca limpar à mão

Se você chegou aqui, está prestes a tocar em algo que **não é fonte de nada**.

| Pasta | O que é | Quem produz |
|---|---|---|
| `build/` | o rascunho do PyInstaller | `tools/build_app.sh` |
| `dist/` | o artefato entregue, mais o instalador e o manual | `tools/build_app.sh` |

## Não leia

Nem com `cat`, `grep`, `find`, `ls`, Read, Glob ou um subagente, e nunca como
contexto de fundo.

Os `.toc`, o `warn-geopotential.txt` e o `xref-geopotential.html` são a
contabilidade do próprio PyInstaller: eles repetem o que
`tools/geopotential.spec` já declara, mais o que a última execução por acaso
viu, e ficam obsoletos no instante em que o spec muda.

**Uma pergunta sobre o que está no bundle, ou sobre por quê, se responde nesta
ordem:**

1. a receita — `tools/geopotential.spec`
2. a regra — `docs/conventions/packaging.md`
3. a evidência — `docs/validation/V-BUILD-linux.md`
4. o manual — `docs/INSTALL.md`

Se nenhum deles responde, **rode o build e leia a saída dele** — ou faça uma
sondagem de `sys.modules` no binário entregue. Nunca vasculhe o rascunho.

## Não edite

Um bundle errado se conserta em `tools/geopotential.spec`, em
`tools/runtime_hook_geodata.py` ou em `tools/frozen_entry.py`, e se reconstrói.

Editar o artefato em `dist/` produz uma coisa que **nenhum rebuild reproduz**,
que é exatamente a propriedade que empacotar existe para garantir. Um binário
remendado à mão não é o binário que o gate aprovou.

## Não apague à mão

`tools/build_app.sh --clean` é o único que remove as duas. Ele sabe a ordem e
reconstrói em seguida.

## Como chegar no artefato

Pelo `tools/build_app.sh`, que roda o gate **do binário entregue** contra ele —
`--help`, o worker respondendo, `--self-test` e uma captura real, as duas
últimas com `env -i`. Navegar na árvore não é verificação; rodar o binário é.

O caminho e o sha256 do arquivo saem no resumo do build, e as instruções de
instalação vão em `dist/COMO-INSTALAR.txt`, gerado pelo build com o nome real
daquela versão dentro. Não crie um arquivo de instruções à mão nesta pasta: ele
nomearia uma versão e estaria errado no build seguinte.
