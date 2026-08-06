"""Tests for Sleep-EDF loading and signal quality checks."""

from unittest.mock import Mock, patch

import mne
import numpy as np
import pytest

from dreamcore.data.reader import check_quality, load_edf


@pytest.fixture
def config():
    """Return the minimal configuration needed by the data reader."""
    return {
        "eeg": {"sampling_rate_hz": 10.0},
        "data": {
            "preload_edf": False,
            "sampling_rate_tolerance_hz": 0.01,
            "quality": {
                "flatline_threshold_s": 0.3,
                "max_nan_ratio": 0.1,
                "std_ddof": 0,
            },
        },
    }


def test_load_edf_returns_raw_and_structured_annotations(config):
    """Load PSG data and preserve all hypnogram annotation fields."""
    raw = Mock(spec=mne.io.BaseRaw)
    raw.info = {"sfreq": 10.0}
    annotations = mne.Annotations(
        onset=[0.0, 30.0],
        duration=[30.0, 30.0],
        description=["Sleep stage W", "Sleep stage 2"],
    )

    with (
        patch("dreamcore.data.reader.mne.io.read_raw_edf", return_value=raw) as read_raw,
        patch(
            "dreamcore.data.reader.mne.read_annotations", return_value=annotations
        ) as read_annotations,
    ):
        loaded_raw, annotation_array = load_edf("recording.edf", "hypnogram.edf", config)

    assert loaded_raw is raw
    read_raw.assert_called_once_with("recording.edf", preload=False)
    read_annotations.assert_called_once_with("hypnogram.edf")
    assert annotation_array.dtype.names == ("onset", "duration", "description")
    np.testing.assert_array_equal(annotation_array["onset"], annotations.onset)
    np.testing.assert_array_equal(annotation_array["duration"], annotations.duration)
    np.testing.assert_array_equal(annotation_array["description"], annotations.description)


def test_load_edf_rejects_unexpected_sampling_rate(config):
    """Use configured sampling rate only as a validation constraint."""
    raw = Mock(spec=mne.io.BaseRaw)
    raw.info = {"sfreq": 20.0}

    with (
        patch("dreamcore.data.reader.mne.io.read_raw_edf", return_value=raw),
        pytest.raises(ValueError, match="sampling rate does not match"),
    ):
        load_edf("recording.edf", "hypnogram.edf", config)


def test_check_quality_reports_stats_nan_ratio_and_flatline(config):
    """Report per-channel statistics and flag long identical runs."""
    channel_data = np.array(
        [
            [0.0, 1.0, np.nan, 3.0, 4.0],
            [2.0, 2.0, 2.0, 2.0, 3.0],
        ]
    )
    info = mne.create_info(["varying", "flat"], sfreq=10.0, ch_types="eeg")
    raw = mne.io.RawArray(channel_data, info, verbose=False)

    report = check_quality(raw, config)

    assert report["sampling_rate_hz"] == 10.0
    assert report["n_channels"] == 2
    assert report["n_samples"] == 5
    assert report["passed"] is False
    assert report["channels"]["varying"]["mean"] == 2.0
    assert report["channels"]["varying"]["std"] == pytest.approx(np.sqrt(2.5))
    assert report["channels"]["varying"]["nan_ratio"] == 0.2
    assert report["channels"]["varying"]["flatline"] is False
    assert report["channels"]["flat"]["longest_flatline_samples"] == 4
    assert report["channels"]["flat"]["longest_flatline_duration_s"] == 0.4
    assert report["channels"]["flat"]["flatline"] is True


def test_flatline_requires_duration_to_exceed_threshold(config):
    """A run exactly equal to the configured duration is not a flatline."""
    info = mne.create_info(["channel"], sfreq=10.0, ch_types="eeg")
    raw = mne.io.RawArray(np.array([[1.0, 1.0, 1.0, 2.0]]), info, verbose=False)

    report = check_quality(raw, config)

    assert report["channels"]["channel"]["longest_flatline_duration_s"] == 0.3
    assert report["channels"]["channel"]["flatline"] is False
