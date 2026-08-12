"""Sleep-EDF loading and signal quality checks."""

from collections.abc import Mapping
from os import PathLike
from typing import Any

import mne
import numpy as np


def _config_section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a required mapping section with a useful configuration error."""
    try:
        section = config[key]
    except KeyError as error:
        raise ValueError(f"Missing required config section: {key}") from error
    if not isinstance(section, Mapping):
        raise TypeError(f"Config section '{key}' must be a mapping")
    return section


def _config_value(config: Mapping[str, Any], key: str, path: str) -> Any:
    """Return a required configuration value with a useful error."""
    try:
        return config[key]
    except KeyError as error:
        raise ValueError(f"Missing required config value: {path}.{key}") from error


def load_edf(
    edf_path: str | PathLike[str],
    hypnogram_path: str | PathLike[str],
    config: Mapping[str, Any],
) -> tuple[mne.io.BaseRaw, np.ndarray]:
    """Load a Sleep-EDF PSG recording and its hypnogram annotations.

    The configured sampling rate is used only to validate the recording. The
    signal remains at its native sampling rate.

    Returns:
        The MNE raw recording and a structured annotation array with ``onset``,
        ``duration``, and ``description`` fields.
    """
    data_config = _config_section(config, "data")
    eeg_config = _config_section(config, "eeg")
    preload = _config_value(data_config, "preload_edf", "data")
    expected_sfreq = float(_config_value(eeg_config, "sampling_rate_hz", "eeg"))
    sfreq_tolerance = float(_config_value(data_config, "sampling_rate_tolerance_hz", "data"))

    raw = mne.io.read_raw_edf(edf_path, preload=preload)
    actual_sfreq = float(raw.info["sfreq"])
    if abs(actual_sfreq - expected_sfreq) > sfreq_tolerance:
        raise ValueError(
            "EDF sampling rate does not match config: "
            f"recording={actual_sfreq} Hz, configured={expected_sfreq} Hz, "
            f"tolerance={sfreq_tolerance} Hz"
        )

    annotations = mne.read_annotations(hypnogram_path)
    annotation_array = np.empty(
        len(annotations),
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    annotation_array["onset"] = annotations.onset
    annotation_array["duration"] = annotations.duration
    annotation_array["description"] = annotations.description
    return raw, annotation_array


def _longest_identical_run(values: np.ndarray) -> int:
    """Return the longest run of adjacent, equal, non-NaN samples."""
    if values.size == 0:
        return 0

    equal_to_previous = np.equal(values[1:], values[:-1])
    run_end_indices = np.flatnonzero(~equal_to_previous)
    run_lengths = np.diff(
        np.concatenate((np.array([-1]), run_end_indices, np.array([values.size - 1])))
    )
    return int(run_lengths.max())


def check_quality(raw: mne.io.BaseRaw, config: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate per-channel statistics and detect flatline segments."""
    data_config = _config_section(config, "data")
    quality_config = _config_section(data_config, "quality")
    flatline_threshold_s = float(
        _config_value(quality_config, "flatline_threshold_s", "data.quality")
    )
    max_nan_ratio = float(_config_value(quality_config, "max_nan_ratio", "data.quality"))
    std_ddof = int(_config_value(quality_config, "std_ddof", "data.quality"))

    if flatline_threshold_s < 0:
        raise ValueError("data.quality.flatline_threshold_s must be non-negative")
    if not 0 <= max_nan_ratio <= 1:
        raise ValueError("data.quality.max_nan_ratio must be between 0 and 1")
    if std_ddof < 0:
        raise ValueError("data.quality.std_ddof must be non-negative")

    sfreq = float(raw.info["sfreq"])
    samples = raw.get_data()
    channel_reports: dict[str, dict[str, float | int | bool]] = {}

    for channel_name, values in zip(raw.ch_names, samples, strict=True):
        nan_mask = np.isnan(values)
        valid_values = values[~nan_mask]
        mean = float(np.mean(valid_values)) if valid_values.size else float("nan")
        std = (
            float(np.std(valid_values, ddof=std_ddof))
            if valid_values.size > std_ddof
            else float("nan")
        )
        nan_ratio = float(np.mean(nan_mask)) if values.size else float("nan")
        longest_run_samples = _longest_identical_run(values)
        longest_run_s = longest_run_samples / sfreq
        flatline = longest_run_s > flatline_threshold_s

        channel_reports[channel_name] = {
            "mean": mean,
            "std": std,
            "nan_ratio": nan_ratio,
            "flatline": flatline,
            "longest_flatline_samples": longest_run_samples,
            "longest_flatline_duration_s": longest_run_s,
        }

    passed = all(
        not report["flatline"] and report["nan_ratio"] <= max_nan_ratio
        for report in channel_reports.values()
    )
    return {
        "sampling_rate_hz": sfreq,
        "n_channels": len(raw.ch_names),
        "n_samples": int(samples.shape[1]),
        "flatline_threshold_s": flatline_threshold_s,
        "max_nan_ratio": max_nan_ratio,
        "channels": channel_reports,
        "passed": passed,
    }
