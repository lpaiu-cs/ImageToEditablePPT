from __future__ import annotations

from image_to_editable_ppt.ml.phase16.annotation_drafting import (
    DraftCandidate,
    fuse_draft_candidates,
)


def test_fuse_draft_candidates_uses_original_coordinate_consensus() -> None:
    candidates = [
        DraftCandidate((10, 20, 110, 80), "node", "rectangle", (768,), ("outline",)),
        DraftCandidate((11, 19, 111, 81), "node", "rectangle", (1280,), ("outline",)),
        DraftCandidate((200, 20, 260, 80), "container", "rounded_rectangle", (768,), ("fill",)),
    ]

    fused = fuse_draft_candidates(candidates)

    assert len(fused) == 2
    assert fused[0].bbox == (10.5, 19.5, 110.5, 80.5)
    assert fused[0].scales == (768, 1280)
    assert fused[1].role == "container"
