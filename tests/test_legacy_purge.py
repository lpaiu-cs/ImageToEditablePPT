from __future__ import annotations

import ast
from importlib import import_module
from importlib.util import resolve_name
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "image_to_editable_ppt"
PRESERVE_EVAL_FILES = (
    SRC_ROOT / "validation.py",
    SRC_ROOT / "eval_debug.py",
    SRC_ROOT / "benchmark_report.py",
    SRC_ROOT / "diagnostics.py",
    SRC_ROOT / "source_attribution.py",
)
PURGED_ROOT_FILES = (
    "components.py",
    "config.py",
    "detector.py",
    "emit.py",
    "exporter.py",
    "fallback.py",
    "filtering.py",
    "fitter.py",
    "gating.py",
    "geometry.py",
    "graph.py",
    "guides.py",
    "ir.py",
    "objects.py",
    "pipeline.py",
    "preprocess.py",
    "repair.py",
    "router.py",
    "selection.py",
    "style.py",
    "svg_exporter.py",
    "text.py",
    "vlm_parser.py",
)
DISALLOWED_IMPORT_PREFIXES = (
    "image_to_editable_ppt.components",
    "image_to_editable_ppt.config",
    "image_to_editable_ppt.detector",
    "image_to_editable_ppt.emit",
    "image_to_editable_ppt.exporter",
    "image_to_editable_ppt.fallback",
    "image_to_editable_ppt.filtering",
    "image_to_editable_ppt.fitter",
    "image_to_editable_ppt.gating",
    "image_to_editable_ppt.geometry",
    "image_to_editable_ppt.graph",
    "image_to_editable_ppt.guides",
    "image_to_editable_ppt.ir",
    "image_to_editable_ppt.objects",
    "image_to_editable_ppt.pipeline",
    "image_to_editable_ppt.preprocess",
    "image_to_editable_ppt.reconstructors",
    "image_to_editable_ppt.repair",
    "image_to_editable_ppt.router",
    "image_to_editable_ppt.selection",
    "image_to_editable_ppt.style",
    "image_to_editable_ppt.svg_exporter",
    "image_to_editable_ppt.text",
    "image_to_editable_ppt.vlm_parser",
)


def test_purged_root_runtime_files_are_removed() -> None:
    missing = [path for path in PURGED_ROOT_FILES if (SRC_ROOT / path).exists()]
    assert missing == []
    assert not (SRC_ROOT / "reconstructors").exists()


def test_preserve_eval_modules_do_not_import_purged_runtime_modules() -> None:
    violations: list[str] = []
    for path in PRESERVE_EVAL_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        package_name = package_name_for(path)
        for lineno, imported in iter_internal_imports(tree, package_name):
            if imported.startswith(DISALLOWED_IMPORT_PREFIXES):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno} imports removed runtime {imported}")
    assert violations == []


def test_validation_module_is_explicit_tombstone() -> None:
    validation = import_module("image_to_editable_ppt.validation")
    assert "v2 core removed, use v3 path / see plan.md" in validation.REMOVED_MESSAGE
    assert "tools/run_v3_debug.py" in validation.REMOVED_MESSAGE
    with pytest.raises(validation.ValidationAdapterUnavailableError):
        validation.run_validation_iteration()


def test_cli_module_is_explicit_tombstone() -> None:
    cli = import_module("image_to_editable_ppt.cli")
    assert "v2 core removed, use v3 path / see plan.md" in cli.REMOVED_MESSAGE
    assert "tools/run_v3_debug.py" in cli.REMOVED_MESSAGE
    with pytest.raises(RuntimeError):
        cli.main()


def iter_internal_imports(tree: ast.AST, package_name: str) -> list[tuple[int, str]]:
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("image_to_editable_ppt"):
                    imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            target = resolve_import_target(node, package_name)
            if target.startswith("image_to_editable_ppt"):
                imports.append((node.lineno, target))
    return imports


def resolve_import_target(node: ast.ImportFrom, package_name: str) -> str:
    if node.level == 0:
        return node.module or ""
    relative_name = "." * node.level + (node.module or "")
    return resolve_name(relative_name, package_name)


def package_name_for(path: Path) -> str:
    module_parts = path.relative_to(REPO_ROOT / "src").with_suffix("").parts
    if module_parts[-1] == "__init__":
        return ".".join(module_parts[:-1])
    return ".".join(module_parts)
