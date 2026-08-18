"""Deterministic EOG feature aggregation and Wake Music V1 mapping."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any

from dreamcore.wake_music.profile import (
    GenerationConstraints,
    MusicDirections,
    PhysiologySummary,
    SourceWindow,
    WakeMusicProfile,
)


class WakeWindowUnavailableError(ValueError):
    """Raised when no annotation-confirmed Wake transition can supply a profile."""


def select_wake_window(
    annotations: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> SourceWindow:
    """Select the configured interval immediately before the final non-Wake→Wake transition."""

    wake_label = str(config["wake_stage_label"])
    duration_s = float(config["duration_s"])
    tolerance_s = float(config["transition_gap_tolerance_s"])
    ordered = sorted(annotations, key=lambda item: float(item["start_seconds"]))
    transitions: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if str(previous.get("label")) == wake_label or str(current.get("label")) != wake_label:
            continue
        previous_end = float(previous["start_seconds"]) + float(previous["duration_seconds"])
        current_start = float(current["start_seconds"])
        if abs(previous_end - current_start) <= tolerance_s:
            transitions.append((previous, current))
    if not transitions:
        raise WakeWindowUnavailableError(
            "Wake window unavailable: no annotation-confirmed Wake transition"
        )
    previous, wake = transitions[-1]
    transition_s = float(wake["start_seconds"])
    return SourceWindow(
        start_s=max(0.0, transition_s - duration_s),
        end_s=transition_s,
        selection="last_configured_interval_preceding_annotation_confirmed_wake_transition",
        transition_time_s=transition_s,
        preceding_stage=str(previous["label"]),
        wake_stage=str(wake["label"]),
    )


def manual_window(start_s: float, end_s: float, recording_duration_s: float) -> SourceWindow:
    if not math.isfinite(start_s) or not math.isfinite(end_s):
        raise ValueError("manual wake-music window must be finite")
    if start_s < 0 or end_s <= start_s or end_s > recording_duration_s:
        raise ValueError("manual wake-music window must fall within the recording")
    return SourceWindow(
        start_s=start_s,
        end_s=end_s,
        selection="manual_research_window",
        transition_time_s=None,
        preceding_stage=None,
        wake_stage=None,
    )


def summarize_physiology(
    rows: Sequence[Mapping[str, Any]], source_feature: str, minimum_rows: int
) -> PhysiologySummary:
    valid = [row for row in rows if str(row.get("signal_quality")) == "valid"]
    if len(valid) < minimum_rows:
        raise WakeWindowUnavailableError(
            f"Wake window unavailable: {len(valid)} valid EOG feature rows; {minimum_rows} required"
        )

    def values(field: str) -> list[float]:
        output = []
        for row in valid:
            value = row.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = float(value)
                if math.isfinite(number):
                    output.append(number)
        return output

    activities = values("activity_score")
    amplitudes = values("amplitude_score")
    event_rates = values("event_rate_per_min")
    times = values("window_end_s")
    if any(len(series) != len(valid) for series in (activities, amplitudes, event_rates, times)):
        raise WakeWindowUnavailableError(
            "Wake window unavailable: required EOG features are missing"
        )
    activity_trend = _linear_slope_per_minute(times, activities)
    channels = {str(row.get("source_channel", "")) for row in valid}
    source_channel = next(iter(channels)) if len(channels) == 1 else "multiple"
    return PhysiologySummary(
        activity_level=_bounded_mean(activities),
        event_rate_level=_bounded_mean(event_rates, ceiling=max(event_rates) or 1.0),
        event_rate_per_min=fmean(event_rates),
        activity_trend=activity_trend,
        amplitude_level=_bounded_mean(amplitudes),
        feature_row_count=len(valid),
        source_channel=source_channel,
        source_feature=source_feature,
    )


def build_profile(
    *,
    session_id: str,
    source_window: SourceWindow,
    physiology: PhysiologySummary,
    requested_style: str,
    generation_seed: int,
    config: Mapping[str, Any],
) -> WakeMusicProfile:
    mapping = config["mapping"]
    register_thresholds = mapping["activity_register_thresholds"]
    density_thresholds = mapping["event_rate_density_thresholds_per_min"]
    trend_thresholds = mapping["trend_thresholds_per_min"]
    amplitude_thresholds = mapping["amplitude_expression_thresholds"]

    register = _category(
        physiology.activity_level,
        float(register_thresholds["low_max"]),
        float(register_thresholds["middle_max"]),
        ("low", "mid", "high"),
    )
    density = _category(
        physiology.event_rate_per_min,
        float(density_thresholds["sparse_max"]),
        float(density_thresholds["moderate_max"]),
        ("sparse", "moderate", "moderately_active"),
    )
    stable_max = float(trend_thresholds["stable_absolute_max"])
    strong_rise = float(trend_thresholds["strongly_rising_min"])
    if physiology.activity_trend <= stable_max:
        brightness, curve = "warm", "stable"
    elif physiology.activity_trend < strong_rise:
        brightness, curve = "gradually_brighter", "slightly_rising"
    else:
        brightness, curve = "noticeably_brighter", "rising"
    expression = _category(
        physiology.amplitude_level,
        float(amplitude_thresholds["delicate_max"]),
        float(amplitude_thresholds["natural_max"]),
        ("delicate", "natural", "slightly_more_present"),
    )
    style_family = _select_style(requested_style, brightness, generation_seed, config)
    styles = config["styles"]
    if style_family not in styles:
        raise ValueError(f"unsupported Wake Music style {requested_style!r}")
    variation_count = len(styles[style_family]["variants"])
    if variation_count < 1:
        raise ValueError(f"Wake Music style {style_family!r} has no variants")
    variation_id = f"{style_family}.v{generation_seed % variation_count + 1:02d}"
    constraints = config["constraints"]
    return WakeMusicProfile(
        profile_version=str(config["profile_version"]),
        session_id=session_id,
        source_window=source_window,
        physiology=physiology,
        music=MusicDirections(
            register=register,
            density=density,
            brightness=brightness,
            expressive_strength=expression,
            energy="gentle" if curve == "stable" else "calm_to_moderately_awake",
            energy_curve=curve,
            style_family=style_family,
            style_label=str(styles[style_family]["label"]),
            tempo_character="slow_to_moderate",
        ),
        constraints=GenerationConstraints(
            max_energy=str(constraints["max_energy"]),
            max_percussiveness=str(constraints["max_percussiveness"]),
            allow_aggressive_styles=bool(constraints["allow_aggressive_styles"]),
            allow_vocals=bool(constraints["allow_vocals"]),
        ),
        mapping_version=str(config["mapping_version"]),
        generation_seed=generation_seed,
        variation_id=variation_id,
        style_selection="auto_exploratory" if requested_style == "auto" else "user_override",
    )


def profile_fingerprint(profile: WakeMusicProfile) -> str:
    payload = json.dumps(profile.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _bounded_mean(values: Sequence[float], ceiling: float = 1.0) -> float:
    if ceiling <= 0:
        raise ValueError("normalization ceiling must be positive")
    return min(1.0, max(0.0, fmean(values) / ceiling))


def _linear_slope_per_minute(times: Sequence[float], values: Sequence[float]) -> float:
    if len(times) != len(values) or len(times) < 2:
        return 0.0
    mean_time = fmean(times)
    mean_value = fmean(values)
    denominator = sum((time - mean_time) ** 2 for time in times)
    if denominator == 0:
        return 0.0
    slope_per_second = (
        sum(
            (time - mean_time) * (value - mean_value)
            for time, value in zip(times, values, strict=True)
        )
        / denominator
    )
    return slope_per_second * 60.0


def _category(value: float, first: float, second: float, labels: tuple[str, str, str]) -> str:
    if first > second:
        raise ValueError("mapping thresholds must be ordered")
    if value <= first:
        return labels[0]
    if value <= second:
        return labels[1]
    return labels[2]


def _select_style(
    requested_style: str, brightness: str, generation_seed: int, config: Mapping[str, Any]
) -> str:
    if requested_style != "auto":
        return requested_style
    candidates = tuple(config["mapping"]["auto_style_candidates"][brightness])
    if not candidates:
        raise ValueError(f"no Auto style candidates configured for {brightness!r}")
    material = f"{brightness}:{generation_seed}".encode()
    index = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % len(candidates)
    return str(candidates[index])
