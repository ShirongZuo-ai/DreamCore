"""Pure descriptive statistics for frozen cross-dataset EOG validation."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar


@dataclass(frozen=True)
class EventMatch:
    event_a_id: str
    event_b_id: str
    timestamp_a: float
    timestamp_b: float
    absolute_difference_s: float


def match_events(
    events_a: Sequence[Mapping[str, Any]],
    events_b: Sequence[Mapping[str, Any]],
    tolerance_s: float,
) -> tuple[EventMatch, ...]:
    """Greedily assign closest deterministic one-to-one temporal pairs."""

    if tolerance_s < 0:
        raise ValueError("event matching tolerance must be non-negative")
    pairs = []
    for event_a in events_a:
        for event_b in events_b:
            timestamp_a = float(event_a["timestamp"])
            timestamp_b = float(event_b["timestamp"])
            difference = abs(timestamp_a - timestamp_b)
            if difference <= tolerance_s:
                pairs.append(
                    (
                        difference,
                        timestamp_a,
                        timestamp_b,
                        str(event_a["candidate_id"]),
                        str(event_b["candidate_id"]),
                    )
                )
    pairs.sort()
    matched_a: set[str] = set()
    matched_b: set[str] = set()
    output = []
    for difference, timestamp_a, timestamp_b, event_a_id, event_b_id in pairs:
        if event_a_id in matched_a or event_b_id in matched_b:
            continue
        matched_a.add(event_a_id)
        matched_b.add(event_b_id)
        output.append(
            EventMatch(
                event_a_id=event_a_id,
                event_b_id=event_b_id,
                timestamp_a=timestamp_a,
                timestamp_b=timestamp_b,
                absolute_difference_s=difference,
            )
        )
    return tuple(output)


def assign_event_stage(
    timestamp: float,
    annotations: Sequence[Mapping[str, Any]],
    *,
    unknown_label: str,
) -> dict[str, Any]:
    """Assign the half-open annotation active at one candidate timestamp."""

    for annotation in annotations:
        start = float(annotation["start_seconds"])
        end = start + float(annotation["duration_seconds"])
        if start <= timestamp < end:
            return {
                "raw_label": str(annotation.get("raw_label", annotation.get("label", ""))),
                "normalized_label": str(
                    annotation.get("normalized_label", annotation.get("label", unknown_label))
                ),
                "scorer": annotation.get("scorer"),
                "scoring_standard": annotation.get("scoring_standard"),
            }
    return {
        "raw_label": unknown_label,
        "normalized_label": unknown_label,
        "scorer": None,
        "scoring_standard": None,
    }


def stage_exposure(
    annotations: Sequence[Mapping[str, Any]],
    *,
    recording_duration_s: float,
    canonical_labels: Sequence[str],
) -> dict[str, float]:
    """Calculate annotation exposure in seconds, preserving explicit zero exposure."""

    exposure = {label: 0.0 for label in canonical_labels}
    for annotation in annotations:
        start = max(0.0, float(annotation["start_seconds"]))
        end = min(
            recording_duration_s,
            start + max(0.0, float(annotation["duration_seconds"])),
        )
        label = str(annotation.get("normalized_label", annotation.get("label", "UNKNOWN")))
        if label not in exposure:
            label = "UNKNOWN"
        exposure[label] += max(0.0, end - start)
    return exposure


T = TypeVar("T")


def deterministic_stratified_sample(
    items: Sequence[T],
    *,
    target: int,
    seed: int,
    stratum: Callable[[T], tuple[str, ...]],
    identity: Callable[[T], str],
) -> tuple[T, ...]:
    """Round-robin across deterministically shuffled strata without score sorting."""

    if target < 0:
        raise ValueError("sample target must be non-negative")
    groups: dict[tuple[str, ...], list[T]] = defaultdict(list)
    for item in items:
        groups[stratum(item)].append(item)
    randomizer = random.Random(seed)
    for key in sorted(groups):
        values = groups[key]
        values.sort(key=identity)
        randomizer.shuffle(values)
    selected = []
    ordered_keys = sorted(groups)
    while len(selected) < min(target, len(items)):
        advanced = False
        for key in ordered_keys:
            if groups[key]:
                selected.append(groups[key].pop())
                advanced = True
                if len(selected) == min(target, len(items)):
                    break
        if not advanced:
            break
    return tuple(selected)


def build_control_sample(
    annotations: Sequence[Mapping[str, Any]],
    event_timestamps: Iterable[float],
    *,
    dataset_id: str,
    stage: str,
    target: int,
    seed: int,
    window_s: float,
    exclusion_s: float,
    minimum_separation_s: float,
) -> tuple[dict[str, Any], ...]:
    """Select deterministic non-candidate windows inside stage annotations."""

    if window_s <= 0 or exclusion_s < 0 or minimum_separation_s < 0:
        raise ValueError("control sampling durations are invalid")
    events = sorted(float(value) for value in event_timestamps)
    candidates = []
    step = max(window_s, minimum_separation_s)
    for annotation in annotations:
        normalized = str(annotation.get("normalized_label", annotation.get("label", "UNKNOWN")))
        if normalized != stage:
            continue
        annotation_start = float(annotation["start_seconds"])
        annotation_end = annotation_start + float(annotation["duration_seconds"])
        center = annotation_start + window_s / 2
        while center + window_s / 2 <= annotation_end:
            if all(abs(center - event) > exclusion_s + window_s / 2 for event in events):
                candidates.append(center)
            center += step
    randomizer = random.Random(seed)
    candidates.sort()
    randomizer.shuffle(candidates)
    selected = sorted(candidates[:target])
    return tuple(
        {
            "control_id": f"{dataset_id}:{stage}:{index:03d}",
            "stage": stage,
            "start_s": center - window_s / 2,
            "end_s": center + window_s / 2,
            "center_s": center,
        }
        for index, center in enumerate(selected, start=1)
    )
