# R4.1: observed border extent, after frozen scale failure

2026-09-08. Synthetic-v1 scored 10/11 exact count contracts. The 1.5x chain lost both
connectors while preserving three boxes. The tracing audit reports one three-owner
component: inner-edge detection plus fixed 2px masking leaves the outside of thick
box borders, which joins otherwise separate links. Preserve this failure as evidence.

Bounded follow-up, before execution: derive a per-owner mask extent from observed dark
border coverage outside each side. Scan at most max(4, min(12, round(.03*ROI-short-side)))
pixels; only bands covering >=60% of the central 80% of that side count as border.
Take largest supported outward offset +1, never less than the original base pad.
Scan each side contiguously; stop on the first bright band after support, or after the
base search distance without support. Never jump a bright gap to a nearby parallel line.
No attachment-tolerance, grayscale, direction or ambiguous-owner cutoff changes.
Container masking remains border-only. Record each inferred pad. This masks observed
owner ink, not arbitrary space between owners. If no band support exists, keep base pad.

Require previous five natural diagrams to retain 23 targets/15 edges/zero extras, and
all 11 fixed synthetics to meet their original contracts, particularly three-way branch
abstention. Add thick-border and close-parallel-line regression checks. R4.1 is not a
post-result relabeling of synthetic-v1. OCR still retains one BLIP spacing error despite
two-scale agreement; document that limitation, do not repair strings from target labels.
