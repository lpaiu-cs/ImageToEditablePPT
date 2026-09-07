# R2: fixed ROI candidate selection diagnostic

2026-09-08. Parent freeze ef0be7f. User approved R2. Preregister before result execution.

## Population and boundary

Use all six already-consumed R0 development samples, **roi_cv for every sample**.
This differs from R1's selected oracle scenes. Input is the complete frozen R0 ROI scene,
source RGB and coarse ROI, with scene/source hashes bound in a new manifest.
No detector, OCR, connection recovery or target annotation changes. No new holdout.
No labels, target IDs, expected edges or semantic text content enter the selector.
The source-provided candidate source/kind/bbox and frozen connector incidence are allowed.

## Fixed arms

A all_candidates: original ROI scene.
B deduplicate: collapse near-concentric observations across roles (fill/outline/ellipse).
C evidence_select: B plus local source-evidence rejection below.
All arms use R1 normalize_only output (unchanged production writer, 768px-wide slide).
Do NOT use R1 custom connection sites: R2 has no endpoint intervention.
Retained primitive geometry, role, label, connector path and direction are byte-equivalent
scene fields. No merged geometry, OCR label transfer, retyping, endpoint remap or new paths.
Remove connectors only when an owner is removed; report that loss explicitly.

## Rules frozen before implementation

- B: duplicates require intersection/smaller >=0.90, area ratio >=0.50, all four bound
  differences <=0.16 of larger width/height, center differences <=0.08. Greedy suppression
  against an actual representative, not transitive union (nested chains must not collapse).
  Prefer existing connector incidence, then closed ellipse, closed outline, uniform fill;
  then node role, larger area, confidence and geometry. IDs/labels do not affect preference.
- C empty gap face: near-white uniform inner region (6% inset, median RGB min >=225,
  fraction within max-channel distance 24 from median >=0.985), no substantially smaller
  candidate inside, and top/bottom (or left/right) align to **different, wider** candidate
  boundaries within max(3px, 0.04 of face short side). Both bounding candidates span the face
  and are >=1.5x wider in that axis. Blank standalone boxes are not rejected.
- C discontinuous envelope: closed-outline candidate, excluding corner 10%, with at least
  two boundary traces having an unsupported continuous gap >0.15. Trace band is max(2px,
  0.025 of short side), clipped to ROI; support pixel min-channel <200. This may fail on
  legitimately occluded boxes: record lost targets rather than relaxing after observation.
- C scatter-like region: inner 6% crop, reduced to longest side <=512px, color mask
  max-min RGB >=50 and max RGB >=100. At least 20 disconnected colored components of
  area 1..0.005 crop area, collectively >=0.01 crop area. Reject candidate, and any candidate
  >=95% contained within that rejected candidate. This is local texture rejection, NOT a
  general chart classifier; monochrome charts/dense graphics are expected limits.
- No threshold tuning within R2 run1. Any follow-up is separately named after freezing failure.

## Checks and stop criteria

Synthetic tests: true nested boxes and standalone empty nodes retained, fill/ellipse
duplicates removed, touching boxes distinct, duplicate chain not transitively merged,
blank shared-border face removed, disconnected envelope rejected, scatter locally rejected
without deleting an adjacent diagram, label/ID changes do not change selected geometry,
retained labels unchanged, dropped-owner connector omitted rather than rebound.

Report per arm/sample target matches, extra local objects, missing targets, role errors,
retained/lost frozen connections, labels, removed candidate IDs and reason/features.
"Deletion burden" means count of unmatched objects, not measured human seconds.
Primary development gain: fewer extra objects with no matched-target loss on any positive
sample and no decrease in matched frozen edges. Negative sample reported separately.
Failure in any positive case prevents full C promotion, even if aggregate extras decrease.

Generate 18 PPTX; render in real PowerPoint, inspect all six source/A/B/C ROI sheets directly.
Also inspect intermediate source candidate overlays before deciding the next direction.
Freeze protocol, code execution SHA, source/scene SHA, results, PPTX/render SHA and visual
notes. Keep R0/R1/Phase15/16 evidence and production defaults unchanged. R2 is not product
acceptance or human-time validation. Finish and commit the diagnostic including failures.
