# Production validation continuation

2026-09-08 after clean 6a0688d source-to-CLI run1. Five diagram inputs retained 23/23
targets, 15/15 edges and zero extras. Large negative-plots ROI exceeded the documented
4MP processing bound and was rejected before output. This is **not** a successful blank
negative classification. Preserve run1 and record rejection in run2; no limit relaxation,
resizing of this sample or data-dependent rescue. Run2 changes only evidence-runner error
recording, not the production algorithm.

Supplement with new deterministic synthetic cases: horizontal chain at 0.75/1/1.5 scale,
vertical chain, elbow pair, undecorated blank box, blank canvas, seeded scatter plot,
unowned arrow, ambiguous three-way branch and two nearby unconnected boxes. OCR disabled
to isolate structure. Freeze generator and expectations before execution, retain failures,
inspect native renders; no new cutoff tuning in this validation run. These are development
counterexamples, not independent natural-image or holdout acceptance.

Native edit probe uses the same Attention/PERCEIVE transformations and stages as R3-E1.
Audit actual XML endpoints, owner identities, site indices, absence of helper/raster objects,
and render outputs. No layout/reroute success inferred from connection flags alone.
