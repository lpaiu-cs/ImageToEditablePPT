# Region-first R0: causal diagnostics, not acceptance
Date: 2026-09-08. Base: bf86a84b7d76eda839c03a12d748fb396a2f2d2b.
User authorized a new research line after the first-principles review.

## Branch and frozen evidence
- Local main fast-forwarded from 9fe246b to origin/main fe2fc99.
- Former claude/charming-euler-d8be44 preserved as archive/phase16-baseline.
- Annotated tag archive/phase16-baseline-bf86a84 preserves its exact tip.
- New branch: codex/region-first-diagnostics. PR #6 is open; remote branch and PR remain untouched.
- Phase 15/16 code, annotations, baseline artifacts, lock, NO-GO and calibration contract remain frozen.
- This protocol supersedes Phase 16's calibration prerequisite ONLY for this separate diagnostic line.
  Human timings are still required for claims of human time saved. No weighted time score here.

## Correction to the previous evaluation
p063 and p040 are mixed figures with clearly convertible local structures.
Their frozen whole-scene non_diagram annotations are unsuitable for partial-recovery evaluation.
R0 records newly reviewed local targets; it does not relabel or rescore the old formal benchmark.
The remaining 62 labels have NOT been revalidated. No claim that the full dataset is now repaired.

## R0 sample and information contract
Six source-bound development scenes; no new holdout access. Five previously consumed Phase 16 dev
images and input.png. Positives are LOCAL, intentionally partial targets, not full-figure ground truth.
Unmatched output outside the selected ROI is unassessed, except explicitly excluded raster/chart regions.
The negative is a chart: no convertible target, full-scene exclusion.

A full_cv: original native RGB -> frozen visual_geometry -> frozen visual_connectors -> bounded OCR -> writer.
B roi_cv: same code, but a manually chosen coarse ROI (native pixels, no rescale).
C oracle_boxes: same ROI, but manually supplied source-observed boxes AND roles.
C receives no target labels, connector pairs, or routes; OCR and connections remain automatic.
D roi_cv_mixed / oracle_boxes_mixed, if opened AFTER R0 observation: only mixed-role endpoint
enumeration changes. Must preserve the first run and record a new protocol amendment.

Existing frozen ML PPTX renders are contextual baselines, NOT a controlled A/B against A.
A removes the model/gate and changes resolution; only B vs A and C vs B isolate the stated intervention.
None of A/B/C is a production model or evidence of fully automatic product quality.

## Fixed shared settings and measurements
- Native source coordinates, exact source SHA check; normalized annotations mapped to native coordinates.
- Frozen CV thresholds; no sample-specific thresholds, OCR strings, or output route templates.
- Node OCR crop inset 3 px, snippet confidence >= 0.90, no language-model repair.
- Object matching: one-to-one IoU >= 0.50; report matched targets, missing targets, role errors,
  unmatched output intersecting ROI, and explicit excluded-region hits (intersection/output area >= 0.5).
- Relations: directed endpoint pairs matched through object correspondence, deduplicated; also report
  raw emitted pair count and unmatched/incorrect local edges. Multiple observed strokes between the
  same owners cannot be represented as distinct relations in this metric; flag separately in visuals.
- Labels: whitespace-normalized exact match only on annotated labels; report missing versus wrong.
- These are raw diagnostic counts, not calibrated edit time. Manual inputs are not scored as automatic recall.
- Export native PPTX, inspect OOXML binding/raster counts, render with actual PowerPoint, view both
  source overlays and rendered result. No pass solely from counts. No final user acceptance inferred.

## Decision order and stop
1. Freeze source/ROI/target manifest and protocol in Git BEFORE running algorithm outputs.
2. View target overlays BEFORE conversion; annotation errors get a versioned correction before experiments.
3. Run A/B/C once. Compare local useful structure, wrong objects, links, labels and native bindings.
4. If ROI alone fails, do not spend a training cycle on scene gating. If oracle boxes help, focus on
   object/role proposals. If oracle boxes still lose links, isolate attachment/path extraction next.
5. At most one bounded mixed-role follow-up in this R0. Do not keep tuning six examples until success.
6. Report failures as failures; preserve existing production default and propose the next falsifiable test.

## Pre-conversion target review
All six native-source target overlays in artifacts/region-first-r0/targets-v1 were opened
and visually inspected before conversion on 2026-09-08. The boxes delimit the intended
23 local objects and 15 directed relations. No algorithm output was used to revise these targets.
This is an assistant review, not human acceptance. Sources, current target coordinates and ROI
boundaries were accepted for this coarse IoU diagnostic; they are not pixel-perfect annotations.
Containers have no target OCR label in R0; node label accuracy is evaluated separately.
