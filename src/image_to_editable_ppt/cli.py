from __future__ import annotations


REMOVED_MESSAGE = (
    "v2 core removed, use v3 path / see plan.md. "
    "Run tools/run_v3_debug.py for the current inspection workflow."
)


def main() -> int:
    raise RuntimeError(REMOVED_MESSAGE)
