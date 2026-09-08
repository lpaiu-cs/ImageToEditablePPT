# R5 / v0.3: complex reasoning diagram, conservative production scope

2026-09-08. Development study under [the registered plan](region_complex_r5_plan.md).
Previous v0.2 artifacts and Phase 16 annotations/holdout are untouched.

## Primary visual result

Directly inspected original source, native PowerPoint steps 1, 2 and 3:

| Stage | Real nodes | False large nodes | Correct node labels | Relations |
|---|---:|---:|---:|---|
| frozen v0.2 | 18 | 5 | not a reliable total (merged ownership) | 8 emitted |
| closure-first step 1 | 24 | 0 | 11 | 18 emitted; Gating elbow reversed |
| step 2 | 24 | 0 | 24 | 18 correct solid directed relations |
| straight-shaft fanout | 24 | 0 | 24 | 24 correct solid directed relations |

The five dashed convergence links remain absent: Symbolic Prediction 1/2/3 and
Neural Prediction 2/3 to Mixture-of-Experts. Neural Prediction 1's solid link is
present. Both gray background panels, section titles and ellipses indicating
repetition are omitted. These counts come from source/native visual comparison,
not an independent holdout or a complete frozen annotation score.

The old p034 manual annotations mix coordinate frames (e.g. Text Embedding
x=398..464 versus source outline x=447..520). They were not edited or used to
score these new full-image claims. Do not substitute emitted counts for accuracy.

## What changed

- Region-only proposal assembly validates four source-supported fill sides
  before duplicate suppression. Inset low-contrast borders have a bounded 12px
  search. Fill-only panels cannot own contained node text or suppress children.
- Prefer a near-identical, independently observed square outline to its fill.
  Narrow vertical outlines retain the original area floor.
- Arrow direction uses a bounded endpoint window; a distant elbow is not a head.
- Multi-owner recovery is restricted to a unique straight-ray hub, straight
  shaft evidence and independently arrowed leaves. Bent/ambiguous branches abstain.
- OCR can retry overlapping snippets with a fixed interior-color border, and a
  failed tall crop with CCW rotation. Confidence and two-scale agreement stay
  unchanged. Observed vertical text is emitted as editable rotated text.

## Failed arms preserved

- First fanout criterion used the entire shortest pixel path; triangular heads
  caused 4.6..7.4px off-center paths. It abstained. The shaft-only model is a
  separate exploratory arm, not a pass under the first threshold.
- Cohort revision 1 lost five genuine contrastive nodes because quantized fill
  bounds are inset from pale borders. The initial outward-band probe then let a
  gray panel suppress six children. Revision 2 fixes both without lowering the
  closure support or confidence thresholds. Earlier artifacts remain intact.

## Validation boundary

Existing five natural ROI regressions retain 23 matched objects, 15 directed
links and zero extra objects. OCR now emits 15 labels (the original BLIP spacing
error remains; two previously blank reasoning labels are recovered). The large
negative source is still rejected by the 4MP bound, not classified as negative.
Eleven synthetic count/abstention contracts pass; they are not real-image accuracy.

Native step-3 edit probe: all 24 connectors retain owners/sites through text
edit, owner move/resize and save/reopen. Original file unchanged. Explicit reroute
changes sites, as before. This proves editability, not automatic overlap repair.

No remote publication, human edit-time measurement or holdout promotion is
authorized by these diagnostic results.

## Completion evidence

- Full suite: **279 passed**, 9 existing warnings; 11 new R5 counterexample tests.
- All seven final complex-cohort PPTs open in native PowerPoint. Object IDs and
  endpoint owners match emitted scenes; zero raster objects. Final primary edit
  probe repeats the 24-binding preservation check against the exact final PPT SHA.
- Contrastive revision-1 regression is recovered to its original five genuine
  large nodes. Dark-transformer removes the false orange panel and gains two
  correct local links. Blue links, nested-panel ownership errors and original
  input's false database ellipses still prevent general complex-image approval.
- Built and separately target-installed `image_to_editable_ppt-0.3.0-py3-none-any.whl`.
  Installed runtime file hashes exactly match final cohort runtime hashes. The
  isolated installed CLI reconstructs the scaled chain without importing torch.
  Wheel SHA256: `b6f35fab939d7d8be428b0cafa58f52444a39d04f47a98c3c0cf493ef6ee0376`.
- Tracked evidence: `benchmarks/region_complex_r5_evidence_v2.json`, both input
  revision manifests and `region_complex_r5_visual_review.json`. The graph audit
  checks 24 source-named solid relations, separately from rendered object counts.
- Final artifacts: `artifacts/region-complex-r5/final-v2/{run,renders,review,edit-probe}`.
  Primary output: `run/reasoning-full.pptx`; native comparison:
  `review/reasoning-full-comparison.png`; package: `../package/dist/`.

Replay into **new** output directories (frozen manifests/artifacts refuse overwrite):
`tools/run_region_r5.py`, `tools/run_region_production.py`,
`tools/validate_region_synthetic.py`, `tools/render_pptx_via_powerpoint.ps1`,
`tools/probe_region_runtime.ps1`, `tools/verify_region_package.py`.
`tools/summarize_region_r5.py` asserts source/runtime/package SHA agreement,
named graph correctness, native edit preservation and regression contracts.

## Decision

The primary drawing is a useful, visually verified editable partial reconstruction.
The production code path can expose this bounded improvement; complex-diagram
conversion in general is still not approved. Human acceptance of this particular
draft and measured editing-time savings are distinct from technical readiness.
