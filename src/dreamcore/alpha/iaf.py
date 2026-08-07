"""Individual alpha frequency estimation with explicit unavailability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import find_peaks

from dreamcore.alpha.spectral import SpectralEstimate, get_alpha_profile


@dataclass(frozen=True)
class IAFResult:
    """A session/channel IAF result that may be explicitly unavailable."""

    individual_alpha_frequency_hz: float | None
    iaf_confidence: float
    available: bool
    reason: str | None
    peak_prominence_db: float | None
    search_band_low_hz: float
    search_band_high_hz: float
    provenance: str = "derived"


def estimate_iaf(
    estimate: SpectralEstimate,
    config: Mapping[str, Any],
    profile_name: str | None = None,
) -> IAFResult:
    """Find a reliable PSD peak without forcing an IAF when evidence is weak."""
    selected, profile = get_alpha_profile(config, profile_name)
    iaf = profile.get("iaf")
    if not isinstance(iaf, Mapping):
        raise TypeError(f"alpha.profiles.{selected}.iaf must be a mapping")
    low_hz = float(iaf["search_band_low_hz"])
    high_hz = float(iaf["search_band_high_hz"])
    edge_margin_hz = float(iaf["edge_margin_hz"])
    min_prominence_db = float(iaf["min_prominence_db"])
    high_confidence_db = float(iaf["high_confidence_prominence_db"])
    if low_hz <= 0 or high_hz <= low_hz or edge_margin_hz < 0:
        raise ValueError("IAF search bounds and edge margin are invalid")
    if high_confidence_db <= min_prominence_db:
        raise ValueError("IAF high-confidence prominence must exceed its minimum")

    mask = (estimate.frequencies_hz >= low_hz) & (estimate.frequencies_hz <= high_hz)
    frequencies = estimate.frequencies_hz[mask]
    power = estimate.psd_uv2_per_hz[mask]
    if frequencies.size < 3 or not np.all(np.isfinite(power)) or np.max(power) <= 0:
        return IAFResult(None, 0.0, False, "insufficient_search_band_psd", None, low_hz, high_hz)
    power_db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
    peaks, properties = find_peaks(power_db, prominence=min_prominence_db)
    if peaks.size == 0:
        return IAFResult(None, 0.0, False, "no_reliable_alpha_peak", None, low_hz, high_hz)

    best_position = int(np.argmax(properties["prominences"]))
    peak_index = int(peaks[best_position])
    peak_hz = float(frequencies[peak_index])
    prominence_db = float(properties["prominences"][best_position])
    if peak_hz <= low_hz + edge_margin_hz or peak_hz >= high_hz - edge_margin_hz:
        return IAFResult(
            None,
            0.0,
            False,
            "peak_too_close_to_search_boundary",
            prominence_db,
            low_hz,
            high_hz,
        )
    confidence = float(
        np.clip(
            (prominence_db - min_prominence_db) / (high_confidence_db - min_prominence_db),
            0.0,
            1.0,
        )
    )
    return IAFResult(peak_hz, confidence, True, None, prominence_db, low_hz, high_hz)
