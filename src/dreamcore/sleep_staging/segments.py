"""N3 EEG segment selection and extraction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import mne
import numpy as np

from dreamcore.sleep_staging.labels import StageInterval


@dataclass(frozen=True)
class N3Segment:
    """One extracted, sample-aligned N3 EEG segment."""

    segment_id: str
    start_s: float
    end_s: float
    normalized_label: str
    raw_labels: tuple[str, ...]
    channel_names: tuple[str, ...]
    sampling_rate_hz: float
    data: np.ndarray = field(repr=False, compare=False)

    @property
    def duration_s(self) -> float:
        """Return sample-aligned duration in seconds."""
        return self.end_s - self.start_s

    @property
    def n_samples(self) -> int:
        """Return the number of time samples per channel."""
        return int(self.data.shape[1])


def _extraction_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        section = config["n3_extraction"]
    except KeyError as error:
        raise ValueError("Missing required config section: n3_extraction") from error
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'n3_extraction' must be a mapping")
    return section


def filter_n3_intervals(
    intervals: Sequence[StageInterval], config: Mapping[str, Any]
) -> list[StageInterval]:
    """Select N3 intervals meeting the configured minimum duration."""
    extraction_config = _extraction_config(config)
    target_label = str(extraction_config["target_label"])
    min_duration_s = float(extraction_config["min_segment_duration_s"])
    if min_duration_s < 0:
        raise ValueError("n3_extraction.min_segment_duration_s must be non-negative")
    return [
        interval
        for interval in intervals
        if interval.label == target_label and interval.duration_s >= min_duration_s
    ]


def resolve_eeg_channels(
    raw: mne.io.BaseRaw,
    config: Mapping[str, Any],
    channel_names: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Resolve configured or CLI-selected channels and require EEG channel types."""
    extraction_config = _extraction_config(config)
    selected = channel_names if channel_names is not None else extraction_config["eeg_channels"]
    if not isinstance(selected, Sequence) or isinstance(selected, str) or not selected:
        raise ValueError("At least one EEG channel must be supplied by config or CLI")
    selected_names = tuple(str(channel) for channel in selected)
    if len(set(selected_names)) != len(selected_names):
        raise ValueError("Selected EEG channels must be unique")

    channel_types = dict(zip(raw.ch_names, raw.get_channel_types(), strict=True))
    missing = [channel for channel in selected_names if channel not in channel_types]
    if missing:
        raise ValueError(f"Selected channels not found in recording: {missing}")
    non_eeg = [channel for channel in selected_names if channel_types[channel] != "eeg"]
    if non_eeg:
        raise ValueError(f"Selected channels are not EEG channels: {non_eeg}")
    return selected_names


def extract_n3_segments(
    raw: mne.io.BaseRaw,
    intervals: Sequence[StageInterval],
    source_id: str,
    config: Mapping[str, Any],
    channel_names: Sequence[str] | None = None,
) -> list[N3Segment]:
    """Extract configured EEG channels from qualifying N3 intervals."""
    selected_channels = resolve_eeg_channels(raw, config, channel_names)
    selected_intervals = filter_n3_intervals(intervals, config)
    sfreq = float(raw.info["sfreq"])
    segments: list[N3Segment] = []

    for index, interval in enumerate(selected_intervals, start=1):
        start_sample = max(0, int(round(interval.start_s * sfreq)))
        end_sample = min(int(raw.n_times), int(round(interval.end_s * sfreq)))
        if end_sample <= start_sample:
            continue
        data = raw.get_data(
            picks=list(selected_channels),
            start=start_sample,
            stop=end_sample,
        )
        segments.append(
            N3Segment(
                segment_id=f"{source_id}_n3_{index:04d}",
                start_s=start_sample / sfreq,
                end_s=end_sample / sfreq,
                normalized_label=interval.label,
                raw_labels=interval.raw_labels,
                channel_names=selected_channels,
                sampling_rate_hz=sfreq,
                data=data,
            )
        )
    return segments
