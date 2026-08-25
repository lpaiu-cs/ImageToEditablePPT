from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.v3.app.config import V3Config
from image_to_editable_ppt.v3.ir.models import ConnectorSpec, PrimitiveConnectorCandidate


@dataclass(slots=True, frozen=True)
class ConnectorCandidateSolver:
    def resolve(
        self,
        *,
        connector_candidates: tuple[PrimitiveConnectorCandidate, ...],
        config: V3Config,
    ) -> tuple[ConnectorSpec, ...]:
        del config
        solved: list[ConnectorSpec] = []
        best_by_port_pair: dict[tuple[str, str], PrimitiveConnectorCandidate] = {}
        pair_counts: dict[tuple[str, str], int] = {}

        for candidate in connector_candidates:
            if candidate.start_attachment is None or candidate.end_attachment is None:
                continue
            if candidate.start_attachment.owner_id == candidate.end_attachment.owner_id:
                continue

            # A shared owner pair is not enough evidence to merge: two shapes may
            # legitimately have multiple connectors on different sides. Exact
            # attachment ports are the conservative duplicate boundary for Hough
            # fragments of one visible line.
            port_pair = tuple(
                sorted((candidate.start_attachment.port_id, candidate.end_attachment.port_id))
            )
            pair_counts[port_pair] = pair_counts.get(port_pair, 0) + 1
            current = best_by_port_pair.get(port_pair)
            candidate_rank = (bool(candidate.arrowhead_start or candidate.arrowhead_end), candidate.confidence)
            current_rank = (
                (bool(current.arrowhead_start or current.arrowhead_end), current.confidence)
                if current is not None
                else None
            )
            if current is None or candidate_rank > current_rank:
                best_by_port_pair[port_pair] = candidate

        for port_pair, candidate in best_by_port_pair.items():
            solved.append(
                ConnectorSpec(
                    id=_solved_connector_id(candidate.id),
                    kind=candidate.kind,
                    confidence=candidate.confidence,
                    source_owner_id=candidate.start_attachment.owner_id,
                    source_owner_kind=candidate.start_attachment.owner_kind,
                    target_owner_id=candidate.end_attachment.owner_id,
                    target_owner_kind=candidate.end_attachment.owner_kind,
                    source_port_id=candidate.start_attachment.port_id,
                    target_port_id=candidate.end_attachment.port_id,
                    path_points=candidate.path_points,
                    source_instance_id=None,
                    target_instance_id=None,
                    arrowhead_start=candidate.arrowhead_start,
                    arrowhead_end=candidate.arrowhead_end,
                    source_candidate_id=candidate.id,
                    source_evidence_id=candidate.source_evidence_id,
                    source="phase6_connector_resolve",
                    provenance=(
                        *candidate.provenance,
                        "connector_resolve:attached_candidate",
                        *(
                            ("connector_resolve:port_pair_deduplicated",)
                            if pair_counts[port_pair] > 1
                            else ()
                        ),
                    ),
                )
            )

        return tuple(solved)


def resolve_connector_candidates(
    *,
    connector_candidates: tuple[PrimitiveConnectorCandidate, ...],
    config: V3Config,
) -> tuple[ConnectorSpec, ...]:
    return ConnectorCandidateSolver().resolve(connector_candidates=connector_candidates, config=config)


def _solved_connector_id(candidate_id: str) -> str:
    if candidate_id.startswith("connector_candidate:"):
        return candidate_id.replace("connector_candidate:", "connector:", 1)
    return f"connector:{candidate_id}"
