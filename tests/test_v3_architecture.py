from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
V3_ROOT = SRC_ROOT / "image_to_editable_ppt" / "v3"
ALLOWED_INTERNAL_PREFIXES = (
    "image_to_editable_ppt.v3",
    "image_to_editable_ppt.shared",
    "image_to_editable_ppt.eval_runtime",
)


def test_v3_modules_do_not_import_legacy_runtime_modules() -> None:
    violations: list[str] = []
    for path in sorted(V3_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        package_name = package_name_for(path)
        for lineno, imported in iter_internal_imports(tree, package_name):
            if imported == "image_to_editable_ppt" or not imported.startswith(ALLOWED_INTERNAL_PREFIXES):
                rel_path = path.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}:{lineno} imports disallowed internal module {imported}")
    assert violations == []


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
    module_parts = path.relative_to(SRC_ROOT).with_suffix("").parts
    if module_parts[-1] == "__init__":
        return ".".join(module_parts[:-1])
    return ".".join(module_parts[:-1])
