# Next architecture experiment: accepted objects before rendering

Status: proposed next research design, NOT implemented or validated by R6.
The R6 transfer failure is preserved; those sources are now consumed development
evidence and cannot be reused as an untouched acceptance set.

## Required pipeline boundary

Source -> coarse region roles -> local candidate proposals -> object identity /
ownership -> accepted owner graph -> observed stroke-piece graph -> native emit.

Keep `candidate` and `accepted` scene types distinct. OCR and owner masking may
consume only accepted owners, not every closed contour.

## Minimal experiment, in order

1. Create a NEW source-pixel annotation schema outside the Phase16 lock. Annotate
   diagram node, container, connector/port, nonstructural graphic and unknown;
   include parent ownership and exclusion masks. Audit original pixel frames and
   store every view-to-source transform. Never use display-scaled coordinates as
   source coordinates. R5's old mixed-coordinate annotation remains frozen.
2. Evaluate proposal ceilings independently: can local-scale proposals recover
   missed small nodes at fixed false-positive count when semantic/ownership roles
   are supplied as an oracle? Can oracle owners restore traced core relations?
   If not, fix the representation before training a classifier.
3. Train/calibrate a patch-plus-context structural-role model only on a newly
   declared development slice; model output is a reject/unknown decision, not
   permission to invent geometry. Compare against the R6 contour-only baseline.
   The release must support backend-unavailable/uncertain abstention explicitly.
4. Build a stroke-piece graph with endpoint/head evidence, color/style continuity
   and junction uncertainty. Test broken/dashed pieces, crossings without joins,
   shared fanout and compound cylinders independently. Do not pair all owners.
5. Evaluate native representability separately from graph correctness. A correct
   relation omitted by preset fitting is an emission limitation, not a tracing FN.

## Acceptance protocol

- Freeze source-group-separated development/calibration/acceptance manifests
  before outcomes. Obtain a genuinely fresh source batch; R6 reserved cases are
  no longer fresh. Do not consume Phase16's locked holdout as a shortcut.
- Report node/role precision, proposal recall, exclusion-region violations,
  parent/label ownership and directed relation precision/recall separately.
- Zero photo/logo reconstruction violations in the declared acceptance slice is
  a hard gate. Incorrect large objects or cross-node label ownership fail visual
  approval even if aggregate recall rises.
- Preserve R5's approved drawing and five-ROI directed relations. Native edit /
  reopen remains a separate gate. Declare coverage and unsupported families.
- Choose numerical recall/precision thresholds on development BEFORE acceptance;
  no post-result threshold rescue or omitted failed cases.
- Human editing-time savings still require actual timed human operations; do not
  claim that pixel metrics or programmatic movement prove reduced human effort.

No claim of implementation, model quality, trained weights, new data acquisition
or general production approval is made by this specification.
