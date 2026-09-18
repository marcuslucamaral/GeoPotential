# V-M5 — Geothermal Decision Engine

Date: `2026-09-01`
Result: **PASS**
Milestone: `M5`
Plan: `../milestones/M5_DECISION_ENGINE.md`
Storyboard: `images/m5/STORYBOARD.md`
Environment: conda `mcda_geo`, Python 3.11.14, PySide6 6.10.1, numpy 2.4.1,
rasterio 1.4.4, Linux 6.5.0 x86_64

Reproduce from `geopotencial_msp/`:

```
./tools/run_gate.sh
./run.sh --self-test
tools/capture_sequence.py m5
```

---

## 1. Full regression gate

```
20 passed, 0 failed, 0 blocked, of 20
```

Every check green, including `decision` (35 tests), `pipeline` (19 tests),
`vertical-slice` (59 interface checks) and `storyboards` (8/8 + 6/6 frames).
285 unit, contract and integration tests in total. Every M1–M4 contract stayed
green. The self-test was run twice consecutively; 59/59 each time.

---

## 2. The M5 gate: the flow, arrow by arrow

§20 M5 asks for a complete workflow rather than a list of features, so each
arrow is a check.

| Arrow | Check | Evidence |
|---|---|---|
| dados → QA/QC | 36 | `large_field.tif: no problems found.` |
| QA/QC → harmonização | 37 | 2 layers on 1024 × 1024 at 40 m in EPSG:26912 |
| harmonização → membership | 38 | `heat_proxy linear_increasing [−45.88, 39.76] mGal`; `structure_proxy linear_decreasing [−7.90, 116.27] mGal` |
| membership → AHP/pesos | 39 | weights `[0.75, 0.25]`, CR = 0.0000 against 0.10 |
| AHP/pesos → MCDA | 42 | **worst \|worker − numpy\| = 0.00e+00 over 90 000 pixels** |
| MCDA → prospectividade | 43 | criterion order `['heat_proxy', 'structure_proxy']`, gamma 0.7, every input hashed, grid 1024 × 1024 |

And the refusals, which are where a decision engine either earns trust or does
not:

| Refusal | Check | Evidence |
|---|---|---|
| an inconsistent matrix | 40 | `the comparison matrix is inconsistent: CR = 6.1303, above the 0.10 threshold…` |
| an override, recorded | 41 | 2 AHP verdicts in the audit trail; CR = 6.1303 accepted with its written reason |

Checked in the suites rather than the interface gate: a RAW criterion cannot be
aggregated; weights that do not sum to 1; a negative weight; more than 10
criteria against Saaty's RI table; a non-reciprocal matrix; a judgment off the
fundamental scale; gamma outside [0, 1]; a continuous layer used as a boolean
constraint; a categorical layer resampled by averaging; a geographic target CRS.

---

## 3. Checked against independent calculation, not against itself

The arithmetic claims are the ones that matter, and a golden file would only
prove the code has not changed. So:

- **AHP** is checked against matrices whose answer is known by construction:
  `a_ij = w_i / w_j` gives back `w` exactly, with `lambda_max = n` and
  `CI = 0`. The 2 × 2 case returns `[0.9, 0.1]` for a judgment of 9.
- **The fuzzy operators** are checked against the published formulae evaluated
  by hand: the product at `0.2 × 0.6`, the sum at `1 − (1−0.2)(1−0.6)`, and
  gamma at `((1−(1−0.2)(1−0.6))^0.7)((0.2×0.6)^0.3)`. Gamma at 0 reproduces the
  product and at 1 the sum, and at 0.5 lies between them everywhere.
- **The whole pipeline** is checked by recomputing it in numpy from the
  manifest's own anchors — check 42, agreeing to **exactly zero** over 90 000
  pixels. That is the strongest form available: the worker's answer and an
  independent one written from the paper, on the same data.

---

## 4. Double counting

