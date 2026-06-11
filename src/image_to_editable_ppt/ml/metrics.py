from __future__ import annotations

from dataclasses import dataclass

from image_to_editable_ppt.ml.annotation_schema import (
    AnnotationBBox,
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
class DetectorEvaluationReport:
    image_id: str
    reference_image_id: str
    iou_threshold: float
    family_proposals: FamilyProposalMetrics
    nodes: DetectionMetrics
    containers: DetectionMetrics

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
        return DetectorEvaluationReport(
            image_id=prediction.image_id,
            reference_image_id=reference.image_id,
            iou_threshold=self.iou_threshold,
            family_proposals=FamilyProposalMetrics(
                accuracy=_accuracy_from_matches(
                    matched=len(family_matches),
                    prediction_count=len(prediction.family_proposals),
                    reference_count=len(reference.family_proposals),
                ),
                matched=len(family_matches),
                prediction_count=len(prediction.family_proposals),
                reference_count=len(reference.family_proposals),
                matches=family_matches,
            ),
            nodes=_detection_metrics(
                matches=node_matches,
                prediction_count=len(prediction_scene.nodes),
                reference_count=len(reference_scene.nodes),
            ),
            containers=_detection_metrics(
                matches=container_matches,
                prediction_count=len(prediction_scene.containers),
                reference_count=len(reference_scene.containers),
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


def _accuracy_from_matches(*, matched: int, prediction_count: int, reference_count: int) -> float:
    denominator = max(prediction_count, reference_count)
    if denominator == 0:
        return 1.0
    return matched / float(denominator)


def _safe_ratio(numerator: int, denominator: int, *, perfect_when_both_zero: bool) -> float:
    if denominator == 0:
        return 1.0 if perfect_when_both_zero else 0.0
    return numerator / float(denominator)
