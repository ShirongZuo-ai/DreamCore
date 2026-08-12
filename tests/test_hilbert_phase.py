"""Synthetic tests for the offline Hilbert phase baseline."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from dreamcore.config import load_config
from dreamcore.phase_prediction.hilbert import (
    PhaseProvenance,
    circular_error,
    compare_overlapping_channel_phases,
    estimate_channel_hilbert,
    estimate_hilbert_phase,
    get_phase_profile,
    validate_event_landmarks,
)
from dreamcore.preprocessing.eeg import PreprocessedEEG
from dreamcore.slow_oscillation.detector import (
    SlowOscillationDetection,
    SlowOscillationEvent,
)


def _profile(**overrides):
    profile = {
        "phase_band": {
            "low_hz": 0.5,
            "high_hz": 2.0,
            "method": "fir",
            "phase": "zero",
        },
        "project_phase_offset_rad": -np.pi,
        "boundary_invalid_s": 1.0,
        "min_signal_duration_s": 2.0,
        "constant_std_tolerance": 0.0,
        "amplitude_envelope": {
            "strategy": "none",
            "fixed_min_uv": None,
            "quantile": 0.1,
        },
        "instantaneous_frequency": {"enabled": True, "min_hz": 0.5, "max_hz": 1.5},
        "invalid_time_masks": [],
        "expected_landmark_phases_rad": {
            "downward_zero_crossing": -np.pi / 2,
            "trough": 0.0,
            "upward_zero_crossing": np.pi / 2,
            "positive_peak": np.pi,
        },
        "event_validation": {
            "reverse_step_tolerance_rad": 0.05,
            "max_reverse_step_fraction": 0.05,
            "min_forward_advance_rad": np.pi,
            "min_event_valid_fraction": 0.9,
        },
    }
    profile.update(overrides)
    return profile


def _config(profile=None):
    return {
        "hilbert_phase": {
            "active_profile": "test",
            "amplitude_scale_to_uv": 1.0,
            "profiles": {"test": profile or _profile()},
            "cross_channel": {
                "accepted_only": True,
                "min_overlap_s": 0.0,
                "comparison_time": "overlap_midpoint",
            },
        }
    }


def _sine(duration_s=20.0, sfreq=100.0, frequency_hz=1.0, amplitude=20.0):
    times = np.arange(int(duration_s * sfreq)) / sfreq
    return -amplitude * np.sin(2 * np.pi * frequency_hz * times)


def _provenance(channel="EEG 1"):
    return PhaseProvenance(
        subject_id="S01",
        recording_id="R01",
        segment_id="synthetic_n3_0001",
        channel=channel,
        preprocessing_profile="broadband",
        detector_profile="strict",
    )


def _event(channel="EEG 1", event_id="event_1", start_s=10.0):
    return SlowOscillationEvent(
        event_id=event_id,
        segment_id="synthetic_n3_0001",
        channel=channel,
        event_start_s=start_s,
        event_end_s=start_s + 1.0,
        downward_zero_crossing_s=start_s,
        trough_time_s=start_s + 0.25,
        trough_amplitude_uv=-20.0,
        upward_zero_crossing_s=start_s + 0.5,
        positive_peak_time_s=start_s + 0.75,
        positive_peak_amplitude_uv=20.0,
        peak_to_peak_amplitude_uv=40.0,
        negative_halfwave_duration_s=0.5,
        full_cycle_duration_s=1.0,
        estimated_frequency_hz=1.0,
        down_slope=-80.0,
        up_slope=80.0,
        accepted=True,
        rejection_reasons=(),
        detector_profile="strict",
        amplitude_threshold_uv=None,
    )


def _pipeline(data):
    values = np.atleast_2d(np.asarray(data, dtype=float))
    channels = tuple(f"EEG {index + 1}" for index in range(values.shape[0]))
    sfreq = 100.0
    duration_s = values.shape[1] / sfreq
    eeg = PreprocessedEEG(
        segment_id="synthetic_n3_0001",
        channel_names=channels,
        raw_data=values.copy(),
        data=values.copy(),
        original_sampling_rate_hz=sfreq,
        output_sampling_rate_hz=sfreq,
        start_s=0.0,
        end_s=duration_s,
        profile_name="broadband",
        metadata={},
    )
    detection = SlowOscillationDetection(
        segment_id=eeg.segment_id,
        channel_names=channels,
        detection_data=values.copy(),
        sampling_rate_hz=sfreq,
        start_s=0.0,
        end_s=duration_s,
        detector_profile="strict",
        events=(),
        amplitude_thresholds_uv={channel: None for channel in channels},
        parameters={},
    )
    return eeg, detection


def test_default_config_exposes_offline_phase_profile():
    config = load_config(Path("configs/default.yaml"))

    name, profile = get_phase_profile(config)

    assert name == "offline_strict_so"
    assert profile["phase_band"]["phase"] == "zero"
    assert profile["project_phase_offset_rad"] == -np.pi


def test_known_sine_wrapped_phase_and_project_convention():
    result = estimate_channel_hilbert(_sine(), 100.0, 0.0, _provenance(), _config())
    expected = {
        10.0: -np.pi / 2,
        10.25: 0.0,
        10.5: np.pi / 2,
        10.75: np.pi,
    }

    for time_s, expected_phase in expected.items():
        estimated = result.wrapped_phase[int(round(time_s * 100.0))]
        assert circular_error(estimated, expected_phase) == pytest.approx(0.0, abs=0.03)
    assert np.all(result.wrapped_phase >= -np.pi)
    assert np.all(result.wrapped_phase < np.pi)


def test_phase_unwrap_envelope_and_instantaneous_frequency():
    result = estimate_channel_hilbert(_sine(amplitude=20.0), 100.0, 0.0, _provenance(), _config())
    middle = slice(500, 1500)

    assert np.all(np.diff(result.unwrapped_phase[middle]) > 0)
    np.testing.assert_allclose(result.amplitude_envelope[middle], 20.0, atol=0.2)
    np.testing.assert_allclose(result.instantaneous_frequency_hz[middle], 1.0, atol=0.02)


def test_circular_error_handles_wrap_boundary():
    error = circular_error(-np.pi + 0.1, np.pi - 0.1)

    assert error == pytest.approx(0.2)


def test_boundary_and_invalid_time_masks_preserve_timeline():
    result = estimate_channel_hilbert(
        _sine(),
        100.0,
        0.0,
        _provenance(),
        _config(),
        invalid_time_masks=[{"start_s": 5.0, "end_s": 6.0}],
    )

    assert result.valid_phase_mask.shape == (2000,)
    assert np.all(result.invalid_reason_masks["boundary"][:100])
    assert np.all(result.invalid_reason_masks["boundary"][-100:])
    assert np.all(result.invalid_reason_masks["invalid_time_mask"][500:600])
    assert not np.any(result.valid_phase_mask[500:600])


def test_low_envelope_strategy_marks_samples_invalid():
    amplitude = {"strategy": "fixed", "fixed_min_uv": 30.0, "quantile": 0.1}
    result = estimate_channel_hilbert(
        _sine(amplitude=20.0),
        100.0,
        0.0,
        _provenance(),
        _config(_profile(amplitude_envelope=amplitude)),
    )

    assert result.amplitude_threshold_uv == 30.0
    assert np.all(result.invalid_reason_masks["low_amplitude_envelope"][500:1500])
    assert not np.any(result.valid_phase_mask[500:1500])


def test_nan_is_retained_and_invalid_without_changing_length():
    signal = _sine()
    signal[1000] = np.nan
    result = estimate_channel_hilbert(signal, 100.0, 0.0, _provenance(), _config())

    assert result.wrapped_phase.size == signal.size
    assert result.invalid_reason_masks["nan_or_nonfinite"][1000]
    assert not result.valid_phase_mask[1000]


@pytest.mark.parametrize(
    ("signal", "match"),
    [
        (np.array([]), "empty"),
        (np.ones(1000), "constant"),
        (_sine(duration_s=1.0), "shorter"),
    ],
)
def test_empty_constant_and_short_signals_raise(signal, match):
    with pytest.raises(ValueError, match=match):
        estimate_channel_hilbert(signal, 100.0, 0.0, _provenance(), _config())


def test_multichannel_processing_is_independent_and_preserves_provenance():
    eeg, detection = _pipeline(np.vstack((_sine(amplitude=20), _sine(amplitude=10))))
    result = estimate_hilbert_phase(eeg, detection, "S01", "R01", _config())

    assert result.channel_names == ("EEG 1", "EEG 2")
    assert result.channel("EEG 1").provenance.subject_id == "S01"
    assert result.channel("EEG 2").provenance.recording_id == "R01"
    assert result.channel("EEG 1").provenance.preprocessing_profile == "broadband"
    assert result.channel("EEG 1").provenance.detector_profile == "strict"
    assert result.channel("EEG 1").phase_profile == "test"
    assert np.median(result.channel("EEG 1").amplitude_envelope) > np.median(
        result.channel("EEG 2").amplitude_envelope
    )


def test_event_landmarks_match_targets_and_phase_moves_forward():
    eeg, detection = _pipeline(_sine())
    detection = SlowOscillationDetection(**{**detection.__dict__, "events": (_event(),)})
    phase = estimate_hilbert_phase(eeg, detection, "S01", "R01", _config())

    landmarks, validations = validate_event_landmarks(phase, detection)

    assert [landmark.landmark_type for landmark in landmarks] == [
        "downward_zero_crossing",
        "trough",
        "upward_zero_crossing",
        "positive_peak",
    ]
    assert all(abs(landmark.circular_error_rad) < 0.03 for landmark in landmarks)
    assert all(landmark.phase_valid for landmark in landmarks)
    assert validations[0].event_phase_valid
    assert validations[0].phase_forward
    assert validations[0].net_phase_advance_rad == pytest.approx(2 * np.pi, abs=0.1)


def test_cross_channel_phase_difference_uses_valid_overlap_midpoint():
    eeg, detection = _pipeline(np.vstack((_sine(), _sine())))
    detection = SlowOscillationDetection(
        **{
            **detection.__dict__,
            "events": (
                _event("EEG 1", "event_1"),
                _event("EEG 2", "event_2", start_s=10.1),
            ),
        }
    )
    phase = estimate_hilbert_phase(eeg, detection, "S01", "R01", _config())

    comparison = compare_overlapping_channel_phases(phase, detection, _config())[0]

    assert comparison["overlapping_pair_count"] == 1
    assert comparison["valid_pair_count"] == 1
    assert comparison["circular_mean_direction_rad"] == pytest.approx(0.0, abs=0.03)
    assert comparison["circular_dispersion"] == pytest.approx(0.0, abs=1e-12)


def test_hilbert_does_not_modify_signal_or_config():
    signal = _sine()
    original = signal.copy()
    config = _config()
    config_before = deepcopy(config)

    estimate_channel_hilbert(signal, 100.0, 0.0, _provenance(), config)

    np.testing.assert_array_equal(signal, original)
    assert config == config_before
