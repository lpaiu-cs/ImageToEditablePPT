# R6: causal diagnosis and transfer result — NO PROMOTION

2026-09-08. User-approved v0.3 baseline `80b0937` remains on
`codex/region-first-diagnostics`. R6 is isolated on
`codex/region-generalization-r6`; no new release/package is promoted.

**Generalization is not established.** Color/polarity invariance improves at
the stroke level, but source-held transfer does not establish useful overall
complex-diagram improvement. Passing unit tests is not the quality verdict.

## What the experiments establish

| Cause | Intervention and observation | Remaining boundary |
|---|---|---|
| `gray < 110` drops colored ink | Local dark contrast + thin chromatic ink + bright-on-dark evidence recovers 7 blue-flow routes | Only 5 fit native presets |
| Fixed-width head sampling clips thick heads | Shaft-scaled transverse/endpoint windows preserve the same head/shaft ratios; 5 emitted blue arrows have correct directions | General curves/junctions not solved |
| Outline thresholds miss colored boundaries | p058 has 14 legacy dark-outline versus 30 multichannel-edge proposals; closed colored child outlines recover | Small children below the area floor still merge into parent OCR |
| Dark fill is mistaken for a header line | First dark-field arm made all 11 transformer nodes containers; continuous edge/divider evidence fixes this | Mixed-polarity page parsing remains weak |
| A center point is treated as containment | Require whole child box containment | Bounding boxes alone do not establish semantic role |

The repaired candidate retains the approved reasoning drawing's 24 real nodes,
24 labels and 24 solid links. The old five-ROI regression retains 23 matched
objects, 15 directed links and zero extras. Existing 11 synthetic contracts pass.
Full suite: **309 passed**, 9 known warnings; **30 new R6 tests** cover hue,
polarity, endpoint direction, geometry roles and counterexamples. Oracle-owner
tracing and end-to-end owner detection tests are explicitly separate.

Final native visual review also catches a regression hidden by connector counts:
dark-transformer's two former arrows become two **undirected lines**. The same
number of emitted connectors is not preservation of directed topology. This
alone blocks promotion, independently of the reserved-transfer failure.

## Transfer design and result

The source slice was fixed before runtime edits. It excludes both Phase 16 split
IDs/source groups and perceptual neighbors at <=4 Hamming bits. SHA ordering
selected 8 diagram suggestions and the only 2 eligible non-diagram suggestions.
The pool had historical source-sheet exposure; it is R6-reserved transfer data,
not a historically unseen or formal holdout. No runtime edits followed candidate
freeze or candidate transfer outputs.

Both v0.3 installed runtime and R6 ran on all 10 fixed sources. Three were
resource-rejected, identically: P146/P114 exceed 4MP ROI, P104 exceeds 16MP input.
Do not remove them from the denominator or call those negative classifications.
Seven PPTs per arm were rendered in actual PowerPoint and all ten comparison
sheets were directly inspected. Native ID/binding/raster audits pass; that only
proves serialization.

- P137 shows a narrow colored-boundary gain, not recovered overall topology.
- P159 retains a useful partial chain; it does not improve on v0.3.
- P144/P057/P084 expose false block/compound-shape/icon interpretations.
- P088 still lacks decision shapes and topology and converts an icon to a circle.
- P009, the non-rejected non-diagram, still emits three photo-derived rectangles.
- No broad complex-image acceptance follows from this result. The complete
  per-source findings are in `benchmarks/region_r6_visual_review.json`.

## Why further threshold tuning is insufficient

The pipeline currently treats a sufficiently closed pixel region as an editable
diagram object. But a photograph frame, logo disk, tensor block face, cylinder
cap, panel and actual graph node can all have equally strong closure evidence.
Color/contrast corrections recover pixels without deciding **what owns them**.
The next stage then masks those candidates out before tracing and assigns all
interior OCR to them. An early role error destroys later topology and label
ownership. More aggressive detection can therefore increase repair work.

There are three additional independent ceilings:

1. The whole-ROI area floor is not invariant to diagram density: legitimate small
   nodes disappear in larger figures. Lowering it alone also admits icon details.
2. Connected components do not represent port/junction topology. Dashes and
   crossings require a graph of observed stroke pieces and typed uncertainty.
3. The emitter represents only bounded native presets. An above-endpoint U route
   or general curve can be traced correctly but still be omitted during emission.

Thus the evidence supports a hierarchical structural/semantic acceptance stage,
followed by local-scale node proposals and explicit junction graphs. It does
not support declaring a few additional heuristics a general solution. See
`region_generalization_next_spec.md` for the next bounded architecture experiment.

## Evidence and preservation

- Frozen source/candidate manifests: `benchmarks/region_r6_transfer_inputs.json`,
  `benchmarks/region_r6_candidate.json`.
- Artifacts: `artifacts/region-generalization-r6/complex-candidate2`,
  `transfer-baseline`, `transfer-candidate`, `transfer-review-complete`.
- Failed first dark-field and pre-scaled arrow diagnostics remain separate.
- The first transfer sheet attempt stopped before candidate rendering completed;
  its partial directory is retained, and `transfer-review-complete` is canonical.
- Existing Phase 16 annotations, formal holdout and human edit-time lock remain
  untouched. No automation timing is substituted for human editing time.
