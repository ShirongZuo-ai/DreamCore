"""Sleep staging — label mapping, N2/N3 epoch extraction."""

from dreamcore.sleep_staging.labels import (
    StageInterval,
    clip_annotations,
    merge_adjacent_intervals,
    normalize_annotations,
    normalize_label,
)
from dreamcore.sleep_staging.segments import (
    N3Segment,
    extract_n3_segments,
    filter_n3_intervals,
    resolve_eeg_channels,
)

__all__ = [
    "N3Segment",
    "StageInterval",
    "clip_annotations",
    "extract_n3_segments",
    "filter_n3_intervals",
    "merge_adjacent_intervals",
    "normalize_annotations",
    "normalize_label",
    "resolve_eeg_channels",
]
