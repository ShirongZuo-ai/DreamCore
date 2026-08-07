"""Non-clinical Awake/Drowsy heuristic for Alpha V1 research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from dreamcore.alpha.features import SignalQuality
from dreamcore.alpha.trend import AlphaTrendPoint


@dataclass(frozen=True)
class ResearchState:
    """Heuristic state scores; this is not a validated sleep-stage model."""

    awake_score: float | None
    drowsiness_score: float | None
    state_confidence: float
    available: bool
    reason: str | None
    provenance: str = "derived"


def estimate_research_state(
    trend: AlphaTrendPoint,
    signal_quality: SignalQuality,
    config: Mapping,
) -> ResearchState:
    """Combine history-aware Alpha evidence into bounded research scores."""
    state = config.get("alpha", {}).get("state")
    if not isinstance(state, Mapping):
        raise TypeError("Config section 'alpha.state' must be a mapping")
    if not signal_quality.valid:
        return ResearchState(None, None, 0.0, False, "poor_signal_quality")
    if (
        trend.alpha_trend == "unavailable"
        or trend.short_alpha is None
        or trend.baseline_alpha is None
        or trend.alpha_change_from_baseline is None
    ):
        return ResearchState(None, None, 0.0, False, "insufficient_alpha_history")

    awake_ratio = float(state["awake_alpha_ratio"])
    drowsy_ratio = float(state["drowsy_alpha_ratio"])
    if awake_ratio <= drowsy_ratio:
        raise ValueError("Awake alpha ratio must exceed drowsy alpha ratio")
    ratio = trend.short_alpha / trend.baseline_alpha
    low_alpha_score = 1.0 - float(
        np.clip((ratio - drowsy_ratio) / (awake_ratio - drowsy_ratio), 0.0, 1.0)
    )
    drop_score = float(
        np.clip(
            -trend.alpha_change_from_baseline / float(state["full_scale_alpha_drop_fraction"]),
            0.0,
            1.0,
        )
    )
    trend_scores = state["trend_drowsiness_scores"]
    trend_score = float(trend_scores[trend.alpha_trend])
    weights = state["weights"]
    weight_sum = float(weights["low_alpha"] + weights["alpha_drop"] + weights["trend"])
    if weight_sum <= 0:
        raise ValueError("Alpha state weights must sum to a positive value")
    drowsiness = float(
        np.clip(
            (
                float(weights["low_alpha"]) * low_alpha_score
                + float(weights["alpha_drop"]) * drop_score
                + float(weights["trend"]) * trend_score
            )
            / weight_sum,
            0.0,
            1.0,
        )
    )
    confidence = float(np.clip(signal_quality.score * trend.confidence, 0.0, 1.0))
    return ResearchState(
        awake_score=1.0 - drowsiness,
        drowsiness_score=drowsiness,
        state_confidence=confidence,
        available=True,
        reason=None,
    )
