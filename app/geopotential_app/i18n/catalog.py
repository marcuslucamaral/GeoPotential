"""Every string the interface shows, in both languages.

One catalogue, two columns. A key with only one column is a bug the gate fails
on, and a literal typed straight into a `.qml` file is the same bug wearing a
different hat: it cannot be translated, so it is always wrong in one language.

Keys are hierarchical and name the place, not the text: `menu.file.new`, not
`menu.newProject`. Renaming the label then never touches the key.

Scientific vocabulary is **not** translated. `CRS`, `NoData`, `AHP`, `WLC`,
`membership`, `gamma`, `nodata`, an EPSG code and a unit symbol mean one thing
in both languages, and translating them would make two vocabularies out of one.
"""
from __future__ import annotations

# key -> (português, English)
CATALOG: dict[str, tuple[str, str]] = {
    # ---- menu bar -------------------------------------------------------
    "menu.file": ("Arquivo", "File"),
    "menu.edit": ("Editar", "Edit"),
    "menu.view": ("Exibir", "View"),
    # O menu que faltava: o fluxo e as operações que o alimentam, no mesmo
    # lugar. As oito etapas aparecem aqui, na trilha e no painel — as três
    # leem o mesmo modelo e roteiam o mesmo token.
    "menu.processing": ("Processamento", "Processing"),
    "menu.help": ("Ajuda", "Help"),

    "menu.file.new": ("Novo projeto", "New project"),
    "menu.file.open": ("Abrir projeto…", "Open project…"),
    "menu.file.recent": ("Projetos recentes", "Recent projects"),
    "menu.file.import": ("Importar dados…", "Import data…"),
    "menu.file.exportResult": ("Exportar resultado", "Export result"),
    "menu.file.exportMap": ("Exportar mapa…", "Export map…"),
    "menu.file.exportDiagnostic": ("Exportar diagnóstico…", "Export diagnostic…"),
    "menu.file.quit": ("Fechar", "Quit"),

    "menu.edit.undo": ("Desfazer", "Undo"),
    "menu.edit.redo": ("Refazer", "Redo"),
    "menu.edit.layerProperties": ("Propriedades da camada…", "Layer properties…"),
    "menu.edit.rename": ("Renomear camada…", "Rename layer…"),
    "menu.edit.removeLayer": ("Remover da visualização", "Remove from the view"),
    "menu.edit.preferences": ("Preferências", "Preferences"),

    "menu.view.layers": ("Painel de camadas", "Layer panel"),
    "menu.view.workflow": ("Fluxo de trabalho", "Workflow"),
    "menu.view.inspector": ("Inspector", "Inspector"),
    "menu.view.jobs": ("Jobs", "Jobs"),
    "menu.view.rail": ("Trilha de ícones", "Icon rail"),
    "menu.processing.harmonize": (
        "Harmonizar para a grade de análise…",
        "Harmonise onto the analysis grid…"),
    "menu.processing.membership": (
        "Editor de pertinência…", "Membership editor…"),
    "menu.processing.potentialFields": (
        "Campos potenciais — bancada…", "Potential fields — workbench…"),
    "menu.processing.scenarios": (
        "Cenários e sensibilidade…", "Scenarios and sensitivity…"),
    "menu.processing.decision": (
        "Modelo de decisão — AHP e agregação…",
        "Decision model — AHP and aggregation…"),
    "menu.view.fullScreen": ("Tela cheia", "Full screen"),
    "menu.view.coordinateFormat": ("Formato das coordenadas", "Coordinate format"),
    "menu.view.coordinate.native": ("CRS da camada", "The layer's own CRS"),
    "menu.view.coordinate.utm": ("UTM com a zona", "UTM with the zone"),
    "menu.view.coordinate.decimal": ("Graus decimais", "Decimal degrees"),
    "menu.view.coordinate.dms": ("Graus, minutos, segundos", "Degrees, minutes, seconds"),
    "menu.view.crs": ("CRS da vista", "View CRS"),
    "menu.view.crs.layer": ("Seguir a camada ativa", "Follow the active layer"),
    "menu.view.crs.wgs84": ("WGS 84 (graus)", "WGS 84 (degrees)"),
    "menu.view.crs.mercator": ("Web Mercator", "Web Mercator"),
    "menu.view.basemap": ("Mapa de fundo", "Basemap"),
    "menu.view.basemap.none": ("Nenhum (offline)", "None (offline)"),
    "menu.view.basemap.tip": (
        "Tiles de fontes abertas, buscados só quando você liga. A atribuição "
        "da licença aparece no mapa e vai junto no mapa exportado.",
        "Tiles from open sources, fetched only when you turn this on. The "
        "licence's attribution is shown on the map and goes with the exported "
        "image."),
    "status.online": ("mapa de fundo: %1", "basemap: %1"),
    "menu.view.crs.tip": (
        "Só a vista é reprojetada. Os arquivos não mudam: reprojetar o dado é "
        "uma run, com manifesto.",
        "Only the view is reprojected. The files do not change: reprojecting "
        "the data is a run, with a manifest."),
    "menu.view.colormap": ("Colormap da camada", "Layer colormap"),
    "menu.view.background": ("Fundo do mapa", "Map background"),
    "menu.view.background.black": ("Preto", "Black"),
    "menu.view.background.charcoal": ("Grafite", "Charcoal"),
    "menu.view.background.grey": ("Cinza", "Grey"),
    "menu.view.background.white": ("Branco", "White"),
    "layers.symbol": ("Símbolo", "Symbol"),
    "layers.symbol.size": ("Tamanho do ponto", "Point size"),
    "layers.symbol.shape": ("Forma", "Shape"),
    "symbol.circle": ("Círculo", "Circle"),
    "symbol.square": ("Quadrado", "Square"),
    "symbol.triangle": ("Triângulo", "Triangle"),
    "symbol.diamond": ("Losango", "Diamond"),
    "symbol.cross": ("Cruz", "Cross"),
    "symbol.x": ("X", "X"),
    "layers.symbol.outline": ("Contorno claro", "Light outline"),
    "layers.symbol.tip": (
        "Só exibição, como o colormap: muda o desenho e nunca um valor.",
        "Display only, like the colormap: it changes the drawing, never a "
        "value."),
    "menu.view.theme": ("Tema", "Theme"),
    "menu.view.theme.dark": ("Escuro", "Dark"),
    "menu.view.theme.light": ("Claro", "Light"),
    "menu.view.theme.contrast": ("Alto contraste", "High contrast"),
    "menu.view.theme.system": ("Automático (sistema)", "Automatic (system)"),
    "menu.view.language": ("Idioma", "Language"),
    "menu.view.language.pt": ("Português", "Portuguese"),
    "menu.view.language.en": ("Inglês", "English"),

    "menu.help.workflow": ("Guia do fluxo de trabalho", "Workflow guide"),
    "menu.help.shortcuts": ("Atalhos", "Shortcuts"),
    "menu.help.documentation": ("Documentação", "Documentation"),
    "menu.help.diagnostic": ("Diagnóstico…", "Diagnostic…"),
    "menu.help.versions": ("Versões", "Versions"),
    "menu.help.about": ("Sobre o GeoPotential", "About GeoPotential"),

    # ---- reasons a menu entry is disabled -------------------------------
    "reason.arrivesIn": (" — chega em %1", " — arrives in %1"),
    "reason.noProject": (" — nenhum projeto aberto", " — no project is open"),
    "reason.noLayer": (" — nenhuma camada ativa", " — no active layer"),

    # ---- workflow -------------------------------------------------------
    "workflow.caption": ("FLUXO", "WORKFLOW"),
    "workflow.needs": ("PRECISA DE", "NEEDS"),
    "workflow.produces": ("PRODUZ", "PRODUCES"),
    "workflow.leadsTo": ("LEVA A", "LEADS TO"),

    "workflow.state.not_started": ("não iniciada", "not started"),
    "workflow.state.available": ("disponível", "available"),
    "workflow.state.running": ("em execução", "running"),
    "workflow.state.done": ("concluída", "done"),
    "workflow.state.attention": ("alerta", "attention"),
    "workflow.state.blocked": ("bloqueada", "blocked"),

    "workflow.project.title": ("Projeto", "Project"),
    "workflow.project.purpose": (
        "Criar, abrir, duplicar ou recuperar um projeto.",
        "Create, open, duplicate or recover a project."),
    "workflow.project.in.folder": ("uma pasta de projeto", "a project folder"),
    "workflow.project.out.open": ("projeto aberto", "an open project"),
    "workflow.project.out.session": ("sessão registrada", "a recorded session"),

    "workflow.data.title": ("Dados", "Data"),
    "workflow.data.purpose": (
        "Importar raster, vetor ou tabela, com prévia antes de importar.",
        "Import a raster, a vector or a table, previewed before it enters."),
    "workflow.data.in.project": ("projeto aberto", "an open project"),
    "workflow.data.in.file": ("um arquivo legível", "a readable file"),
    "workflow.data.out.dataset": (
        "dataset registrado com hash e caminho",
        "a dataset registered with its hash and path"),

    "workflow.qc.title": ("QA/QC", "QA/QC"),
    "workflow.qc.purpose": (
        "Verificar CRS, unidade, NoData, extensão, cobertura e campos.",
        "Check CRS, unit, NoData, extent, coverage and fields."),
    "workflow.qc.in.dataset": ("ao menos um dataset", "at least one dataset"),
    "workflow.qc.out.verdict": (
        "veredito gravado por dataset", "a recorded verdict per dataset"),

    "workflow.harmonize.title": ("Harmonização", "Harmonisation"),
    "workflow.harmonize.purpose": (
        "Levar cada camada a um mesmo grid: CRS-alvo, pixel, resampling e "
        "política de extensão.",
        "Bring every layer onto one grid: target CRS, pixel size, resampling "
        "and extent policy."),
    "workflow.harmonize.in.approved": (
        "datasets aprovados no QA/QC", "datasets approved by QA/QC"),
    "workflow.harmonize.in.crs": ("um CRS-alvo métrico", "a metric target CRS"),
    "workflow.harmonize.out.grid": (
        "camadas num TargetGrid comum", "layers on one common TargetGrid"),

    "workflow.membership.title": ("Membership", "Membership"),
    "workflow.membership.purpose": (
        "Transformar valores físicos em pertinência [0-1], com os anchors "
        "registrados.",
        "Turn physical values into a [0-1] membership, with the anchors "
        "recorded."),
    "workflow.membership.in.layer": (
        "uma camada harmonizada", "a harmonised layer"),
    "workflow.membership.in.sense": (
        "sentido físico do critério", "the criterion's physical sense"),
    "workflow.membership.out.criterion": (
        "critério NORMALIZED em [0,1]", "a NORMALIZED criterion in [0,1]"),

    "workflow.weights.title": ("Pesos/AHP", "Weights/AHP"),
    "workflow.weights.purpose": (
        "Matriz de comparação par a par, pesos e consistency ratio.",
        "Pairwise comparison matrix, weights and consistency ratio."),
    "workflow.weights.in.criteria": (
        "dois ou mais critérios normalizados",
        "two or more normalised criteria"),
    "workflow.weights.out.weights": (
        "pesos que somam 1", "weights summing to 1"),
    "workflow.weights.out.cr": ("CR reportado", "the CR reported"),

    "workflow.aggregate.title": ("Agregação", "Aggregation"),
    "workflow.aggregate.purpose": (
        "Combinar os critérios por Fuzzy Gamma, Product, Sum ou WLC.",
        "Combine the criteria by Fuzzy Gamma, Product, Sum or WLC."),
    "workflow.aggregate.in.criteria": (
        "critérios normalizados", "normalised criteria"),
    "workflow.aggregate.in.weights": (
        "pesos com CR aceito", "weights with an accepted CR"),
    "workflow.aggregate.out.map": (
        "mapa de prospectividade", "a prospectivity map"),
    "workflow.aggregate.out.manifest": (
        "manifesto que reproduz a run", "a manifest that reproduces the run"),

    "workflow.results.title": ("Resultados", "Results"),
    "workflow.results.purpose": (
        "Visualizar, comparar, inspecionar e exportar.",
        "View, compare, inspect and export."),
    "workflow.results.in.run": (
        "uma run de agregação comitada", "a committed aggregation run"),
    "workflow.results.out.map": ("mapa exportado", "an exported map"),
    "workflow.results.out.diagnostic": ("diagnóstico", "a diagnostic"),

    # ---- why a step is blocked ------------------------------------------
    "workflow.blocked.noProject": (
        "Nenhum projeto aberto. Abra ou crie um projeto.",
        "No project is open. Open or create one."),
    "workflow.blocked.noDataset": (
        "Nenhum dataset importado. Todo arquivo é verificado antes de entrar "
        "no projeto.",
        "No dataset has been imported. Every file is checked before it enters "
        "the project."),
    "workflow.blocked.nothingApproved": (
        "Nenhum dataset aprovado no QA/QC. Uma camada só entra no grid depois "
        "de verificada.",
        "No dataset passed QA/QC. A layer reaches the grid only after it is "
        "checked."),
    "workflow.blocked.noLayer": (
        "Nenhuma camada disponível: o QA/QC ainda não aprovou nada.",
        "No layer is available: QA/QC has approved nothing yet."),
    "workflow.blocked.noCriterion": (
        "Nenhum critério normalizado. Pesos só fazem sentido sobre critérios "
        "em [0,1].",
        "No normalised criterion. Weights only mean something over criteria "
        "in [0,1]."),
    "workflow.blocked.nothingToCombine": (
        "Nenhum critério normalizado para combinar.",
        "No normalised criterion to combine."),
    "workflow.blocked.noAggregation": (
        "Nenhuma run de agregação comitada.",
        "No aggregation run has been committed."),
    "workflow.attention.qcRefused": (
        "Nenhum dataset passou na verificação. Corrija o dado ou declare o que "
        "falta.",
        "No dataset passed the checks. Fix the data, or declare what is "
        "missing."),
    "workflow.attention.qcWarned": (
        "Aprovado com aviso. Leia o veredito antes de seguir.",
        "Approved with a warning. Read the verdict before going on."),
    "workflow.attention.failed": (
        "A última execução desta etapa falhou.",
        "This step's last run failed."),

    # ---- top bar --------------------------------------------------------
    "top.subtitle": ("Análise multicritério", "Multicriteria analysis"),
    "top.chip.crs": ("CRS", "CRS"),
    "top.chip.layers": ("camadas", "layers"),
    "top.theme.tip": (
        "Troca o tema: escuro, claro, alto contraste, do sistema. Só "
        "repinta — nada muda de lugar.",
        "Switch the theme: dark, light, high contrast, system. It only "
        "repaints — nothing moves."),
    # A trilha da esquerda. Cada botão é um ícone, e o texto que ele perdeu
    # está aqui, na dica que aparece ao passar o mouse.
    "rail.import.tip": (
        "Carregar arquivo — raster, tabela de amostras ou vetor. Passa "
        "pela QA/QC antes de entrar no projeto.",
        "Load a file — raster, sample table or vector. It goes through "
        "QA/QC before entering the project."),
    "rail.gridding.tip": (
        "Gerar grade a partir de dado esparso: interpolar amostras, medir "
        "distância até feições, ou queimar um atributo.",
        "Build a grid from sparse data: interpolate samples, measure the "
        "distance to features, or burn an attribute."),
    "rail.panel.workflow.tip": (
        "Mostrar ou esconder o painel do fluxo",
        "Show or hide the flow panel"),
    "rail.panel.layers.tip": (
        "Mostrar ou esconder o painel de camadas",
        "Show or hide the layer panel"),
    "rail.panel.inspector.tip": (
        "Mostrar ou esconder o Inspector",
        "Show or hide the Inspector"),
    "rail.panel.jobs.tip": (
        "Mostrar ou esconder o painel de jobs",
        "Show or hide the jobs panel"),
    "rail.preferences.tip": ("Preferências", "Preferences"),
    "top.projects": ("Projetos", "Projects"),
    "top.projects.tip": (
        "Criar, abrir, duplicar — e ver o que a recuperação encontrou.",
        "Create, open, duplicate — and see what recovery found."),
    "top.undo": ("Desfazer", "Undo"),
    "top.redo": ("Refazer", "Redo"),
    "top.run": ("Executar", "Run"),
    "top.run.tip": (
        "Executar a etapa atual do fluxo sobre a camada ativa.",
        "Run the current workflow step on the active layer."),
    "top.run.blocked": (
        "O worker científico está %1.", "The scientific worker is %1."),
    "top.cancel": ("Cancelar", "Cancel"),
    "top.cancel.tip": (
        "Pedir ao worker que pare o job selecionado. Nada parcial é registrado.",
        "Ask the worker to stop the selected job. Nothing partial is recorded."),
    "top.compare": ("Comparar", "Compare"),
    "top.compare.tip": (
        "Dividir o canvas para ver duas camadas lado a lado, na mesma extensão "
        "e na mesma escala.",
        "Split the canvas to see two layers side by side, at the same extent "
        "and the same scale."),
    "top.worker": ("worker: %1", "worker: %1"),
    "top.worker.restart": ("Reiniciar worker", "Restart worker"),

    # ---- canvas ---------------------------------------------------------
    "canvas.empty": (
        "Nenhuma camada ainda.\nImporte um dado, ou execute um operador.",
        "No layer yet.\nImport a dataset, or run an operator."),
    "canvas.lod": (
        "vista 1:%1 · valores lidos em resolução plena",
        "view 1:%1 · values read at full resolution"),
    "canvas.membershipUnit": ("membership [0-1]", "membership [0-1]"),

    # ---- map tools ------------------------------------------------------
    "tool.navigate": ("Selecionar e navegar", "Select and navigate"),
    "tool.layers": ("Painel de camadas", "Layer panel"),
    "tool.zoomIn": ("Aproximar", "Zoom in"),
    "tool.zoomOut": ("Afastar", "Zoom out"),
    "tool.zoomFull": ("Extensão total", "Full extent"),
    "tool.fullScreen": ("Tela cheia", "Full screen"),
    "tool.identify": ("Identificar valor ou feição", "Identify a value or feature"),
    "tool.aoi": ("Criar e editar AOI", "Create and edit an AOI"),
    "tool.measureDistance": ("Medir distância", "Measure a distance"),
    "tool.measureArea": ("Medir área", "Measure an area"),
    "tool.exportMap": ("Exportar mapa", "Export the map"),

    "tool.navigate.tip": (
        "Arrastar para mover, roda para aproximar sobre o cursor.",
        "Drag to pan, wheel to zoom about the cursor."),
    "tool.identify.tip": (
        "Clicar lê o valor da camada ativa **na fonte**, em resolução plena, "
        "nunca no tile desenhado.",
        "Clicking reads the active layer's value **from the source**, at full "
        "resolution, never from the drawn tile."),
    "tool.aoi.tip": (
        "Clicar coloca vértices. Três ou mais fecham a área; ela é salva como "
        "uma nova versão.",
        "Click to place vertices. Three or more close the area; it is saved as "
        "a new version."),
    "tool.measure.tip": (
        "Medida no CRS da camada. Recusada em CRS geográfico: metros não "
        "existem em graus.",
        "Measured in the layer's CRS. Refused on a geographic CRS: metres do "
        "not exist in degrees."),

    # ---- AOI ------------------------------------------------------------
    "aoi.drawing": ("Desenhando AOI", "Drawing an AOI"),
    "aoi.vertices": ("%1 vértices", "%1 vertices"),
    "aoi.needMore": (
        "Coloque ao menos três vértices.", "Place at least three vertices."),
    "aoi.finish": ("Finalizar", "Finish"),
    "aoi.undo": ("Desfazer vértice", "Undo the last vertex"),
    "aoi.cancel": ("Cancelar", "Cancel"),
    "aoi.cancelled": (
        "Desenho cancelado. Nada foi salvo.",
        "Drawing cancelled. Nothing was saved."),
    "aoi.saved": ("AOI salva como versão %1.", "AOI saved as version %1."),

    # ---- layer panel ----------------------------------------------------
    "layers.caption": ("CAMADAS", "LAYERS"),
    "layers.empty": (
        "Nenhuma camada na vista. Importe um dado ou execute um operador.",
        "No layer in the view. Import a dataset or run an operator."),
    "layers.opacity": ("Opacidade", "Opacity"),
    "layers.zoomTo": ("Enquadrar a camada", "Zoom to the layer"),
    "layers.remove": ("Remover da visualização", "Remove from the view"),
    "layers.remove.tip": (
        "Só da vista. O dado, as runs e os artefatos permanecem no projeto.",
        "From the view only. The data, the runs and the artefacts stay in the "
        "project."),
    "layers.moveUp": ("Subir na ordem de desenho", "Move up in the draw order"),
    "layers.moveDown": ("Descer na ordem de desenho", "Move down in the draw order"),
    "layers.properties": ("Propriedades e estatísticas", "Properties and statistics"),
    "layers.visible": ("Visível", "Visible"),
    "layers.active": ("Camada ativa", "Active layer"),
    "layers.attributes": ("Tabela de atributos", "Attribute table"),
    "layers.attributes.empty": (
        "Esta camada não tem tabela: é um raster.",
        "This layer has no table: it is a raster."),
    "layers.details": ("Detalhes da camada", "Layer details"),
    "layers.rename": ("Renomear…", "Rename…"),
    "layers.active.tip": (
        "O Inspector e a ferramenta de identificar leem a camada ativa.",
        "The Inspector and the identify tool read the active layer."),

    "layers.role.original": ("original", "original"),
    "layers.role.harmonized": ("harmonizado", "harmonised"),
    "layers.role.membership": ("membership", "membership"),
    "layers.role.result": ("resultado", "result"),
    "layers.role.aoi": ("AOI", "AOI"),
    "layers.role.basemap": ("mapa de fundo", "basemap"),
    "layers.basemap.note": (
        "Só visualização: não entra em harmonização, membership, AHP nem "
        "agregação, e não tem valor sob o cursor.",
        "Display only: it takes no part in harmonisation, membership, AHP or "
        "aggregation, and has no value under the cursor."),

    # ---- colormap -------------------------------------------------------
    "colormap.caption": ("COLORMAP", "COLORMAP"),
    "colormap.invert": ("Inverter cores", "Invert the colours"),
    "colormap.min": ("Mínimo", "Minimum"),
    "colormap.max": ("Máximo", "Maximum"),
    "colormap.auto": ("Restaurar limites automáticos", "Restore automatic limits"),
    "colormap.displayOnly": (
        "Só exibição: repinta a vista e nunca reescreve um valor.",
        "Display only: it repaints the view and never rewrites a value."),
    "colormap.diverging": (
        "Divergente, centrado exatamente em zero.",
        "Diverging, centred exactly on zero."),

    # ---- inspector ------------------------------------------------------
    "inspector.caption": ("INSPECTOR", "INSPECTOR"),
    "inspector.empty": (
        "Selecione uma camada para inspecioná-la.",
        "Select a layer to inspect it."),
    "inspector.theData": ("O DADO", "THE DATA"),
    "inspector.theView": ("A VISTA", "THE VIEW"),
    "inspector.layer": ("Camada", "Layer"),
    "inspector.crs": ("CRS", "CRS"),
    "inspector.crs.tip": (
        "As coordenadas e o tamanho de pixel abaixo estão neste CRS.",
        "The coordinates and pixel size below are in this CRS."),
    "inspector.crsUnit": ("Unidade do CRS", "CRS unit"),
    "inspector.valueUnit": ("Unidade do valor", "Value unit"),
    "inspector.valueUnit.tip": (
        "Uma membership é adimensional; não carrega unidade física.",
        "A membership is dimensionless; it carries no physical unit."),
    "inspector.size": ("Tamanho", "Size"),
    "inspector.valid": ("Válidos", "Valid"),
    "inspector.valid.value": ("%1 % dos pixels", "%1 % of pixels"),
    "inspector.valid.tip": (
        "O resto é nodata, desenhado transparente — nunca como a ponta baixa "
        "da rampa.",
        "The rest is nodata, drawn transparent — never as the low end of the "
        "ramp."),
    "inspector.range": ("Faixa", "Range"),
    "inspector.range.value": ("%1 a %2", "%1 to %2"),
    "inspector.size.value": ("%1 x %2 px", "%1 x %2 px"),
    "inspector.pixelsRead.value": ("%1 de %2", "%1 of %2"),
    "inspector.mean": ("Média", "Mean"),
    "inspector.view": ("Vista", "View"),
    "inspector.view.full": ("1:1 (plena)", "1:1 (full)"),
    "inspector.view.decimated": ("1:%1 (decimada)", "1:%1 (decimated)"),
    "inspector.view.tip": (
        "Nível de detalhe da imagem. Os valores sob o cursor são sempre lidos "
        "da fonte em resolução plena.",
        "Level of detail of the picture. Values under the cursor are always "
        "read from the source at full resolution."),
    "inspector.pixelsRead": ("Pixels lidos", "Pixels read"),
    "inspector.pixelsRead.tip": (
        "A leitura é proporcional à tela, não ao arquivo.",
        "Reading is proportional to the screen, not to the file."),
    "inspector.cache": ("Cache de tiles", "Tile cache"),
    "inspector.cache.value": (
        "%1 MB, %2 tiles, %3 % de acertos", "%1 MB, %2 tiles, %3 % hits"),
    "inspector.cache.tip": (
        "O cache é descartável: limpá-lo custa tempo e nada mais.",
        "The cache is discardable: clearing it costs time and nothing else."),
    "inspector.colormap": ("Colormap", "Colormap"),
    "inspector.project": ("Projeto", "Project"),
    "inspector.app": ("Aplicação", "Application"),
    "inspector.worker": ("Worker", "Worker"),
    "inspector.boundary": (
        "Este é um resultado numérico determinístico — uma pertinência fuzzy, "
        "não uma saída de aprendizado de máquina. Favorabilidade espacial não "
        "é recurso, reserva, potência nem viabilidade econômica.",
        "This is a deterministic numerical result — a fuzzy membership, not a "
        "machine-learning output. Spatial favourability is not a resource, a "
        "reserve, thermal or electrical power, or economic viability."),

    # ---- jobs -----------------------------------------------------------
    "jobs.caption": ("JOBS", "JOBS"),
    "jobs.empty": ("Nenhum job foi submetido.", "No job has been submitted."),
    "jobs.what": (
        "Cada job é um cálculo que o worker executou: ler um arquivo, "
        "verificá-lo, harmonizar, calcular membership, agregar. É daqui que "
        "sai a procedência — o que rodou, sobre o quê, com que parâmetros.",
        "Each job is a computation the worker ran: reading a file, checking "
        "it, harmonising, computing a membership, aggregating. This is where "
        "provenance comes from — what ran, over what, with which parameters."),
    "jobs.filter.active": ("Ativos", "Active"),
    "jobs.filter.all": ("Histórico", "History"),
    "jobs.collapse": ("Recolher", "Collapse"),
    "jobs.expand": ("Expandir", "Expand"),
    "jobs.inputs": ("Entradas", "Inputs"),
    "jobs.outputs": ("Saídas", "Outputs"),
    "jobs.artifacts": ("Artefatos", "Artefacts"),
    "jobs.elapsed": ("Decorrido", "Elapsed"),
    "jobs.stage": ("Etapa", "Stage"),
    "jobs.retry": ("Repetir", "Retry"),
    "jobs.retry.tip": (
        "Submete de novo com os mesmos parâmetros. A run anterior é preservada.",
        "Submits again with the same parameters. The previous run is preserved."),
    "jobs.openResult": ("Abrir resultado", "Open the result"),
    "jobs.showLog": ("Ver log", "Show the log"),
    "jobs.cancel": ("Cancelar", "Cancel"),
    "jobs.noArtifacts": ("nenhum artefato", "no artefact"),
    "jobs.artifactCount": ("%1 artefato(s)", "%1 artefact(s)"),
    "jobs.selectOne": (
        "Selecione um job para ver o que ele fez.",
        "Select a job to see what it did."),

    "jobs.state.Queued": ("em espera", "queued"),
    "jobs.state.Validating": ("validando", "validating"),
    "jobs.state.Running": ("executando", "running"),
    "jobs.state.Committing": ("gravando", "committing"),
    "jobs.state.Succeeded": ("concluído", "succeeded"),
    "jobs.state.Warning": ("alerta", "warning"),
    "jobs.state.Cancelled": ("cancelado", "cancelled"),
    "jobs.state.Interrupted": ("interrompido", "interrupted"),
    "jobs.state.Failed": ("falhou", "failed"),

    # Friendly names, per operator. The technical name is shown beside them:
    # one is what the person recognises, the other is what a bug report needs.
    "operator.io.describe_dataset": ("Ler o arquivo", "Read the file"),
    "operator.qc.validate_dataset": ("Verificar o dado", "Check the data"),
    "operator.grid.harmonize": ("Harmonizar no grid", "Harmonise onto the grid"),
    "operator.grid.difference": ("Diferença entre camadas", "Difference between layers"),
    "operator.decision.membership": ("Calcular membership", "Compute the membership"),
    "operator.decision.ahp_weights": ("Calcular pesos AHP", "Compute the AHP weights"),
    "operator.decision.aggregate": ("Agregar critérios", "Aggregate the criteria"),

    # ---- status bar -----------------------------------------------------
    "status.coordinate": ("Coordenada", "Coordinate"),
    "status.value": ("Valor", "Value"),
    "status.noValue": ("sem valor", "no value"),
    "status.mode": ("Modo", "Mode"),
    "status.noLayer": ("sem camada", "no layer"),
    "status.offline": ("offline · tudo local", "offline · local-first"),

    # ---- dialogs --------------------------------------------------------
    "dialog.ok": ("OK", "OK"),
    "dialog.cancel": ("Cancelar", "Cancel"),
    "dialog.error.title": ("A execução não terminou", "The run did not complete"),
    "dialog.error.detail": (
        "O detalhe técnico está no log do worker, referência %1",
        "Technical detail is in the worker log, reference %1"),
    "dialog.guide.title": (
        "Guia do fluxo de trabalho", "Workflow guide"),
    "dialog.guide.intro": (
        "Oito etapas, do arquivo ao mapa de prospectividade. O estado de cada "
        "uma é lido do projeto — nada aqui é escrito à mão.",
        "Eight steps, from a file to a prospectivity map. Each step's state is "
        "read from the project — nothing here is written by hand."),
    "dialog.shortcuts.title": ("Atalhos", "Shortcuts"),
    "dialog.versions.title": ("Versões", "Versions"),
    "dialog.versions.none": ("nenhum aberto", "none open"),
    "dialog.about.title": ("Sobre o GeoPotential", "About GeoPotential"),
    "dialog.about.body": (
        "Análise de decisão multicritério espacial para dados geopotenciais e "
        "GIS. IDW, pertinência fuzzy, AHP e WLC são métodos numéricos "
        "determinísticos — não são IA nem aprendizado de máquina. "
        "Favorabilidade espacial não é recurso, reserva, potência nem "
        "viabilidade econômica.",
        "Spatial multicriteria decision analysis for geopotential and GIS "
        "data. IDW, fuzzy membership, AHP and WLC are deterministic numerical "
        "methods — they are not AI and not machine learning. Spatial "
        "favourability is not a resource, a reserve, power, or economic "
        "viability."),
    "dialog.diagnostic.title": (
        "Onde gravar o diagnóstico", "Where to write the diagnostic"),
    "dialog.exportMap.title": (
        "Onde gravar a imagem do mapa", "Where to write the map image"),


    # ---- project hub ----------------------------------------------------
    "hub.title": ("Projetos", "Projects"),
    "hub.pickOpen": ("Escolha uma pasta de projeto .gpot",
                     "Choose a .gpot project directory"),
    "hub.pickCreate": ("Escolha onde o novo projeto vai ficar",
                       "Choose where the new project goes"),
    "hub.pickCopy": ("Escolha onde a cópia vai ficar",
                     "Choose where the copy goes"),
    "hub.open": ("Abrir", "Open"),
    "hub.openDots": ("Abrir…", "Open…"),
    "hub.duplicate": ("Duplicar…", "Duplicate…"),
    "hub.duplicate.tip": (
        "Copia o projeto — catálogo, artefatos e logs. Nada é movido.",
        "Copy the project — catalogue, artefacts and logs. Nothing is moved."),
    "hub.recent": ("RECENTES", "RECENT"),
    "hub.noRecent": ("Nenhum projeto aberto ainda nesta máquina.",
                     "No projects opened yet on this machine."),
    "hub.newName": ("Nome do novo projeto", "New project name"),
    "hub.create": ("Criar…", "Create…"),
    "hub.recovery.tip": (
        "Abrir sempre roda a recuperação: um projeto que não fechou bem é "
        "reconciliado antes de qualquer trabalho novo.",
        "Opening always runs the recovery pass, so a project that did not "
        "close cleanly is reconciled before any new work."),
    "hub.close": ("Fechar", "Close"),
    "hub.where": ("Pasta", "Folder"),
    "hub.where.tip": (
        "Onde o projeto vai ser criado. Editável; o botão Escolher abre o "
        "seletor do sistema, mas criar não depende dele.",
        "Where the project will be created. Editable; the Choose button opens "
        "the system picker, but creating does not depend on it."),
    "hub.browse": ("Escolher…", "Choose…"),
    "hub.openPath": ("Caminho de um projeto .gpot", "Path to a .gpot project"),
    "hub.openHere": ("Abrir caminho", "Open path"),
    "hub.clickToOpen": ("Clique para abrir", "Click to open"),
    "hub.missing": ("(não está mais lá)", "(no longer there)"),
    "hub.noProject": ("nenhum projeto aberto", "no project open"),
    "hub.forget": ("Esquecer", "Forget"),
    "hub.forget.tip": (
        "Tira da lista de recentes. Não apaga nada do disco.",
        "Removes it from the recents list. Nothing on disk is deleted."),

    # ---- membership editor ----------------------------------------------
    "membership.title": ("Membership", "Membership"),
    "membership.layer": ("Camada", "Layer"),
    "membership.function": ("Função", "Function"),
    "membership.xmin": ("x mín", "x min"),
    "membership.xmax": ("x máx", "x max"),
    "membership.noLayer": (
        "Escolha uma camada no painel de camadas antes de abrir a "
        "pertinência: a curva é desenhada sobre a distribuição daquela "
        "camada, e sem ela não há o que desenhar.",
        "Pick a layer in the layer panel before opening the membership: the "
        "curve is drawn over that layer's distribution, and without one there "
        "is nothing to draw."),
    "membership.preferred": ("Azimute preferido (°)", "Preferred azimuth (°)"),
    "membership.spread": ("Meia-pertinência a (°)", "Half membership at (°)"),
    "membership.midpoint": ("ponto médio", "midpoint"),
    "membership.centre": ("centro", "centre"),
    "membership.note": (
        "A curva mapeia os valores acima para uma pertinência adimensional em "
        "[0,1]. Os anchors ficam registrados na run.",
        "The curve maps the values above onto a dimensionless membership in "
        "[0,1]. The anchors are recorded with the run."),
    "membership.apply": ("Aplicar", "Apply"),
    # Classes. Geologia, uso do solo e solo chegam como códigos inteiros, e
    # `categorical` recusa qualquer código sem nota — então a tela precisa
    # listar os códigos que o arquivo tem, e dizer quantos faltam.
    "membership.classes": ("Classes", "Classes"),
    "membership.class.code": ("código", "code"),
    "membership.class.name": ("classe", "class"),
    "membership.class.share": ("área", "share"),
    "membership.class.score": ("nota [0-1]", "score [0-1]"),
    # De onde vieram os nomes. Um rótulo afirma o que um código significa,
    # e uma afirmação sem origem não é conferível.
    "membership.class.legend": ("legenda: %1", "legend: %1"),
    "membership.class.unnamed": (
        "%1 código(s) sem nome na legenda. Eles continuam pontuáveis; o "
        "arquivo é que não diz o que são.",
        "%1 code(s) the legend does not name. They are still scoreable; it "
        "is the file that does not say what they are."),
    "membership.class.missing": (
        "Faltam %1 classe(s) sem nota. Pontuar uma classe como zero é uma "
        "afirmação científica; deixar em branco não é, e por isso o botão "
        "espera.",
        "%1 class(es) still have no score. Scoring a class zero is a "
        "scientific claim; leaving it blank is not, which is why the button "
        "waits."),
    "membership.class.none": (
        "Esta camada não tem códigos de classe: os valores são contínuos. "
        "Escolha uma das outras funções.",
        "This layer has no class codes: the values are continuous. Pick one "
        "of the other functions."),
    "membership.class.tooMany": (
        "Esta camada tem %1 classes distintas, acima do limite de %2 que "
        "cabe pontuar à mão. Reclassifique a camada antes.",
        "This layer has %1 distinct classes, above the limit of %2 that can "
        "be scored by hand. Reclassify the layer first."),

    # ---- decision model --------------------------------------------------
    "decision.title": ("Modelo de decisão", "Decision model"),
    "decision.criteria": ("CRITÉRIOS", "CRITERIA"),
    "decision.noCriteria": (
        "Nenhum critério ainda. Harmonize algumas camadas primeiro.",
        "No criteria yet. Harmonize some layers first."),
    "decision.justification": ("Justificativa", "Justification"),
    "decision.justification.hint": (
        "Por que estes julgamentos são aceitáveis apesar do CR",
        "Why these judgments are acceptable despite the CR"),
    "decision.correlation": ("CORRELAÇÃO", "CORRELATION"),
    "decision.operator": ("Operador", "Operator"),
    "decision.gamma": ("Gamma", "Gamma"),
    "decision.gamma.hint": (
        "0 é o produto algébrico (tipo E), 1 a soma algébrica (tipo OU); "
        "entre os dois, o gamma interpola.",
        "0 is the algebraic product (AND-like), 1 the algebraic sum (OR-like); "
        "in between, gamma interpolates."),
    "decision.close": ("Fechar", "Close"),
    "decision.run": ("Executar", "Run"),

    # ---- import wizard ---------------------------------------------------
    "import.title": ("Importar um dado", "Import a dataset"),
    "import.pick": ("Escolha um arquivo", "Choose a dataset"),
    "import.file": ("Arquivo", "File"),
    "import.noFile": ("Nenhum arquivo escolhido", "No file chosen"),
    "import.choose": ("Escolher…", "Choose…"),
    "import.detected": ("Detectado", "Detected"),
    "import.declare": (
        "Declarar (registrado como sua asserção, nunca aplicado em silêncio)",
        "Declare (recorded as your assertion, never applied silently)"),
    "import.unit": ("Unidade do valor", "Unit of the value"),
    # Nenhum arquivo tem onde escrever a sua unidade — um CSV certamente não —
    # então ela é sempre uma asserção de quem importa. Dizer isso na tela é o
    # que separa "campo vazio porque falhou" de "campo vazio porque ninguém
    # declarou ainda".
    "import.unit.none": ("— não declarada —", "— not declared —"),
    "import.unit.why": (
        "Nenhum formato guarda a unidade do que foi medido, então ela não é "
        "lida do arquivo: você declara. Sem ela o manifesto não registra o "
        "que foi medido e duas camadas em unidades diferentes entram na mesma "
        "conta — a QA/QC avisa, e não bloqueia.",
        "No format stores the unit of what was measured, so it is not read "
        "from the file: you declare it. Without it the manifest cannot record "
        "what was measured and two layers in different units enter the same "
        "sum — QA/QC warns, and does not block."),
    "import.unit.candidates": (
        "Compatível com esta faixa: %1",
        "Compatible with this range: %1"),
    "import.unit.noCandidates": (
        "Nenhuma unidade conhecida cobre esta faixa.",
        "No known unit covers this range."),
    "import.nodata": ("NoData", "NoData"),
    "import.clean": ("Nenhum problema encontrado.", "No problems found."),
    "import.pickFirst": (
        "Escolha um arquivo para ver o que ele contém e o que há de errado "
        "com ele.",
        "Choose a file to see what it contains and what is wrong with it."),
    "import.recheck": ("Verificar de novo", "Re-check"),
    "import.checking": ("Verificando…", "Checking…"),
    "import.import": ("Importar", "Import"),
    "import.preview": ("PRÉVIA", "PREVIEW"),
    "import.columns": ("COLUNAS", "COLUMNS"),
    "import.columns.x": ("X (leste / longitude)", "X (easting / longitude)"),
    "import.columns.y": ("Y (norte / latitude)", "Y (northing / latitude)"),
    "import.columns.value": ("Valor medido", "Measured value"),
    "import.columns.tip": (
        "Qual coluna é o quê. O que não for declarado é adivinhado, e a "
        "adivinhação aparece como aviso no veredito.",
        "Which column is what. Anything not declared is guessed, and the "
        "guess shows up as a warning in the verdict."),
    "import.columns.guessed": ("adivinhado", "guessed"),
    "import.columns.declared": ("declarado por você", "declared by you"),
    "import.verdict.pending": (
        "Verificando com o que você declarou…",
        "Checking with what you declared…"),
    "import.verdict.first": (
        "Escolha um arquivo para verificá-lo.",
        "Choose a file to have it checked."),
    "import.verdict.ok": ("Este dado pode ser importado.",
                          "This dataset can be imported."),
    "import.verdict.blocked": (
        "Bloqueado. Corrija as declarações acima, ou escolha outro arquivo.",
        "Blocked. Correct the declarations above, or choose another file."),
    "import.preview.rows": (
        "%1 linhas no arquivo, mostrando %2",
        "%1 rows in the file, showing %2"),
    "import.preview.points": (
        "%1 pontos, mostrando %2", "%1 points, showing %2"),
    "import.preview.features": (
        "%1 feições, mostrando %2", "%1 features, showing %2"),
    "import.preview.decimated": (
        "Amostrado para caber: é uma silhueta do dado, não o dado.",
        "Sampled to fit: this is a silhouette of the data, not the data."),
    "import.preview.none": (
        "Sem prévia para este formato.", "No preview for this format."),
    "import.histogram": ("DISTRIBUIÇÃO", "DISTRIBUTION"),

    # ---- preferences, section 9.11 ---------------------------------------
    "prefs.title": ("Preferências", "Preferences"),
    "prefs.explain": (
        "Estas escolhas são suas, não do projeto: elas acompanham você de um "
        "projeto para outro e ficam guardadas fora de qualquer .gpot.",
        "These choices are yours, not the project's: they follow you from one "
        "project to the next and are stored outside every .gpot."),
    "prefs.language": ("Idioma", "Language"),
    "prefs.theme": ("Tema", "Theme"),
    "prefs.coordinates": ("Formato das coordenadas", "Coordinate format"),
    "prefs.ground": ("Fundo do mapa", "Map background"),
    "prefs.scope": (
        "Nada aqui altera um valor, uma unidade, um CRS ou um artefato. "
        "Trocar de tema só repinta a tela: nenhum painel se move.",
        "Nothing here changes a value, a unit, a CRS or an artefact. "
        "Changing theme only repaints: no panel moves."),

    "layer.rename.title": ("Renomear a camada", "Rename the layer"),
    "layer.rename.explain": (
        "Renomeia a camada na vista. O dataset no catálogo mantém o nome com "
        "que foi registrado, e nenhum manifesto muda.",
        "Renames the layer in the view. The dataset in the catalogue keeps "
        "the name it was registered under, and no manifest changes."),

    # ---- harmonization, step 4 -------------------------------------------
    #
    # Nothing here has a default worth hiding: the CRS has none by decision,
    # the pixel size decides what the analysis resolves, and the two extent
    # policies are two different maps.
    "harmonize.title": ("Harmonizar para uma grade",
                        "Harmonise onto one grid"),
    "harmonize.explain": (
        "Toda camada é reprojetada e reamostrada para uma única grade de "
        "análise. Não existe CRS padrão: o alvo é escolhido aqui e fica "
        "registrado no manifesto da run.",
        "Every layer is reprojected and resampled onto a single analysis "
        "grid. There is no default CRS: the target is chosen here and is "
        "recorded in the run's manifest."),
    "harmonize.crs": ("CRS alvo", "Target CRS"),
    "harmonize.pixel": ("Pixel (na unidade do CRS)", "Pixel (in the CRS unit)"),
    "harmonize.extent": ("Extensão", "Extent"),
    "harmonize.extent.intersection": (
        "Interseção — só onde todas as camadas têm dado",
        "Intersection — only where every layer has data"),
    "harmonize.extent.union": (
        "União — onde qualquer camada tem dado",
        "Union — where any layer has data"),
    # A prévia. A escolha entre interseção e união decide o resultado inteiro
    # — no Utah FORGE, 100 % contra 27,7 % de células com score — e era feita
    # antes de qualquer um dos dois números existir na tela.
    "harmonize.preview": ("Comparar as duas", "Compare the two"),
    # Curtos, para a tabela comparativa: o nome inteiro elide justamente
    # onde a linha precisa ser lida. A frase completa continua no combo,
    # que é onde a escolha é feita.
    "harmonize.extent.intersection.short": ("Interseção", "Intersection"),
    "harmonize.extent.union.short": ("União", "Union"),
    "harmonize.preview.busy": ("medindo…", "measuring…"),
    "harmonize.preview.grid": ("grade", "grid"),
    "harmonize.preview.scored": ("com score", "scored"),
    "harmonize.preview.empty": (
        "vazia — as camadas não se sobrepõem neste CRS",
        "empty — the layers do not overlap in this CRS"),
    "harmonize.preview.estimated": (
        "Fração estimada em uma grade de %1×%2 (1 célula a cada %3).",
        "Fraction estimated on a %1×%2 grid (1 cell in every %3)."),
    "harmonize.preview.same": (
        "As duas políticas dão o mesmo número de células com score: %1. A "
        "união só acrescenta área sem score.",
        "Both policies give the same number of scored cells: %1. The union "
        "only adds area with no score."),
    "harmonize.preview.note": (
        "Um score precisa de todos os critérios, então as células com score "
        "são a interseção das camadas — qualquer que seja a extensão da "
        "grade. Nenhuma das duas está errada: elas respondem a perguntas "
        "diferentes.",
        "A score needs every criterion, so the scored cells are the "
        "intersection of the layers whatever extent the grid has. Neither is "
        "wrong: they answer different questions."),
    "harmonize.run": ("Harmonizar", "Harmonise"),
    "harmonize.willRun": (
        "%1 camadas serão trazidas para esta grade.",
        "%1 layers will be brought onto this grid."),
    "harmonize.blocked": (
        "Informe o CRS alvo e um pixel maior que zero, com ao menos uma "
        "camada disponível.",
        "Give a target CRS and a pixel greater than zero, with at least one "
        "layer available."),
    "harmonize.none": (
        "Nenhum raster importado ainda. Importe dados na etapa 2.",
        "No raster imported yet. Import data in step 2."),
    "harmonize.missing": ("arquivo ausente", "file missing"),
    "harmonize.sparse": (
        "Dado esparso (%1) não é harmonizado: ele vira grade antes, em "
        "Dados › Gerar grade.",
        "Sparse data (%1) is not harmonised: it becomes a grid first, in "
        "Data › Build a grid."),

    # ---- gridding, MSP-06 ------------------------------------------------
    "gridding.title": ("Gerar grade a partir de dado esparso",
                       "Build a grid from sparse data"),
    "gridding.explain": (
        "A harmonização reprojeta e reamostra um raster. Uma tabela de "
        "amostras ou um vetor de feições chega à grade por outro caminho — e "
        "qual caminho é uma decisão científica, não encanamento.",
        "Harmonisation reprojects and resamples a raster. A table of samples "
        "or a vector of features reaches the grid another way — and which way "
        "is a scientific decision, not plumbing."),
    "gridding.none": (
        "Nenhuma tabela ou vetor importado neste projeto.",
        "No table or vector imported into this project."),
    "gridding.dataset": ("Dado", "Dataset"),
    "gridding.method": ("Método", "Method"),
    "gridding.method.grid.idw": (
        "IDW — interpolar amostras (Shepard 1968)",
        "IDW — interpolate samples (Shepard 1968)"),
    # Os três nomes que o QGIS usa, para quem conhece um reconhecer o outro.
    "gridding.method.grid.tin_linear": (
        "TIN linear — triangulação de Delaunay",
        "TIN linear — Delaunay triangulation"),
    "gridding.method.grid.tin_cubic": (
        "TIN Clough-Tocher (cúbico) — suave",
        "TIN Clough-Toucher (cubic) — smooth"),
    "gridding.method.grid.euclidean_distance": (
        "Distância euclidiana até a feição mais próxima",
        "Euclidean distance to the nearest feature"),
    "gridding.method.grid.rasterize": (
        "Rasterizar — queimar o valor do atributo",
        "Rasterize — burn the attribute value"),
    "gridding.estimates": (
        "Este método ESTIMA valor onde nada foi medido. Célula sem amostra "
        "suficiente dentro do raio fica nula, e não é preenchida de longe.",
        "This method ESTIMATES a value where nothing was measured. A cell "
        "without enough samples inside the radius stays null, and is not "
        "filled from far away."),
    "gridding.estimates.tin": (
        "Este método ESTIMA valor onde nada foi medido. Ele para no casco "
        "convexo das amostras: fora da área que elas cercam o resultado é "
        "nulo, e nada é preenchido a partir da amostra mais próxima.",
        "This method ESTIMATES a value where nothing was measured. It stops "
        "at the samples' convex hull: outside the area they enclose the "
        "result is null, and nothing is filled in from the nearest sample."),
    "gridding.transfers": (
        "Este método não estima nada: leva para a grade um fato que já "
        "existe.",
        "This method estimates nothing: it carries a fact that already "
        "exists onto the grid."),
    # Escolher "distância" sobre uma tabela de amostras é legítimo e quase
    # nunca é o que a pessoa quer: o resultado mede a cobertura do
    # levantamento, não uma propriedade do terreno.
    "gridding.distance.onSamples": (
        "Atenção: as \"feições\" aqui são as próprias amostras da tabela. O "
        "resultado é a distância até a amostra mais próxima — um mapa de "
        "cobertura do levantamento, não uma propriedade do terreno. Para um "
        "critério a partir de valores medidos, use IDW.",
        "Careful: the \"features\" here are the table's own samples. The "
        "result is the distance to the nearest sample — a map of the survey's "
        "coverage, not a property of the ground. For a criterion from measured "
        "values, use IDW."),
    "gridding.distance.onFeatures": (
        "Distância em linha reta, na unidade do CRS, até a feição mais "
        "próxima. É assim que se produz um critério do tipo "
        "\"distância até falhas\".",
        "Straight-line distance, in the CRS unit, to the nearest feature. "
        "This is how a \"distance to faults\" criterion is made."),
    "gridding.radius": ("Raio de busca (unidade do CRS)",
                        "Search radius (CRS unit)"),
    "gridding.power": ("Potência / mínimo de pontos",
                       "Power / minimum points"),
    "gridding.minPoints": ("mín.", "min."),
    "gridding.maxDistance": ("Distância máxima (opcional)",
                            "Maximum distance (optional)"),
    "gridding.maxDistance.hint": (
        "Em branco, o limite é o casco convexo das amostras — o que o QGIS "
        "faz. Preenchida, célula mais longe que isso de qualquer amostra "
        "fica nula.",
        "Blank, the limit is the samples' convex hull — what QGIS does. "
        "Filled, a cell farther than this from every sample stays null."),
    # O overshoot do cúbico é propriedade do método, fica no manifesto e não é
    # cortado (ADR-MSP-007). Dito antes de rodar, não descoberto depois.
    "gridding.cubic.overshoot": (
        "Clough-Tocher é C1 entre triângulos: num degrau abrupto a superfície "
        "cúbica pode passar do maior e do menor valor amostrado. Isso é do "
        "método, fica registrado no manifesto e não é cortado.",
        "Clough-Tocher is C1 across triangles: at a sharp step the cubic "
        "surface can pass above the highest and below the lowest sampled "
        "value. That is the method, it is recorded in the manifest, and it is "
        "not clamped."),
    # A escolha entre os três interpoladores é medida, não preferida.
    "gridding.compare": ("Medir qual método erra menos",
                         "Measure which method errs least"),
    "gridding.compare.hint": (
        "Separa um quinto das amostras, prevê com cada método e compara o "
        "erro. Não altera nada: a escolha continua sendo sua.",
        "Holds a fifth of the samples out, predicts them with each method and "
        "compares the error. It changes nothing: the choice stays yours."),
    "gridding.compare.running": ("Medindo…", "Measuring…"),
    "gridding.compare.best": ("menor erro", "lowest error"),
    "gridding.compare.coverage": ("cobertura %1%", "coverage %1%"),
    "gridding.compare.scored": (
        "RMSE na unidade do dado, sobre as %1 amostras que todo método "
        "respondeu, em %2 partições.",
        "RMSE in the data's own unit, over the %1 samples every method "
        "answered, in %2 folds."),
    # ---- M7: campos potenciais, secao 9.4 -------------------------------
    "pf.title": ("Campos potenciais", "Potential fields"),
    "pf.explain": (
        "Transformações lineares de um campo medido: derivadas, realces de "
        "borda, continuação para cima, redução ao polo. Elas realçam; nenhuma "
        "delas interpreta.",
        "Linear transformations of a measured field: derivatives, edge "
        "enhancements, upward continuation, reduction to the pole. They "
        "enhance; none of them interprets."),
    "pf.noLayer": (
        "Nenhuma camada com arquivo na visualização. Importe um grid do campo "
        "primeiro — e ele precisa estar numa grade métrica.",
        "No layer with a file in the view. Import a field grid first — and it "
        "has to be on a metric grid."),
    "pf.field": ("Campo", "Field"),
    "pf.kind": ("Tipo de campo", "Kind of field"),
    "pf.kind.gravity": ("Gravimétrico", "Gravity"),
    "pf.kind.magnetic": ("Magnético", "Magnetic"),
    "pf.kind.other": ("Outro — não é campo potencial",
                      "Other — not a potential field"),
    # A razão vai no rótulo do item, porque um item indisponível não recebe
    # hover. Mesma regra dos menus desabilitados desde o M5.5.
    "pf.only.potential": (
        "só para campo potencial: usa a derivada vertical, que é inferida do "
        "dado horizontal pela equação de Laplace",
        "potential fields only: it uses the vertical derivative, inferred "
        "from the horizontal data through Laplace's equation"),
    "pf.only.magnetic": (
        "só para campo magnético: depende da natureza dipolar do campo",
        "magnetic fields only: it depends on the field being dipolar"),
    "pf.operator": ("Operador", "Operator"),
    "pf.axis": ("Eixo e ordem", "Axis and order"),
    "pf.axis.x": ("x (leste)", "x (east)"),
    "pf.axis.y": ("y (norte)", "y (north)"),
    "pf.axis.z": ("z (para baixo)", "z (downward)"),
    "pf.order": ("ordem", "order"),
    "pf.height": ("Altura", "Height"),
    "pf.height.hint": (
        "Positiva, para cima, na unidade do CRS. Continuar para baixo "
        "amplifica ruído sem limite e é recusado.",
        "Positive, upward, in the CRS unit. Downward continuation amplifies "
        "noise without bound and is refused."),
    "pf.field.geomagnetic": ("Campo geomagnético", "Geomagnetic field"),
    # I e D são símbolos, e símbolo não se traduz — como CRS e AHP. Mas
    # passam pelo catálogo assim mesmo: a regra é que nenhuma tela carrega
    # literal, e uma exceção "só para duas letras" é uma exceção.
    "pf.symbol.inclination": ("I", "I"),
    "pf.symbol.declination": ("D", "D"),
    "pf.degrees": ("inclinação e declinação, em graus",
                   "inclination and declination, in degrees"),
    "pf.border": ("Borda: padding", "Border: padding"),
    "pf.taper": ("taper", "taper"),
    "pf.border.hint": (
        "Fração do lado que a grade cresce antes da FFT, e quanto da região "
        "refletida recebe o cosseno. A diferença entre 0,1 e 0,5 é visível no "
        "resultado, e o valor vai para o manifesto.",
        "How much the grid grows on each side before the FFT, and how much of "
        "the reflected region gets the cosine. The difference between 0.1 and "
        "0.5 shows in the result, and the value goes to the manifest."),
    # MSP-15 manda avisar, e o aviso aparece antes de executar.
    "pf.rtp.unstable": (
        "⚠ Inclinação abaixo de 30°: perto do equador magnético a redução ao "
        "polo amplifica uma faixa de números de onda sem limite, na direção "
        "da declinação. Compare com o sinal analítico, que não depende da "
        "direção de magnetização.",
        "⚠ Inclination below 30°: near the magnetic equator the reduction to "
        "the pole amplifies a band of wavenumbers without bound, along the "
        "declination. Compare with the analytic signal, which does not depend "
        "on the magnetisation direction."),
    "pf.conventions": (
        "Convenções: z é positivo para baixo, então a derivada vertical cresce "
        "ao aproximar-se da fonte. A altura é positiva para cima. x é leste, y "
        "é norte, na unidade do CRS. Uma derivada divide a unidade do campo "
        "pela unidade de comprimento; o tilt sai em radianos. Blakely (1995).",
        "Conventions: z is positive downward, so the vertical derivative grows "
        "as you approach the source. Height is positive upward. x is east, y "
        "is north, in the CRS unit. A derivative divides the field's unit by "
        "the length unit; the tilt comes out in radians. Blakely (1995)."),
    "pf.run": ("Executar", "Run"),
    "pf.willRun": ("Produz a camada %1, ao lado do original.",
                   "Produces the layer %1, beside the original."),
    "pf.blocked": ("Escolha um campo e uma altura positiva.",
                   "Choose a field and a positive height."),
    "pf.op.potential_fields.derivative": (
        "Derivada direcional", "Directional derivative"),
    "pf.op.potential_fields.total_horizontal_gradient": (
        "Gradiente horizontal total (THG)",
        "Total horizontal gradient (THG)"),
    "pf.op.potential_fields.analytic_signal": (
        "Sinal analítico", "Analytic signal"),
    "pf.op.potential_fields.tilt": ("Tilt", "Tilt"),
    "pf.op.potential_fields.upward_continuation": (
        "Continuação para cima", "Upward continuation"),
    "pf.op.potential_fields.regional_residual": (
        "Regional e residual", "Regional and residual"),
    "pf.op.potential_fields.rtp": (
        "Redução ao polo (RTP)", "Reduction to the pole (RTP)"),
    "pf.does.potential_fields.derivative": (
        "d/dx, d/dy ou d/dz. A vertical realça fontes rasas; ordem 2 realça "
        "mais e amplifica mais ruído.",
        "d/dx, d/dy or d/dz. The vertical one enhances shallow sources; order "
        "2 enhances more and amplifies more noise."),
    "pf.does.potential_fields.total_horizontal_gradient": (
        "sqrt(dx² + dy²). Máximo sobre um contato vertical. Realça bordas — "
        "quem decide que ali há um contato é quem interpreta.",
        "sqrt(dx² + dy²). Maximum over a vertical contact. It enhances edges — "
        "deciding there is a contact is the interpreter's."),
    "pf.does.potential_fields.analytic_signal": (
        "sqrt(dx² + dy² + dz²). Máximo sobre a fonte independentemente da "
        "direção de magnetização — exato em 2D, aproximado em 3D.",
        "sqrt(dx² + dy² + dz²). Maximum over the source regardless of the "
        "magnetisation direction — exact in 2D, approximate in 3D."),
    "pf.does.potential_fields.tilt": (
        "atan2(dz, THG), em radianos. O zero cai perto da borda da fonte, e o "
        "valor é limitado: realça sem depender da amplitude do campo.",
        "atan2(dz, THG), in radians. The zero falls near the source edge, and "
        "the value is bounded: it enhances without depending on amplitude."),
    "pf.does.potential_fields.upward_continuation": (
        "Observa o mesmo campo mais alto. Atenua o raso e preserva o profundo.",
        "Observes the same field from higher up. It attenuates the shallow and "
        "preserves the deep."),
    "pf.does.potential_fields.regional_residual": (
        "Separa em regional (continuado) e residual (o resto). A altura decide "
        "o que é regional: outra altura é outra separação.",
        "Splits into regional (continued) and residual (the rest). The height "
        "decides what counts as regional: another height is another split."),
    "pf.does.potential_fields.rtp": (
        "Transforma o campo no que seria medido no polo magnético, centrando a "
        "anomalia sobre a fonte. Instável em baixa inclinação.",
        "Transforms the field into what would be measured at the magnetic "
        "pole, centring the anomaly over the source. Unstable at low "
        "inclination."),

    # ---- M6: cenários, sensibilidade, explicabilidade -------------------
    "scenarios.title": ("Cenários e sensibilidade",
                        "Scenarios and sensitivity"),
    "scenarios.explain": (
        "O mapa responde \"onde\". Aqui você mede o quanto essa resposta "
        "depende das escolhas que a produziram: tirar um critério, ou mexer "
        "num parâmetro, e ver o quanto o mapa e o ranking se movem.",
        "The map answers \"where\". Here you measure how much that answer "
        "depends on the choices behind it: drop a criterion, or move a "
        "parameter, and see how far the map and the ranking move."),
    "scenarios.needsTwo": (
        "Sensibilidade precisa de pelo menos dois critérios. Com um só, o "
        "mapa É o critério.",
        "Sensitivity needs at least two criteria. With one, the map IS the "
        "criterion."),
    "scenarios.loo": ("De quais critérios o resultado depende",
                      "Which criteria the result depends on"),
    "scenarios.loo.hint": (
        "Tira um critério por vez e reagrega os demais. O primeiro da lista é "
        "aquele cuja remoção mais move o mapa.",
        "Removes one criterion at a time and re-aggregates the rest. The "
        "first row is the one whose removal moves the map most."),
    "scenarios.sweep": ("O quanto depende de um parâmetro",
                        "How much it depends on one parameter"),
    "scenarios.param.gamma": ("Gamma (compensação)", "Gamma (compensation)"),
    "scenarios.param.weight": ("Peso de um critério", "One criterion's weight"),
    "scenarios.measure": ("Medir", "Measure"),
    "scenarios.measuring": ("Medindo no worker…", "Measuring in the worker…"),
    # P-173: a tela mostra, e não decide.
    "scenarios.decides": (
        "Isto mede; não altera nada. Nenhum peso é reescrito e nenhum "
        "critério é escondido — quem escolhe é você.",
        "This measures; it changes nothing. No weight is rewritten and no "
        "criterion is hidden — the choice stays yours."),
    "scenarios.col.dropped": ("SEM O CRITÉRIO", "WITHOUT THE CRITERION"),
    "scenarios.col.change": ("|Δ| MÉDIO", "MEAN |Δ|"),
    "scenarios.col.rho": ("RHO", "RHO"),
    "scenarios.col.top": ("MELHORES 10 %", "TOP 10 %"),
    "scenarios.col.cells": ("CÉLULAS", "CELLS"),
    "scenarios.worst": (
        "Pior caso da varredura: |Δ| médio %1, e %2 das melhores áreas "
        "continuam as mesmas.",
        "Worst case in the sweep: mean |Δ| %1, and %2 of the best areas stay "
        "the same."),
    "dialog.close": ("Fechar", "Close"),

    "identify.title": ("O QUE HÁ AQUI", "WHAT IS HERE"),
    "identify.noData": ("sem dado nesta célula", "no data in this cell"),
    "identify.outside": ("fora desta camada", "outside this layer"),
    "identify.notAField": (
        "amostras, não um campo contínuo",
        "samples, not a continuous field"),
    "identify.cell": ("col %1, lin %2", "col %1, row %2"),

    "gridding.detail": ("Detalhe", "Detail"),
    "gridding.detail.coarse": (
        "Rápida — um pixel por amostra", "Fast — one pixel per sample"),
    "gridding.detail.balanced": (
        "Equilibrada — 3 pixels por amostra (recomendada)",
        "Balanced — 3 pixels per sample (recommended)"),
    "gridding.detail.fine": (
        "Detalhada — 5 pixels por amostra", "Fine — 5 pixels per sample"),
    "gridding.gridSize": ("→ %1 x %2 células, ~%3 MB",
                          "→ %1 x %2 cells, ~%3 MB"),

    "gridding.spacing": (
        "As amostras estão a ~%1 m umas das outras. Um raio menor que isso "
        "deixa quase toda célula nula; o valor proposto é o triplo.",
        "The samples sit ~%1 m apart. A radius below that leaves almost every "
        "cell null; the proposed value is three times it."),
    "gridding.wholeExtent": (
        "Usar toda a extensão do dado",
        "Use the whole extent of the data"),
    "gridding.bounds.hint": ("esquerda, baixo, direita, topo",
                             "left, bottom, right, top"),
    "gridding.run": ("Gerar grade", "Build the grid"),
    "gridding.willRun": (
        "O raster resultante entra no projeto e passa a ser harmonizável.",
        "The resulting raster enters the project and becomes harmonisable."),
    "gridding.blocked": (
        "Informe CRS, pixel e — para IDW — um raio maior que zero.",
        "Give a CRS, a pixel and — for IDW — a radius greater than zero."),
    "menu.file.gridding": ("Gerar grade…", "Build a grid…"),
    "harmonize.mixedCrs": (
        "As camadas escolhidas estão em %1. Reprojetá-las para uma grade só é "
        "justamente o que esta etapa faz — mas se elas cobrem áreas "
        "diferentes, a interseção sai vazia.",
        "The chosen layers are in %1. Reprojecting them onto one grid is "
        "exactly what this step does — but if they cover different areas, the "
        "intersection comes out empty."),
    "harmonize.explainMore": (
        "Escolha quais camadas entram. O catálogo guarda tudo o que já foi "
        "importado neste projeto, inclusive de sessões anteriores; uma "
        "análise é um subconjunto dele.",
        "Choose which layers go in. The catalogue keeps everything ever "
        "imported into this project, including from earlier sessions; an "
        "analysis is a subset of it."),

    # Por que um botão do painel de jobs está desabilitado. Um ToolTip nunca
    # dispara num controle desabilitado, então o motivo vai numa linha.
    "jobs.why.cancel": (
        "Cancelar vale só para um job em execução.",
        "Cancel applies only to a running job."),
    "jobs.why.noResult": (
        "Este operador só lê e responde: não produz artefato para abrir.",
        "This operator only reads and answers: it produces no artefact to "
        "open."),

    # A container file holds more than one dataset. Reading the first is a
    # guess, and a guess would be recorded as the dataset (A26).
    "import.layers": ("CAMADA DO ARQUIVO", "LAYER IN THE FILE"),
    "import.layers.choose": ("— escolha uma —", "— choose one —"),
    "import.layers.undecided": (
        "Este arquivo tem %1 camadas. Escolha qual importar: nenhuma é a "
        "padrão.",
        "This file holds %1 layers. Choose which to import: none is the "
        "default."),
    "import.layers.chosen": (
        "Importando a camada %1.", "Importing layer %1."),
    "import.verdict.layer": (
        "Escolha a camada do arquivo antes de importar.",
        "Choose the layer in the file before importing."),
    "import.import.tip": (
        "Adiciona este dataset ao catálogo do projeto.",
        "Add this dataset to the project catalogue."),
    "import.import.tip.layer": (
        "O arquivo tem mais de uma camada e nenhuma foi escolhida.",
        "The file holds more than one layer and none has been chosen."),
    "import.import.tip.blocked": (
        "Um problema bloqueante impede a importação. Os achados acima dizem "
        "o que corrigir.",
        "A blocking problem prevents import. The findings above say what to "
        "correct."),
    "import.import.tip.unchecked": (
        "As checagens de QA/QC ainda não rodaram.",
        "The QA/QC checks have not run yet."),

    # The facts the wizard states about a file. They were English literals in
    # the QML until E4, which made them the one panel the language switch did
    # not reach (P-124).
    "fact.format": ("Formato", "Format"),
    "fact.crs": ("CRS", "CRS"),
    "fact.crsUnit": ("Unidade do CRS", "CRS unit"),
    "fact.extent": ("Extensão", "Extent"),
    "fact.size": ("Tamanho", "Size"),
    "fact.pixel": ("Pixel", "Pixel"),
    "fact.bands": ("Bandas", "Bands"),
    "fact.overviews": ("Overviews", "Overviews"),
    "fact.cog": ("%1 · COG", "%1 · COG"),
    "fact.nodata": ("NoData", "NoData"),
    "fact.notDeclared": ("não declarado", "not declared"),
    "fact.features": ("Feições", "Features"),
    "fact.geometry": ("Geometria", "Geometry"),
    "fact.layers": ("Camadas", "Layers"),
    "fact.rows": ("Linhas", "Rows"),
    "fact.fields": ("Campos", "Fields"),
    "fact.valid": ("Válidos", "Valid"),
    "fact.range": ("Faixa", "Range"),

    # The map inside the wizard. Each caption says what is on screen *and*
    # what it leaves out: a silhouette that does not announce itself is a
    # wrong drawing of the file.
    "preview.map": ("MAPA DA PRÉVIA", "PREVIEW MAP"),
    "preview.map.raster": (
        "O raster, lido do arquivo na resolução da tela.",
        "The raster, read from the file at screen resolution."),
    "preview.map.vector": (
        "Silhueta: %1 de %2 feições, contorno simplificado.",
        "Silhouette: %1 of %2 features, outline simplified."),
    "preview.map.table": (
        "%1 pontos desenhados, de %2 linhas.",
        "%1 points drawn, of %2 rows."),
    "preview.map.none": (
        "Este formato não tem desenho de prévia.",
        "This format has no preview drawing."),
    "preview.map.empty": (
        "sem prévia para desenhar", "nothing to preview"),
    "import.open": ("Abrir arquivo", "Open a file"),
    "import.drop": (
        "Solte um arquivo aqui, ou use Escolher…",
        "Drop a file here, or use Choose…"),

    # ---- histogram -------------------------------------------------------
    "histogram.empty": ("sem distribuição", "no distribution"),

    # ---- recovery banner ------------------------------------------------
    "recovery.nothingRecorded": (
        "Nada foi registrado do trabalho interrompido.",
        "Nothing was recorded from interrupted work."),
    "recovery.dismiss": ("Dispensar", "Dismiss"),
}


def keys() -> tuple[str, ...]:
    return tuple(CATALOG)
