"""Configuration-driven preprocessing for extracted N3 EEG segments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import mne
import numpy as np
from scipy import signal

from dreamcore.sleep_staging.segments import N3Segment


@dataclass(frozen=True)
class PreprocessedEEG:
    """Raw and processed views of one sample-aligned N3 EEG segment."""

    segment_id: str
    channel_names: tuple[str, ...]
    raw_data: np.ndarray = field(repr=False, compare=False)
    data: np.ndarray = field(repr=False, compare=False)
    original_sampling_rate_hz: float
    output_sampling_rate_hz: float
    start_s: float
    end_s: float
    profile_name: str
    metadata: dict[str, Any]

    @property
    def duration_s(self) -> float:
        """Return the processed, sample-aligned duration in seconds."""
        return self.data.shape[1] / self.output_sampling_rate_hz

    @property
    def raw_n_samples(self) -> int:
        """Return the retained number of native-rate samples per channel."""
        return int(self.raw_data.shape[1])

    @property
    def n_samples(self) -> int:
        """Return the retained number of processed samples per channel."""
        return int(self.data.shape[1])


def _required_mapping(config: Mapping[str, Any], key: str, path: str = "") -> Mapping[str, Any]:
    try:
        section = config[key]
    except KeyError as error:
        full_path = f"{path}.{key}" if path else key
        raise ValueError(f"Missing required config section: {full_path}") from error
    if not isinstance(section, Mapping):
        full_path = f"{path}.{key}" if path else key
        raise TypeError(f"Config section '{full_path}' must be a mapping")
    return section


def get_preprocessing_profile(
    config: Mapping[str, Any], profile_name: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Return a detached preprocessing profile selected from configuration."""
    preprocessing = _required_mapping(config, "preprocessing")
    profiles = _required_mapping(preprocessing, "profiles", "preprocessing")
    selected_name = str(profile_name or preprocessing["active_profile"])
    if selected_name not in profiles:
        raise ValueError(f"Unknown preprocessing profile: {selected_name}")
    profile = profiles[selected_name]
    if not isinstance(profile, Mapping):
        raise TypeError(f"preprocessing.profiles.{selected_name} must be a mapping")
    return selected_name, deepcopy(dict(profile))


def _configured_channels(
    segment: N3Segment,
    config: Mapping[str, Any],
    channel_names: Sequence[str] | None,
) -> tuple[str, ...]:
    preprocessing = _required_mapping(config, "preprocessing")
    selected = channel_names if channel_names is not None else preprocessing["eeg_channels"]
    if not isinstance(selected, Sequence) or isinstance(selected, str) or not selected:
        raise ValueError("At least one preprocessing EEG channel must be configured")
    names = tuple(str(name) for name in selected)
    if len(names) != len(set(names)):
        raise ValueError("Preprocessing EEG channels must be unique")
    missing = [name for name in names if name not in segment.channel_names]
    if missing:
        raise ValueError(f"Preprocessing channels not found in N3 segment: {missing}")
    return names


def _validated_parameters(profile: Mapping[str, Any], sfreq: float) -> dict[str, Any]:
    if sfreq <= 0:
        raise ValueError("N3 segment sampling rate must be positive")
    nyquist_hz = sfreq / 2.0

    bandpass = _required_mapping(profile, "bandpass", "preprocessing profile")
    low_hz = bandpass.get("low_hz")
    high_hz = bandpass.get("high_hz")
    if (low_hz is None) != (high_hz is None):
        raise ValueError("Bandpass low_hz and high_hz must both be set or both be null")
    if low_hz is not None:
        low_hz = float(low_hz)
        high_hz = float(high_hz)
        if low_hz <= 0 or high_hz <= low_hz or high_hz >= nyquist_hz:
            raise ValueError("Bandpass frequencies must satisfy 0 < low_hz < high_hz < Nyquist")

    notch_freqs = profile["notch_freqs_hz"]
    if not isinstance(notch_freqs, Sequence) or isinstance(notch_freqs, str):
        raise TypeError("notch_freqs_hz must be a sequence")
    notch_freqs_hz = [float(frequency) for frequency in notch_freqs]
    if any(frequency <= 0 or frequency >= nyquist_hz for frequency in notch_freqs_hz):
        raise ValueError("Notch frequencies must satisfy 0 < frequency < Nyquist")

    target_sfreq = profile["target_sampling_rate_hz"]
    if target_sfreq is not None:
        target_sfreq = float(target_sfreq)
        if target_sfreq <= 0:
            raise ValueError("target_sampling_rate_hz must be positive or null")
        output_nyquist_hz = target_sfreq / 2.0
        if high_hz is not None and high_hz >= output_nyquist_hz:
            raise ValueError("Bandpass high_hz must be below the target Nyquist frequency")

    detrend = str(profile["detrend"])
    if detrend not in {"none", "demean", "linear"}:
        raise ValueError("detrend must be one of: none, demean, linear")

    reference = _required_mapping(profile, "reference", "preprocessing profile")
    reference_mode = str(reference["mode"])
    if reference_mode not in {"none", "average", "channels"}:
        raise ValueError("reference.mode must be one of: none, average, channels")
    reference_channels = reference["channels"]
    if not isinstance(reference_channels, Sequence) or isinstance(reference_channels, str):
        raise TypeError("reference.channels must be a sequence")
    reference_channels = [str(name) for name in reference_channels]
    if reference_mode == "channels" and not reference_channels:
        raise ValueError("reference.channels cannot be empty when reference.mode is channels")

    boundary_discard_s = float(profile["boundary_discard_s"])
    if boundary_discard_s < 0:
        raise ValueError("boundary_discard_s must be non-negative")

    return {
        "bandpass": {
            "low_hz": low_hz,
            "high_hz": high_hz,
            "method": str(bandpass["method"]),
        },
        "notch_freqs_hz": notch_freqs_hz,
        "notch_method": str(profile["notch_method"]),
        "reference": {"mode": reference_mode, "channels": reference_channels},
        "detrend": detrend,
        "target_sampling_rate_hz": target_sfreq,
        "resample_method": str(profile["resample_method"]),
        "boundary_discard_s": boundary_discard_s,
    }


