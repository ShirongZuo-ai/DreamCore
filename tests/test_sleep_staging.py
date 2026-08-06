"""Tests for label normalization and N3 EEG extraction."""

from pathlib import Path

import mne
import numpy as np
import pytest

from dreamcore.sleep_staging.labels import (
    StageInterval,
    clip_annotations,
    merge_adjacent_intervals,
    normalize_annotations,
    normalize_label,
)
from dreamcore.sleep_staging.segments import (
    extract_n3_segments,
    filter_n3_intervals,
    resolve_eeg_channels,
)


@pytest.fixture
def staging_config(tmp_path: Path) -> dict:
    return {
        "sleep_staging": {
            "stage_labels": {
                "W": ["Sleep stage W"],
                "N1": ["Sleep stage 1"],
                "N2": ["Sleep stage 2"],
                "N3": ["Sleep stage 3", "Sleep stage 4"],
                "REM": ["Sleep stage R"],
                "UNKNOWN": ["Sleep stage ?"],
                "MOVEMENT": ["Movement time"],
            },
            "unknown_label_policy": "map_to_unknown",
            "unknown_label": "UNKNOWN",
            "merge_tolerance_s": 0.0,
        },
        "n3_extraction": {
            "target_label": "N3",
            "min_segment_duration_s": 2.0,
            "eeg_channels": ["EEG A", "EEG B"],
            "output_csv": str(tmp_path / "segments.csv"),
            "output_json": str(tmp_path / "segments.json"),
            "json_indent": 2,
        },
    }


def _annotations(rows: list[tuple[float, float, str]]) -> np.ndarray:
    annotations = np.empty(
        len(rows),
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    for index, row in enumerate(rows):
        annotations[index] = row
    return annotations


@pytest.mark.parametrize(
    ("raw_label", "expected"),
    [
        ("Sleep stage W", "W"),
        ("Sleep stage 1", "N1"),
        ("Sleep stage 2", "N2"),
        ("Sleep stage 3", "N3"),
        ("Sleep stage 4", "N3"),
        ("Sleep stage R", "REM"),
        ("Sleep stage ?", "UNKNOWN"),
        ("Movement time", "MOVEMENT"),
    ],
)
def test_known_label_mapping(staging_config, raw_label, expected):
    assert normalize_label(raw_label, staging_config) == expected


def test_unknown_label_policy_maps_or_raises(staging_config):
    assert normalize_label("unexpected", staging_config) == "UNKNOWN"

    staging_config["sleep_staging"]["unknown_label_policy"] = "raise"
    with pytest.raises(ValueError, match="Unrecognized"):
        normalize_label("unexpected", staging_config)


def test_annotations_are_clipped_to_psg_range():
    annotations = _annotations(
        [(-5.0, 10.0, "Sleep stage W"), (8.0, 5.0, "Sleep stage 2"), (10.0, 2.0, "Sleep stage ?")]
    )

    clipped = clip_annotations(annotations, raw_duration_s=10.0)

    assert len(clipped) == 2
    np.testing.assert_array_equal(clipped["onset"], [0.0, 8.0])
    np.testing.assert_array_equal(clipped["duration"], [5.0, 2.0])


def test_adjacent_stage_3_and_4_merge_as_n3(staging_config):
    annotations = _annotations([(0.0, 30.0, "Sleep stage 3"), (30.0, 30.0, "Sleep stage 4")])
    normalized = normalize_annotations(annotations, 60.0, staging_config)

    merged = merge_adjacent_intervals(normalized, staging_config)

    assert merged == [StageInterval(0.0, 60.0, "N3", ("Sleep stage 3", "Sleep stage 4"))]


def test_non_contiguous_n3_intervals_do_not_merge(staging_config):
    annotations = _annotations([(0.0, 30.0, "Sleep stage 3"), (31.0, 30.0, "Sleep stage 4")])
    normalized = normalize_annotations(annotations, 61.0, staging_config)

    merged = merge_adjacent_intervals(normalized, staging_config)

    assert len(merged) == 2


def test_n3_gap_within_configured_tolerance_is_merged(staging_config):
    staging_config["sleep_staging"]["merge_tolerance_s"] = 1.0
    annotations = _annotations([(0.0, 30.0, "Sleep stage 3"), (31.0, 30.0, "Sleep stage 4")])
    normalized = normalize_annotations(annotations, 61.0, staging_config)

    merged = merge_adjacent_intervals(normalized, staging_config)

    assert merged == [StageInterval(0.0, 61.0, "N3", ("Sleep stage 3", "Sleep stage 4"))]


def test_minimum_n3_duration_filter(staging_config):
    intervals = [
        StageInterval(0.0, 1.0, "N3", ("Sleep stage 3",)),
        StageInterval(2.0, 4.0, "N3", ("Sleep stage 4",)),
        StageInterval(4.0, 8.0, "N2", ("Sleep stage 2",)),
    ]

    filtered = filter_n3_intervals(intervals, staging_config)

    assert filtered == [StageInterval(2.0, 4.0, "N3", ("Sleep stage 4",))]


def test_eeg_channel_selection_and_segment_sample_count(staging_config):
    info = mne.create_info(
        ["EEG A", "EEG B", "Resp"],
        sfreq=10.0,
        ch_types=["eeg", "eeg", "resp"],
    )
    raw = mne.io.RawArray(np.arange(150.0).reshape(3, 50), info, verbose=False)
    intervals = [StageInterval(1.0, 3.0, "N3", ("Sleep stage 3",))]

    segments = extract_n3_segments(raw, intervals, "synthetic", staging_config)

    assert resolve_eeg_channels(raw, staging_config) == ("EEG A", "EEG B")
    assert len(segments) == 1
    assert segments[0].channel_names == ("EEG A", "EEG B")
    assert segments[0].data.shape == (2, 20)
    assert segments[0].n_samples == 20
    assert segments[0].duration_s == 2.0
    assert segments[0].n_samples == segments[0].duration_s * segments[0].sampling_rate_hz


def test_non_eeg_channel_selection_is_rejected(staging_config):
    info = mne.create_info(["EEG A", "Resp"], sfreq=10.0, ch_types=["eeg", "resp"])
    raw = mne.io.RawArray(np.zeros((2, 10)), info, verbose=False)

    with pytest.raises(ValueError, match="not EEG"):
        resolve_eeg_channels(raw, staging_config, ["Resp"])
