"""Tests for configuration-driven N3 EEG preprocessing."""

from copy import deepcopy
from pathlib import Path

import mne
import numpy as np
import pytest

from dreamcore.config import load_config
from dreamcore.preprocessing.eeg import (
    get_preprocessing_profile,
    preprocess_n3_segment,
)
from dreamcore.sleep_staging.labels import StageInterval
from dreamcore.sleep_staging.segments import N3Segment, extract_n3_segments


def _profile(**overrides):
    profile = {
        "reference": {"mode": "none", "channels": []},
        "notch_freqs_hz": [],
        "notch_method": "fir",
        "bandpass": {"low_hz": None, "high_hz": None, "method": "fir"},
        "detrend": "none",
        "target_sampling_rate_hz": None,
        "resample_method": "fft",
        "boundary_discard_s": 0.0,
    }
    profile.update(overrides)
    return profile


def _config(profile=None, channels=None):
    return {
        "preprocessing": {
            "active_profile": "test",
            "eeg_channels": channels or ["EEG A", "EEG B"],
            "profiles": {"test": profile or _profile()},
        }
    }


def _segment(sfreq=10.0, duration_s=10.0):
    n_samples = int(sfreq * duration_s)
    times = np.arange(n_samples) / sfreq
    data = np.vstack((2.0 + np.sin(2 * np.pi * times), -3.0 + 0.5 * times))
    return N3Segment(
        segment_id="synthetic_n3_0001",
        start_s=20.0,
        end_s=20.0 + duration_s,
        normalized_label="N3",
        raw_labels=("Sleep stage 3", "Sleep stage 4"),
        channel_names=("EEG A", "EEG B"),
        sampling_rate_hz=sfreq,
        data=data,
    )


def test_default_config_exposes_three_research_profiles():
    config = load_config(Path("configs/default.yaml"))

    profile_name, profile = get_preprocessing_profile(config)

    assert profile_name == "slow_oscillation_observation"
    assert profile["bandpass"] == {"low_hz": 0.5, "high_hz": 4.0, "method": "fir"}
    assert set(config["preprocessing"]["profiles"]) == {
        "raw_eeg",
        "broadband_sleep_eeg",
        "slow_oscillation_observation",
    }


def test_channel_selection_and_missing_channel_error():
    segment = _segment()
    output = preprocess_n3_segment(segment, _config(channels=["EEG B"]))

    assert output.channel_names == ("EEG B",)
    np.testing.assert_array_equal(output.data, segment.data[[1]])

    with pytest.raises(ValueError, match="not found"):
        preprocess_n3_segment(segment, _config(channels=["EEG Missing"]))


def test_demean_is_applied_per_channel():
    output = preprocess_n3_segment(_segment(), _config(_profile(detrend="demean")))

    np.testing.assert_allclose(np.mean(output.data, axis=1), 0.0, atol=1e-12)


def test_average_reference_is_optional_and_configuration_driven():
    reference = {"mode": "average", "channels": []}
    output = preprocess_n3_segment(_segment(), _config(_profile(reference=reference)))

    np.testing.assert_allclose(np.mean(output.data, axis=0), 0.0, atol=1e-12)


def test_notch_filter_can_be_enabled_explicitly():
    sfreq = 100.0
    times = np.arange(1000) / sfreq
    line_noise = np.sin(2 * np.pi * 25.0 * times)
    segment = N3Segment(
        segment_id="notch_test",
        start_s=0.0,
        end_s=10.0,
        normalized_label="N3",
        raw_labels=("Sleep stage 3",),
        channel_names=("EEG A", "EEG B"),
        sampling_rate_hz=sfreq,
        data=np.vstack((line_noise, line_noise)),
    )
    profile = _profile(notch_freqs_hz=[25.0], notch_method="iir")

    output = preprocess_n3_segment(segment, _config(profile))

    assert np.std(output.data) < np.std(segment.data) * 0.25


@pytest.mark.parametrize(
    ("low_hz", "high_hz"),
    [(-0.5, 2.0), (2.0, 2.0), (3.0, 2.0), (0.5, 5.0), (None, 2.0)],
)
def test_invalid_bandpass_parameters_are_rejected(low_hz, high_hz):
    profile = _profile(bandpass={"low_hz": low_hz, "high_hz": high_hz, "method": "fir"})

    with pytest.raises(ValueError, match="Bandpass"):
        preprocess_n3_segment(_segment(sfreq=10.0), _config(profile))


@pytest.mark.parametrize("notch_freqs", [[0.0], [-1.0], [5.0], [6.0]])
def test_invalid_notch_parameters_are_rejected(notch_freqs):
    with pytest.raises(ValueError, match="Notch"):
        preprocess_n3_segment(
            _segment(sfreq=10.0),
            _config(_profile(notch_freqs_hz=notch_freqs)),
        )


def test_explicit_resampling_changes_rate_and_sample_count():
    output = preprocess_n3_segment(
        _segment(sfreq=10.0),
        _config(_profile(target_sampling_rate_hz=5.0)),
    )

    assert output.original_sampling_rate_hz == 10.0
    assert output.output_sampling_rate_hz == 5.0
    assert output.raw_n_samples == 100
    assert output.n_samples == 50
    assert output.metadata["parameters"]["target_sampling_rate_hz"] == 5.0


def test_boundary_discard_preserves_expected_duration_at_both_rates():
    output = preprocess_n3_segment(
        _segment(sfreq=10.0),
        _config(_profile(target_sampling_rate_hz=5.0, boundary_discard_s=1.0)),
    )

    assert output.start_s == 21.0
    assert output.end_s == 29.0
    assert output.duration_s == 8.0
    assert output.raw_n_samples == 80
    assert output.n_samples == 40


def test_preprocessing_does_not_modify_segment_data():
    segment = _segment()
    original = segment.data.copy()

    preprocess_n3_segment(segment, _config(_profile(detrend="linear")))

    np.testing.assert_array_equal(segment.data, original)


def test_preprocessing_does_not_modify_source_raw():
    info = mne.create_info(["EEG A", "EEG B"], sfreq=10.0, ch_types=["eeg", "eeg"])
    raw = mne.io.RawArray(_segment().data.copy(), info, verbose=False)
    original_data = raw.get_data().copy()
    original_info = deepcopy(raw.info)
    config = _config()
    config["n3_extraction"] = {
        "target_label": "N3",
        "min_segment_duration_s": 1.0,
        "eeg_channels": ["EEG A", "EEG B"],
    }
    intervals = [StageInterval(0.0, 10.0, "N3", ("Sleep stage 3",))]
    segment = extract_n3_segments(raw, intervals, "synthetic", config)[0]

    preprocess_n3_segment(segment, config)

    np.testing.assert_array_equal(raw.get_data(), original_data)
    assert raw.info["sfreq"] == original_info["sfreq"]
    assert raw.ch_names == original_info["ch_names"]


def test_boundary_discard_cannot_remove_entire_segment():
    with pytest.raises(ValueError, match="entire N3 segment"):
        preprocess_n3_segment(
            _segment(duration_s=2.0),
            _config(_profile(boundary_discard_s=1.0)),
        )
