# R6: cross-diagram evidence, not more image-specific repairs

User approved R5 on 2026-09-08. Baseline is `80b0937`, v0.3. Preserve its
artifacts and the Phase 16 formal holdout/blocked human-time contract.

## Causal diagnosis

1. Absolute gray<110 foreground excludes bright/chromatic strokes, while dark
   backgrounds become enormous foreground components. Geometry cannot repair
   information discarded before tracing.
2. Global image-fraction object floors exclude locally clear small boxes in
   dense diagrams. Fill-only partition identity and nested OCR ownership remain
   separate failure modes; a better connector fitter cannot resolve either.
3. Two-owner connected components do not encode general junctions; R5 solves
   only a unique straight fanout. Dashes, curved paths and crossings need explicit
   continuity evidence. Do not invent complete graphs from touched owners.
4. Development-only visual improvements cannot establish broad generalization.

## Registered work and promotion gates

- First arm: polarity/color-aware thin-stroke evidence. Keep original dark
  strokes on light backgrounds, add source-supported chromatic strokes, and use
  locally contrasting bright strokes on dark backgrounds. No source-ID branches.
- Test independent synthetic hue, polarity, width, layout and disconnected-line
  variants, including negative unowned marks. Retain old ROI 23 objects/15 edges,
  R5 reasoning 24 nodes/24 labels/24 solid relations and existing 11 contracts.
- Re-render all existing complex cases. Numeric increases require owner,
  direction and original/native visual verification, not count-based approval.
- Reserve a deterministic pool slice BEFORE runtime changes: up to 8 caption-
  suggested diagrams and 4 non-diagrams outside both Phase 16 splits, source-group
  disjoint from them. Sort by source SHA; no replacement based on outputs. This
  pool had historical source-sheet exposure, so it is R6-reserved transfer
  evidence, NOT a historically unseen or formal holdout. Never tune after opening
  its candidate results. Oversized cases remain explicit resource rejections.
- After candidate freeze, run baseline and candidate on the reserved slice once,
  visually inspect all outputs and report failures as well as improvements.
- If broader generalization does not pass, keep the narrower validated advance
  with an explicit scope boundary; do not call generalization solved.
- Nested-owner/small-object recovery is a separate arm and must be registered
  before implementation. No automatic gate relaxation or repurposing holdout.

## Development findings before transfer evaluation

Color evidence recovers seven blue-flow routes; native fitting emits five and
rejects two. Thick arrowheads are also truncated by the old fixed 41px transverse
sample and short endpoint window. Scale these observations from measured shaft
width, capped at 80px; do not lower the head/shaft ratio. Add thick line/elbow
negative controls. This is arrow evidence, not proof that all seven routes emit.

Oracle-owner white-on-black tracing passes but end-to-end detection returns four
wrong owners and no links. Add a separately gated geometry-polarity arm: invert
the outline-analysis image only when its median is dark AND all four border
medians are dark. Keep actual RGB for fill, text and style. Test the end-to-end
chain and uniform dark negative; mixed-polarity panels remain out of scope.

Colored-outline/role arm (before transfer): p058 has 14 legacy dark-outline
proposals but 30 closed multichannel-edge proposals. Add only otherwise-missing
closed contours with chromatic boundary support on every side, retaining the
global area floor. Do not add gray background panels. Detect header dividers
from a long continuous edge, not a broad filled dark row. Existing containment
uses a child's center only; require its whole box to be contained instead.
The first dark-field arm made all 11 colored nodes containers because uniform
inverted fills looked like dividers; preserve this failure and test the cause.
