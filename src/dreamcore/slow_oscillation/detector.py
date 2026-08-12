"""Auditable, configuration-driven slow-oscillation candidate detection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from typing import Any

import mne
import numpy as np

from dreamcore.preprocessing.eeg import PreprocessedEEG


@dataclass(frozen=True)
class ZeroCrossing:
    """A linearly interpolated zero crossing between adjacent samples."""

    left_sample_index: int
    time_s: float
    direction: str


@dataclass(frozen=True)
class SlowOscillationEvent:
    """Features and audit status for one complete negative-positive cycle."""

    event_id: str
    segment_id: str
    channel: str
    event_start_s: float
    event_end_s: float
    downward_zero_crossing_s: float
    trough_time_s: float
    trough_amplitude_uv: float
    upward_zero_crossing_s: float
    positive_peak_time_s: float
    positive_peak_amplitude_uv: float
    peak_to_peak_amplitude_uv: float
    negative_halfwave_duration_s: float
    full_cycle_duration_s: float
    estimated_frequency_hz: float
    down_slope: float | None
    up_slope: float | None
    accepted: bool
    rejection_reasons: tuple[str, ...]
    detector_profile: str
    amplitude_threshold_uv: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible event record."""
        record = asdict(self)
        record["rejection_reasons"] = list(self.rejection_reasons)
        return record


@dataclass(frozen=True)
class SlowOscillationDetection:
    """Detection signal, candidates, thresholds, and resolved parameters."""

    segment_id: str
    channel_names: tuple[str, ...]
    detection_data: np.ndarray = field(repr=False, compare=False)
    sampling_rate_hz: float
    start_s: float
    end_s: float
    detector_profile: str
    events: tuple[SlowOscillationEvent, ...]
    amplitude_thresholds_uv: dict[str, float | None]
    parameters: dict[str, Any]


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


