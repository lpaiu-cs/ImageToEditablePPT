from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import V3ConversionResult, convert_image
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.emit import build_emit_scene
from image_to_editable_ppt.v3.emit.models import EmitScene
from image_to_editable_ppt.v3.ir.models import (
    ConnectorAttachment,
    ConnectorEvidence,
    ConnectorSpec,
    DiagramContainer,
    DiagramInstance,
    DiagramNode,
    FamilyProposal,
    PortSpec,
    PrimitiveConnectorCandidate,
    PrimitiveResidual,
    PrimitiveScene,
    PrimitiveText,
    UnattachedConnectorEvidence,
)


@dataclass(slots=True, frozen=True)
class V3DebugArtifacts:
    output_dir: Path
    family_proposals_json: Path
    diagram_instances_json: Path
    connector_evidence_json: Path
    primitive_scene_json: Path
    attached_connectors_json: Path
    solved_connectors_json: Path
    emit_scene_json: Path
    overlay_proposals_png: Path
    overlay_instances_png: Path
    overlay_connector_evidence_png: Path
    overlay_ports_png: Path
    overlay_primitives_png: Path
    overlay_attached_connectors_png: Path
    overlay_solved_connectors_png: Path
    overlay_emit_scene_png: Path
    debug_summary_json: Path


@dataclass(slots=True)
class V3DebugRun:
    conversion: V3ConversionResult
    artifacts: V3DebugArtifacts


