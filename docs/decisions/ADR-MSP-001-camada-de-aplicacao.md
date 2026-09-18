# ADR-MSP-001 — A camada de aplicação é Python/PySide6, e o C++ fica atrás de um gate

Status: `ACCEPTED`
Data: `2026-09-01`
Decidido por: Marcus, sobre a evidência do ADR-007 do workspace
Substitui, para este projeto: nada. **Reconcilia** `IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §2.1/§2.2 com `../../docs/decisions/ADR-007-backend-language.md`

## Contexto

`IMPLEMENTACAO_GEOPOTENTIAL_MSP.md` §2.1 é explícito: use **Qt/C++ para a
camada de aplicação**, CMake para o build, e kernels científicos em C++
expostos ao Python por pybind11. O §2.2 detalha a fronteira: bootstrap,
lifecycle, ViewModels, models, commands, controllers, jobs, IPC,
WorkerSupervisor, GeoCanvas, autosave, recovery e empacotamento em C++;
ciência em Python, em processo separado.

O workspace já respondeu à pergunta de linguagem uma vez, e respondeu por
medição. O ADR-007 mediu quinze estágios a 16 e 64 Mpx:

- **doze dos quinze já rodam em código compilado** — GDAL, scipy, numpy;
- o throughput é **plano** de 16 para 64 Mpx, ou seja, o interpretador não
  contribui custo por elemento;
- uma run MCDA de 8 critérios a 16 Mpx fecha em **3,4 s** ponta a ponta;
- os únicos estágios ligados ao interpretador estavam no **desenho vetorial**,
  não na ciência, e foram corrigidos em Python com ganho de 154–311×.

Há ainda `../../src/geopotencial`: 6.903 linhas em PySide6, com gate verde,
139 testes unitários, 21 checagens de interface e um binário Linux verificado.

A colisão é real e precisava de decisão explícita, não de acomodação
silenciosa.

## Decisão

**A camada de aplicação do GeoPotential Professional é Python/PySide6.**

Todo o resto do §2.2 vale integralmente e sem afrouxamento:

1. **QML só apresenta.** Nenhuma regra científica, regra de negócio
   persistente, acesso a filesystem, SQLite, GDAL, NumPy, chamada Python,
   decisão de provenance ou algoritmo de MCDA em `.qml`.
2. **A camada de aplicação é a fronteira**, com ViewModels pequenos por
   domínio, models Qt, Commands, controllers, WorkerSupervisor, GeoCanvas,
   Project Store, autosave, recovery e logs.
3. **O worker científico roda em processo separado do processo da GUI**,
   iniciado por `QProcess`, falando **JSON Lines** por stdin/stdout, com
   handshake, anúncio de capacidades, progresso real, cancelamento cooperativo,
   artefatos atômicos e encerramento controlado. Sem HTTP, sem localhost.
4. **O worker não importa Qt** e **o app não importa o pacote do worker.** O
   gate de arquitetura falha nos dois casos e foi testado negativamente.
5. **Os oito critérios do §2.2 para um kernel compilado continuam valendo.**
   Nenhuma linha de C++ antes do gate.

## Por que isto não é uma diluição do §2.1

O §2.1 tem dois conteúdos, e só um deles depende da linguagem.

**O conteúdo arquitetural** — camadas separadas, QML restrito à apresentação,
ciência fora do processo da GUI, contrato versionado entre as duas metades,
canvas nativo, sem web em lugar nenhum — é o que faz o produto auditável, e
está **inteiramente preservado**. A implementação desta sessão já o demonstra:
o gate M1 verifica que o worker é outro processo (`pid` distinto), que sobe uma
única vez, que fecha limpo, que nenhuma porta TCP fica aberta e que nenhum
módulo web foi importado.

**O conteúdo de linguagem** — que a fronteira seja escrita em C++ — é o que o
ADR-007 mediu e não sustentou para esta carga de trabalho. Reescrever os
estágios numéricos em C++ substituiria chamadas a GDAL, scipy e numpy por
chamadas a GDAL, ao C++ subjacente do scipy e a BLAS, entregando o overhead de
despacho como economia: microssegundos contra operações de centenas de
milissegundos.

E, decisivo: **a fronteira IPC é agnóstica de linguagem.** O protocolo, os
schemas, o Project Store, os operadores e os artefatos não sabem em que
linguagem está escrito o supervisor. Portar a camada de aplicação para C++
depois é um trabalho localizado que **não toca no worker**. A decisão é
reversível ao custo de reescrever o supervisor, não o produto.

## Custos que a decisão evita, e que precisam ser ditos

Estes não são a justificativa — a justificativa é a medição — mas seriam pagos
e não foram:

- uma toolchain nova (Qt6 dev, CMake, compilador, pybind11) para todo
  contribuidor;
- a decisão de licenciamento Qt do §27, que passa a ser urgente no instante em
  que se vincula C++ ao Qt e se distribui um binário;
- o descarte de 6.903 linhas com gate verde e binário verificado;
- um segundo lugar onde a `Criterion` pode ser representada.

## Custos que a decisão aceita

Ditos porque uma decisão que só lista ganhos não é uma decisão:

- **A GUI carrega um interpretador Python.** O empacotamento já resolveu isto
  uma vez (`../../docs/validation/V-BUILD-linux.md`), ao preço de um bundle de
  176 MB.
- **Não há verificação de tipos em tempo de compilação na camada de
  aplicação.** O contrapeso é o gate de arquitetura executável e a pirâmide de
  testes do §22, ambos já rodando.
- **Duas cópias do módulo de protocolo.** O app não pode importar o pacote do
  worker sem reintroduzir o acoplamento que a separação de processos existe
  para eliminar, então o contrato é espelhado. **O gate compara os dois
  arquivos byte a byte** e falha na primeira divergência; o teste de contrato
  faz a mesma verificação por um segundo caminho.

## O gate de migração para C++

A pergunta do §2.1 é reaberta em **M8**, e só então. Migrar a camada de
aplicação para C++ exige, cumulativamente:

1. hotspot comprovado por profiling **por estágio**, não por impressão;
2. ganho end-to-end medido em dataset representativo;
3. custo de transferência e de manutenção medido;
4. teste de equivalência numérica com tolerância declarada **antes** da
   execução;
5. fallback de referência em Python preservado.

Introduzir um **kernel** C++ (não a camada de aplicação) exige os oito
critérios do §2.2, sem exceção, e o kernel é exposto por pybind11 com bindings
versionados.

Sem esses critérios, a camada de aplicação continua Python. **Preferência de
linguagem não é critério.**

## Consequências

- Uma toolchain, um ambiente (`mcda_geo`), sem passo de compilação.
- O gate numérico continua tendo dez linhas em vez de um harness com build.
- **A disciplina de vetorização passa a ser carga estrutural.** Python é rápido
  aqui *porque* despacha para kernels compilados; código que para de fazer isso
  perde duas ordens de grandeza em silêncio. A regra está em
  `docs/conventions/python.md` com o número medido.
- O empacotamento reaproveita o caminho PyInstaller já verificado, incluindo a
  lição de que **um log de build limpo não é evidência**: o script roda o gate
  do binário entregue e falha o build se ele não passar.

## Verificação

- `tools/architecture_check.py` — o worker não importa Qt; o app não importa o
  worker; as duas cópias do protocolo são idênticas. **Testado negativamente**:
  `--self-check` injeta uma violação de cada classe e exige que todas sejam
  pegas (10/10).
- `./run.sh --self-test` — a fatia vertical, incluindo `pid` distinto do
  worker, início único, encerramento limpo, nenhuma porta TCP aberta e nenhum
  módulo web carregado (20/20).
- `../../tools/benchmark_backend.py` continua sendo o gate desta decisão. Um
  estágio que cair abaixo do throughput registrado é regressão, e em geral
  significa que um laço entrou.
