from __future__ import annotations

from dataclasses import dataclass
import math

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.core.enums import ConnectorOrientation, PortOwnerKind, PortSide
from image_to_editable_ppt.v3.ir.models import (
    ConnectorAttachment,
    ConnectorEvidence,
    PortSpec,
    PrimitiveConnectorCandidate,
    UnattachedConnectorEvidence,
)


@dataclass(slots=True, frozen=True)
class AttachmentCandidate:
    port: PortSpec
    distance: float
    score: float


@dataclass(slots=True, frozen=True)
class ConnectorAttachmentBridge:
    max_attachment_distance: float = 28.0

    def attach(
        self,
        *,
        connector_evidence: tuple[ConnectorEvidence, ...],
        ports: tuple[PortSpec, ...],
        config: V3Config,
    ) -> tuple[tuple[PrimitiveConnectorCandidate, ...], tuple[UnattachedConnectorEvidence, ...]]:
        del config
        candidates: list[PrimitiveConnectorCandidate] = []
        unattached: list[UnattachedConnectorEvidence] = []

        for evidence in connector_evidence:
            start_point = evidence.path_points[0]
            end_point = evidence.path_points[-1]
            start_candidates = _rank_port_candidates(
                start_point,
                ports=ports,
                orientation=evidence.orientation,
                nearby_node_ids=evidence.start_nearby_node_ids,
                nearby_container_ids=evidence.nearby_container_ids,
                max_distance=self.max_attachment_distance,
            )
            end_candidates = _rank_port_candidates(
                end_point,
                ports=ports,
                orientation=evidence.orientation,
                nearby_node_ids=evidence.end_nearby_node_ids,
                nearby_container_ids=evidence.nearby_container_ids,
                max_distance=self.max_attachment_distance,
            )
            attachment_pair = _choose_attachment_pair(start_candidates, end_candidates)
            if attachment_pair is None:
                reason = _attachment_failure_reason(start_candidates, end_candidates)
                candidate_port_ids = tuple(
                    dict.fromkeys(
                        [item.port.id for item in start_candidates[:3]] + [item.port.id for item in end_candidates[:3]]
                    )
                )
                unattached.append(
                    UnattachedConnectorEvidence(
                        id=f"unattached_connector_evidence:{len(unattached) + 1}",
                        evidence_id=evidence.id,
                        reason=reason,
                        confidence=evidence.confidence,
                        candidate_port_ids=candidate_port_ids,
                        source="phase5_attachment_bridge",
                        provenance=(
                            "connector_evidence:phase4",
                            "bridge:port_attachment",
                        ),
                    )
                )
                continue

            start_attachment = _to_attachment(attachment_pair[0])
            end_attachment = _to_attachment(attachment_pair[1])
            confidence = min(
                0.97,
                evidence.confidence * 0.64
                + start_attachment.confidence * 0.18
                + end_attachment.confidence * 0.18,
            )
            candidates.append(
                PrimitiveConnectorCandidate(
                    id=f"connector_candidate:{len(candidates) + 1}",
                    kind=evidence.kind,
                    bbox=evidence.bbox,
                    confidence=confidence,
                    source_evidence_id=evidence.id,
                    path_points=evidence.path_points,
                    start_attachment=start_attachment,
                    end_attachment=end_attachment,
                    arrowhead_start=evidence.arrowhead_start,
                    arrowhead_end=evidence.arrowhead_end,
                    source="phase5_attachment_bridge",
                    provenance=(
                        *evidence.provenance,
                        "bridge:port_attachment",
                    ),
                )
            )

        return tuple(candidates), tuple(unattached)


def attach_connector_evidence(
    *,
    connector_evidence: tuple[ConnectorEvidence, ...],
    ports: tuple[PortSpec, ...],
    config: V3Config,
) -> tuple[tuple[PrimitiveConnectorCandidate, ...], tuple[UnattachedConnectorEvidence, ...]]:
    return ConnectorAttachmentBridge().attach(connector_evidence=connector_evidence, ports=ports, config=config)


def _rank_port_candidates(
    point,
    *,
    ports: tuple[PortSpec, ...],
    orientation: ConnectorOrientation,
    nearby_node_ids: tuple[str, ...],
    nearby_container_ids: tuple[str, ...],
    max_distance: float,
) -> tuple[AttachmentCandidate, ...]:
    candidates: list[AttachmentCandidate] = []
    nearby_nodes = set(nearby_node_ids)
    nearby_containers = set(nearby_container_ids)
    for port in ports:
        distance = math.hypot(point.x - port.point.x, point.y - port.point.y)
        if distance > max_distance:
            continue
        score = distance + _side_penalty(port.side, orientation) + _owner_penalty(port.owner_kind)
        if port.owner_id in nearby_nodes:
            score -= 4.0
        elif port.owner_id in nearby_containers:
            score -= 1.5
        candidates.append(AttachmentCandidate(port=port, distance=distance, score=score))
    return tuple(sorted(candidates, key=lambda item: (item.score, item.distance, item.port.id)))


def _choose_attachment_pair(
    start_candidates: tuple[AttachmentCandidate, ...],
    end_candidates: tuple[AttachmentCandidate, ...],
) -> tuple[AttachmentCandidate, AttachmentCandidate] | None:
    if not start_candidates or not end_candidates:
        return None
    best_pair: tuple[AttachmentCandidate, AttachmentCandidate] | None = None
    best_score = float("inf")
    for start in start_candidates[:4]:
        for end in end_candidates[:4]:
            if start.port.owner_id == end.port.owner_id:
                continue
            pair_score = start.score + end.score
            if pair_score < best_score:
                best_score = pair_score
                best_pair = (start, end)
    return best_pair


def _attachment_failure_reason(
    start_candidates: tuple[AttachmentCandidate, ...],
    end_candidates: tuple[AttachmentCandidate, ...],
) -> str:
    if not start_candidates and not end_candidates:
        return "no_compatible_ports_near_either_endpoint"
    if not start_candidates:
        return "start_endpoint_unattached"
    if not end_candidates:
        return "end_endpoint_unattached"
    return "same_owner_attachment_only"


def _to_attachment(candidate: AttachmentCandidate) -> ConnectorAttachment:
    confidence = max(0.25, candidate.port.confidence * (1.0 - min(1.0, candidate.distance / 32.0)))
    return ConnectorAttachment(
        port_id=candidate.port.id,
        owner_id=candidate.port.owner_id,
        owner_kind=candidate.port.owner_kind,
        side=candidate.port.side,
        point=candidate.port.point,
        distance=candidate.distance,
        confidence=confidence,
        source="phase5_attachment_bridge",
        provenance=(
            *candidate.port.provenance,
            "bridge:port_attachment",
        ),
    )


def _owner_penalty(owner_kind: PortOwnerKind) -> float:
    return 0.0 if owner_kind is PortOwnerKind.NODE else 2.5


def _side_penalty(side: PortSide, orientation: ConnectorOrientation) -> float:
    if orientation is ConnectorOrientation.HORIZONTAL:
        return 0.0 if side in {PortSide.LEFT, PortSide.RIGHT} else 8.0
    if orientation is ConnectorOrientation.VERTICAL:
        return 0.0 if side in {PortSide.TOP, PortSide.BOTTOM} else 8.0
    return 2.0
