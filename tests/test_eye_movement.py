"""Tests for the stage-agnostic Eye Movement / EOG V1 pipeline."""

from copy import deepcopy
from pathlib import Path

import numpy as np

from dreamcore.config import load_config
from dreamcore.eye_movement import discover_eog_channels, extract_eye_movement_track


def _config():
    return deepcopy(load_config(Path("configs/default.yaml")))


def test_eog_discovery_uses_metadata_type_or_configured_label_without_substitution():
    config = _config()
    names = ["frontal", "Horizontal EOG", "chin"]

    assert discover_eog_channels(names, ["eeg", "eeg", "emg"], config) == ("Horizontal EOG",)
    assert discover_eog_channels(names, ["eeg", "eog", "emg"], config) == ("Horizontal EOG",)
    assert discover_eog_channels(["frontal", "chin"], ["eeg", "emg"], config) == ()


def test_feature_windows_use_window_end_timestamps_and_preserve_raw_input():
    config = _config()
    sampling_rate_hz = 50.0
    duration_s = 12.0
    times = np.arange(int(duration_s * sampling_rate_hz)) / sampling_rate_hz
    signal = 12.0 * np.sin(2 * np.pi * 0.8 * times)
    original = signal.copy()

    track = extract_eye_movement_track(
        signal,
        sampling_rate_hz,
        "fixture-eog",
        "fixture-session",
        "2020-01-01T00:00:00+00:00",
        config,
    )

    assert np.array_equal(signal, original)
    assert len(track.features) == 9
    assert track.features[0].window_start_s == 0.0
    assert track.features[0].window_end_s == 4.0
    assert track.features[-1].window_end_s == 12.0
    assert track.features[0].absolute_window_end == "2020-01-01T00:00:04+00:00"
    assert all(row.feature_provenance == "derived" for row in track.features)


def test_activity_burst_produces_interpretable_candidate_not_rem_label():
    config = _config()
    sampling_rate_hz = 50.0
    duration_s = 180.0
    times = np.arange(int(duration_s * sampling_rate_hz)) / sampling_rate_hz
    signal = 4.0 * np.sin(2 * np.pi * 0.7 * times)
    burst = (times >= 90.0) & (times < 94.0)
    signal[burst] += 120.0 * np.sin(2 * np.pi * 0.8 * (times[burst] - 90.0))

    track = extract_eye_movement_track(
        signal, sampling_rate_hz, "fixture-eog", "fixture-session", None, config
    )

    assert track.events
    assert any(88.0 <= event.timestamp <= 96.0 for event in track.events)
    assert all(event.event_type == "eye_movement_candidate" for event in track.events)
    assert all(event.polarity in {"positive", "negative"} for event in track.events)
    assert all(0.0 <= event.confidence <= 1.0 for event in track.events)
    assert not any("rem" in event.event_type.casefold() for event in track.events)


def test_short_flat_and_nan_signals_are_explicitly_unavailable():
    config = _config()
    sampling_rate_hz = 50.0
    short = extract_eye_movement_track(
        np.zeros(10), sampling_rate_hz, "fixture-eog", "fixture", None, config
    )
    assert short.features == ()
    assert short.coverage_start_s is None
    assert short.rejection_reasons == {"insufficient_samples": 1}

    flat = extract_eye_movement_track(
        np.zeros(int(10 * sampling_rate_hz)),
        sampling_rate_hz,
        "fixture-eog",
        "fixture",
        None,
        config,
    )
    assert flat.features
    assert all(row.signal_quality == "invalid" for row in flat.features)
    assert all(row.activity_score is None for row in flat.features)
    assert flat.events == ()

    with_nan = np.sin(np.arange(int(10 * sampling_rate_hz)) / sampling_rate_hz)
    with_nan[: int(2 * sampling_rate_hz)] = np.nan
    nan_track = extract_eye_movement_track(
        with_nan, sampling_rate_hz, "fixture-eog", "fixture", None, config
    )
    assert any(
        "insufficient_finite_samples" in row.signal_quality_reasons for row in nan_track.features
    )
