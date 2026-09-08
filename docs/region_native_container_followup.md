# R4.2: distinguish owner masks from traversed container borders

2026-09-08. Preserve bd6d19c run3 failure: Attention 0/4 relations and two residual faces,
despite synthetic-v2 11/11. The observed-pad change enlarged its container mask from 2px
to 3px on both sides. The inclusive 7px erased border band is wider than the fixed closing
kernel can reconnect; tracing reports no two-owner components. Other four diagrams retained
their previous result. R4.1 therefore fails the joint promotion gate.

Follow-up before execution: adaptive observed-ink padding applies only to NODE owners,
whose interior ends a connection. CONTAINER borders remain the frozen base-pad bands because
connections traverse them. Do not enlarge gap closing or attachment tolerances. This is a
role-based distinction, not a case ID exception. Thick ambiguous container crossings can
still abstain; no universal crossing reconstruction claim. Re-run the same 11 synthetics
and five diagrams at unchanged thresholds. Keep both failed campaigns in final provenance.
