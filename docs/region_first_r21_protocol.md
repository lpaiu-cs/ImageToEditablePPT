# R2.1: independent filters and local rejection

2026-09-08. Parent 4eef333. User approved the proposed follow-up.
Reuse the six consumed R2 ROI inputs and target manifest, hash checked. No holdout.
Freeze this protocol before implementation/execution. Do not tune thresholds after run1.
R2 code, inputs, evidence and verdict remain unchanged. No production changes.

## Arms

Every arm starts with unchanged R2 deduplicate B. Same 768px normalize_only writer.
1. baseline: deduplicate only.
2. face_only: R2 blank shared-border-face rule, unchanged.
3. envelope_only: R2 discontinuous-envelope rule, unchanged.
4. local_scatter: old R2 component rule, but reject ONLY the examined candidate.
5. guarded_scatter: old component rule plus source-only dot shape/spread checks below.
6. combined: union of face_only, envelope_only and guarded_scatter decisions, computed
   on the same deduplicated population (no cascade or iterative reclassification).

No parent-to-child rejection propagation in ANY arm. Strong child evidence survives
even if the enclosing candidate is rejected. No labels/target IDs/expected connections
are consulted. Retained scene primitives and labels are exact original subsets. Drop
incident connectors when their owner is removed; no rebinding or recognition reruns.

## Guarded scatter hypothesis (not a general classifier)

Use the same inner 6% crop, longest side <=512, chroma mask and connected components
as R2. Old gate: >=20 small components, total small-component area fraction >=0.01.
Eligible dot component: area >=3px and <=0.005 crop area, bbox aspect 0.5..2.0,
component area / bbox area >=0.45. Require >=20 eligible dots, comprising >=65% of
the old small components. Dot centroid 10th-to-90th percentile span must be >=0.25
crop width and >=0.35 crop height. Divide vertical coordinate into eight fixed bins:
the two most populated bins together must hold <=70% of eligible dots (text-row veto).
These conservative conditions may retain dense plots or reject unusual text. Record it.
No new OCR engine, semantic label correction or sample-specific recipes.

## Checks and decision

Add realistic source-rendered synthetic counterexamples: colored title, anti-aliased
text on colored fill, genuine scatter, standalone blank box, nested valid child within
scatter parent, and shared-border face. Verify local-scatter fails on colored text when
applicable while guarded_scatter preserves it; no blanket child deletion. Verify that
unchanged labels/IDs do not influence the new filter. Synthetic behavior is not proof
of real-image quality; preserve any failed checks instead of moving cutoffs silently.

Execute 36 PPTX and source selection overlays. Inspect intermediate overlays before
acceptance, render all outputs in PowerPoint 16, inspect two four-column comparison
sheets per sample: source/baseline/face/envelope and source/baseline/local/guarded;
also inspect source/baseline/combined for all six samples.
Report per-arm target preservation, extra objects, correct/missing/raw connections,
rejection reasons and dot features. Primary gate: fewer extras than R2 B, zero target
loss on every positive sample, no correct-edge loss. Combined is a separate result;
do not pool its improvement with independent arms to hide a failure.
Existing human-time and product-acceptance boundaries remain. Freeze and commit all
results including limits. R1 reroute failure, OCR and missing elbow paths are untouched.
