"""Traditional spectral estimates for the Alpha V1 research baseline."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import mne
import numpy as np
from scipy.signal import hilbert, welch


@dataclass(frozen=True)
class SpectralEstimate:
    """Welch power spectral density in microvolt-squared per hertz."""

    frequencies_hz: np.ndarray
    psd_uv2_per_hz: np.ndarray
    parameters: Mapping[str, Any]


def _required_mapping(config: Mapping[str, Any], key: str, path: str = "") -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        full_path = f"{path}.{key}" if path else key
        raise TypeError(f"Config section '{full_path}' must be a mapping")
    return value


def get_alpha_profile(
    config: Mapping[str, Any], profile_name: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Return a detached named Alpha research profile."""
    section = _required_mapping(config, "alpha")
    profiles = _required_mapping(section, "profiles", "alpha")
    selected = str(profile_name or section["active_profile"])
    profile = profiles.get(selected)
    if not isinstance(profile, Mapping):
        raise ValueError(f"Unknown Alpha profile: {selected}")
    return selected, deepcopy(dict(profile))


def estimate_welch_psd(
    signal: np.ndarray,
    sampling_rate_hz: float,
    config: Mapping[str, Any],
    profile_name: str | None = None,
) -> SpectralEstimate:
    """Estimate an interpretable Welch PSD without modifying the input."""
    original = np.asarray(signal, dtype=float)
    if original.ndim != 1 or original.size == 0:
        raise ValueError("Alpha spectral input must be a non-empty 1D signal")
    if sampling_rate_hz <= 0:
        raise ValueError("Alpha sampling rate must be positive")
    if not np.all(np.isfinite(original)):
        raise ValueError("Alpha spectral input must contain only finite samples")

    selected, profile = get_alpha_profile(config, profile_name)
    spectral = _required_mapping(profile, "spectral", f"alpha.profiles.{selected}")
    section = _required_mapping(config, "alpha")
    scale = float(section["input_scale_to_uv"])
    segment_s = float(spectral["welch_segment_s"])
    overlap_fraction = float(spectral["welch_overlap_fraction"])
    low_hz = float(spectral["total_power_band"]["low_hz"])
    high_hz = float(spectral["total_power_band"]["high_hz"])
    if scale <= 0 or segment_s <= 0:
        raise ValueError("Alpha scale and Welch segment duration must be positive")
    if not 0 <= overlap_fraction < 1:
        raise ValueError("Welch overlap fraction must be within [0, 1)")
    if low_hz < 0 or high_hz <= low_hz or high_hz >= sampling_rate_hz / 2:
        raise ValueError("Total power band must lie below Nyquist")

    nperseg = int(round(segment_s * sampling_rate_hz))
    if nperseg < 2 or original.size < nperseg:
        raise ValueError("Alpha input is shorter than the configured Welch segment")
    noverlap = int(round(nperseg * overlap_fraction))
    frequencies, psd = welch(
        original * scale,
        fs=sampling_rate_hz,
        window=str(spectral["welch_window"]),
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=str(spectral["welch_detrend"]),
        scaling="density",
    )
    keep = (frequencies >= low_hz) & (frequencies <= high_hz)
    return SpectralEstimate(
        frequencies_hz=frequencies[keep],
        psd_uv2_per_hz=psd[keep],
        parameters={
            "profile": selected,
            "method": "welch",
            "welch_segment_s": segment_s,
            "welch_overlap_fraction": overlap_fraction,
            "welch_window": str(spectral["welch_window"]),
            "welch_detrend": str(spectral["welch_detrend"]),
            "input_scale_to_uv": scale,
            "total_power_band": {"low_hz": low_hz, "high_hz": high_hz},
        },
    )


def integrate_band_power(estimate: SpectralEstimate, low_hz: float, high_hz: float) -> float:
    """Integrate PSD over a configured half-open-like frequency interval."""
    if low_hz < 0 or high_hz <= low_hz:
        raise ValueError("Band power bounds must be ordered and non-negative")
    mask = (estimate.frequencies_hz >= low_hz) & (estimate.frequencies_hz <= high_hz)
    if np.count_nonzero(mask) < 2:
        raise ValueError("Frequency resolution is insufficient for requested band")
    return float(np.trapezoid(estimate.psd_uv2_per_hz[mask], estimate.frequencies_hz[mask]))


def alpha_filtered_envelope(
    signal: np.ndarray,
    sampling_rate_hz: float,
    low_hz: float,
    high_hz: float,
    config: Mapping[str, Any],
    profile_name: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return zero-phase alpha-band signal and analytic envelope in microvolts."""
    original = np.asarray(signal, dtype=float)
    if original.ndim != 1 or original.size == 0 or not np.all(np.isfinite(original)):
        raise ValueError("Alpha envelope input must be a finite non-empty 1D signal")
    selected, profile = get_alpha_profile(config, profile_name)
    spectral = _required_mapping(profile, "spectral", f"alpha.profiles.{selected}")
    if low_hz <= 0 or high_hz <= low_hz or high_hz >= sampling_rate_hz / 2:
        raise ValueError("Alpha filter band must lie below Nyquist")
    scale = float(config["alpha"]["input_scale_to_uv"])
    filtered = mne.filter.filter_data(
        original * scale,
        sfreq=sampling_rate_hz,
        l_freq=low_hz,
        h_freq=high_hz,
        method=str(spectral["filter_method"]),
        phase=str(spectral["filter_phase"]),
        copy=True,
        verbose=False,
    )
    return filtered, np.abs(hilbert(filtered))
