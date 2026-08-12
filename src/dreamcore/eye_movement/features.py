"""Classical, replay-aligned EOG feature and candidate-event extraction."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, find_peaks, sosfiltfilt


@dataclass(frozen=True)
class EyeMovementFeature:
    """One analysis-window feature row timestamped at its window end."""

    session_id: str
    source_channel: str
    window_start_s: float
    window_end_s: float
    recording_start_time: str | None
    absolute_window_start: str | None
    absolute_window_end: str | None
    eog_rms_uv: float | None
    peak_to_peak_uv: float | None
    mean_absolute_derivative_uv_per_s: float | None
    robust_deviation_z: float | None
    activity_score: float | None
    amplitude_score: float | None
    event_rate_per_min: float | None
    event_candidate: bool
    signal_quality: str
    signal_quality_reasons: tuple[str, ...]
    feature_version: str
    feature_provenance: str = "derived"

    def to_dict(self) -> dict[str, Any]:
        output = asdict(self)
        output["signal_quality_reasons"] = ";".join(self.signal_quality_reasons)
        return output


@dataclass(frozen=True)
class EyeMovementEvent:
    """A robust EOG activity excursion; not a REM or dream label."""

    event_id: str
    session_id: str
    timestamp: float
    window_start_s: float
    window_end_s: float
    duration_s: float
    amplitude_uv: float
    polarity: str
    confidence: float
    robust_deviation_z: float
    source_channel: str
    feature_version: str
    provenance: str = "derived"
    event_type: str = "eye_movement_candidate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EyeMovementTrack:
    """Filtered signal plus replay-aligned activity and event artifacts."""

    filtered_signal_uv: np.ndarray
    features: tuple[EyeMovementFeature, ...]
    events: tuple[EyeMovementEvent, ...]
    attempted_windows: int
    accepted_windows: int
    rejected_windows: int
    rejection_reasons: Mapping[str, int]
    coverage_start_s: float | None
    coverage_end_s: float | None


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Config section {key!r} must be a mapping")
    return value


def discover_eog_channels(
    channel_names: Sequence[str],
    channel_types: Sequence[str],
    config: Mapping[str, Any],
) -> tuple[str, ...]:
    """Discover EOG labels from EDF/MNE metadata without channel substitution."""

    if len(channel_names) != len(channel_types):
        raise ValueError("Channel names and types must have equal length")
    eye = _section(config, "eye_movement")
    discovery = _section(eye, "channel_discovery")
    preferred_types = {str(value).casefold() for value in discovery["preferred_mne_types"]}
    patterns = tuple(re.compile(str(value)) for value in discovery["label_patterns"])
    type_matches = {
        name
        for name, channel_type in zip(channel_names, channel_types, strict=True)
        if channel_type.casefold() in preferred_types
    }
    label_matches = {
        name for name in channel_names if any(pattern.search(name) for pattern in patterns)
    }
    matches = tuple(name for name in channel_names if name in type_matches | label_matches)
    if bool(discovery["require_unique"]) and len(matches) > 1:
        raise ValueError(f"EOG discovery is ambiguous; matched channels: {list(matches)}")
    return matches


def _iso_at(recording_start_time: str | None, offset_s: float) -> str | None:
    if recording_start_time is None:
        return None
    origin = datetime.fromisoformat(recording_start_time.replace("Z", "+00:00"))
    return (origin + timedelta(seconds=offset_s)).isoformat()


def _normalized(values: np.ndarray, valid: np.ndarray, config: Mapping[str, Any]) -> np.ndarray:
    output = np.full(values.shape, np.nan, dtype=float)
    finite_valid = valid & np.isfinite(values)
    if not np.any(finite_valid):
        return output
    normalization = _section(_section(config, "eye_movement"), "normalization")
    selected = values[finite_valid]
    low = float(np.quantile(selected, float(normalization["low_quantile"])))
    high = float(np.quantile(selected, float(normalization["high_quantile"])))
    epsilon = float(normalization["epsilon"])
    if high - low <= epsilon:
        return output
    output[finite_valid] = np.clip((values[finite_valid] - low) / (high - low), 0.0, 1.0)
    return output


def _filter_eog(
    values_uv: np.ndarray, sampling_rate_hz: float, config: Mapping[str, Any]
) -> np.ndarray:
    filtering = _section(_section(config, "eye_movement"), "filtering")
    if str(filtering["method"]) != "butterworth" or str(filtering["phase"]) != "zero":
        raise ValueError("Eye Movement V1 supports configured zero-phase Butterworth filtering")
    low_hz = float(filtering["low_hz"])
    high_hz = float(filtering["high_hz"])
    if not 0 < low_hz < high_hz < sampling_rate_hz / 2:
        raise ValueError("Configured EOG passband must be inside the recording Nyquist range")
    sos = butter(
        int(filtering["order"]),
        [low_hz, high_hz],
        btype="bandpass",
        fs=sampling_rate_hz,
        output="sos",
    )
    return np.asarray(sosfiltfilt(sos, values_uv), dtype=float)


def extract_eye_movement_track(
    signal_uv: Sequence[float] | np.ndarray,
    sampling_rate_hz: float,
    source_channel: str,
    session_id: str,
    recording_start_time: str | None,
    config: Mapping[str, Any],
) -> EyeMovementTrack:
    """Extract stage-agnostic EOG activity and robust candidate events."""

    eye = _section(config, "eye_movement")
    windowing = _section(eye, "windowing")
    if str(windowing["timestamp_semantics"]) != "window_end":
        raise ValueError("Eye Movement V1 requires window-end timestamps")
    values = np.asarray(signal_uv, dtype=float)
    if values.ndim != 1:
        raise ValueError("EOG signal must be one-dimensional")
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be positive")
    window_samples = int(round(float(windowing["analysis_window_s"]) * sampling_rate_hz))
    step_samples = int(round(float(windowing["step_s"]) * sampling_rate_hz))
    if window_samples <= 0 or step_samples <= 0:
        raise ValueError("Configured EOG window and step must be positive")
    if values.size < window_samples:
        return EyeMovementTrack(
            filtered_signal_uv=np.full(values.shape, np.nan),
            features=(),
            events=(),
            attempted_windows=0,
            accepted_windows=0,
            rejected_windows=0,
            rejection_reasons={"insufficient_samples": 1},
            coverage_start_s=None,
            coverage_end_s=None,
        )

    finite = np.isfinite(values)
    if np.any(finite):
        cleaned = np.interp(np.arange(values.size), np.flatnonzero(finite), values[finite])
        filtered = _filter_eog(cleaned, sampling_rate_hz, config)
    else:
        cleaned = np.zeros(values.shape, dtype=float)
        filtered = np.full(values.shape, np.nan)

    starts = np.arange(0, values.size - window_samples + 1, step_samples, dtype=int)
    ends = starts + window_samples
    attempted = int(starts.size)
    filtered_for_windows = np.nan_to_num(filtered, nan=0.0)
    filtered_windows = np.lib.stride_tricks.sliding_window_view(
        filtered_for_windows, window_samples
    )[::step_samples][:attempted]
    cleaned_windows = np.lib.stride_tricks.sliding_window_view(cleaned, window_samples)[
        ::step_samples
    ][:attempted]
    finite_windows = np.lib.stride_tricks.sliding_window_view(finite, window_samples)[
        ::step_samples
    ][:attempted]
    rms = np.sqrt(np.mean(filtered_windows * filtered_windows, axis=1))
    peak_to_peak = np.ptp(filtered_windows, axis=1)
    derivative = np.abs(np.diff(filtered_windows, axis=1)) * sampling_rate_hz
    mean_absolute_derivative = np.mean(derivative, axis=1)
    finite_ratio = np.mean(finite_windows, axis=1)
    raw_standard_deviation = np.std(cleaned_windows, axis=1)

    quality = _section(eye, "quality")
    reasons: list[tuple[str, ...]] = []
    rejection_counts: Counter[str] = Counter()
    valid = np.ones(attempted, dtype=bool)
    for index in range(attempted):
        row_reasons = []
        if finite_ratio[index] < float(quality["min_finite_ratio"]):
            row_reasons.append("insufficient_finite_samples")
        if raw_standard_deviation[index] < float(quality["min_standard_deviation_uv"]):
            row_reasons.append("flat_signal")
        if peak_to_peak[index] > float(quality["max_peak_to_peak_uv"]):
            row_reasons.append("excessive_peak_to_peak")
        if not np.isfinite(filtered_windows[index]).all():
            row_reasons.append("filter_failure")
        reasons.append(tuple(row_reasons))
        if row_reasons:
            valid[index] = False
            rejection_counts.update(row_reasons)

    valid_rms = rms[valid]
    fill = float(np.median(valid_rms)) if valid_rms.size else 0.0
    baseline_input = np.where(valid, rms, fill)
    baseline = _section(eye, "local_baseline")
    baseline_points = max(
        3,
        int(round(float(baseline["duration_s"]) / float(windowing["step_s"]))),
    )
    if baseline_points % 2 == 0:
        baseline_points += 1
    local_median = median_filter(baseline_input, size=baseline_points, mode="nearest")
    local_mad = median_filter(
        np.abs(baseline_input - local_median), size=baseline_points, mode="nearest"
    )
    epsilon = float(_section(eye, "normalization")["epsilon"])
    robust_scale = float(baseline["robust_scale_factor"]) * local_mad
    robust_z = np.zeros(rms.shape, dtype=float)
    np.divide(
        rms - local_median,
        robust_scale,
        out=robust_z,
        where=robust_scale > epsilon,
    )
    robust_z[~valid] = np.nan
    activity_score = _normalized(rms, valid, config)
    amplitude_score = _normalized(peak_to_peak, valid, config)

    event_config = _section(eye, "event_detection")
    peak_distance = max(
        1,
        int(round(float(event_config["minimum_separation_s"]) / float(windowing["step_s"]))),
    )
    peak_indices, _ = find_peaks(
        np.nan_to_num(robust_z, nan=-np.inf),
        height=float(event_config["activity_robust_z_threshold"]),
        distance=peak_distance,
    )
    feature_version = str(eye["feature_version"])
    events: list[EyeMovementEvent] = []
    for sequence, feature_index in enumerate(peak_indices, start=1):
        sample_start = int(starts[feature_index])
        sample_end = int(ends[feature_index])
        segment = filtered_for_windows[sample_start:sample_end]
        local_center = float(np.median(segment))
        absolute = np.abs(segment - local_center)
        peak_sample_local = int(np.argmax(absolute))
        peak_amplitude = float(absolute[peak_sample_local])
        threshold = peak_amplitude * (1.0 - float(event_config["peak_width_relative_height"]))
        left = peak_sample_local
        right = peak_sample_local
        while left > 0 and absolute[left - 1] >= threshold:
            left -= 1
        while right + 1 < absolute.size and absolute[right + 1] >= threshold:
            right += 1
        width_samples = float(right - left + 1)
        duration_s = float(
            np.clip(
                width_samples / sampling_rate_hz,
                float(event_config["minimum_duration_s"]),
                float(event_config["maximum_duration_s"]),
            )
        )
        timestamp = (sample_start + peak_sample_local) / sampling_rate_hz
        event_start = max(sample_start / sampling_rate_hz, timestamp - duration_s / 2)
        event_end = min(sample_end / sampling_rate_hz, event_start + duration_s)
        signed_amplitude = float(segment[peak_sample_local] - local_center)
        score = float(robust_z[feature_index])
        confidence = float(
            np.clip(score / float(event_config["confidence_saturation_z"]), 0.0, 1.0)
        )
        events.append(
            EyeMovementEvent(
                event_id=f"{session_id}-eye-{sequence:06d}",
                session_id=session_id,
                timestamp=timestamp,
                window_start_s=event_start,
                window_end_s=event_end,
                duration_s=event_end - event_start,
                amplitude_uv=signed_amplitude,
                polarity="positive" if signed_amplitude >= 0 else "negative",
                confidence=confidence,
                robust_deviation_z=score,
                source_channel=source_channel,
                feature_version=feature_version,
            )
        )

    event_times = np.asarray([event.timestamp for event in events], dtype=float)
    window_end_times = ends / sampling_rate_hz
    window_start_times = starts / sampling_rate_hz
    history_s = float(event_config["event_rate_history_s"])
    event_rates = np.zeros(attempted, dtype=float)
    event_candidates = np.zeros(attempted, dtype=bool)
    if event_times.size:
        left = np.searchsorted(event_times, window_end_times - history_s, side="right")
        right = np.searchsorted(event_times, window_end_times, side="right")
        event_rates = (right - left) * 60.0 / history_s
        candidate_left = np.searchsorted(event_times, window_start_times, side="left")
        candidate_right = np.searchsorted(event_times, window_end_times, side="right")
        event_candidates = candidate_right > candidate_left

    features = []
    for index, (sample_start, sample_end) in enumerate(zip(starts, ends, strict=True)):
        start_s = float(sample_start / sampling_rate_hz)
        end_s = float(sample_end / sampling_rate_hz)
        is_valid = bool(valid[index])
        features.append(
            EyeMovementFeature(
                session_id=session_id,
                source_channel=source_channel,
                window_start_s=start_s,
                window_end_s=end_s,
                recording_start_time=recording_start_time,
                absolute_window_start=_iso_at(recording_start_time, start_s),
                absolute_window_end=_iso_at(recording_start_time, end_s),
                eog_rms_uv=float(rms[index]) if is_valid else None,
                peak_to_peak_uv=float(peak_to_peak[index]) if is_valid else None,
                mean_absolute_derivative_uv_per_s=(
                    float(mean_absolute_derivative[index]) if is_valid else None
                ),
                robust_deviation_z=float(robust_z[index]) if is_valid else None,
                activity_score=float(activity_score[index]) if is_valid else None,
                amplitude_score=float(amplitude_score[index]) if is_valid else None,
                event_rate_per_min=float(event_rates[index]) if is_valid else None,
                event_candidate=bool(event_candidates[index]),
                signal_quality="valid" if is_valid else "invalid",
                signal_quality_reasons=reasons[index],
                feature_version=feature_version,
            )
        )
    accepted = int(np.sum(valid))
    return EyeMovementTrack(
        filtered_signal_uv=filtered,
        features=tuple(features),
        events=tuple(events),
        attempted_windows=attempted,
        accepted_windows=accepted,
        rejected_windows=attempted - accepted,
        rejection_reasons=dict(rejection_counts),
        coverage_start_s=float(window_end_times[0]) if attempted else None,
        coverage_end_s=float(window_end_times[-1]) if attempted else None,
    )
