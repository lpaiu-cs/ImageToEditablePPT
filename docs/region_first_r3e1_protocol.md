# R3-E1: native preset route approximation, distinct from failed custom-path E0

2026-09-08. E0 custom p:cxnSp polyline files fail to open in PowerPoint (0x80070570),
despite valid ZIP/XML and exact serialized vertices. Preserve that failure; do not call
this follow-up an E0 pass. Continue the user-approved research campaign.

Same six R3-T transparent-gap scenes. Allow a different, explicitly approximate contract:
one native preset line or bentConnector3, with R1 owner connection sites and bound ends.
Candidates are chord, horizontal-then-vertical L, vertical-then-horizontal L, and HVH
routes at observed interior x coordinates or mid-x, inside endpoint bbox. Fit only to
the frozen observed polyline, not source targets. No new endpoints or helper segments.
Choose smallest sampled symmetric Hausdorff deviation; accept <=4 normalized pixels
(3pt), samples spaced <=0.25 normalized px. Record deviation and vertex simplification.
If no candidate meets the limit, fail that entire scene before output; do not silently
omit a connector. This changes local corner curvature, not object ownership or direction.

Native PPT initial endpoint tolerance <=1pt and approximation ceiling as above.
Run the same E0 fixed-owner edit + save/reopen + explicit reroute tests on Attention and
PERCEIVE. Exact source vertices are NOT required in E1; endpoints, intended one-connection
identity, owner bindings, route format and changes are separately audited. If movement
changes bend locations, disclose it; no automatic non-overlap layout claim. Reroute failure
is not rescued by reapplying XML. Production and all previous freezes remain unchanged.
