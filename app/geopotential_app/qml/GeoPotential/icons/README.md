# Ícones da interface

Onde ficam os ícones que a interface desenha. **Não é aqui que ficam os
símbolos dos pontos no mapa** — esses são desenhados com numpy, e o porquê está
no fim deste arquivo.

## Onde por cada coisa

| Pasta | O que vai nela | Quem usa |
|---|---|---|
| `tools/` | as ferramentas da barra vertical do mapa: navegar, identificar, AOI, medir, zoom, tela cheia, exportar | `MapToolBar.qml` |
| `workflow/` | as oito etapas do fluxo, se um dia deixarem de ser números | `WorkflowPanel.qml` |
| `layers/` | tipos de camada e ações: raster, pontos, vetor, AOI, mapa de fundo, visibilidade, remover | `LayerPanel.qml` |
| `jobs/` | estados de um job: em espera, executando, gravando, concluído, alerta, falhou | `JobsPanel.qml` |
| `app/` | o ícone da aplicação e o que o sistema operacional mostra: janela, lançador, `.desktop` | empacotamento (M8) |

Uma pasta nova se justifica quando existe uma tela nova. Até lá, o ícone vai na
pasta de quem o desenha.

## Como um ícone tem de ser

- **SVG monocromático**, desenhado com `currentColor` ou com um único
  `fill="#000"` que o QML recolore. Um ícone com cor própria não segue o tema,
  e o tema claro é um dos quatro que o M5.5 promete.
- **Área de 24 × 24**, com o desenho dentro de 20 × 20: a margem é o que impede
  o ícone de encostar na borda do botão.
- **Traço de 1,5 px** na área de 24. Mais fino some no tema claro; mais grosso
  vira mancha no escuro.
- **Nome que diz a função, não a forma**: `identify.svg`, não `target.svg`.
  A forma muda; a função é o que o código chama.
- **Licença registrada.** Um ícone de terceiro entra com a licença anotada em
  `CREDITS.md` nesta pasta. Sem isso não entra — é a mesma regra que tirou a
  Carto do mapa de fundo.

## Como usar no QML

```qml
Image {
    source: "icons/tools/identify.svg"
    sourceSize: Qt.size(20, 20)
    // Recolorido pelo tema: o ícone não escolhe a sua cor.
    layer.enabled: true
    layer.effect: ColorOverlay { color: Theme.text }
}
```

O caminho é relativo ao módulo `GeoPotential`, que já está no import path.

## Hoje a barra usa glifos, não arquivos

`MapToolBar.qml` desenha caracteres (`➤`, `◎`, `⬠`) porque um glifo não é um
arquivo para manter, e há um teste que **renderiza cada glifo** e reprova se a
fonte não o tiver — dois já apareceram como caixas vazias e foram trocados por
isso (`tests/unit/test_map_tools.py`, `TheToolbarsGlyphs`).

Trocar por SVG é uma melhoria de aparência, não uma correção. Quando for feita,
o mesmo teste deve passar a verificar que cada `source:` aponta para um arquivo
que existe.

## Os símbolos dos pontos não ficam aqui

A forma de um ponto no mapa — círculo, quadrado, triângulo, losango, cruz, X —
é desenhada em `render/points.py`, com numpy, como uma máscara sobre a área do
marcador. Não é um ícone e não é um arquivo, por um motivo de desempenho que o
ADR-007 mede: um `.svg` por ponto seria uma leitura de arquivo e uma composição
por ponto, num caminho de desenho, para 5 000 pontos por quadro.

Uma forma nova se acrescenta em `SYMBOLS`, com a sua máscara em `footprint()`, e
o seu nome nas duas línguas em `i18n/catalog.py` como `symbol.<nome>`.

`../../../../assets/symbols/` existe para o outro caso: um símbolo cartográfico
que **precise** ser uma imagem — uma legenda de afloramento, um pictograma de
norma técnica. Nada usa essa pasta ainda, e o primeiro que usar precisa dizer
por que a máscara não bastou.
