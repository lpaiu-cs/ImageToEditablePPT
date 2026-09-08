# v0.2 region conversion: production integration and evidence boundary

2026-09-08. User authorized research through production integration. Delivered an
explicit-ROI conversion feature in the existing CLI and a maintained runtime package,
not a general reconstruction quality certificate or promotion of the failed ML model.

## Delivered

`image-to-editable-ppt-convert image.png -o output.pptx --region x0 y0 x1 y1`

Coordinates are normalized 0..1 against source pixels. A user-provided scope is required;
use 0 0 1 1 only when the input is already the desired diagram region. No ML checkpoint
or PowerPoint installation is needed for conversion. Optional OCR uses the existing
RapidOCR backend. `--no-ocr` produces structure only; absent/erroring OCR leaves labels
blank. Existing default ML/v3 behavior and its bundle acceptance checks remain unchanged.

The production `image_to_editable_ppt.region` package does not import research modules or
load frozen scenes, annotations, object IDs or expected edges. It detects source geometry,
selects conservative candidates, traces source-supported connections, validates identity,
recovers stable labels, fits supported native presets and emits one connector per relation.

Each result has a `.region.json` sidecar containing source/output SHA, image coordinates,
objects/paths, OCR and rejection reasons, counts and limitations. Inputs are byte-snapshotted
before decoding so later input mutation cannot corrupt provenance. Transparent backgrounds
are composited over white. Output pairs are staged and published without overwriting an
existing PPTX/sidecar, including a tested concurrent-output creation race. Hard-link support
on the destination filesystem is required; publication errors fail rather than overwrite.

Limits: 64MiB input file, 16MP source, 4MP ROI, minimum ROI 16x16 source pixels, at most 300
geometry candidates. Oversized input fails explicitly; recognition is not silently resized.
Output fits the long side to 768 units and pads an exceptionally short slide dimension to
128 units to remain usable by PowerPoint. No automatic non-overlap layout is performed.

## Measured result

| Check | Result and scope |
|---|---|
| Consumed natural diagram ROIs, actual CLI | 5 inputs; 23/23 target objects, 15/15 directed relations, 0 extras |
| Large natural negative plot | Rejected before conversion by 4MP bound; **not** a successful negative classification |
| R4 frozen-scene ablation | All 6 files rendered; extras 3 to 0 while 23 objects / 15 relations retained |
| New synthetic development cases | Final 11/11 node/link count and abstention contracts; not a general direction score |
| Retained natural labels | 13 emitted: 12 match reference, 1 BLIP spacing error; 4 target labels omitted |
| Native initial geometry | Max endpoint error 0.000102pt; no added helpers or raster objects |
| Preset approximation | Max sampled path deviation 2.361122 normalized px, within frozen 4px ceiling |
| Actual PowerPoint edit/reopen | 2 owners / 6 links, binding sites and arrow ends retained; max error 0.000281pt |
| Explicit reroute | Site preservation **fails** in both samples; owner identities remain |

All five natural outputs and eleven synthetic outputs were rendered by PowerPoint 16.
Five source/R3/production sheets, both edit/reopen/reroute sheets, and the eleven-case
synthetic contact sheet were directly inspected. The native XML audit independently
compared source-derived expected coordinates, IDs, labels, owner bindings and arrow ends.

![Attention comparison](../artifacts/region-native-production/review-v2/mixed-attention-initial.png)

![HEVC comparison](../artifacts/region-native-production/review-v2/serial-hevc-initial.png)

Attention loses the two false faces and heavy shadowed arrows while retaining four distinct
attachments. HEVC word ordering improves. PERCEIVE's fill fragment disappears, but its two
unstable lower labels are blank and the final bounded fit simplifies the left bend to a
slightly oblique route. Reasoning also loses two unreliable labels. BLIP retains a spacing
error (`textdecoder`) despite scale agreement. These are honest partial outputs, not evidence
that OCR is solved or correction time is necessarily lower for every case.

![PERCEIVE tradeoff](../artifacts/region-native-production/review-v2/cogbot-perceive-initial.png)

