from __future__ import annotations

from tools.apply_phase16_annotation_review import apply_decision


def _draft() -> dict[str, object]:
    return {
        "sample_id": "sample",
        "kind": "diagram",
        "objects": [
            {
                "id": "object:auto:node-1",
                "role": "node",
                "shape_kind": "rectangle",
                "bbox": {"x0": 1, "y0": 1, "x1": 10, "y1": 10},
                "parent_id": None,
                "importance": "secondary",
                "label": None,
                "ambiguity_note": None,
            },
            {
                "id": "object:auto:reject-me",
                "role": "node",
                "shape_kind": "rectangle",
                "bbox": {"x0": 20, "y0": 1, "x1": 30, "y1": 10},
                "parent_id": None,
                "importance": "secondary",
                "label": None,
                "ambiguity_note": None,
            },
        ],
        "connectors": [],
        "excluded_regions": [],
        "allowed_omissions": [],
        "ambiguity_notes": [],
        "review": {"status": "draft", "passes": []},
    }


def _decision() -> dict[str, object]:
    return {
        "objects": {
            "keep": ["node-1"],
            "core": ["node-1"],
            "labels": {"node-1": "Kept"},
            "overrides": {
                "node-1": {"bbox": {"x0": 2, "y0": 2, "x1": 11, "y1": 11}}
            },
            "add": [
                {
                    "id": "object:manual:container",
                    "role": "container",
                    "shape_kind": "rectangle",
                    "bbox": {"x0": 0, "y0": 0, "x1": 40, "y1": 20},
                    "importance": "core",
                }
            ],
        },
        "connectors": {
            "keep": [],
            "core": [],
            "overrides": {},
            "add": [
                {
                    "id": "connector:manual:1",
                    "source_id": "object:auto:node-1",
                    "target_id": "object:manual:container",
                    "path_points": [{"x": 10, "y": 6}, {"x": 20, "y": 6}],
                }
            ],
        },
        "excluded_regions": [],
        "allowed_omissions": ["tiny glyphs"],
        "ambiguity_notes": [],
    }


def test_visual_review_filters_overrides_and_adds_manual_structure_idempotently() -> None:
    first = apply_decision(
        _draft(), _decision(), review_sha256="a" * 64, finalized=True
    )
    second = apply_decision(
        first, _decision(), review_sha256="a" * 64, finalized=True
    )

    assert first == second
    assert [item["id"] for item in first["objects"]] == [
        "object:auto:node-1",
        "object:manual:container",
    ]
    assert first["objects"][0]["importance"] == "core"
    assert first["objects"][0]["label"]["text"] == "Kept"
    assert first["objects"][0]["bbox"]["x0"] == 2
    assert first["connectors"][0]["direction"] == "directed"
    assert first["review"]["status"] == "resolved"
    assert len(first["review"]["passes"]) == 2
