# R4 to production-facing region conversion

2026-09-08, baseline edffcd4. User authorizes continued research through production
integration while away. Preserve frozen R0-R3 and Phase15/16 evidence and implementations.
No remote publication, paid services or human-time substitution. No holdout tuning.

## Scope and ordered gates

1. R4 object identity: six consumed R3 source/scene hashes unchanged. Test shared-boundary
   gaps with explicit borrowed border evidence, not a lowered whiteness cutoff alone;
   reject uniform-fill fragments only when their color matches their enclosing container
   and their perimeter has no independent contrast. Protect ordinary near-white boxes,
   valid shared-boundary boxes, labeled boxes and small colored nodes with synthetic
   counterexamples. Require all 23 prior targets and 15 directed edges retained. Do not
   infer that every removable extra can safely be rejected; retain ambiguity and report it.
2. Text: source-only, node-bounded OCR. Use geometric reading order and require agreement
   between original and scaled crop plus per-snippet confidence >=.90. Any unreliable
   whole label is omitted with reason. No target strings/semantic correction. Containers
   do not gain guessed titles. Test ordering jitter, disagreement, low confidence, blank
   and unavailable backend. Preserve structures when OCR fails.
3. Emission: supported native presets + explicit owner sites. Neutralize inherited effects
   and set native arrow/line style explicitly. No helper objects or raster. Reject unsupported
   individual routes with explicit diagnostic (retain correct objects); no silently distorted
   route fallback. Fit <=4 normalized px as R3-E1, endpoints <=1pt in PowerPoint.
4. Production implementation: a maintained package with no research-module imports and a
   user-facing `--region x0 y0 x1 y1` mode in the existing conversion CLI. ROI coordinates
   are normalized to original image; explicit human scope, not automatic diagram discovery.
   Keep existing default ML/v3 path and model acceptance gates unchanged. New region mode
   needs no checkpoint; supports --no-ocr/--no-style, bounded image sizes, input validation,
   observable abstention, structured diagnostics, atomic output and overwrite protection.
5. Verify end-to-end on six consumed development sources from image pixels, not loaded
   selected scenes, plus new synthetic positives/near-miss negatives. Inspect actual native
   PPT renders, initial/ordinary edit/reopen/reroute. Run full regression, package/CLI smoke,
   empty result and invalid input tests. Update README/plan/API usage, freeze and commit.

## Production claim boundary

Deliver a tested, accessible conservative region conversion feature, not a canonical ML
model or a general quality certificate. ROI choice, partial omission, OCR agreement limits,
unsupported routes, explicit reroute changes and missing human-time calibration remain
user-visible. If a gate fails, record the failure before a separately named follow-up;
integrate only defensible behavior and never relabel dev performance as holdout acceptance.