After the prescribed downward move/resize, nodes overlap and connectors become oblique.
False faces no longer appear, and endpoints follow their owners, but automatic layout is
still absent. Explicit RerouteConnections moves attachment sites by up to 64.636428pt in
Attention and 44.860404pt in PERCEIVE. These failures are neither patched after native edits
nor counted as successful site preservation.

## Failed attempts retained, not hidden

1. Synthetic-v1: 10/11 contracts; a 1.5x chain lost its two links because outer thick-border
   pixels remained outside fixed masks and joined the three owners into one component.
2. R4.1 (bd6d19c): observed-ink masks fixed that synthetic case (11/11) but regressed natural
   Attention to 0/4 links. Enlarging a traversed container border erased more ink than the
   frozen closing kernel could bridge. This attempt failed the joint promotion gate.
3. R4.2 (b8bf361): distinguish terminal NODE masking from traversed CONTAINER bands. Adaptive
   observed-ink masking applies only to nodes; container bands keep their frozen base pad.
   Both original natural and synthetic contracts pass. No named-sample branch or threshold
   retuning was introduced. Thick ambiguous container crossings may still abstain.

Protocols were committed before their respective executions. Old outputs and failures remain
under run1/run2/run3 and synthetic-v1/v2; final source conversion is run4, synthetic-v3 and
edit-probe-v2. The input snapshot/transparency hardening in 13aa0c8 was subsequently covered
by direct regression and installed-wheel checks; the geometry/tracing/emission code is the
same as run4. R0-R3 and Phase15/16 frozen files/implementations were not rewritten.

## Verification and installable artifact

- Full regression: **268 passed**, 9 existing dependency/worker warnings.
- New runtime tests cover identity counterexamples, geometric OCR order, confidence/scale
  abstention, invalid/oversized ROI, unsupported paths, native site geometry, no-effects,
  CLI conversion/empty output, no-overwrite race, thick-border/parallel-line separation,
  research-import exclusion and decoded-input hash/transparency.
- A v0.2.0 wheel was built with `pip wheel --no-deps --no-build-isolation`, installed into a
  separate target directory, and invoked in an isolated Python process. The imported module
  path was asserted inside that installation; all installed runtime file hashes matched the
  source. Its CLI converted the formerly failing thick chain into 3 nodes/2 connectors without
  loading torch. This uses the host's existing base dependencies; it is not an offline clean-OS
  dependency-install proof.
- Latest wheel: `artifacts/region-native-production/package-v2/dist/image_to_editable_ppt-0.2.0-py3-none-any.whl`.
  Exact hash and executed command outputs: `artifacts/region-native-production/package-v2/verification.json`.
- [Combined campaign evidence](../benchmarks/region_native_evidence_v1.json),
  [visual review](../benchmarks/region_native_visual_review_v1.json),
  [packaging evidence](../benchmarks/region_native_package_v1.json).

No external package publication, push, deployment, canonical-model promotion, independent
natural-image holdout run or human edit-time measurement was performed. The feature is usable
from the production CLI under its documented explicit-scope contract; broader acceptance
remains unproven. Future work should target independently selected diagram ROIs and measured
human corrections, not further success claims from these repeatedly consumed samples.

## Local replay

```powershell
rtk proxy .venv/Scripts/python.exe -m image_to_editable_ppt.ml.convert_to_pptx diagram.png -o new-output.pptx --region 0 0 1 1
rtk proxy .venv/Scripts/python.exe tools/run_region_production.py --output-dir artifacts/region-native-production/new-run
rtk proxy .venv/Scripts/python.exe tools/validate_region_synthetic.py --output-dir artifacts/region-native-production/new-synthetics
```

Use new output names. Native PowerPoint probes refuse existing PowerPoint processes, never
overwrite the source presentation and close only their own application/presentations.

## Subsequent complex-input check

The unchanged v0.2 runtime was subsequently tested on harder whole diagrams. Seven native
renders expose false large uniform-fill objects, misplaced text and missing colored/junction
connections. The complex-image visual standard is not met; this does not erase the narrower
ROI gain above. See [complex validation](region_complex_validation_results.md) for the frozen
inputs, actual source/output comparisons and the distinction between omission and false geometry.
