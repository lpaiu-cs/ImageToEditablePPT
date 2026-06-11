from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
    AnnotationConnectorCandidate,
    AnnotationConnectorEndpoint,
    AnnotationPrimitiveScene,
    DetectorAnnotationDocument,
    annotation_to_json,
)


@dataclass(slots=True, frozen=True)
class MatchRecord:
    prediction_id: str
    reference_id: str
    iou: float


@dataclass(slots=True, frozen=True)
class FamilyProposalMetrics:
    accuracy: float
    matched: int
    prediction_count: int
    reference_count: int
    matches: tuple[MatchRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class DetectionMetrics:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    prediction_count: int
    reference_count: int
    matches: tuple[MatchRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class ConnectorAttachmentMetrics:
    """Endpoint-level attachment accuracy for matched connector candidates.

    A reference endpoint counts as correct only when its connector was
    matched, the predicted endpoint attaches to the prediction-side owner
    that corresponds to the reference owner (via the node/container match),
    and the attachment side agrees. Endpoints of unmatched reference
    connectors stay in the denominator as misses.
    """

    endpoint_accuracy: float
    correct_endpoints: int
    endpoint_reference_count: int
    matched: int
    prediction_count: int
    reference_count: int
    matches: tuple[MatchRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class StructuralExactness:
    """Slide-level all-or-nothing structural agreement."""

    exact: bool
    family_exact: bool
    nodes_exact: bool
    containers_exact: bool
    connectors_exact: bool


@dataclass(slots=True, frozen=True)
class DetectorEvaluationReport:
    image_id: str
    reference_image_id: str
    iou_threshold: float
    family_proposals: FamilyProposalMetrics
    nodes: DetectionMetrics
    containers: DetectionMetrics
    connectors: ConnectorAttachmentMetrics
    structural: StructuralExactness

    def to_dict(self) -> dict[str, object]:
        payload = annotation_to_json(self)
        assert isinstance(payload, dict)
        return payload


@dataclass(slots=True)
class DetectorMetrics:
    iou_threshold: float = 0.5

    def evaluate(
        self,
        prediction: DetectorAnnotationDocument,
        reference: DetectorAnnotationDocument,
    ) -> DetectorEvaluationReport:
        family_matches = _match_entities(
            predictions=[
                _ComparableBBox(id=item.id, label=item.family.value, bbox=item.focus_bbox)
                for item in prediction.family_proposals
            ],
            references=[
                _ComparableBBox(id=item.id, label=item.family.value, bbox=item.focus_bbox)
                for item in reference.family_proposals
            ],
            iou_threshold=self.iou_threshold,
        )
        prediction_scene = prediction.primitive_scene or AnnotationPrimitiveScene()
        reference_scene = reference.primitive_scene or AnnotationPrimitiveScene()
        node_matches = _match_entities(
            predictions=[
                _ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox)
                for item in prediction_scene.nodes
            ],
            references=[
                _ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox)
                for item in reference_scene.nodes
            ],
            iou_threshold=self.iou_threshold,
        )
        container_matches = _match_entities(
            predictions=[
                _ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox)
                for item in prediction_scene.containers
            ],
            references=[
                _ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox)
                for item in reference_scene.containers
            ],
            iou_threshold=self.iou_threshold,
        )
        owner_map = {match.prediction_id: match.reference_id for match in (*node_matches, *container_matches)}
        connector_metrics = _connector_attachment_metrics(
            predictions=prediction_scene.connector_candidates,
            references=reference_scene.connector_candidates,
            owner_map=owner_map,
            iou_threshold=self.iou_threshold,
        )
        family_metrics = FamilyProposalMetrics(
            accuracy=_accuracy_from_matches(
                matched=len(family_matches),
                prediction_count=len(prediction.family_proposals),
                reference_count=len(reference.family_proposals),
            ),
            matched=len(family_matches),
            prediction_count=len(prediction.family_proposals),
            reference_count=len(reference.family_proposals),
            matches=family_matches,
        )
        node_metrics = _detection_metrics(
            matches=node_matches,
            prediction_count=len(prediction_scene.nodes),
            reference_count=len(reference_scene.nodes),
        )
        container_metrics = _detection_metrics(
            matches=container_matches,
            prediction_count=len(prediction_scene.containers),
            reference_count=len(reference_scene.containers),
        )
        return DetectorEvaluationReport(
            image_id=prediction.image_id,
            reference_image_id=reference.image_id,
            iou_threshold=self.iou_threshold,
            family_proposals=family_metrics,
            nodes=node_metrics,
            containers=container_metrics,
            connectors=connector_metrics,
            structural=_structural_exactness(
                family=family_metrics,
                nodes=node_metrics,
                containers=container_metrics,
                connectors=connector_metrics,
            ),
        )


def evaluate_detector_predictions(
    prediction: DetectorAnnotationDocument,
    reference: DetectorAnnotationDocument,
    *,
    iou_threshold: float = 0.5,
) -> DetectorEvaluationReport:
    return DetectorMetrics(iou_threshold=iou_threshold).evaluate(prediction, reference)


@dataclass(slots=True, frozen=True)
class _ComparableBBox:
    id: str
    label: str
    bbox: AnnotationBBox


