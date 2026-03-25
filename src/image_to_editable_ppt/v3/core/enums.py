from __future__ import annotations

from enum import StrEnum


class DiagramFamily(StrEnum):
    BLOCK_FLOW = "block_flow"
    ORTHOGONAL_FLOW = "orthogonal_flow"
    CYCLE = "cycle"
    SWIMLANE = "swimlane"
    TABLE_MATRIX = "table_matrix"
    TIMELINE = "timeline"
    LAYERED_STACK = "layered_stack"


class BranchKind(StrEnum):
    RGB = "rgb"
    STRUCTURE = "structure"
    STYLE = "style"
    TEXT = "text"
    STRUCTURAL_CANVAS = "structural_canvas"


class NodeKind(StrEnum):
    BOX = "box"
    ROUNDED_BOX = "rounded_box"
    SECTION = "section"
    LABEL_ANCHOR = "label_anchor"


class ConnectorKind(StrEnum):
    LINE = "line"
    ORTHOGONAL = "orthogonal"
    ARROW = "arrow"


class StyleTokenKind(StrEnum):
    FILL_COLOR = "fill_color"
    STROKE_COLOR = "stroke_color"
    STROKE_WIDTH = "stroke_width"
    TEXT_STYLE = "text_style"


class ResidualKind(StrEnum):
    UNRESOLVED = "unresolved"
    RASTER = "raster"
    NON_DIAGRAM = "non_diagram"


class StageName(StrEnum):
    MULTIVIEW = "multiview"
    TEXT_SPLIT = "text_split"
    RASTER_SPLIT = "raster_split"
    FAMILY_DETECT = "family_detect"
    FAMILY_PARSE = "family_parse"
    CONNECTOR_RESOLVE = "connector_resolve"
    STYLE_RESOLVE = "style_resolve"
    COMPOSE = "compose"
    EMIT = "emit"
