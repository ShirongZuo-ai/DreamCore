"""Config-driven sleep-stage label normalization and interval handling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class StageInterval:
    """One normalized, half-open sleep-stage interval."""

    start_s: float
    end_s: float
    label: str
    raw_labels: tuple[str, ...]

    @property
    def duration_s(self) -> float:
        """Return interval duration in seconds."""
        return self.end_s - self.start_s


def _required_mapping(config: Mapping[str, Any], key: str, path: str = "") -> Mapping[str, Any]:
    """Return a required mapping configuration section."""
    try:
        section = config[key]
    except KeyError as error:
        full_path = f"{path}.{key}" if path else key
        raise ValueError(f"Missing required config section: {full_path}") from error
    if not isinstance(section, Mapping):
        full_path = f"{path}.{key}" if path else key
        raise TypeError(f"Config section '{full_path}' must be a mapping")
    return section


def _sleep_staging_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return _required_mapping(config, "sleep_staging")


def _label_lookup(config: Mapping[str, Any]) -> dict[str, str]:
    stage_config = _sleep_staging_config(config)
    stage_labels = _required_mapping(stage_config, "stage_labels", "sleep_staging")
    lookup: dict[str, str] = {}
    for normalized_label, raw_labels in stage_labels.items():
        if not isinstance(raw_labels, Sequence) or isinstance(raw_labels, str):
            raise TypeError(f"sleep_staging.stage_labels.{normalized_label} must be a sequence")
        for raw_label in raw_labels:
            raw_label = str(raw_label)
            previous = lookup.get(raw_label)
            if previous is not None and previous != str(normalized_label):
                raise ValueError(
                    f"Raw label '{raw_label}' maps to both '{previous}' and '{normalized_label}'"
                )
            lookup[raw_label] = str(normalized_label)
    return lookup


def normalize_label(raw_label: str, config: Mapping[str, Any]) -> str:
    """Map one raw dataset label to a unified project label."""
    lookup = _label_lookup(config)
    raw_label = str(raw_label)
    if raw_label in lookup:
        return lookup[raw_label]

    stage_config = _sleep_staging_config(config)
    policy = str(stage_config["unknown_label_policy"])
    if policy == "map_to_unknown":
        return str(stage_config["unknown_label"])
    if policy == "raise":
        raise ValueError(f"Unrecognized sleep-stage label: {raw_label}")
    raise ValueError(f"Unsupported sleep_staging.unknown_label_policy: {policy}")


def clip_annotations(annotations: np.ndarray, raw_duration_s: float) -> np.ndarray:
    """Clip annotations to the half-open PSG range ``[0, raw_duration_s)``."""
    if raw_duration_s <= 0:
        raise ValueError("raw_duration_s must be positive")
    required_fields = {"onset", "duration", "description"}
    if annotations.dtype.names is None or not required_fields.issubset(annotations.dtype.names):
        raise TypeError("annotations must contain onset, duration, and description fields")

    clipped_rows: list[tuple[float, float, str]] = []
    order = np.argsort(annotations["onset"], kind="stable")
    for annotation in annotations[order]:
        start_s = max(0.0, float(annotation["onset"]))
        end_s = min(
            raw_duration_s,
            float(annotation["onset"]) + float(annotation["duration"]),
        )
        if end_s > start_s:
            clipped_rows.append((start_s, end_s - start_s, str(annotation["description"])))

    clipped = np.empty(
        len(clipped_rows),
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    for index, (onset, duration, description) in enumerate(clipped_rows):
        clipped[index] = (onset, duration, description)
    return clipped


def normalize_annotations(
    annotations: np.ndarray,
    raw_duration_s: float,
    config: Mapping[str, Any],
) -> list[StageInterval]:
    """Clip and normalize an annotation array into stage intervals."""
    clipped = clip_annotations(annotations, raw_duration_s)
    return [
        StageInterval(
            start_s=float(annotation["onset"]),
            end_s=float(annotation["onset"] + annotation["duration"]),
            label=normalize_label(str(annotation["description"]), config),
            raw_labels=(str(annotation["description"]),),
        )
        for annotation in clipped
    ]


def _combined_raw_labels(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*first, *second)))


def merge_adjacent_intervals(
    intervals: Sequence[StageInterval], config: Mapping[str, Any]
) -> list[StageInterval]:
    """Merge adjacent equal labels when their gap is within config tolerance."""
    stage_config = _sleep_staging_config(config)
    tolerance_s = float(stage_config["merge_tolerance_s"])
    if tolerance_s < 0:
        raise ValueError("sleep_staging.merge_tolerance_s must be non-negative")
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda interval: interval.start_s)
    merged = [sorted_intervals[0]]
    for interval in sorted_intervals[1:]:
        previous = merged[-1]
        gap_s = interval.start_s - previous.end_s
        if interval.label == previous.label and gap_s <= tolerance_s:
            merged[-1] = StageInterval(
                start_s=previous.start_s,
                end_s=max(previous.end_s, interval.end_s),
                label=previous.label,
                raw_labels=_combined_raw_labels(previous.raw_labels, interval.raw_labels),
            )
        else:
            merged.append(interval)
    return merged
