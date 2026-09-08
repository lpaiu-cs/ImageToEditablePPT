# v0.2 complex-input validation: small-ROI gain does not generalize yet

2026-09-08. At user request, froze runtime f7897b0 and tested six more complex existing
development figures plus two predefined scopes of the original input.png. Source/ROI
selection preceded outputs; no runtime change, new resize, post-result crop, threshold
change or holdout access. This is diagnostic validation, not a new algorithm experiment.

## Outcome

**Complex diagrams still fall short.** Native preset output remains helpful, but source
object identity, text ownership and connection evidence are the dominant failures. The
previous limited-region improvement stands; broad complex-image suitability does not.

Counts here are emitted primitives, **not** correctly recovered object/edge counts:

| Source case | Nodes / containers | Links | Labels | Direct visual conclusion |
|---|---:|---:|---:|---|
| Full reasoning, p034 | 23 / 0 | 8 | 10 | False large boxes and merged text; missing fanout/join |
| Blue flow, p042 | 7 / 0 | 0 | 2 | Boxes remain, all blue connections lost |
| Nested panels, p058 | 23 / 6 | 0 | 16 | Useful partial layout, missing headers/child boundaries, wrong ownership |
| Contrastive model, p043 | 5 / 0 | 0 | 5 | Only major blocks, most structural content absent |
| Dark transformer, p011 | 12 / 0 | 0 | 5 | False vertical shape, missing nested frame and links |
| Fusion, p092 | 5 / 2 | 1 | 5 | Some useful boxes, fusion/output and most relations absent |
| Original input, full | — | — | — | Resource rejection: 4,151,040px exceeds 4MP ROI bound |
| Original input, body ROI | 14 / 3 | 6 | 4 | Islands remain; false shapes, text debris and missing cross-region links |

The body ROI was fixed at (0,.04,1,1) before execution. Its excluded top strip is out of
scope; this condition cannot be reported as full-image success. No automatic resizing
or resource-limit relaxation was performed after the full-input rejection.

![Full reasoning comparison](../artifacts/region-complex-v1/review/reasoning-full-comparison.png)

![Blue flow comparison](../artifacts/region-complex-v1/review/blue-flow-comparison.png)

![Original body comparison](../artifacts/region-complex-v1/review/original-body-comparison.png)

## Evidence-backed diagnosis

1. **False geometry is not conservative omission.** In the full reasoning figure, several
   large false boxes come from `visual_geometry:uniform_fill` (including node:region:15,
   :17 and :18). Their source-coordinate extents span real rows and curves rather than
   individual diagram boxes. The old three-extra filter does not generalize to these faces.
   Cropping to one simple row concealed this harder object-identity problem.
2. **Fixed dark-foreground tracing excludes colored strokes.** In p042, a source-only blue
   selector (B-R>70, G-R>30, B>160) selects 39,947 pixels, with median grayscale 121; zero
   pass the current `<110` test. This selector is descriptive, not annotated ground truth,
   but explains why prominent blue arrows are unavailable to the tracer. Broadly raising
   the threshold without negative controls would also introduce filled-region/background ink.
3. **Junction/curve support remains limited.** Two multi-owner components are explicitly
   rejected in reasoning. Other missing links can arise before or after that stage: the
   preset fitter explicitly rejects one contrastive, two dark-transformer and four original
   body paths. Do not attribute every missing edge to one multi-owner rule.
4. **Confident OCR cannot repair wrong owners.** Text can be stable across scales while
   collected from a false large box containing several true labels. It then becomes editable
   but semantically misplaced text. Correct ownership must precede confidence aggregation.

All seven generated PPTX files opened/rendered in actual PowerPoint 16. The native audit
found exact emitted ID sets, valid source/target owner bindings and zero picture objects.
This checks serialization/attachment identity, not whether the owners themselves are true.
The report does not substitute native-object counts for visual quality or human edit time.

## Next order

First separate real filled objects from background faces and prevent text from attaching to
those false owners, with legitimate large/nested/near-white counterexamples. Next evaluate
color- and polarity-aware source stroke evidence. Then address multi-owner junction topology
and curve support separately. Increasing native preset complexity alone does not repair the
currently wrong scene. The user requested verification; no such fixes were applied here.

Source and runtime manifest: [inputs](../benchmarks/region_complex_inputs_v1.json).
Native/CLI evidence and failure diagnostics: [ledger](../benchmarks/region_complex_evidence_v1.json).
Per-image judgments: [visual review](../benchmarks/region_complex_visual_review_v1.json).

The six development images have prior baseline exposure; original input.png was previously
consumed. These are harder scopes than the last run, not a new independent holdout population.
Production runtime and all previous frozen verdicts/artifacts remain unchanged. Existing
268-test evidence is not rerun or repurposed as a visual acceptance score.