def _apply_reference(
    data: np.ndarray,
    selected_channels: tuple[str, ...],
    reference: Mapping[str, Any],
) -> np.ndarray:
    mode = reference["mode"]
    if mode == "none":
        return data
    if mode == "average":
        return data - np.mean(data, axis=0, keepdims=True)

    reference_channels = tuple(reference["channels"])
    missing = [name for name in reference_channels if name not in selected_channels]
    if missing:
        raise ValueError(f"Reference channels not selected for preprocessing: {missing}")
    indices = [selected_channels.index(name) for name in reference_channels]
    reference_signal = np.mean(data[indices], axis=0, keepdims=True)
    return data - reference_signal


def preprocess_n3_segment(
    segment: N3Segment,
    config: Mapping[str, Any],
    profile_name: str | None = None,
    channel_names: Sequence[str] | None = None,
) -> PreprocessedEEG:
    """Preprocess one N3 segment without mutating the segment's signal array."""
    selected_profile_name, profile = get_preprocessing_profile(config, profile_name)
    selected_channels = _configured_channels(segment, config, channel_names)
    parameters = _validated_parameters(profile, segment.sampling_rate_hz)

    indices = [segment.channel_names.index(name) for name in selected_channels]
    native_data = np.array(segment.data[indices], dtype=float, copy=True)
    processed = _apply_reference(native_data.copy(), selected_channels, parameters["reference"])

    if parameters["detrend"] == "demean":
        processed -= np.mean(processed, axis=1, keepdims=True)
    elif parameters["detrend"] == "linear":
        processed = signal.detrend(processed, axis=-1, type="linear", overwrite_data=False)

    notch_freqs_hz = parameters["notch_freqs_hz"]
    if notch_freqs_hz:
        processed = mne.filter.notch_filter(
            processed,
            Fs=segment.sampling_rate_hz,
            freqs=np.asarray(notch_freqs_hz),
            method=parameters["notch_method"],
            copy=True,
            verbose=False,
        )

    bandpass = parameters["bandpass"]
    if bandpass["low_hz"] is not None:
        processed = mne.filter.filter_data(
            processed,
            sfreq=segment.sampling_rate_hz,
            l_freq=bandpass["low_hz"],
            h_freq=bandpass["high_hz"],
            method=bandpass["method"],
            copy=True,
            verbose=False,
        )

    output_sfreq = segment.sampling_rate_hz
    if parameters["target_sampling_rate_hz"] is not None:
        output_sfreq = parameters["target_sampling_rate_hz"]
        processed = mne.filter.resample(
            processed,
            up=output_sfreq,
            down=segment.sampling_rate_hz,
            axis=-1,
            method=parameters["resample_method"],
            verbose=False,
        )

    discard_s = parameters["boundary_discard_s"]
    native_discard = int(round(discard_s * segment.sampling_rate_hz))
    output_discard = int(round(discard_s * output_sfreq))
    if 2 * native_discard >= native_data.shape[1] or 2 * output_discard >= processed.shape[1]:
        raise ValueError("boundary_discard_s removes the entire N3 segment")
    if native_discard:
        native_data = native_data[:, native_discard:-native_discard]
    if output_discard:
        processed = processed[:, output_discard:-output_discard]

    start_s = segment.start_s + discard_s
    end_s = start_s + processed.shape[1] / output_sfreq
    metadata = {
        "input": {
            "segment_id": segment.segment_id,
            "start_s": segment.start_s,
            "end_s": segment.end_s,
            "sampling_rate_hz": segment.sampling_rate_hz,
            "n_samples": segment.n_samples,
            "available_channels": list(segment.channel_names),
        },
        "profile_name": selected_profile_name,
        "parameters": parameters,
        "output": {
            "start_s": start_s,
            "end_s": end_s,
            "sampling_rate_hz": output_sfreq,
            "n_samples": int(processed.shape[1]),
            "channels": list(selected_channels),
        },
        "processing_order": [
            "channel_selection",
            "reference",
            "detrend",
            "notch",
            "bandpass",
            "resample",
            "boundary_discard",
        ],
    }
    return PreprocessedEEG(
        segment_id=segment.segment_id,
        channel_names=selected_channels,
        raw_data=native_data,
        data=processed,
        original_sampling_rate_hz=segment.sampling_rate_hz,
        output_sampling_rate_hz=output_sfreq,
        start_s=start_s,
        end_s=end_s,
        profile_name=selected_profile_name,
        metadata=metadata,
    )


def signal_statistics(
    data: np.ndarray, channel_names: Sequence[str], scale: float = 1.0
) -> dict[str, dict[str, float]]:
    """Compute JSON-compatible per-channel summary statistics."""
    if data.ndim != 2 or data.shape[0] != len(channel_names):
        raise ValueError("data must have shape (len(channel_names), n_samples)")
    scaled = np.asarray(data, dtype=float) * float(scale)
    return {
        str(channel): {
            "mean": float(np.mean(scaled[index])),
            "std": float(np.std(scaled[index])),
            "peak_to_peak": float(np.ptp(scaled[index])),
        }
        for index, channel in enumerate(channel_names)
    }