§15.1's example is three criteria from one piece of evidence. `decision/
correlation.py` computes Pearson *r* over jointly valid pixels and names the
pair:

> `'heat_flow'` and `'gradient'` correlate at r = +1.00 over 1,600 shared
> pixels. Together they carry 60% of the total weight. They may be measuring
> the same evidence, in which case independent weights count it twice. Put them
> in one hierarchical group, drop one, or record why both belong.

Putting them in a group silences it — that is the documented remedy, and
warning about a fix afterwards would be nagging. `group_weights` then makes the
arithmetic match the intent: three thermal criteria draw 0.6 **between them**,
not 0.6 each.

---

## 5. The interface

![the M5 storyboard](images/m5/contact_sheet.png)

Six frames, one per arrow, captured from the running application and checked
numerically. The full table is `images/m5/STORYBOARD.md`.

| # | State | What the frame carries |
|---|---|---|
| 01 | QA/QC | `usable=True severity=INFO` |
| 02 | harmonised | `grid=1024x1024 crs=EPSG:26912 layers=2` |
| 03 | Membership Editor | `function=linear_increasing sense=more is more favourable` |
| 04 | Decision Model | `cr=0.0 consistent=True w_heat=0.75` |
| 05 | refused | `cr=0.8623 run_enabled=False` |
| 06 | prospectivity | `method=fuzzy_gamma range=0.000-0.981 valid=98.9` |

MSP-07 asks for the histogram, the curve, the unit and the physical sense
**at the same time**, and that is what frame 03 shows: the membership curve
drawn over the distribution it is shaping, on one axis in mGal, with
"more is more favourable" written beside it. Frame 05 shows the refusal as the
user meets it — CR in red, Run disabled, the reason on the button, and the
correlated pair named underneath.

---

## 6. Three defects the storyboard found that nothing else did

The storyboard runner was built at the start of this milestone precisely so
that interface claims stop resting on somebody glancing at a screenshot. It
earned that on its first two uses.

**The display stretch was recomputed per view.** Zooming out and back produced
a saturated map, because the colour mapping came from whatever tile was on
screen rather than from the layer. A colour meant a different value at every
zoom. Found by an `expect` comparing a probe pixel across a zoom round-trip;
no unit test covered it, and the contact sheet made it visible only because two
frames happened to sit side by side. The stretch is now fixed when a layer
opens and held.

**The membership curve was not drawn at all.** It looked plausible at thumbnail
size — the histogram was there, the caption was there — and the curve was
absent. Caught by counting pixels of the curve's own colour: 146, all of them
the caption. Two causes, in sequence: `Canvas` does not composite under the
offscreen platform (replaced with a declarative polyline), and then
`onCriterionChanged` read `ready`, a binding on the same property, which has
not re-evaluated when the handler runs — so every anchor stayed empty and the
"curve" was a flat line along the bottom. Now 838 curve pixels, and an `expect`
that fails below 400.

**A self-test check that depended on history.** "Science is not undoable"
assumed something undoable sat on the command stack, which was true until M3
added an import and false again when M5 added an aggregation. It now creates
the undoable command it needs. A check that passes because of what ran before
it is not checking what it claims.

---

## 7. What this does not prove

- **Nothing about scenarios or sensitivity.** Leave-one-out, weight and gamma
  variation, spatial stability, explainability and target ranking are M6. A
  suitability map without them is a number, not yet an argument.
- **Nothing about gravity or magnetics.** M7. The `heat_proxy` and
  `structure_proxy` criteria here are synthetic fields with real units and a
  real CRS; they exercise the machinery, not the geophysics.
- **Nothing about the AHP interface at scale.** The Decision Model shows
  weights and the consistency ratio; there is no matrix editor, so judgments
  are entered through the operator's parameters. With 10 criteria that is 45
  judgments, and a screen for them belongs with the scenarios of M6.
- **Nothing about hillshade or vector criteria on the canvas.** Both carried
  from M4 and still open.
- **Nothing about packaging.** M8.