def get_detector_profile(
    config: Mapping[str, Any], profile_name: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Return a detached slow-oscillation detector profile from config."""
    section = _required_mapping(config, "slow_oscillation")
    profiles = _required_mapping(section, "profiles", "slow_oscillation")
    selected_name = str(profile_name or section["active_profile"])
    if selected_name not in profiles:
        raise ValueError(f"Unknown slow-oscillation detector profile: {selected_name}")
    profile = profiles[selected_name]
    if not isinstance(profile, Mapping):
        raise TypeError(f"slow_oscillation.profiles.{selected_name} must be a mapping")
    return selected_name, deepcopy(dict(profile))


def _validated_profile(
    config: Mapping[str, Any], profile_name: str | None, sfreq: float
) -> tuple[str, dict[str, Any]]:
    selected_name, profile = get_detector_profile(config, profile_name)
    if sfreq <= 0:
        raise ValueError("Detection sampling rate must be positive")

    band = _required_mapping(profile, "detection_band", "detector profile")
    low_hz = float(band["low_hz"])
    high_hz = float(band["high_hz"])
    if low_hz <= 0 or high_hz <= low_hz or high_hz >= sfreq / 2.0:
        raise ValueError("Detection band must satisfy 0 < low_hz < high_hz < Nyquist")

    duration = _required_mapping(profile, "duration", "detector profile")
    negative_min_s = float(duration["negative_halfwave_min_s"])
    negative_max_s = float(duration["negative_halfwave_max_s"])
    full_min_s = float(duration["full_cycle_min_s"])
    full_max_s = float(duration["full_cycle_max_s"])
    if not 0 < negative_min_s <= negative_max_s:
        raise ValueError("Negative half-wave duration bounds must be positive and ordered")
    if not 0 < full_min_s <= full_max_s:
        raise ValueError("Full-cycle duration bounds must be positive and ordered")

    amplitude = _required_mapping(profile, "amplitude", "detector profile")
    strategy = str(amplitude["strategy"])
    if strategy not in {"none", "fixed", "adaptive_quantile"}:
        raise ValueError("Amplitude strategy must be one of: none, fixed, adaptive_quantile")
    metric = str(amplitude["metric"])
    if metric != "peak_to_peak_amplitude_uv":
        raise ValueError("Only peak_to_peak_amplitude_uv is currently supported")
    fixed_min_uv = amplitude["fixed_min_uv"]
    if fixed_min_uv is not None:
        fixed_min_uv = float(fixed_min_uv)
        if fixed_min_uv < 0:
            raise ValueError("amplitude.fixed_min_uv must be non-negative or null")
    if strategy == "fixed" and fixed_min_uv is None:
        raise ValueError("Fixed amplitude strategy requires amplitude.fixed_min_uv")
    quantile = float(amplitude["quantile"])
    if not 0 <= quantile <= 1:
        raise ValueError("amplitude.quantile must be within [0, 1]")

    artifacts = _required_mapping(profile, "artifact_rejection", "detector profile")
    boundary_exclusion_s = float(artifacts["boundary_exclusion_s"])
    max_peak_to_peak_uv = float(artifacts["max_peak_to_peak_uv"])
    if boundary_exclusion_s < 0:
        raise ValueError("artifact_rejection.boundary_exclusion_s must be non-negative")
    if max_peak_to_peak_uv <= 0:
        raise ValueError("artifact_rejection.max_peak_to_peak_uv must be positive")
    invalid_masks = _normalize_masks(artifacts["invalid_time_masks"])

    amplitude_scale_to_uv = float(config["slow_oscillation"]["amplitude_scale_to_uv"])
    if amplitude_scale_to_uv <= 0:
        raise ValueError("slow_oscillation.amplitude_scale_to_uv must be positive")

    return selected_name, {
        "detection_band": {
            "low_hz": low_hz,
            "high_hz": high_hz,
            "method": str(band["method"]),
        },
        "duration": {
            "negative_halfwave_min_s": negative_min_s,
            "negative_halfwave_max_s": negative_max_s,
            "full_cycle_min_s": full_min_s,
            "full_cycle_max_s": full_max_s,
        },
        "amplitude": {
            "strategy": strategy,
            "metric": metric,
            "fixed_min_uv": fixed_min_uv,
            "quantile": quantile,
        },
        "artifact_rejection": {
            "boundary_exclusion_s": boundary_exclusion_s,
            "max_peak_to_peak_uv": max_peak_to_peak_uv,
            "invalid_time_masks": invalid_masks,
        },
        "amplitude_scale_to_uv": amplitude_scale_to_uv,
    }


def _normalize_masks(masks: Any) -> list[dict[str, float]]:
    if not isinstance(masks, Sequence) or isinstance(masks, str):
        raise TypeError("invalid_time_masks must be a sequence")
    normalized: list[dict[str, float]] = []
    for mask in masks:
        if not isinstance(mask, Mapping):
            raise TypeError("Each invalid time mask must be a mapping")
        start_s = float(mask["start_s"])
        end_s = float(mask["end_s"])
        if end_s <= start_s:
            raise ValueError("Invalid time masks must satisfy start_s < end_s")
        normalized.append({"start_s": start_s, "end_s": end_s})
    return normalized


def find_zero_crossings(
    signal: np.ndarray, sampling_rate_hz: float, start_s: float = 0.0
) -> list[ZeroCrossing]:
    """Find and linearly interpolate upward and downward zero crossings."""
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1:
        raise ValueError("signal must be one-dimensional")
    if sampling_rate_hz <= 0:
        raise ValueError("sampling_rate_hz must be positive")

    crossings: list[ZeroCrossing] = []
    for index in range(values.size - 1):
        left = values[index]
        right = values[index + 1]
        if not np.isfinite(left) or not np.isfinite(right) or left == right:
            continue
        if left >= 0 > right:
            direction = "downward"
        elif left <= 0 < right:
            direction = "upward"
        else:
            continue
        fraction = float(np.clip(-left / (right - left), 0.0, 1.0))
        crossings.append(
            ZeroCrossing(
                left_sample_index=index,
                time_s=start_s + (index + fraction) / sampling_rate_hz,
                direction=direction,
            )
        )
    return crossings


def _interpolate_nonfinite(signal: np.ndarray) -> np.ndarray:
    values = np.asarray(signal, dtype=float)
    finite = np.isfinite(values)
    if np.count_nonzero(finite) < 2:
        return np.full(values.shape, np.nan, dtype=float)
    sample_indices = np.arange(values.size)
    return np.interp(sample_indices, sample_indices[finite], values[finite])


def _filter_for_detection(
    data: np.ndarray, sfreq: float, parameters: Mapping[str, Any]
) -> np.ndarray:
    output = np.empty_like(data, dtype=float)
    band = parameters["detection_band"]
    for channel_index, channel_data in enumerate(data):
        filled = _interpolate_nonfinite(channel_data)
        if not np.all(np.isfinite(filled)):
            output[channel_index] = filled
            continue
        output[channel_index] = mne.filter.filter_data(
            filled,
            sfreq=sfreq,
            l_freq=band["low_hz"],
            h_freq=band["high_hz"],
            method=band["method"],
            copy=True,
            verbose=False,
        )
    return output


def _sample_extreme(
    signal: np.ndarray, first: ZeroCrossing, second: ZeroCrossing, mode: str
) -> int:
    start = first.left_sample_index
    stop = second.left_sample_index + 2
    window = signal[start:stop]
    relative_index = int(np.argmin(window) if mode == "min" else np.argmax(window))
    return start + relative_index


def _overlaps_mask(start_s: float, end_s: float, masks: Sequence[Mapping[str, float]]) -> bool:
    return any(start_s < mask["end_s"] and end_s > mask["start_s"] for mask in masks)


def _slope(amplitude_change_uv: float, duration_s: float) -> float | None:
    if duration_s <= 0:
        return None
    return amplitude_change_uv / duration_s


def _candidate_events_for_channel(
    channel_signal: np.ndarray,
    source_signal: np.ndarray,
    channel: str,
    channel_index: int,
    eeg: PreprocessedEEG,
    profile_name: str,
    parameters: Mapping[str, Any],
    masks: Sequence[Mapping[str, float]],
) -> list[SlowOscillationEvent]:
    crossings = find_zero_crossings(channel_signal, eeg.output_sampling_rate_hz, eeg.start_s)
    duration = parameters["duration"]
    artifacts = parameters["artifact_rejection"]
    scale = parameters["amplitude_scale_to_uv"]
    candidates: list[SlowOscillationEvent] = []

    for crossing_index in range(len(crossings) - 2):
        downward, upward, next_downward = crossings[crossing_index : crossing_index + 3]
        if [crossing.direction for crossing in (downward, upward, next_downward)] != [
            "downward",
            "upward",
            "downward",
        ]:
            continue

        trough_index = _sample_extreme(channel_signal, downward, upward, "min")
        peak_index = _sample_extreme(channel_signal, upward, next_downward, "max")
        trough_time_s = eeg.start_s + trough_index / eeg.output_sampling_rate_hz
        peak_time_s = eeg.start_s + peak_index / eeg.output_sampling_rate_hz
        trough_uv = float(channel_signal[trough_index] * scale)
        positive_peak_uv = float(channel_signal[peak_index] * scale)
        peak_to_peak_uv = positive_peak_uv - trough_uv
        negative_duration_s = upward.time_s - downward.time_s
        full_duration_s = next_downward.time_s - downward.time_s

        reasons: list[str] = []
        if negative_duration_s < duration["negative_halfwave_min_s"]:
            reasons.append("negative_halfwave_too_short")
        if negative_duration_s > duration["negative_halfwave_max_s"]:
            reasons.append("negative_halfwave_too_long")
        if full_duration_s < duration["full_cycle_min_s"]:
            reasons.append("full_cycle_too_short")
        if full_duration_s > duration["full_cycle_max_s"]:
            reasons.append("full_cycle_too_long")

        source_start = downward.left_sample_index
        source_stop = next_downward.left_sample_index + 2
        if not np.all(np.isfinite(source_signal[source_start:source_stop])):
            reasons.append("nan_or_nonfinite")
        boundary_s = artifacts["boundary_exclusion_s"]
        if (
            downward.time_s < eeg.start_s + boundary_s
            or next_downward.time_s > eeg.end_s - boundary_s
        ):
            reasons.append("near_boundary")
        if peak_to_peak_uv > artifacts["max_peak_to_peak_uv"]:
            reasons.append("extreme_peak_to_peak")
        if _overlaps_mask(downward.time_s, next_downward.time_s, masks):
            reasons.append("invalid_time_mask")

        candidate_number = len(candidates) + 1
        candidates.append(
            SlowOscillationEvent(
                event_id=(f"{eeg.segment_id}_{channel_index + 1:02d}_{candidate_number:05d}"),
                segment_id=eeg.segment_id,
                channel=channel,
                event_start_s=downward.time_s,
                event_end_s=next_downward.time_s,
                downward_zero_crossing_s=downward.time_s,
                trough_time_s=trough_time_s,
                trough_amplitude_uv=trough_uv,
                upward_zero_crossing_s=upward.time_s,
                positive_peak_time_s=peak_time_s,
                positive_peak_amplitude_uv=positive_peak_uv,
                peak_to_peak_amplitude_uv=peak_to_peak_uv,
                negative_halfwave_duration_s=negative_duration_s,
                full_cycle_duration_s=full_duration_s,
                estimated_frequency_hz=1.0 / full_duration_s,
                down_slope=_slope(trough_uv, trough_time_s - downward.time_s),
                up_slope=_slope(
                    positive_peak_uv - trough_uv,
                    peak_time_s - trough_time_s,
                ),
                accepted=not reasons,
                rejection_reasons=tuple(reasons),
                detector_profile=profile_name,
                amplitude_threshold_uv=None,
            )
        )
    return candidates


def _amplitude_threshold(
    events: Sequence[SlowOscillationEvent], amplitude: Mapping[str, Any]
) -> float | None:
    strategy = amplitude["strategy"]
    if strategy == "none":
        return None
    if strategy == "fixed":
        return float(amplitude["fixed_min_uv"])
    eligible = [event.peak_to_peak_amplitude_uv for event in events if event.accepted]
    if not eligible:
        return None
    return float(np.quantile(eligible, amplitude["quantile"]))


def _apply_amplitude_threshold(
    events: Sequence[SlowOscillationEvent], threshold_uv: float | None
) -> list[SlowOscillationEvent]:
    output = []
    for event in events:
        reasons = list(event.rejection_reasons)
        if threshold_uv is not None and event.peak_to_peak_amplitude_uv < threshold_uv:
            reasons.append("below_amplitude_threshold")
        output.append(
            replace(
                event,
                amplitude_threshold_uv=threshold_uv,
                accepted=not reasons,
                rejection_reasons=tuple(reasons),
            )
        )
    return output


def detect_slow_oscillations(
    eeg: PreprocessedEEG,
    config: Mapping[str, Any],
    profile_name: str | None = None,
    invalid_time_masks: Sequence[Mapping[str, float]] | None = None,
) -> SlowOscillationDetection:
    """Detect auditable slow-oscillation candidates independently per channel."""
    original = np.asarray(eeg.data)
    if original.ndim != 2 or original.shape[0] != len(eeg.channel_names):
        raise ValueError("Preprocessed EEG data and channel names are inconsistent")
    selected_name, parameters = _validated_profile(
        config, profile_name, eeg.output_sampling_rate_hz
    )
    configured_masks = parameters["artifact_rejection"]["invalid_time_masks"]
    extra_masks = _normalize_masks(invalid_time_masks or [])
    masks = [*configured_masks, *extra_masks]
    parameters["artifact_rejection"]["invalid_time_masks"] = masks
    detection_data = _filter_for_detection(
        np.array(original, dtype=float, copy=True),
        eeg.output_sampling_rate_hz,
        parameters,
    )

    all_events: list[SlowOscillationEvent] = []
    thresholds: dict[str, float | None] = {}
    for channel_index, channel in enumerate(eeg.channel_names):
        candidates = _candidate_events_for_channel(
            detection_data[channel_index],
            original[channel_index],
            channel,
            channel_index,
            eeg,
            selected_name,
            parameters,
            masks,
        )
        threshold = _amplitude_threshold(candidates, parameters["amplitude"])
        thresholds[channel] = threshold
        all_events.extend(_apply_amplitude_threshold(candidates, threshold))

    return SlowOscillationDetection(
        segment_id=eeg.segment_id,
        channel_names=eeg.channel_names,
        detection_data=detection_data,
        sampling_rate_hz=eeg.output_sampling_rate_hz,
        start_s=eeg.start_s,
        end_s=eeg.end_s,
        detector_profile=selected_name,
        events=tuple(all_events),
        amplitude_thresholds_uv=thresholds,
        parameters=parameters,
    )
