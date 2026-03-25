"""Evaluation runtime adapters for comparing legacy and v3 outputs."""

from .v3_adapter import (
    SUPPORTED_EVAL_STAGES,
    V3EvalAdapterResult,
    build_v3_eval_adapter_result,
    merge_eval_debug_payload,
    stage_artifacts_to_json,
    write_v3_eval_debug_artifacts,
)

__all__ = [
    "SUPPORTED_EVAL_STAGES",
    "V3EvalAdapterResult",
    "build_v3_eval_adapter_result",
    "merge_eval_debug_payload",
    "stage_artifacts_to_json",
    "write_v3_eval_debug_artifacts",
]
