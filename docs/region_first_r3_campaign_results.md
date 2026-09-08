# R3 campaign: tracing gains survive native initial output, with explicit edit limits

2026-09-08. User-approved continuous campaign completed: source tracing, exact-path
native emission attempt, separately preregistered native-preset approximation, visual
inspection, real PowerPoint editing, evidence audit and regression tests. No production
promotion. This report does not replace any frozen R0/R1/R2 or Phase15/16 verdict.

## Outcome

On the same six consumed development ROIs, correct directed relations rose from 9/15
to 15/15, with wrong/unresolved relations 4 to 0. All 23 target objects remain, alongside
the same three extra objects. This is a topology gain, not an object-detection gain.
The oracle-box arm recovered only 12/15; approximate manual boxes are not an upper bound.

The old writer visibly destroyed useful source paths: Attention arrows converged at
one target location and PERCEIVE bends became diagonal chords. The new experimental
preset writer preserves distinct attachment sites and approximates supported paths with
one native connector per relation. All six outputs opened/rendered in PowerPoint 16.0.
The five nonempty scenes contain 26 shapes and 15 connectors total, no pictures or hidden
helper anchors. Labels, shape geometry and owner bindings were audited against frozen scenes.

![Attention: source, old writer, new native preset](../artifacts/region-first-r3e1/review-v2/mixed-attention-initial.png)

![PERCEIVE: source, old writer, new native preset](../artifacts/region-first-r3e1/review-v2/cogbot-perceive-initial.png)

These are directly inspected native renders, not source overlays or a numerical similarity
claim. Attention's four arrows are visibly separate; PERCEIVE's left L route returns.
The right PERCEIVE corner is approximated by a short diagonal, not exactly reconstructed.
Maximum sampled symmetric path deviation is 2.361122 normalized pixels (1.770842pt), below
the separately frozen E1 limit of 4px. Initial endpoint error is at most 0.000102pt.

## Failure retained: E0 exact custom connector

E0 serialized one custom polyline per native connector and retained its exact vertices.
The ZIP/XML and coordinate checks succeeded, but **all five nonempty files failed to open
in PowerPoint**, error 0x80070570. The empty negative file opened. The exact representation
is rejected by this PowerPoint instance; schema expressibility is not native compatibility.
No universal claim about every possible custom geometry encoding follows from this probe.

E1 was preregistered after recording E0 failure. It uses native line/bentConnector3 presets
within a bounded approximation error. It is not an E0 pass or a post-result relaxation of
E0's exact-vertex requirement. Failed files and their per-file native errors remain saved.

## Native editing: attachment pass is not automatic layout quality

Both probes edit text then restore it, move one owner +12/+18pt, resize width/height by
1.25/1.20, save, close and reopen. Originals remain unchanged. The audit computes expected
endpoints independently from source attachment ratios and the prescribed owner transform.

| Probe | Endpoint error after edit/reopen | Explicit reroute error | Original sites after reroute |
|---|---:|---:|---|
| Attention target owner | 0.000168pt | 64.636428pt | changed |
| PERCEIVE source owner | 0.000281pt | 44.860404pt | changed |

Initial roundtrip preserves fitted routes within 1pt. Ordinary move/resize/save/reopen
preserves owner identities, site indices and arrow ends. No added or missing objects,
raster substitution, or unrelated owner movement was found. Explicit RerouteConnections
keeps owner identities but changes sites and fails spatial attachment preservation.

The moved objects overlap other objects under the prescribed downward movement. Native
connectors become oblique and bends shift; the rendered layout is **not satisfactory**.
This probe establishes attachment mechanics only. It neither measures human edit time
nor demonstrates automatic collision avoidance or uniformly good post-edit layouts.
Attention's two false gap boxes become especially visible after moving the large target.

![Attachment versus layout and reroute stress](../artifacts/region-first-r3e1/review-v2/mixed-attention-edit.png)

## What remains fundamentally unresolved

1. Object identity: two Attention gap faces and one PERCEIVE fill fragment remain emitted.
   Ignoring them as trace obstacles was useful, but they still cost edits and can be exposed
   by movement. They must not be counted as correct objects just because initially unobtrusive.
2. Text reliability: HEVC's third label has visibly incorrect OCR word order; source external
   labels are omitted. Editable text is not necessarily trustworthy text. Typography is small
   in BLIP and differs elsewhere; PERCEIVE label content also differs from source.
3. Output style: inherited theme-like connector shadows, heavy arrowheads, missing outlines
   and rounded-corner differences remain. The emitter comparison deliberately froze styles.
4. Geometry coverage: two-owner connected components only; ambiguous branching/crossings
   are omitted. Colored strokes, long occlusion and imperfect masks are unvalidated. E1 only
   supports paths that fit its bounded preset family; it rejects unsupported scenes rather
   than silently splitting a relation into helper segments.
5. Evaluation: all six samples and ROIs were repeatedly consumed. No independent accuracy,
   full-image automatic-region success or human-time benefit has been established.

The supported diagnosis is now narrower and actionable: source path support and native
attachment preservation were separate bottlenecks, both improved locally. Further connector
count tuning alone will not remove false shape objects, OCR mistakes or edit-layout costs.

## Next research order, not a production rollout

First freeze a separate object-identity experiment against the three surviving extras with
near-white valid-box counterexamples; do not delete every near-white/shared-edge region.
Require 23/23 existing target preservation and inspect outputs after owner movement as well
as initially. Separately suppress untrustworthy OCR instead of confidently emitting incorrect
labels, and explicitly neutralize inherited effects in a distinct style experiment. Then lock
the combined candidate before evaluating new development inputs; keep formal acceptance and
human-operation-time calibration separate. Do not repair explicit reroute failures by silently
reapplying XML and calling them preserved native behavior.

## Provenance and verification

- Plan: 95accb6; tracing execution: ac7e584 (clean); trace freeze/probe protocol: 197604f.
- E0 execution: 3988336 (clean); E0 rejection/E1 protocol: 0a5fb9a.
- E1 execution: f716387 (clean). Final audit scripts are SHA bound inside the evidence ledger.
- Regression: `.venv/Scripts/python.exe -m pytest -q`: **250 passed**, 9 dependency/worker
  warnings, 13.56s. Trace, exact-path and native-preset tests contribute 9 tests.
- Six initial E1 native renders, 24 T renders, two four-stage edit probes; six comparison
  sheets and both edit sheets inspected directly. Native output files remain local/ignored;
  committed ledgers preserve their hashes, measured audits and native probe records.
- No holdout run, training, paid service, remote push, production writer change or human-time
  claim. All prior frozen implementations and evidence remain unchanged.

Evidence: [R3 tracing](../benchmarks/region_first_r3_evidence_v1.json),
[E0/E1 combined ledger](../benchmarks/region_first_r3e_evidence_v1.json),
[direct visual notes](../benchmarks/region_first_r3e_visual_review_v1.json).

Replay audit (refuses existing output paths):

```powershell
rtk proxy .venv/Scripts/python.exe tools/review_preset_campaign.py --output-dir artifacts/region-first-r3e1/review-new --visual-review benchmarks/region_first_r3e_visual_review_v1.json
```

The native COM probe likewise refuses an existing PowerPoint process and output directory;
it closes only its owned presentations/application and never overwrites source decks.
