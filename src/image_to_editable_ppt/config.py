from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PipelineConfig:
    foreground_threshold: float = 32.0
    min_component_area: int = 18
    min_stroke_length: int = 18
    stroke_alignment_tolerance: int = 4
    stroke_merge_gap: int = 18
    min_box_size: int = 24
    min_side_support: float = 0.42
    min_box_support: float = 0.68
    min_line_aspect_ratio: float = 2.8
    max_straight_orth_error: float = 4.5
    orthogonal_cover_threshold: float = 0.82
    min_arrow_widen_ratio: float = 1.65
    inclusion_confidence: float = 0.80
    tentative_confidence: float = 0.60
    text_confidence: float = 0.92
    fill_delta_threshold: float = 14.0
    slide_padding_pt: float = 24.0
    text_margin: float = 10.0
