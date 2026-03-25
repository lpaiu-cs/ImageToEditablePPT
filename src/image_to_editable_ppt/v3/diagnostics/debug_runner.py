from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.app.convert import V3ConversionResult, convert_image
from image_to_editable_ppt.v3.core.enums import BranchKind
from image_to_editable_ppt.v3.ir.models import ConnectorEvidence, DiagramContainer, DiagramInstance, DiagramNode, FamilyProposal


@dataclass(slots=True, frozen=True)
class V3DebugArtifacts:
    output_dir: Path
    family_proposals_json: Path
    diagram_instances_json: Path
    connector_evidence_json: Path
    overlay_proposals_png: Path
    overlay_instances_png: Path
    overlay_connector_evidence_png: Path
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
        },
    }

    family_json = output_path / "family_proposals.json"
    instance_json = output_path / "diagram_instances.json"
    connector_json = output_path / "connector_evidence.json"
    summary_json = output_path / "debug_summary.json"
    _write_json(family_json, family_payload)
    _write_json(instance_json, instance_payload)
    _write_json(connector_json, connector_payload)
    _write_json(summary_json, summary_payload)

    overlay_proposals = output_path / "overlay_proposals.png"
    overlay_instances = output_path / "overlay_instances.png"
    overlay_connector = output_path / "overlay_connector_evidence.png"
    _render_proposal_overlay(base_image, conversion.slide_ir.family_proposals).save(overlay_proposals)
    _render_instance_overlay(base_image, conversion.slide_ir.diagram_instances).save(overlay_instances)
    _render_connector_overlay(base_image, conversion.slide_ir.diagram_instances, conversion.slide_ir.connector_evidence).save(overlay_connector)

    return V3DebugRun(
        conversion=conversion,
        artifacts=V3DebugArtifacts(
            output_dir=output_path,
            family_proposals_json=family_json,
            diagram_instances_json=instance_json,
            connector_evidence_json=connector_json,
            overlay_proposals_png=overlay_proposals,
            overlay_instances_png=overlay_instances,
            overlay_connector_evidence_png=overlay_connector,
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
            draw.ellipse((points[0][0] - 3, points[0][1] - 3, points[0][0] + 3, points[0][1] + 3), fill=(123, 45, 180))
        if evidence.arrowhead_end:
            draw.ellipse((points[-1][0] - 3, points[-1][1] - 3, points[-1][0] + 3, points[-1][1] + 3), fill=(123, 45, 180))
        draw.text((evidence.bbox.x0 + 2, evidence.bbox.y0 + 2), evidence.id, fill=(196, 38, 54))
    return overlay


def _draw_bbox(draw: ImageDraw.ImageDraw, bbox, *, outline: tuple[int, int, int], width: int) -> None:
    draw.rectangle((bbox.x0, bbox.y0, bbox.x1, bbox.y1), outline=outline, width=width)
