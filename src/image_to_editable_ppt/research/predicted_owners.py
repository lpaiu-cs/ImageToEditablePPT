"""Validated detector objects -> frozen region stages; research only, no GT imports."""
from dataclasses import replace

from image_to_editable_ppt.v3.core.enums import ContainerKind, NodeKind, PortOwnerKind
from image_to_editable_ppt.v3.core.types import BBox, ImageSize
from image_to_editable_ppt.v3.emit.models import EmitScene, EmitShapePrimitive


def prediction_scene(sample):
    """Consume an already validated handoff sample without reranking or snapping."""
    shapes = []
    for obj in sample['objects']:
        role = PortOwnerKind(obj['role'])
        kind = (NodeKind if role is PortOwnerKind.NODE else ContainerKind)(obj['semantic_kind'])
        shapes.append(EmitShapePrimitive(
            id=obj['id'], owner_kind=role, shape_kind=kind,
            bbox=BBox(*obj['bbox_xyxy']), confidence=obj['confidence'],
            source='rgb_detector_prediction', provenance=('research:legacy_inferred', 'geometry:unchanged')))
    if len({s.id for s in shapes}) != len(shapes):
        raise ValueError('duplicate predicted owner ID')
    return EmitScene(image_size=ImageSize(*sample['image_size']), shapes=tuple(shapes),
                     source='research:fixed_rgb_predictions')


def supported_owner_connections(scene):
    """Do not crash or silently flatten connectors attached to text-only owners."""
    unsupported = {s.id for s in scene.shapes if s.shape_kind is NodeKind.LABEL_ANCHOR}
    rejected = {c.id: 'label_anchor_native_attachment_unsupported' for c in scene.connectors
                if c.source_owner_id in unsupported or c.target_owner_id in unsupported}
    return replace(scene, connectors=tuple(c for c in scene.connectors if c.id not in rejected)), rejected
