from __future__ import annotations

from pathlib import Path

from image_to_editable_ppt import cli, validation


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_readme_points_to_v3_debug_path_instead_of_removed_v2_usage() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "tools/run_v3_debug.py" in readme
    assert "v3 debug/inspection path" in readme
    assert "orthogonal_flow" in readme
    assert "image-to-editable-ppt input.png output.pptx" not in readme
    assert "VLM_API_KEY" not in readme
    assert "--legacy" not in readme


def test_tombstones_point_to_current_replacement_path() -> None:
    assert "plan.md" in cli.REMOVED_MESSAGE
    assert "tools/run_v3_debug.py" in cli.REMOVED_MESSAGE
    assert "plan.md" in validation.REMOVED_MESSAGE
    assert "tools/run_v3_debug.py" in validation.REMOVED_MESSAGE


def test_historical_docs_are_marked_as_non_current() -> None:
    conversion_spec = (REPO_ROOT / "conversion-spec.md").read_text(encoding="utf-8").splitlines()[:6]
    legacy_instruction = (REPO_ROOT / "v2.0 instruction.md").read_text(encoding="utf-8").splitlines()[:6]

    assert any("historical" in line.lower() or "archived" in line.lower() for line in conversion_spec)
    assert any("obsolete" in line.lower() or "historical" in line.lower() for line in legacy_instruction)


def test_user_facing_markdown_does_not_expose_local_absolute_paths() -> None:
    markdown_paths = sorted(
        path
        for path in REPO_ROOT.rglob("*.md")
        if ".git" not in path.parts
    )

    offenders = []
    for path in markdown_paths:
        text = path.read_text(encoding="utf-8")
        if "/Users/lpaiu/vs/ImageToEditablePPT" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
