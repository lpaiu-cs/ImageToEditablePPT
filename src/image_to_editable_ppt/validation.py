from __future__ import annotations

from typing import Any


REMOVED_MESSAGE = "v2 core removed, use v3 path / see plan.md. Validation adapter is not implemented yet."


class ValidationAdapterUnavailableError(NotImplementedError):
    """Raised when callers request the removed v2 validation runtime."""


def run_validation_iteration(*args: Any, **kwargs: Any):
    del args, kwargs
    raise ValidationAdapterUnavailableError(REMOVED_MESSAGE)


def stage_eval_items(*args: Any, **kwargs: Any):
    del args, kwargs
    raise ValidationAdapterUnavailableError(REMOVED_MESSAGE)


def build_manifest_payload(*args: Any, **kwargs: Any):
    del args, kwargs
    raise ValidationAdapterUnavailableError(REMOVED_MESSAGE)


def load_pptx_shapes(*args: Any, **kwargs: Any):
    del args, kwargs
    raise ValidationAdapterUnavailableError(REMOVED_MESSAGE)


def export_validation_svg(*args: Any, **kwargs: Any) -> None:
    del args, kwargs
    raise ValidationAdapterUnavailableError(REMOVED_MESSAGE)
