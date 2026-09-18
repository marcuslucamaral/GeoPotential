# Visual evidence

When the interface is part of a deliverable, the evidence is a **sequence of
frames captured from the running application**, not one screenshot taken at a
convenient moment.

    tools/capture_sequence.py m4            run a milestone's storyboard
    tools/capture_sequence.py --all --check every storyboard, failing on a bad frame
    tools/capture_sequence.py --list        what exists

## Every milestone that touches the interface gets a storyboard

One file in `tools/storyboards/`, named for the milestone, walking the states a
person actually walks through. Each step drives the **real** shell — the real
controller, the real worker, the real canvas. A storyboard that photographed a
mock would prove the mock renders.

Write the steps in the order of the milestone's own gate. The storyboard is how
the gate looks; if a gate item cannot be seen, say so in the milestone document
rather than inventing a frame for it.

## Do not read the full-size frames

This is the rule the runner exists to make possible, and the one that matters
most in practice.

- **Read the text report.** `capture_sequence.py` prints one line per frame:
  the facts the step returned, the probe colours, and how much of the frame
  changed. Most questions — did the layer load, did the level of detail change,
  did the job succeed, is the theme applied — are answered there.
- **When looking is genuinely needed, read `contact_sheet.png`.** One
  downscaled grid of every frame. It costs a single small image instead of N
  large ones.
- **To inspect a detail, crop first.** A 200 × 80 crop of the panel in question
  answers the question; the 1440 × 880 frame answers it too, at twenty times
  the cost.
- Never read more than one full-size frame in a row. If two are needed, the
  thing being compared should be a probe or an `expect`, not a pair of images.

## Headless is not the application

A storyboard runs under `QT_QPA_PLATFORM=offscreen`, which uses Qt's **basic**
render loop: `paint` is called on the GUI thread. The real application uses the
**threaded** loop, where `paint` runs on the render thread. The two are not the
same program, and the difference has already cost a crash the gate could not
see:

> The canvas read a GeoTIFF through GDAL while it painted, and the same handle
> was read from the GUI thread for the value under the cursor. Offscreen: never
> a problem. On a real window: a segmentation fault while panning.

So, for anything that draws or reacts to input:

- **Say which loop the evidence came from.** A frame captured offscreen proves
  the drawing is correct; it proves nothing about threading.
- **Exercise the interaction, not only the frame.** Pan, zoom, switch layers,
  change the tool — a picture taken between two events would have missed both
  crashes above.
- **Anything a `paint` does must be safe to do on either thread.** No signal
  emitted from inside `paint` — defer with `QTimer.singleShot(0, …)`. No
  network. No file handle shared with the GUI thread without a lock. When in
  doubt, do it before the frame, not during it.
- **When the report is about a crash or a freeze, run the real window.**
  `./run.sh` on the developer's machine, driven by hand or by a driver, is the
  only evidence that counts for that class of bug.

## Screenshots cost tokens; probes do not

Reading an image is the most expensive check available. The budget for a round
of work is **one or two full frames**, and everything else is asserted:

- prefer a **probe** (a sampled pixel) or a **fact** (the application's own
  state) to any image at all;
- when an image is genuinely needed, take **one**, and crop it to the panel in
  question;
- a contact sheet replaces N frames with one small image — use it instead of a
  series;
- never take a screenshot to confirm something a `expect` already asserts.

## Assert numerically; look only to confirm

Reading an image is the most expensive and least reliable way to check
something, and it has already been wrong twice in this project — a dark theme
read as light, and a legible panel read as blank. Both were settled in seconds
by sampling pixels.

So each step declares what must be true:

- **`probes`** — named points sampled from the frame. A panel background proves
  the theme reached it; a point on the map proves something was drawn.
- **facts** — whatever the step's action returns. Level of detail, pixels read,
  job state, AOI version. These come from the application's own state, which is
  authoritative in a way a picture is not.
- **`must_change`** — a step that changes nothing visible is almost always a
  step that silently failed. The runner fails on it by default.
- **`expect(frame, earlier)`** — for claims about the *sequence*. "The same
  colour after zooming out and back" cannot be asserted from one frame, and it
  is exactly the sort of thing a person is supposed to notice and does not.

`expect` earns its place: it caught a real defect on its first use. The display
stretch was being recomputed from whatever tile was on screen, so a colour meant
a different value at every zoom, and returning to the original view produced a
saturated map. No unit test covered it, and the contact sheet made it obvious
only because two frames happened to be next to each other.

## Um quadro que atribui a propriedade não testa quem a preenche

O editor de pertinência abria vazio — "sem distribuição", âncoras em branco —
porque `criterion` nunca era atribuído no shell. **Nenhum gate pegou**, e a
razão é o padrão que as storyboards usavam: elas atribuíam `functionName`
direto no diálogo e nunca liam `ready`. A *curva* era exercitada; o caminho que
a alimenta, não.

A regra: um quadro que chama `setProperty` para montar o estado está testando o
que vem **depois** daquele ponto. O que vem antes precisa do seu próprio
quadro, que abre a tela pelo caminho real — o token do menu, o botão da trilha
— e então lê a propriedade em vez de escrevê-la.

Um bom sinal de alerta: se o quadro não afirma nada sobre uma propriedade que
ele não atribuiu, ele não cobre nenhuma ligação.

## Efeito de shader não desenha offscreen

`ColorOverlay` e `MultiEffect` devolvem **zero pixels** sob
`QT_QPA_PLATFORM=offscreen` — medido, com um `Image` comum ao lado renderizando
normalmente. Toda storyboard deste projeto é capturada offscreen, então um
ícone tingido por shader seria um quadrado em branco em toda a evidência, **e o
gate passaria**, porque um quadrado em branco é um quadro válido.

Por isso o tingimento de ícone é `QPainter` na CPU (`app/…/icons.py`). E por
isso a regra geral: **toda evidência visual precisa de um número junto**. Uma
captura que existe não é uma captura que desenhou — o build conta cores
distintas e reprova abaixo de 50 pelo mesmo motivo.

## The frames are evidence, so they are regenerable

- Frames go to `docs/validation/images/<storyboard>/`, wiped and rewritten on
  every run. They are outputs, never edited by hand.
- Each run writes `STORYBOARD.md` (the table plus the contact sheet) and
  `frames.json` (the machine-readable record).
- The validation report links the storyboard rather than embedding eight
  images.
- A storyboard runs offscreen (`QT_QPA_PLATFORM=offscreen`) and in a throwaway
  project, so it never touches the developer's recents or a real project.

## What a frame may not be

- **Not a mockup, not a stub, not a design.** The running application or
  nothing.
- **Not a screenshot of a preview file the pipeline wrote.** That proves a file
  exists.
- **Not cropped to hide state.** If a panel is empty in the frame, it was empty
  in the application, and the caption says why.
- **Not retaken until it looks good.** A frame that changed unexpectedly is a
  finding; investigate it before regenerating.
