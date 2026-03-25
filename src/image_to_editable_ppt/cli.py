from __future__ import annotations


REMOVED_MESSAGE = "v2 core removed, use v3 path / see plan.md. The old CLI entrypoint is no longer available."


def main() -> int:
    raise RuntimeError(REMOVED_MESSAGE)