def _match_entities(
    *,
    predictions: list[_ComparableBBox],
    references: list[_ComparableBBox],
    iou_threshold: float,
) -> tuple[MatchRecord, ...]:
    candidates: list[tuple[float, int, int]] = []
    for prediction_index, prediction in enumerate(predictions):
        for reference_index, reference in enumerate(references):
            if prediction.label != reference.label:
                continue
            iou = prediction.bbox.iou(reference.bbox)
            if iou >= iou_threshold:
                candidates.append((iou, prediction_index, reference_index))
    candidates.sort(key=lambda item: item[0], reverse=True)

    matched_predictions: set[int] = set()
    matched_references: set[int] = set()
    matches: list[MatchRecord] = []
    for iou, prediction_index, reference_index in candidates:
        if prediction_index in matched_predictions or reference_index in matched_references:
            continue
        matched_predictions.add(prediction_index)
        matched_references.add(reference_index)
        matches.append(
            MatchRecord(
                prediction_id=predictions[prediction_index].id,
                reference_id=references[reference_index].id,
                iou=iou,
            )
        )
    return tuple(matches)


def _detection_metrics(
    *,
    matches: tuple[MatchRecord, ...],
    prediction_count: int,
    reference_count: int,
) -> DetectionMetrics:
    true_positive = len(matches)
    false_positive = max(0, prediction_count - true_positive)
    false_negative = max(0, reference_count - true_positive)
    precision = _safe_ratio(true_positive, prediction_count, perfect_when_both_zero=reference_count == 0)
    recall = _safe_ratio(true_positive, reference_count, perfect_when_both_zero=prediction_count == 0)
    if precision + recall == 0.0:
        f1 = 1.0 if prediction_count == 0 and reference_count == 0 else 0.0
    else:
        f1 = (2.0 * precision * recall) / (precision + recall)
    return DetectionMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        prediction_count=prediction_count,
        reference_count=reference_count,
        matches=matches,
    )


def _connector_attachment_metrics(
    *,
    predictions: tuple[AnnotationConnectorCandidate, ...],
    references: tuple[AnnotationConnectorCandidate, ...],
    owner_map: dict[str, str],
    iou_threshold: float,
) -> ConnectorAttachmentMetrics:
    matches = _match_entities(
        predictions=[_ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox) for item in predictions],
        references=[_ComparableBBox(id=item.id, label=item.kind.value, bbox=item.bbox) for item in references],
        iou_threshold=iou_threshold,
    )
    prediction_lookup = {item.id: item for item in predictions}
    reference_lookup = {item.id: item for item in references}

    endpoint_reference_count = sum(
        sum(1 for endpoint in (item.start_endpoint, item.end_endpoint) if endpoint is not None)
        for item in references
    )
    correct_endpoints = 0
    for match in matches:
        predicted = prediction_lookup[match.prediction_id]
        referenced = reference_lookup[match.reference_id]
        endpoint_pairs = (
            (predicted.start_endpoint, referenced.start_endpoint),
            (predicted.end_endpoint, referenced.end_endpoint),
        )
        for predicted_endpoint, reference_endpoint in endpoint_pairs:
            if reference_endpoint is None:
                continue
            if _endpoint_attachment_correct(predicted_endpoint, reference_endpoint, owner_map=owner_map):
                correct_endpoints += 1

    if endpoint_reference_count == 0:
        endpoint_accuracy = 1.0 if not predictions or len(matches) == len(references) else 0.0
    else:
        endpoint_accuracy = correct_endpoints / float(endpoint_reference_count)
    return ConnectorAttachmentMetrics(
        endpoint_accuracy=endpoint_accuracy,
        correct_endpoints=correct_endpoints,
        endpoint_reference_count=endpoint_reference_count,
        matched=len(matches),
        prediction_count=len(predictions),
        reference_count=len(references),
        matches=matches,
    )


def _endpoint_attachment_correct(
    predicted: AnnotationConnectorEndpoint | None,
    reference: AnnotationConnectorEndpoint,
    *,
    owner_map: dict[str, str],
) -> bool:
    if reference.owner_id is None:
        return predicted is not None and predicted.owner_id is None
    if predicted is None or predicted.owner_id is None:
        return False
    return (
        owner_map.get(predicted.owner_id) == reference.owner_id
        and predicted.owner_kind == reference.owner_kind
        and predicted.side == reference.side
    )


def _structural_exactness(
    *,
    family: FamilyProposalMetrics,
    nodes: DetectionMetrics,
    containers: DetectionMetrics,
    connectors: ConnectorAttachmentMetrics,
) -> StructuralExactness:
    family_exact = family.accuracy == 1.0
    nodes_exact = nodes.f1 == 1.0
    containers_exact = containers.f1 == 1.0
    connectors_exact = (
        connectors.matched == connectors.reference_count
        and connectors.prediction_count == connectors.reference_count
        and connectors.correct_endpoints == connectors.endpoint_reference_count
    )
    return StructuralExactness(
        exact=family_exact and nodes_exact and containers_exact and connectors_exact,
        family_exact=family_exact,
        nodes_exact=nodes_exact,
        containers_exact=containers_exact,
        connectors_exact=connectors_exact,
    )


def _accuracy_from_matches(*, matched: int, prediction_count: int, reference_count: int) -> float:
    denominator = max(prediction_count, reference_count)
    if denominator == 0:
        return 1.0
    return matched / float(denominator)


def _safe_ratio(numerator: int, denominator: int, *, perfect_when_both_zero: bool) -> float:
    if denominator == 0:
        return 1.0 if perfect_when_both_zero else 0.0
    return numerator / float(denominator)
