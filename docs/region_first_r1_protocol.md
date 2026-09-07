# R1: fixed-scene native emission experiment
Date 2026-09-08. Parent R0 freeze ec1e544. User approved continuation.
All six input scenes are hash-bound R0 results, including their false objects and OCR errors.
No detector, ROI, object, text, topology or Phase 16 annotation changes.

## Interventions, frozen before execution
A: the existing R0 PPTX/render, unchanged.
B normalize_only: map source coordinates to a 768-pixel-wide (8 inch) PPT slide,
keeping aspect ratio and using the existing writer. Inference is not re-run.
C normalized_sites: same B scale, styles, text and shapes, but explicit per-owner
DrawingML custom geometry connection sites at the observed relative endpoint positions.
Each logical object remains ONE native shape with its own text frame. No hidden anchors,
group proxies, raster images or unbound-endpoint visual workaround.
Standard rectangle/rounded-rectangle/ellipse paths are permitted as custom geometry;
this changes preset-shape semantics (e.g. roundness adjustment handle), which must be disclosed.
Only source-supported straight horizontal/vertical R0 paths are tested; no new elbow recovery.
C must not change object count, label strings, endpoint owner IDs or direction flags.

## Hypotheses and checks
H1: physical-slide normalization improves readable size without changing the fixed scene.
H2: explicit normalized connection-site positions avoid fan-in collapse and remain attached
after owner move, non-uniform resize, save/reopen and an explicit reroute stress test.
Track these as separate checks, not a single aggregate success.

- Verify all source scene / old PPTX hashes before execution.
- Unit tests: scaling invariance, paths, custom site indexing, no extra shapes/raster,
  unchanged labels/owner pairs, unsupported paths fail closed.
- Generate 12 new PPTX (6 x B/C); preserve A and all R0 evidence.
- Render with PowerPoint 16.0; visually compare all six source/legacy/B/C panels.
- The primary four-arrow attention case must show four distinct attachments; readable
  arrows rather than merely four XML bindings. At initial export, source endpoint
  error <=1 normalized slide pixel, no extra shape, no dropped binding.
- PowerPoint edits: target +12pt x / +18pt y, width x1.25 / height x1.20;
  untouched sources must remain fixed. Expected endpoint uses the same owner-relative
  fraction. Save edited COPY and reopen it, tolerance <=1pt per endpoint.
- Explicit RerouteConnections is a separate stress condition: record any path/site change,
  do not quietly repair it or call it a pass when only bindings remain.
- Text-frame edit and ordinary shape move/resize must work. No human-time-saved claim.
- Record failures before choosing next direction. No sample-specific sites or text recipes:
  derive all sites solely from the frozen scene endpoints and owner geometry.

## External interface references
Microsoft DrawingML CustomGeometry documents paths, connection sites and inscribed text rect:
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.customgeometry?view=openxml-3.0.1
python-pptx warns that begin_connect is experimental and assumes rectangle point layout:
https://python-pptx.readthedocs.io/en/latest/api/shapes.html
Therefore custom indices must be explicitly serialized and verified in the real application,
not passed through a helper that silently snaps them to rectangle side centers.

## Stop
Finish this emitter experiment before reopening detection or OCR. Keep production writer,
R0 code/results and Phase 15/16 default behavior unchanged. Success here is a native emitter
feasibility finding, not automatic reconstruction or overall product acceptance.

