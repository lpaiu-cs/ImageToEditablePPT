from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.v3.emit.models import EmitScene
from image_to_editable_ppt.v3.ir.models import ConnectorSpec, PrimitiveScene


@dataclass(slots=True, frozen=True)
class EmitSceneDiff:
    coordinate_space: str
    primitive_shape_count: int
    emit_shape_count: int
    primitive_text_count: int
    emit_text_count: int
    primitive_connector_count: int
    emit_connector_count: int
    primitive_residual_count: int
    emit_residual_count: int
    missing_shape_ids: tuple[str, ...] = ()
    extra_shape_ids: tuple[str, ...] = ()
    missing_text_ids: tuple[str, ...] = ()
    extra_text_ids: tuple[str, ...] = ()
    missing_connector_ids: tuple[str, ...] = ()
    extra_connector_ids: tuple[str, ...] = ()
    missing_residual_ids: tuple[str, ...] = ()
    extra_residual_ids: tuple[str, ...] = ()
    shape_bbox_mismatch_ids: tuple[str, ...] = ()
    text_bbox_mismatch_ids: tuple[str, ...] = ()
    connector_path_mismatch_ids: tuple[str, ...] = ()
    residual_bbox_mismatch_ids: tuple[str, ...] = ()

    @property
    def lossless(self) -> bool:
        return (
            self.coordinate_space == "image_space"
            and self.primitive_shape_count == self.emit_shape_count
            and self.primitive_text_count == self.emit_text_count
            and self.primitive_connector_count == self.emit_connector_count
            and self.primitive_residual_count == self.emit_residual_count
            and not self.missing_shape_ids
            and not self.extra_shape_ids
            and not self.missing_text_ids
            and not self.extra_text_ids
            and not self.missing_connector_ids
            and not self.extra_connector_ids
            and not self.missing_residual_ids
            and not self.extra_residual_ids
            and not self.shape_bbox_mismatch_ids
            and not self.text_bbox_mismatch_ids
            and not self.connector_path_mismatch_ids
            and not self.residual_bbox_mismatch_ids
        )


def diff_emit_scene(
    *,
    primitive_scene: PrimitiveScene,
    connectors: tuple[ConnectorSpec, ...],
    emit_scene: EmitScene,
) -> EmitSceneDiff:
    primitive_shapes = {
        item.id: item.bbox
        for item in (*primitive_scene.containers, *primitive_scene.nodes)
    }
    emit_shapes = {item.id: item.bbox for item in emit_scene.shapes}
    primitive_texts = {item.id: item.bbox for item in primitive_scene.texts}
    emit_texts = {item.id: item.bbox for item in emit_scene.texts}
    primitive_connectors = {item.id: item.path_points for item in connectors}
    emit_connectors = {item.id: item.path_points for item in emit_scene.connectors}
    primitive_residuals = {item.id: item.bbox for item in primitive_scene.residuals}
    emit_residuals = {item.id: item.bbox for item in emit_scene.residuals}

    return EmitSceneDiff(
        coordinate_space=emit_scene.coordinate_space,
        primitive_shape_count=len(primitive_shapes),
        emit_shape_count=len(emit_shapes),
        primitive_text_count=len(primitive_texts),
        emit_text_count=len(emit_texts),
        primitive_connector_count=len(primitive_connectors),
        emit_connector_count=len(emit_connectors),
        primitive_residual_count=len(primitive_residuals),
        emit_residual_count=len(emit_residuals),
        missing_shape_ids=_missing_ids(primitive_shapes, emit_shapes),
        extra_shape_ids=_missing_ids(emit_shapes, primitive_shapes),
        missing_text_ids=_missing_ids(primitive_texts, emit_texts),
        extra_text_ids=_missing_ids(emit_texts, primitive_texts),
        missing_connector_ids=_missing_ids(primitive_connectors, emit_connectors),
        extra_connector_ids=_missing_ids(emit_connectors, primitive_connectors),
        missing_residual_ids=_missing_ids(primitive_residuals, emit_residuals),
        extra_residual_ids=_missing_ids(emit_residuals, primitive_residuals),
        shape_bbox_mismatch_ids=_bbox_mismatch_ids(primitive_shapes, emit_shapes),
        text_bbox_mismatch_ids=_bbox_mismatch_ids(primitive_texts, emit_texts),
        connector_path_mismatch_ids=_path_mismatch_ids(primitive_connectors, emit_connectors),
        residual_bbox_mismatch_ids=_bbox_mismatch_ids(primitive_residuals, emit_residuals),
    )


def _missing_ids(expected: dict[str, object], actual: dict[str, object]) -> tuple[str, ...]:
    return tuple(sorted(set(expected) - set(actual)))


def _bbox_mismatch_ids(expected: dict[str, object], actual: dict[str, object]) -> tuple[str, ...]:
    mismatches = []
    for item_id in sorted(set(expected) & set(actual)):
        if expected[item_id] != actual[item_id]:
            mismatches.append(item_id)
    return tuple(mismatches)


def _path_mismatch_ids(expected: dict[str, object], actual: dict[str, object]) -> tuple[str, ...]:
    mismatches = []
    for item_id in sorted(set(expected) & set(actual)):
        if tuple(expected[item_id]) != tuple(actual[item_id]):
            mismatches.append(item_id)
    return tuple(mismatches)
