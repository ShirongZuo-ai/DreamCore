"""Deterministic one-to-one matching for interval and point annotations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from dreamcore.validation.models import BenchmarkInterval, ValidationPoint


@dataclass(frozen=True)
class Match:
    reference_id: str
    detection_id: str
    overlap_s: float
    timing_offset_s: float


def _assign(cost: np.ndarray, valid: np.ndarray) -> list[tuple[int, int]]:
    if not cost.size or not np.any(valid):
        return []
    bounded = np.where(valid, cost, 1.0e12)
    rows, columns = linear_sum_assignment(bounded)
    return [
        (int(row), int(column))
        for row, column in zip(rows, columns, strict=True)
        if valid[row, column]
    ]


def match_intervals(
    references: Sequence[BenchmarkInterval],
    detections: Sequence[ValidationPoint],
    *,
    minimum_overlap_s: float,
) -> tuple[Match, ...]:
    """Maximize total overlap without assigning either event more than once."""

    refs = tuple(item for item in references if item.valid)
    dets = tuple(
        item
        for item in detections
        if item.onset_s is not None and item.end_s is not None and item.end_s > item.onset_s
    )
    overlap = np.zeros((len(refs), len(dets)), dtype=float)
    for row, reference in enumerate(refs):
        for column, detection in enumerate(dets):
            overlap[row, column] = max(
                0.0,
                min(reference.end_s, float(detection.end_s))
                - max(reference.onset_s, float(detection.onset_s)),
            )
    valid = overlap > minimum_overlap_s
    # Tiny stable index penalties make equal-overlap assignments reproducible.
    tie = (
        np.arange(len(refs), dtype=float)[:, None] * max(1, len(dets))
        + np.arange(len(dets), dtype=float)[None, :]
    ) * 1.0e-12
    assignments = _assign(-overlap + tie, valid)
    return tuple(
        Match(
            reference_id=refs[row].event_id,
            detection_id=dets[column].event_id,
            overlap_s=float(overlap[row, column]),
            timing_offset_s=(
                dets[column].timestamp_s - (refs[row].onset_s + refs[row].end_s) / 2.0
            ),
        )
        for row, column in sorted(assignments)
    )


def match_points_to_intervals(
    references: Sequence[BenchmarkInterval],
    detections: Sequence[ValidationPoint],
    *,
    tolerance_s: float,
) -> tuple[Match, ...]:
    """Match candidate landmarks to expert intervals with declared padding."""

    refs = tuple(item for item in references if item.valid)
    dets = tuple(detections)
    cost = np.zeros((len(refs), len(dets)), dtype=float)
    valid = np.zeros(cost.shape, dtype=bool)
    for row, reference in enumerate(refs):
        midpoint = (reference.onset_s + reference.end_s) / 2.0
        for column, detection in enumerate(dets):
            distance = max(
                reference.onset_s - detection.timestamp_s,
                detection.timestamp_s - reference.end_s,
                0.0,
            )
            valid[row, column] = distance <= tolerance_s
            cost[row, column] = distance * 1.0e6 + abs(detection.timestamp_s - midpoint)
    assignments = _assign(cost, valid)
    return tuple(
        Match(
            reference_id=refs[row].event_id,
            detection_id=dets[column].event_id,
            overlap_s=0.0,
            timing_offset_s=(
                dets[column].timestamp_s - (refs[row].onset_s + refs[row].end_s) / 2.0
            ),
        )
        for row, column in sorted(assignments)
    )


def detection_metrics(
    reference_count: int, detection_count: int, matched_count: int
) -> dict[str, float | int | None]:
    precision = matched_count / detection_count if detection_count else None
    recall = matched_count / reference_count if reference_count else None
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    return {
        "reference_events": reference_count,
        "detector_events": detection_count,
        "matched_events": matched_count,
        "unmatched_detector_events": detection_count - matched_count,
        "missed_reference_events": reference_count - matched_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
