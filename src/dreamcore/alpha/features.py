"""Window-level Alpha features and signal-quality gating."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from dreamcore.alpha.iaf import IAFResult, estimate_iaf
from dreamcore.alpha.spectral import (
    alpha_filtered_envelope,
    estimate_welch_psd,
    get_alpha_profile,
    integrate_band_power,
)


@dataclass(frozen=True)
class SignalQuality:
    """Interpretable window-level quality result."""

    valid: bool
    score: float
    finite_ratio: float
    standard_deviation_uv: float | None
    peak_to_peak_uv: float | None
    flatline_ratio: float
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class AlphaWindowFeatures:
    """Derived Alpha features for one channel/window."""

    window_start_s: float
    window_end_s: float
    channel: str
    stage: str
    absolute_alpha_power: float | None
    relative_alpha_power: float | None
    alpha_band_low_hz: float | None
    alpha_band_high_hz: float | None
    individual_alpha_frequency_hz: float | None
    iaf_confidence: float
    iaf_available: bool
    iaf_reason: str | None
    alpha_envelope: float | None
    signal_quality: SignalQuality
    profile: str
    provenance: str = "derived"

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["signal_quality"] = asdict(self.signal_quality)
        return output


def assess_signal_quality(
    signal: np.ndarray,
    config: Mapping[str, Any],
) -> SignalQuality:
    """Assess finite coverage, amplitude, and flat samples in one EEG window."""
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("Alpha quality input must be a non-empty 1D signal")
    quality = config["alpha"]["quality"]
    scale = float(config["alpha"]["input_scale_to_uv"])
    finite = np.isfinite(values)
    finite_ratio = float(np.mean(finite))
    valid_values = values[finite] * scale
    std_uv = float(np.std(valid_values)) if valid_values.size else None
    peak_to_peak_uv = float(np.ptp(valid_values)) if valid_values.size else None
    if values.size > 1:
        equal = np.isfinite(values[1:]) & np.isfinite(values[:-1]) & (values[1:] == values[:-1])
        flatline_ratio = float(np.mean(equal))
    else:
        flatline_ratio = 1.0
    reasons = []
    if finite_ratio < float(quality["min_finite_ratio"]):
        reasons.append("insufficient_finite_samples")
    if std_uv is None or std_uv < float(quality["min_standard_deviation_uv"]):
        reasons.append("standard_deviation_too_low")
    if std_uv is not None and std_uv > float(quality["max_standard_deviation_uv"]):
        reasons.append("standard_deviation_too_high")
    if peak_to_peak_uv is not None and peak_to_peak_uv > float(quality["max_peak_to_peak_uv"]):
        reasons.append("peak_to_peak_too_high")
    if flatline_ratio > float(quality["max_flatline_ratio"]):
        reasons.append("excess_flat_samples")
    score = float(
        np.clip(
            min(finite_ratio / float(quality["min_finite_ratio"]), 1.0)
            * (1.0 - min(flatline_ratio, 1.0)),
            0.0,
            1.0,
        )
    )
    return SignalQuality(
        valid=not reasons,
        score=score if not reasons else min(score, float(quality["invalid_score_ceiling"])),
        finite_ratio=finite_ratio,
        standard_deviation_uv=std_uv,
        peak_to_peak_uv=peak_to_peak_uv,
        flatline_ratio=flatline_ratio,
        reason_codes=tuple(reasons),
    )


def _selected_band(profile: Mapping[str, Any], iaf: IAFResult) -> tuple[float, float] | None:
    strategy = str(profile["band_strategy"])
    fixed = profile["fixed_band"]
    if strategy == "fixed":
        return float(fixed["low_hz"]), float(fixed["high_hz"])
    if strategy != "individualized":
        raise ValueError(f"Unsupported Alpha band strategy: {strategy}")
    if not iaf.available or iaf.individual_alpha_frequency_hz is None:
        if bool(profile["individualized_band"]["fallback_to_fixed"]):
            return float(fixed["low_hz"]), float(fixed["high_hz"])
        return None
    half_width = float(profile["individualized_band"]["half_width_hz"])
    return (
        iaf.individual_alpha_frequency_hz - half_width,
        iaf.individual_alpha_frequency_hz + half_width,
    )


def extract_alpha_features(
    signal: np.ndarray,
    sampling_rate_hz: float,
    channel: str,
    window_start_s: float,
    window_end_s: float,
    stage: str,
    config: Mapping[str, Any],
    profile_name: str | None = None,
    session_iaf: IAFResult | None = None,
) -> AlphaWindowFeatures:
    """Extract fixed- or individualized-band Alpha features for one window."""
    selected, profile = get_alpha_profile(config, profile_name)
    quality = assess_signal_quality(signal, config)
    if not quality.valid:
        iaf = session_iaf or IAFResult(None, 0.0, False, "poor_signal_quality", None, 0.0, 0.0)
        return AlphaWindowFeatures(
            window_start_s,
            window_end_s,
            channel,
            stage,
            None,
            None,
            None,
            None,
            iaf.individual_alpha_frequency_hz,
            iaf.iaf_confidence,
            iaf.available,
            iaf.reason,
            None,
            quality,
            selected,
        )

    finite_signal = np.asarray(signal, dtype=float)
    estimate = estimate_welch_psd(finite_signal, sampling_rate_hz, config, selected)
    iaf = session_iaf or estimate_iaf(estimate, config, selected)
    band = _selected_band(profile, iaf)
    if band is None:
        return AlphaWindowFeatures(
            window_start_s,
            window_end_s,
            channel,
            stage,
            None,
            None,
            None,
            None,
            iaf.individual_alpha_frequency_hz,
            iaf.iaf_confidence,
            iaf.available,
            iaf.reason,
            None,
            quality,
            selected,
        )
    low_hz, high_hz = band
    absolute_power = integrate_band_power(estimate, low_hz, high_hz)
    total = profile["spectral"]["total_power_band"]
    total_power = integrate_band_power(estimate, float(total["low_hz"]), float(total["high_hz"]))
    _, envelope = alpha_filtered_envelope(
        finite_signal, sampling_rate_hz, low_hz, high_hz, config, selected
    )
    return AlphaWindowFeatures(
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        channel=channel,
        stage=stage,
        absolute_alpha_power=absolute_power,
        relative_alpha_power=absolute_power / total_power if total_power > 0 else None,
        alpha_band_low_hz=low_hz,
        alpha_band_high_hz=high_hz,
        individual_alpha_frequency_hz=iaf.individual_alpha_frequency_hz,
        iaf_confidence=iaf.iaf_confidence,
        iaf_available=iaf.available,
        iaf_reason=iaf.reason,
        alpha_envelope=float(np.mean(envelope)),
        signal_quality=quality,
        profile=selected,
    )