def run_v3_debug(
    input_image,
    *,
    output_dir: str | Path,
    config: V3Config | None = None,
) -> V3DebugRun:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    conversion = convert_image(input_image, config=config)
    base_image = Image.fromarray(
        np.asarray(conversion.multiview.branch(BranchKind.RGB).image, dtype=np.uint8),
        mode="RGB",
    )

    family_payload = {"family_proposals": [_proposal_to_json(item) for item in conversion.slide_ir.family_proposals]}
    instance_payload = {"diagram_instances": [_instance_to_json(item) for item in conversion.slide_ir.diagram_instances]}
    connector_payload = {"connector_evidence": [_connector_evidence_to_json(item) for item in conversion.slide_ir.connector_evidence]}
    primitive_scene = conversion.slide_ir.primitive_scene
    emit_scene = None if primitive_scene is None else build_emit_scene(
        primitive_scene=primitive_scene,
        connectors=conversion.slide_ir.connectors,
    )
    primitive_payload = {
        "primitive_scene": None if primitive_scene is None else _primitive_scene_to_json(primitive_scene),
    }
    attached_connector_payload = {
        "connector_candidates": [_connector_candidate_to_json(item) for item in conversion.slide_ir.connector_candidates],
        "unattached_connector_evidence": [
            _unattached_connector_to_json(item) for item in conversion.slide_ir.unattached_connector_evidence
        ],
    }
    solved_connector_payload = {
        "connectors": [_connector_to_json(item) for item in conversion.slide_ir.connectors],
    }
    emit_scene_payload = {
        "emit_scene": None if emit_scene is None else _emit_scene_to_json(emit_scene),
    }
    summary_payload = {
        "image_size": conversion.slide_ir.image_size.as_tuple(),
        "stage_records": [
            {"stage": record.stage.value, "summary": record.summary, "notes": list(record.notes)}
            for record in conversion.stage_records
        ],
        "counts": {
            "family_proposals": len(conversion.slide_ir.family_proposals),
            "diagram_instances": len(conversion.slide_ir.diagram_instances),
            "connector_evidence": len(conversion.slide_ir.connector_evidence),
            "connector_candidates": len(conversion.slide_ir.connector_candidates),
            "unattached_connector_evidence": len(conversion.slide_ir.unattached_connector_evidence),
            "solved_connectors": len(conversion.slide_ir.connectors),
            "primitive_nodes": 0 if primitive_scene is None else len(primitive_scene.nodes),
            "primitive_containers": 0 if primitive_scene is None else len(primitive_scene.containers),
            "primitive_texts": 0 if primitive_scene is None else len(primitive_scene.texts),
            "primitive_ports": 0 if primitive_scene is None else len(primitive_scene.ports),
            "primitive_residuals": 0 if primitive_scene is None else len(primitive_scene.residuals),
            "emit_shapes": 0 if emit_scene is None else len(emit_scene.shapes),
            "emit_texts": 0 if emit_scene is None else len(emit_scene.texts),
            "emit_connectors": 0 if emit_scene is None else len(emit_scene.connectors),
            "emit_residuals": 0 if emit_scene is None else len(emit_scene.residuals),
        },
        "connector_resolve": {
            "connector_candidates": len(conversion.slide_ir.connector_candidates),
            "solved_connectors": len(conversion.slide_ir.connectors),
        },
        "emit_adapter": {
            "shapes": 0 if emit_scene is None else len(emit_scene.shapes),
            "texts": 0 if emit_scene is None else len(emit_scene.texts),
            "connectors": 0 if emit_scene is None else len(emit_scene.connectors),
            "residuals": 0 if emit_scene is None else len(emit_scene.residuals),
        },
    }

    family_json = output_path / "family_proposals.json"
    instance_json = output_path / "diagram_instances.json"
    connector_json = output_path / "connector_evidence.json"
    primitive_json = output_path / "primitive_scene.json"
    attached_connector_json = output_path / "attached_connectors.json"
    solved_connector_json = output_path / "solved_connectors.json"
    emit_scene_json = output_path / "emit_scene.json"
    summary_json = output_path / "debug_summary.json"
    _write_json(family_json, family_payload)
    _write_json(instance_json, instance_payload)
    _write_json(connector_json, connector_payload)
    _write_json(primitive_json, primitive_payload)
    _write_json(attached_connector_json, attached_connector_payload)
    _write_json(solved_connector_json, solved_connector_payload)
    _write_json(emit_scene_json, emit_scene_payload)
    _write_json(summary_json, summary_payload)

    overlay_proposals = output_path / "overlay_proposals.png"
    overlay_instances = output_path / "overlay_instances.png"
    overlay_connector = output_path / "overlay_connector_evidence.png"
    overlay_ports = output_path / "overlay_ports.png"
    overlay_primitives = output_path / "overlay_primitives.png"
    overlay_attached_connectors = output_path / "overlay_attached_connectors.png"
    overlay_solved_connectors = output_path / "overlay_solved_connectors.png"
    overlay_emit_scene = output_path / "overlay_emit_scene.png"
    _render_proposal_overlay(base_image, conversion.slide_ir.family_proposals).save(overlay_proposals)
    _render_instance_overlay(base_image, conversion.slide_ir.diagram_instances).save(overlay_instances)
    _render_connector_overlay(base_image, conversion.slide_ir.diagram_instances, conversion.slide_ir.connector_evidence).save(overlay_connector)
    _render_port_overlay(base_image, primitive_scene).save(overlay_ports)
    _render_primitive_overlay(base_image, primitive_scene).save(overlay_primitives)
    _render_attached_connector_overlay(base_image, primitive_scene).save(overlay_attached_connectors)
    _render_solved_connector_overlay(base_image, conversion.slide_ir.connectors).save(overlay_solved_connectors)
    _render_emit_scene_overlay(base_image, emit_scene).save(overlay_emit_scene)

    return V3DebugRun(
        conversion=conversion,
        artifacts=V3DebugArtifacts(
            output_dir=output_path,
            family_proposals_json=family_json,
            diagram_instances_json=instance_json,
            connector_evidence_json=connector_json,
            primitive_scene_json=primitive_json,
            attached_connectors_json=attached_connector_json,
            solved_connectors_json=solved_connector_json,
            emit_scene_json=emit_scene_json,
            overlay_proposals_png=overlay_proposals,
            overlay_instances_png=overlay_instances,
            overlay_connector_evidence_png=overlay_connector,
            overlay_ports_png=overlay_ports,
            overlay_primitives_png=overlay_primitives,
            overlay_attached_connectors_png=overlay_attached_connectors,
            overlay_solved_connectors_png=overlay_solved_connectors,
            overlay_emit_scene_png=overlay_emit_scene,
            debug_summary_json=summary_json,
        ),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _bbox_to_json(bbox) -> dict[str, float]:
    return {"x0": bbox.x0, "y0": bbox.y0, "x1": bbox.x1, "y1": bbox.y1}


def _point_to_json(point) -> dict[str, float]:
    return {"x": point.x, "y": point.y}


def _proposal_to_json(proposal: FamilyProposal) -> dict[str, object]:
    return {
        "id": proposal.id,
        "family": proposal.family.value,
        "confidence": proposal.confidence,
        "focus_bbox": None if proposal.focus_bbox is None else _bbox_to_json(proposal.focus_bbox),
        "evidence": list(proposal.evidence),
        "provenance": list(proposal.provenance),
    }


def _node_to_json(node: DiagramNode) -> dict[str, object]:
    return {
        "id": node.id,
        "kind": node.kind.value,
        "bbox": _bbox_to_json(node.bbox),
        "confidence": node.confidence,
        "label": node.label,
        "text_region_ids": list(node.text_region_ids),
        "port_ids": list(getattr(node, "port_ids", ())),
        "source": node.source,
        "provenance": list(node.provenance),
    }


def _container_to_json(container: DiagramContainer) -> dict[str, object]:
    return {
        "id": container.id,
        "kind": container.kind.value,
        "bbox": _bbox_to_json(container.bbox),
        "confidence": container.confidence,
        "member_node_ids": list(container.member_node_ids),
        "label": container.label,
        "port_ids": list(getattr(container, "port_ids", ())),
        "source": container.source,
        "provenance": list(container.provenance),
    }


def _instance_to_json(instance: DiagramInstance) -> dict[str, object]:
    return {
        "id": instance.id,
        "family": instance.family.value,
        "confidence": instance.confidence,
        "bbox": _bbox_to_json(instance.bbox),
        "containers": [_container_to_json(item) for item in instance.containers],
        "nodes": [_node_to_json(item) for item in instance.nodes],
        "text_region_ids": list(instance.text_region_ids),
        "source_proposal_ids": list(instance.source_proposal_ids),
        "provenance": list(instance.provenance),
    }


def _connector_evidence_to_json(evidence: ConnectorEvidence) -> dict[str, object]:
    return {
        "id": evidence.id,
        "kind": evidence.kind.value,
        "orientation": evidence.orientation.value,
        "bbox": _bbox_to_json(evidence.bbox),
        "confidence": evidence.confidence,
        "path_points": [_point_to_json(point) for point in evidence.path_points],
        "arrowhead_start": evidence.arrowhead_start,
        "arrowhead_end": evidence.arrowhead_end,
        "start_nearby_node_ids": list(evidence.start_nearby_node_ids),
        "end_nearby_node_ids": list(evidence.end_nearby_node_ids),
        "nearby_container_ids": list(evidence.nearby_container_ids),
        "source": evidence.source,
        "provenance": list(evidence.provenance),
    }


def _port_to_json(port: PortSpec) -> dict[str, object]:
    return {
        "id": port.id,
        "owner_id": port.owner_id,
        "owner_kind": port.owner_kind.value,
        "side": port.side.value,
        "point": _point_to_json(port.point),
        "confidence": port.confidence,
        "source": port.source,
        "provenance": list(port.provenance),
    }


def _attachment_to_json(attachment: ConnectorAttachment | None) -> dict[str, object] | None:
    if attachment is None:
        return None
    return {
        "port_id": attachment.port_id,
        "owner_id": attachment.owner_id,
        "owner_kind": attachment.owner_kind.value,
        "side": attachment.side.value,
        "point": _point_to_json(attachment.point),
        "distance": attachment.distance,
        "confidence": attachment.confidence,
        "source": attachment.source,
        "provenance": list(attachment.provenance),
    }


def _connector_candidate_to_json(candidate: PrimitiveConnectorCandidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "kind": candidate.kind.value,
        "bbox": _bbox_to_json(candidate.bbox),
        "confidence": candidate.confidence,
        "source_evidence_id": candidate.source_evidence_id,
        "path_points": [_point_to_json(point) for point in candidate.path_points],
        "start_attachment": _attachment_to_json(candidate.start_attachment),
        "end_attachment": _attachment_to_json(candidate.end_attachment),
        "arrowhead_start": candidate.arrowhead_start,
        "arrowhead_end": candidate.arrowhead_end,
        "source": candidate.source,
        "provenance": list(candidate.provenance),
    }


def _connector_to_json(connector: ConnectorSpec) -> dict[str, object]:
    return {
        "id": connector.id,
        "kind": connector.kind.value,
        "confidence": connector.confidence,
        "source_owner_id": connector.source_owner_id,
        "source_owner_kind": connector.source_owner_kind.value,
        "target_owner_id": connector.target_owner_id,
        "target_owner_kind": connector.target_owner_kind.value,
        "source_port_id": connector.source_port_id,
        "target_port_id": connector.target_port_id,
        "path_points": [_point_to_json(point) for point in connector.path_points],
        "source_instance_id": connector.source_instance_id,
        "target_instance_id": connector.target_instance_id,
        "arrowhead_start": connector.arrowhead_start,
        "arrowhead_end": connector.arrowhead_end,
        "source_candidate_id": connector.source_candidate_id,
        "source_evidence_id": connector.source_evidence_id,
        "source": connector.source,
        "provenance": list(connector.provenance),
    }


def _unattached_connector_to_json(item: UnattachedConnectorEvidence) -> dict[str, object]:
    return {
        "id": item.id,
        "evidence_id": item.evidence_id,
        "reason": item.reason,
        "confidence": item.confidence,
        "candidate_port_ids": list(item.candidate_port_ids),
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _primitive_text_to_json(item: PrimitiveText) -> dict[str, object]:
    return {
        "id": item.id,
        "role": item.role.value,
        "bbox": _bbox_to_json(item.bbox),
        "confidence": item.confidence,
        "text": item.text,
        "owner_ids": list(item.owner_ids),
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _primitive_residual_to_json(item: PrimitiveResidual) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind.value,
        "bbox": _bbox_to_json(item.bbox),
        "confidence": item.confidence,
        "reason": item.reason,
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _primitive_scene_to_json(scene: PrimitiveScene) -> dict[str, object]:
    return {
        "image_size": scene.image_size.as_tuple(),
        "nodes": [_node_to_json(item) for item in scene.nodes],
        "containers": [_container_to_json(item) for item in scene.containers],
        "texts": [_primitive_text_to_json(item) for item in scene.texts],
        "ports": [_port_to_json(item) for item in scene.ports],
        "connector_candidates": [_connector_candidate_to_json(item) for item in scene.connector_candidates],
        "unattached_connector_evidence": [
            _unattached_connector_to_json(item) for item in scene.unattached_connector_evidence
        ],
        "residuals": [_primitive_residual_to_json(item) for item in scene.residuals],
        "provenance": list(scene.provenance),
    }


def _emit_shape_to_json(item) -> dict[str, object]:
    return {
        "id": item.id,
        "owner_kind": item.owner_kind.value,
        "shape_kind": item.shape_kind.value,
        "bbox": _bbox_to_json(item.bbox),
        "confidence": item.confidence,
        "label": item.label,
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _emit_text_to_json(item) -> dict[str, object]:
    return {
        "id": item.id,
        "role": item.role.value,
        "bbox": _bbox_to_json(item.bbox),
        "confidence": item.confidence,
        "text": item.text,
        "owner_ids": list(item.owner_ids),
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _emit_connector_to_json(item) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind.value,
        "confidence": item.confidence,
        "source_owner_id": item.source_owner_id,
        "source_owner_kind": item.source_owner_kind.value,
        "target_owner_id": item.target_owner_id,
        "target_owner_kind": item.target_owner_kind.value,
        "source_port_id": item.source_port_id,
        "target_port_id": item.target_port_id,
        "path_points": [_point_to_json(point) for point in item.path_points],
        "source_instance_id": item.source_instance_id,
        "target_instance_id": item.target_instance_id,
        "arrowhead_start": item.arrowhead_start,
        "arrowhead_end": item.arrowhead_end,
        "source_candidate_id": item.source_candidate_id,
        "source_evidence_id": item.source_evidence_id,
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _emit_residual_to_json(item) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind.value,
        "bbox": _bbox_to_json(item.bbox),
        "confidence": item.confidence,
        "reason": item.reason,
        "source": item.source,
        "provenance": list(item.provenance),
    }


def _emit_scene_to_json(scene: EmitScene) -> dict[str, object]:
    return {
        "image_size": scene.image_size.as_tuple(),
        "coordinate_space": scene.coordinate_space,
        "shapes": [_emit_shape_to_json(item) for item in scene.shapes],
        "texts": [_emit_text_to_json(item) for item in scene.texts],
        "connectors": [_emit_connector_to_json(item) for item in scene.connectors],
        "residuals": [_emit_residual_to_json(item) for item in scene.residuals],
        "source": scene.source,
        "provenance": list(scene.provenance),
    }


def _render_proposal_overlay(base_image: Image.Image, proposals: tuple[FamilyProposal, ...]) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    for proposal in proposals:
        if proposal.focus_bbox is None:
            continue
        _draw_bbox(draw, proposal.focus_bbox, outline=(32, 93, 179), width=3)
        draw.text((proposal.focus_bbox.x0 + 4, proposal.focus_bbox.y0 + 4), proposal.id, fill=(32, 93, 179))
    return overlay


def _render_instance_overlay(base_image: Image.Image, instances: tuple[DiagramInstance, ...]) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    for instance in instances:
        for container in instance.containers:
            _draw_bbox(draw, container.bbox, outline=(38, 120, 72), width=3)
            draw.text((container.bbox.x0 + 4, container.bbox.y0 + 4), container.id, fill=(38, 120, 72))
        for node in instance.nodes:
            _draw_bbox(draw, node.bbox, outline=(211, 117, 0), width=2)
            draw.text((node.bbox.x0 + 4, node.bbox.y0 + 4), node.id, fill=(211, 117, 0))
    return overlay


def _render_connector_overlay(
    base_image: Image.Image,
    instances: tuple[DiagramInstance, ...],
    connector_evidence: tuple[ConnectorEvidence, ...],
) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    for instance in instances:
        for node in instance.nodes:
            _draw_bbox(draw, node.bbox, outline=(180, 180, 180), width=1)
    for evidence in connector_evidence:
        points = [(point.x, point.y) for point in evidence.path_points]
        draw.line(points, fill=(196, 38, 54), width=3)
        if evidence.arrowhead_start:
            _draw_point(draw, points[0], fill=(123, 45, 180), radius=4)
        if evidence.arrowhead_end:
            _draw_point(draw, points[-1], fill=(123, 45, 180), radius=4)
        draw.text((evidence.bbox.x0 + 2, evidence.bbox.y0 + 2), evidence.id, fill=(196, 38, 54))
    return overlay


def _render_port_overlay(base_image: Image.Image, scene: PrimitiveScene | None) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    if scene is None:
        return overlay
    for node in scene.nodes:
        _draw_bbox(draw, node.bbox, outline=(210, 210, 210), width=1)
    for container in scene.containers:
        _draw_bbox(draw, container.bbox, outline=(180, 220, 180), width=1)
    for port in scene.ports:
        color = (211, 117, 0) if port.owner_kind.value == "node" else (38, 120, 72)
        _draw_point(draw, (port.point.x, port.point.y), fill=color, radius=4)
        draw.text((port.point.x + 3, port.point.y + 3), port.side.value[0], fill=color)
    return overlay


def _render_primitive_overlay(base_image: Image.Image, scene: PrimitiveScene | None) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    if scene is None:
        return overlay
    for container in scene.containers:
        _draw_bbox(draw, container.bbox, outline=(38, 120, 72), width=3)
        draw.text((container.bbox.x0 + 4, container.bbox.y0 + 4), container.id, fill=(38, 120, 72))
    for node in scene.nodes:
        _draw_bbox(draw, node.bbox, outline=(211, 117, 0), width=2)
        draw.text((node.bbox.x0 + 4, node.bbox.y0 + 4), node.id, fill=(211, 117, 0))
    for text in scene.texts:
        _draw_bbox(draw, text.bbox, outline=(50, 50, 200), width=1)
    for residual in scene.residuals:
        _draw_bbox(draw, residual.bbox, outline=(196, 38, 54), width=1)
    return overlay


def _render_attached_connector_overlay(base_image: Image.Image, scene: PrimitiveScene | None) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    if scene is None:
        return overlay
    for node in scene.nodes:
        _draw_bbox(draw, node.bbox, outline=(200, 200, 200), width=1)
    for container in scene.containers:
        _draw_bbox(draw, container.bbox, outline=(210, 240, 210), width=1)
    for candidate in scene.connector_candidates:
        points = [(point.x, point.y) for point in candidate.path_points]
        draw.line(points, fill=(31, 119, 180), width=3)
        if candidate.start_attachment is not None:
            _draw_point(
                draw,
                (candidate.start_attachment.point.x, candidate.start_attachment.point.y),
                fill=(31, 119, 180),
                radius=4,
            )
        if candidate.end_attachment is not None:
            _draw_point(
                draw,
                (candidate.end_attachment.point.x, candidate.end_attachment.point.y),
                fill=(31, 119, 180),
                radius=4,
            )
        if candidate.arrowhead_start:
            _draw_point(draw, points[0], fill=(123, 45, 180), radius=4)
        if candidate.arrowhead_end:
            _draw_point(draw, points[-1], fill=(123, 45, 180), radius=4)
        draw.text((candidate.bbox.x0 + 2, candidate.bbox.y0 + 2), candidate.id, fill=(31, 119, 180))
    return overlay


def _render_solved_connector_overlay(base_image: Image.Image, connectors: tuple[ConnectorSpec, ...]) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    for connector in connectors:
        points = [(point.x, point.y) for point in connector.path_points]
        if len(points) < 2:
            continue
        draw.line(points, fill=(20, 92, 168), width=3)
        _draw_point(draw, points[0], fill=(20, 92, 168), radius=4)
        _draw_point(draw, points[-1], fill=(20, 92, 168), radius=4)
        if connector.arrowhead_start:
            _draw_point(draw, points[0], fill=(123, 45, 180), radius=5)
        if connector.arrowhead_end:
            _draw_point(draw, points[-1], fill=(123, 45, 180), radius=5)
        draw.text((points[0][0] + 3, points[0][1] + 3), connector.id, fill=(20, 92, 168))
    return overlay


def _render_emit_scene_overlay(base_image: Image.Image, scene: EmitScene | None) -> Image.Image:
    overlay = base_image.copy()
    draw = ImageDraw.Draw(overlay)
    if scene is None:
        return overlay
    for shape in scene.shapes:
        color = (38, 120, 72) if shape.owner_kind.value == "container" else (211, 117, 0)
        _draw_bbox(draw, shape.bbox, outline=color, width=2)
    for text in scene.texts:
        _draw_bbox(draw, text.bbox, outline=(50, 50, 200), width=1)
    for residual in scene.residuals:
        _draw_bbox(draw, residual.bbox, outline=(196, 38, 54), width=1)
    for connector in scene.connectors:
        points = [(point.x, point.y) for point in connector.path_points]
        if len(points) < 2:
            continue
        draw.line(points, fill=(20, 92, 168), width=3)
        if connector.arrowhead_start:
            _draw_point(draw, points[0], fill=(123, 45, 180), radius=4)
        if connector.arrowhead_end:
            _draw_point(draw, points[-1], fill=(123, 45, 180), radius=4)
    return overlay


def _draw_point(draw: ImageDraw.ImageDraw, point: tuple[float, float], *, fill: tuple[int, int, int], radius: int) -> None:
    x, y = point
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _draw_bbox(draw: ImageDraw.ImageDraw, bbox, *, outline: tuple[int, int, int], width: int) -> None:
    draw.rectangle((bbox.x0, bbox.y0, bbox.x1, bbox.y1), outline=outline, width=width)
