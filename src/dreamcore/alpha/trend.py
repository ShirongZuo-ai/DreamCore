"""Sliding-history Alpha trend estimation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AlphaTrendPoint:
    """History-aware trend result aligned to one feature window."""

    timestamp_s: float
    short_alpha: float | None
    baseline_alpha: float | None
    alpha_trend: str
    alpha_trend_slope: float | None
    alpha_change_from_baseline: float | None
    confidence: float
    provenance: str = "derived"


def _history_config(config: Mapping) -> Mapping:
    history = config.get("alpha", {}).get("history")
    if not isinstance(history, Mapping):
        raise TypeError("Config section 'alpha.history' must be a mapping")
    return history


def estimate_alpha_trend(
    timestamps_s: Sequence[float],
    relative_alpha_power: Sequence[float | None],
    valid_observations: Sequence[bool],
    config: Mapping,
) -> list[AlphaTrendPoint]:
    """Estimate rising/stable/falling trends without single-window decisions."""
    times = np.asarray(timestamps_s, dtype=float)
    values = np.asarray(
        [np.nan if value is None else float(value) for value in relative_alpha_power]
    )
    valid = np.asarray(valid_observations, dtype=bool) & np.isfinite(values)
    if times.ndim != 1 or values.shape != times.shape or valid.shape != times.shape:
        raise ValueError("Alpha trend inputs must be aligned one-dimensional sequences")
    if times.size == 0:
        return []
    if np.any(np.diff(times) <= 0):
        raise ValueError("Alpha trend timestamps must be strictly increasing")

    history = _history_config(config)
    short_window_s = float(history["short_window_s"])
    trend_window_s = float(history["trend_window_s"])
    baseline_window_s = float(history["baseline_window_s"])
    min_points = int(history["minimum_points"])
    min_coverage = float(history["minimum_time_coverage_ratio"])
    stable_threshold = float(history["stable_slope_fraction_per_min"])
    if min(short_window_s, trend_window_s, baseline_window_s) <= 0 or min_points < 2:
        raise ValueError("Alpha history durations and minimum points must be positive")
    if not 0 <= min_coverage <= 1 or stable_threshold < 0:
        raise ValueError("Alpha trend coverage and stable threshold are invalid")

    baseline_end = times[0] + baseline_window_s
    output: list[AlphaTrendPoint] = []
    for timestamp in times:
        short_mask = (times <= timestamp) & (times >= timestamp - short_window_s) & valid
        short_alpha = (
            float(np.median(values[short_mask]))
            if np.count_nonzero(short_mask) >= min_points
            else None
        )
        baseline_mask = (times <= baseline_end) & valid
        baseline_ready = timestamp >= baseline_end
        baseline_alpha = (
            float(np.median(values[baseline_mask]))
            if baseline_ready and np.count_nonzero(baseline_mask) >= min_points
            else None
        )
        trend_mask = (times <= timestamp) & (times >= timestamp - trend_window_s) & valid
        trend_indices = np.flatnonzero(trend_mask)
        coverage = 0.0
        if trend_indices.size >= 2:
            coverage = min(
                (times[trend_indices[-1]] - times[trend_indices[0]]) / trend_window_s,
                1.0,
            )
        if (
            baseline_alpha is None
            or baseline_alpha <= 0
            or short_alpha is None
            or trend_indices.size < min_points
            or coverage < min_coverage
        ):
            output.append(
                AlphaTrendPoint(
                    timestamp,
                    short_alpha,
                    baseline_alpha,
                    "unavailable",
                    None,
                    None,
                    coverage,
                )
            )
            continue
        x_minutes = (times[trend_indices] - times[trend_indices][0]) / 60.0
        slope_power_per_min = float(np.polyfit(x_minutes, values[trend_indices], 1)[0])
        slope_fraction_per_min = slope_power_per_min / baseline_alpha
        if slope_fraction_per_min > stable_threshold:
            trend = "rising"
        elif slope_fraction_per_min < -stable_threshold:
            trend = "falling"
        else:
            trend = "stable"
        output.append(
            AlphaTrendPoint(
                timestamp_s=timestamp,
                short_alpha=short_alpha,
                baseline_alpha=baseline_alpha,
                alpha_trend=trend,
                alpha_trend_slope=slope_fraction_per_min,
                alpha_change_from_baseline=(short_alpha - baseline_alpha) / baseline_alpha,
                confidence=coverage,
            )
        )
    return output
