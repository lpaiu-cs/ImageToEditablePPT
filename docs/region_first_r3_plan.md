# R3 continuous research campaign

2026-09-08. User requests a plan and uninterrupted execution through useful research stages.
Start c35a670. Do not stop after merely proposing a next experiment; execute R3 tracing,
inspect real images, freeze its result, then execute the needed fixed-path emission probe.
Continue safe local implementation/verification without requesting routine confirmations.
Stop only at completed campaign evidence or a genuinely new authority/data requirement.
No holdout, paid services, training, remote push, production promotion or human-time claims.

## Stage T: frozen connector-tracing diagnostic

Six consumed R0/R2 development sources and ROIs. Inputs: R2.1 combined scenes and R0
oracle_boxes scenes, source and scene SHA bound before run. Do not change shapes or labels.
Four arms per source (24 PPTX, shared normalize_only writer):
- A baseline: frozen selected scene and its existing connectors.
- B strict_trace: trace source strokes with all selected nodes as terminals/obstacles.
- C transparent_gap_trace: same selected shapes, but shared-border gap candidates with
  inner near-white median >=225 and uniform fraction >=0.95 are neither terminals nor
  occluding masks. They remain emitted objects, so this is NOT a claimed object improvement.
- D oracle_trace: same tracer with frozen manually supplied R0 boxes/roles; not automatic
  detection quality. No ground-truth labels or expected edges enter tracing.

Tracer frozen before execution: ROI RGB grayscale <110 foreground; mask node bboxes
expanded by p=max(2,round(0.005*min(ROI width,height))). Containers are not endpoints;
remove their border bands only, leaving child interiors accessible. Bounded axial close
of length min(9,2p+3), then 1px dilation, may reconnect tiny mask/antialiasing gaps; no
long-distance straight-line guessing. Connected components touching exactly two distinct
eligible owners produce a path; components touching >2 owners are ambiguous and omitted.
Attachment tolerance max(5,3p). Shortest 8-neighbor foreground path between nearest contact
pixels, simplify with RDP epsilon max(1,0.002*ROI short side). Preserve observed path points,
project first/last contacts to nearest owner side within tolerance; no new owner pairs without
a continuous observed component. Record masks, rejected components, support and attachments.
Arrow evidence: compare component cross-section widening at path ends with shaft widths;
terminal band first/last 35% of path, shaft reference 25th percentile width. An end must
have width >=1.6x shaft and >=shaft+2, and exceed opposite end by factor1.35; otherwise line.
No forced arrow just because the target annotation expects direction. Cap cross scan radius20px.

Tests: blank no-path negative, straight arrow/undirected line, one-bend arrow, container
crossing, >2-owner ambiguity, dropped/transparent gap owner retained as shape, no label
semantics. No cutoff tuning within run1; failures frozen before any named follow-up.
Report selected vs oracle topology, direction, wrong edges and preserved objects/labels.
View intermediate mask/route overlays before proceeding to native render assessment.
Existing writer may distort bends/sites: keep source-path finding separate from PPT quality.

## Stage E: fixed-path emission, conditional on recovered paths

After T is frozen, preregister emitter-only protocol based on actual recovered scene.
Try one native connector with source-supported path and explicit owner sites, no raster,
hidden anchors, unbound workaround or multiple segment objects per logical connection.
Compare identical scene with original writer. Inspect actual PowerPoint render, move/resize,
save/reopen and explicit reroute stress. Preserve any failure independently of T.
If native representation cannot preserve path semantics, document that boundary rather than
calling independent unbound segments equally editable. Do not alter frozen R1 results.

## Campaign handoff

Freeze code/run SHA, tests, source/mask/path/PPT/render evidence and visual notes per stage.
Commit both useful findings and failures. State best demonstrated partial pipeline and its
remaining unsupported cases; propose next research only after completing these stages.
