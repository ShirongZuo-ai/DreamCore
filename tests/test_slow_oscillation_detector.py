"""Synthetic tests for auditable slow-oscillation candidate detection."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from dreamcore.config import load_config
from dreamcore.preprocessing.eeg import PreprocessedEEG
from dreamcore.slow_oscillation.detector import (
    detect_slow_oscillations,
    find_zero_crossings,
    get_detector_profile,
)


def _profile(**overrides):
    profile = {
        "detection_band": {"low_hz": 0.5, "high_hz": 2.0, "method": "fir"},
        "duration": {
            "negative_halfwave_min_s": 0.3,
            "negative_halfwave_max_s": 0.7,
            "full_cycle_min_s": 0.8,
            "full_cycle_max_s": 1.2,
        },
        "amplitude": {
            "strategy": "none",
            "metric": "peak_to_peak_amplitude_uv",
            "fixed_min_uv": None,
            "quantile": 0.5,
        },
        "artifact_rejection": {
            "boundary_exclusion_s": 0.0,
            "max_peak_to_peak_uv": 1000.0,
            "invalid_time_masks": [],
        },
    }
    profile.update(overrides)
    return profile


def _config(profile=None):
    return {
        "slow_oscillation": {
            "active_profile": "test",
            "amplitude_scale_to_uv": 1.0,
            "profiles": {"test": profile or _profile()},
        }
    }


def _eeg(data, sfreq=100.0, start_s=10.0):
    values = np.atleast_2d(np.asarray(data, dtype=float))
    channels = tuple(f"EEG {index + 1}" for index in range(values.shape[0]))
    duration_s = values.shape[1] / sfreq
    return PreprocessedEEG(
        segment_id="synthetic_n3_0001",
        channel_names=channels,
        raw_data=values.copy(),
        data=values.copy(),
        original_sampling_rate_hz=sfreq,
        output_sampling_rate_hz=sfreq,
        start_s=start_s,
        end_s=start_s + duration_s,
        profile_name="synthetic",
        metadata={},
    )


def _sine(duration_s=10.0, sfreq=100.0, frequency_hz=1.0, amplitude=20.0):
    times = np.arange(int(duration_s * sfreq)) / sfreq
    return -amplitude * np.sin(2 * np.pi * frequency_hz * times)


def test_default_config_has_broad_and_strict_research_profiles():
    config = load_config(Path("configs/default.yaml"))

    profile_name, profile = get_detector_profile(config)

    assert profile_name == "strict_slow_oscillation"
    assert profile["amplitude"]["strategy"] == "adaptive_quantile"
    assert set(config["slow_oscillation"]["profiles"]) == {
        "broad_slow_wave",
        "strict_slow_oscillation",
    }


def test_known_sine_zero_crossing_times_and_directions():
    sfreq = 100.0
    crossings = find_zero_crossings(_sine(duration_s=3.0, sfreq=sfreq), sfreq, start_s=5.0)

    assert [crossing.direction for crossing in crossings[:5]] == [
        "downward",
        "upward",
        "downward",
        "upward",
        "downward",
    ]
    np.testing.assert_allclose(
        [crossing.time_s for crossing in crossings[:5]],
        [5.0, 5.5, 6.0, 6.5, 7.0],
        atol=1e-12,
    )


def test_trough_peak_and_cycle_features_are_located():
    detection = detect_slow_oscillations(_eeg(_sine()), _config())
    event = next(event for event in detection.events if 13.0 < event.event_start_s < 17.0)

    assert event.accepted
    assert event.trough_time_s == pytest.approx(event.event_start_s + 0.25, abs=0.03)
    assert event.upward_zero_crossing_s == pytest.approx(event.event_start_s + 0.5, abs=0.03)
    assert event.positive_peak_time_s == pytest.approx(event.event_start_s + 0.75, abs=0.03)
    assert event.negative_halfwave_duration_s == pytest.approx(0.5, abs=0.03)
    assert event.full_cycle_duration_s == pytest.approx(1.0, abs=0.03)
    assert event.estimated_frequency_hz == pytest.approx(1.0, abs=0.03)
    assert event.trough_amplitude_uv < 0
    assert event.positive_peak_amplitude_uv > 0
    assert event.down_slope < 0
    assert event.up_slope > 0


def test_duration_filtering_retains_rejected_candidates():
    profile = _profile(
        duration={
            "negative_halfwave_min_s": 0.6,
            "negative_halfwave_max_s": 0.8,
            "full_cycle_min_s": 1.1,
            "full_cycle_max_s": 1.3,
        }
    )
    events = detect_slow_oscillations(_eeg(_sine()), _config(profile)).events

    assert events
    assert not any(event.accepted for event in events)
    assert all("negative_halfwave_too_short" in event.rejection_reasons for event in events)
    assert all("full_cycle_too_short" in event.rejection_reasons for event in events)


def test_fixed_amplitude_strategy_accepts_and_rejects_by_threshold():
    amplitude = {
        "strategy": "fixed",
        "metric": "peak_to_peak_amplitude_uv",
        "fixed_min_uv": 50.0,
        "quantile": 0.5,
    }
    events = detect_slow_oscillations(
        _eeg(_sine(amplitude=20.0)), _config(_profile(amplitude=amplitude))
    ).events

    assert events
    assert not any(event.accepted for event in events)
    assert all(event.amplitude_threshold_uv == 50.0 for event in events)
    assert all("below_amplitude_threshold" in event.rejection_reasons for event in events)


def test_adaptive_amplitude_strategy_is_computed_per_channel():
    first = np.concatenate(
        [_sine(duration_s=2.0, amplitude=amplitude) for amplitude in (10.0, 20.0, 30.0, 40.0)]
    )
    second = first * 2.0
    amplitude = {
        "strategy": "adaptive_quantile",
        "metric": "peak_to_peak_amplitude_uv",
        "fixed_min_uv": None,
        "quantile": 0.5,
    }
    detection = detect_slow_oscillations(
        _eeg(np.vstack((first, second))),
        _config(_profile(amplitude=amplitude)),
    )

    assert detection.amplitude_thresholds_uv["EEG 1"] is not None
    assert detection.amplitude_thresholds_uv["EEG 2"] is not None
    assert detection.amplitude_thresholds_uv["EEG 2"] > detection.amplitude_thresholds_uv["EEG 1"]
    for channel in detection.channel_names:
        channel_events = [event for event in detection.events if event.channel == channel]
        assert any(event.accepted for event in channel_events)
        assert any(
            "below_amplitude_threshold" in event.rejection_reasons for event in channel_events
        )


def test_boundary_exclusion_is_auditable():
    artifacts = {
        "boundary_exclusion_s": 1.1,
        "max_peak_to_peak_uv": 1000.0,
        "invalid_time_masks": [],
    }
    events = detect_slow_oscillations(
        _eeg(_sine(duration_s=8.0)), _config(_profile(artifact_rejection=artifacts))
    ).events

    assert any("near_boundary" in event.rejection_reasons for event in events)
    assert any(event.accepted for event in events)


def test_nan_and_extreme_amplitude_are_rejected():
    values = _sine(duration_s=8.0)
    values[225:275] = np.nan
    values[500:600] *= 20.0
    artifacts = {
        "boundary_exclusion_s": 0.0,
        "max_peak_to_peak_uv": 100.0,
        "invalid_time_masks": [],
    }
    events = detect_slow_oscillations(
        _eeg(values), _config(_profile(artifact_rejection=artifacts))
    ).events

    assert any("nan_or_nonfinite" in event.rejection_reasons for event in events)
    assert any("extreme_peak_to_peak" in event.rejection_reasons for event in events)


def test_known_invalid_time_mask_rejects_overlapping_event():
    artifacts = {
        "boundary_exclusion_s": 0.0,
        "max_peak_to_peak_uv": 1000.0,
        "invalid_time_masks": [{"start_s": 12.1, "end_s": 12.9}],
    }
    events = detect_slow_oscillations(
        _eeg(_sine(duration_s=8.0)), _config(_profile(artifact_rejection=artifacts))
    ).events

    masked = [event for event in events if "invalid_time_mask" in event.rejection_reasons]
    assert masked
    assert all(event.event_start_s < 12.9 and event.event_end_s > 12.1 for event in masked)


def test_no_event_input_returns_empty_result():
    detection = detect_slow_oscillations(_eeg(np.zeros(1000)), _config())

    assert detection.events == ()


def test_channels_are_detected_independently():
    data = np.vstack((_sine(), np.zeros(1000)))
    detection = detect_slow_oscillations(_eeg(data), _config())

    assert any(event.channel == "EEG 1" for event in detection.events)
    assert not any(event.channel == "EEG 2" for event in detection.events)


def test_detection_does_not_modify_input_signal():
    eeg = _eeg(np.vstack((_sine(), _sine(amplitude=10.0))))
    original = eeg.data.copy()
    config = _config()
    config_before = deepcopy(config)

    detect_slow_oscillations(eeg, config)

    np.testing.assert_array_equal(eeg.data, original)
    assert config == config_before
