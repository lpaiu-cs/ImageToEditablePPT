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


class ContainerKind(StrEnum):
    FLOW_CLUSTER = "flow_cluster"
    PANEL = "panel"


class ConnectorKind(StrEnum):
    LINE = "line"
    ORTHOGONAL = "orthogonal"
    ARROW = "arrow"


class ConnectorOrientation(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    DIAGONAL = "diagonal"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class PortSide(StrEnum):
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


class PortOwnerKind(StrEnum):
    NODE = "node"
    CONTAINER = "container"


class TextRegionRole(StrEnum):
    UNKNOWN = "unknown"
    LABEL = "label"
    TITLE = "title"
    BODY = "body"


class RasterRegionKind(StrEnum):
    COMPLEX_REGION = "complex_region"
    PHOTO_LIKE = "photo_like"
    NON_DIAGRAM = "non_diagram"


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
    RESIDUAL_CANVAS = "residual_canvas"
    FAMILY_DETECT = "family_detect"
    FAMILY_PARSE = "family_parse"
    CONNECTOR_EVIDENCE = "connector_evidence"
    PORT_GENERATE = "port_generate"
    CONNECTOR_ATTACH = "connector_attach"
    CONNECTOR_RESOLVE = "connector_resolve"
    STYLE_RESOLVE = "style_resolve"
    COMPOSE = "compose"
    EMIT = "emit"
