"""Offline, non-causal Hilbert phase estimation for N3 EEG research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Any

import mne
import numpy as np
from scipy.signal import hilbert

from dreamcore.preprocessing.eeg import PreprocessedEEG
from dreamcore.slow_oscillation.detector import (
    SlowOscillationDetection,
    SlowOscillationEvent,
)


@dataclass(frozen=True)
class PhaseProvenance:
    """Source and profile identifiers retained with a channel phase result."""

    subject_id: str
    recording_id: str
    segment_id: str
    channel: str
    preprocessing_profile: str
    detector_profile: str


@dataclass(frozen=True)
class HilbertChannelPhase:
    """Continuous phase products and validity masks for one EEG channel."""

    provenance: PhaseProvenance
    phase_profile: str
    sampling_rate_hz: float
    start_s: float
    end_s: float
    phase_signal: np.ndarray = field(repr=False, compare=False)
    wrapped_phase: np.ndarray = field(repr=False, compare=False)
    unwrapped_phase: np.ndarray = field(repr=False, compare=False)
    amplitude_envelope: np.ndarray = field(repr=False, compare=False)
    instantaneous_frequency_hz: np.ndarray = field(repr=False, compare=False)
    valid_phase_mask: np.ndarray = field(repr=False, compare=False)
    invalid_reason_masks: dict[str, np.ndarray] = field(repr=False, compare=False)
    amplitude_threshold_uv: float | None
    parameters: dict[str, Any]

    @property
    def valid_phase_ratio(self) -> float:
        """Return the fraction of time samples considered phase-valid."""
        if self.valid_phase_mask.size == 0:
            return 0.0
        return float(np.mean(self.valid_phase_mask))


@dataclass(frozen=True)
class HilbertPhaseResult:
    """Independent per-channel Hilbert phase estimates for one N3 segment."""

    segment_id: str
    channel_names: tuple[str, ...]
    channels: tuple[HilbertChannelPhase, ...]
    phase_profile: str
    parameters: dict[str, Any]

    def channel(self, name: str) -> HilbertChannelPhase:
        """Return one named channel result."""
        for channel_phase in self.channels:
            if channel_phase.provenance.channel == name:
                return channel_phase
        raise KeyError(f"Phase channel not found: {name}")


@dataclass(frozen=True)
class PhaseLandmark:
    """Estimated and expected phase at one accepted-event landmark."""

    segment_id: str
    channel: str
    event_id: str
    landmark_type: str
    landmark_time_s: float
    expected_phase_rad: float
    estimated_phase_rad: float
    circular_error_rad: float
    circular_error_deg: float
    amplitude_envelope: float
    instantaneous_frequency_hz: float | None
    phase_valid: bool
    preprocessing_profile: str
    detector_profile: str
    phase_profile: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible landmark record."""
        return asdict(self)


@dataclass(frozen=True)
class EventPhaseValidation:
    """Within-cycle phase validity and forward-evolution diagnostics."""

    segment_id: str
    channel: str
    event_id: str
    event_phase_valid: bool
    phase_forward: bool
    valid_sample_fraction: float
    net_phase_advance_rad: float | None
    reverse_step_count: int
    total_step_count: int
    reverse_step_fraction: float | None


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


def get_phase_profile(
    config: Mapping[str, Any], profile_name: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Return a detached Hilbert phase profile selected from configuration."""
    section = _required_mapping(config, "hilbert_phase")
    profiles = _required_mapping(section, "profiles", "hilbert_phase")
    selected_name = str(profile_name or section["active_profile"])
    if selected_name not in profiles:
        raise ValueError(f"Unknown Hilbert phase profile: {selected_name}")
    profile = profiles[selected_name]
    if not isinstance(profile, Mapping):
        raise TypeError(f"hilbert_phase.profiles.{selected_name} must be a mapping")
    return selected_name, deepcopy(dict(profile))


def _normalize_masks(masks: Any) -> list[dict[str, float]]:
    if not isinstance(masks, Sequence) or isinstance(masks, str):
        raise TypeError("invalid_time_masks must be a sequence")
    output = []
    for mask in masks:
        if not isinstance(mask, Mapping):
            raise TypeError("Each invalid time mask must be a mapping")
        start_s = float(mask["start_s"])
        end_s = float(mask["end_s"])
        if end_s <= start_s:
            raise ValueError("Invalid time masks must satisfy start_s < end_s")
        output.append({"start_s": start_s, "end_s": end_s})
    return output


def _validated_profile(
    config: Mapping[str, Any], profile_name: str | None, sfreq: float
) -> tuple[str, dict[str, Any]]:
    selected_name, profile = get_phase_profile(config, profile_name)
    if sfreq <= 0:
        raise ValueError("Hilbert sampling rate must be positive")
    band = _required_mapping(profile, "phase_band", "Hilbert phase profile")
    low_hz = float(band["low_hz"])
    high_hz = float(band["high_hz"])
    if low_hz <= 0 or high_hz <= low_hz or high_hz >= sfreq / 2.0:
        raise ValueError("Phase band must satisfy 0 < low_hz < high_hz < Nyquist")
    filter_phase = str(band["phase"])
    if filter_phase not in {"zero", "zero-double"}:
        raise ValueError("Offline Hilbert filter phase must be zero or zero-double")

    boundary_invalid_s = float(profile["boundary_invalid_s"])
    min_signal_duration_s = float(profile["min_signal_duration_s"])
    constant_std_tolerance = float(profile["constant_std_tolerance"])
    if boundary_invalid_s < 0 or min_signal_duration_s <= 0:
        raise ValueError("Boundary invalid time must be non-negative and duration positive")
    if constant_std_tolerance < 0:
        raise ValueError("constant_std_tolerance must be non-negative")

    amplitude = _required_mapping(profile, "amplitude_envelope", "Hilbert phase profile")
    strategy = str(amplitude["strategy"])
    if strategy not in {"none", "fixed", "adaptive_quantile"}:
        raise ValueError("Envelope strategy must be one of: none, fixed, adaptive_quantile")
    fixed_min_uv = amplitude["fixed_min_uv"]
    if fixed_min_uv is not None:
        fixed_min_uv = float(fixed_min_uv)
        if fixed_min_uv < 0:
            raise ValueError("amplitude_envelope.fixed_min_uv must be non-negative")
    if strategy == "fixed" and fixed_min_uv is None:
        raise ValueError("Fixed envelope strategy requires fixed_min_uv")
    quantile = float(amplitude["quantile"])
    if not 0 <= quantile <= 1:
        raise ValueError("amplitude_envelope.quantile must be within [0, 1]")

    frequency = _required_mapping(profile, "instantaneous_frequency", "Hilbert phase profile")
    compute_frequency = bool(frequency["enabled"])
    min_frequency_hz = float(frequency["min_hz"])
    max_frequency_hz = float(frequency["max_hz"])
    if min_frequency_hz < 0 or max_frequency_hz <= min_frequency_hz:
        raise ValueError("Instantaneous-frequency bounds must be ordered")

    event_validation = _required_mapping(profile, "event_validation", "Hilbert phase profile")
    reverse_step_tolerance_rad = float(event_validation["reverse_step_tolerance_rad"])
    max_reverse_step_fraction = float(event_validation["max_reverse_step_fraction"])
    min_forward_advance_rad = float(event_validation["min_forward_advance_rad"])
    min_event_valid_fraction = float(event_validation["min_event_valid_fraction"])
    if reverse_step_tolerance_rad < 0 or min_forward_advance_rad < 0:
        raise ValueError("Event forward-evolution tolerances must be non-negative")
    if not 0 <= max_reverse_step_fraction <= 1 or not 0 <= min_event_valid_fraction <= 1:
        raise ValueError("Event validation fractions must be within [0, 1]")

    expected_landmarks = _required_mapping(
        profile, "expected_landmark_phases_rad", "Hilbert phase profile"
    )
    required_landmarks = {
        "downward_zero_crossing",
        "trough",
        "upward_zero_crossing",
        "positive_peak",
    }
    if set(expected_landmarks) != required_landmarks:
        raise ValueError("Expected landmark phase mapping has unexpected keys")

    scale = float(config["hilbert_phase"]["amplitude_scale_to_uv"])
    if scale <= 0:
        raise ValueError("hilbert_phase.amplitude_scale_to_uv must be positive")
    return selected_name, {
        "phase_band": {
            "low_hz": low_hz,
            "high_hz": high_hz,
            "method": str(band["method"]),
            "phase": filter_phase,
        },
        "project_phase_offset_rad": float(profile["project_phase_offset_rad"]),
        "boundary_invalid_s": boundary_invalid_s,
        "min_signal_duration_s": min_signal_duration_s,
        "constant_std_tolerance": constant_std_tolerance,
        "amplitude_envelope": {
            "strategy": strategy,
            "fixed_min_uv": fixed_min_uv,
            "quantile": quantile,
        },
        "instantaneous_frequency": {
            "enabled": compute_frequency,
            "min_hz": min_frequency_hz,
            "max_hz": max_frequency_hz,
        },
        "invalid_time_masks": _normalize_masks(profile["invalid_time_masks"]),
        "event_validation": {
            "reverse_step_tolerance_rad": reverse_step_tolerance_rad,
            "max_reverse_step_fraction": max_reverse_step_fraction,
            "min_forward_advance_rad": min_forward_advance_rad,
            "min_event_valid_fraction": min_event_valid_fraction,
        },
        "expected_landmark_phases_rad": {
            str(name): float(value) for name, value in expected_landmarks.items()
        },
        "amplitude_scale_to_uv": scale,
        "processing_mode": "offline_noncausal_zero_phase",
    }


def wrap_phase(phase: np.ndarray | float) -> np.ndarray | float:
    """Wrap radians to the half-open interval ``[-pi, pi)``."""
    wrapped = (np.asarray(phase) + np.pi) % (2.0 * np.pi) - np.pi
    if np.ndim(phase) == 0:
        return float(wrapped)
    return wrapped


def circular_error(estimated_phase: float, expected_phase: float) -> float:
    """Return signed shortest angular error in radians."""
    return float(wrap_phase(estimated_phase - expected_phase))


def _interpolate_nonfinite(signal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(signal)
    if np.count_nonzero(finite) < 2:
        raise ValueError("Signal must contain at least two finite samples")
    indices = np.arange(signal.size)
    return np.interp(indices, indices[finite], signal[finite]), ~finite


def _mask_from_ranges(
    size: int,
    sfreq: float,
    start_s: float,
    masks: Sequence[Mapping[str, float]],
) -> np.ndarray:
    times = start_s + np.arange(size) / sfreq
    invalid = np.zeros(size, dtype=bool)
    for mask in masks:
        invalid |= (times >= mask["start_s"]) & (times < mask["end_s"])
    return invalid


def _envelope_threshold(
    envelope_uv: np.ndarray,
    eligible_mask: np.ndarray,
    amplitude_config: Mapping[str, Any],
) -> float | None:
    strategy = amplitude_config["strategy"]
    if strategy == "none":
        return None
    if strategy == "fixed":
        return float(amplitude_config["fixed_min_uv"])
    eligible = envelope_uv[eligible_mask]
    if eligible.size == 0:
        return None
    return float(np.quantile(eligible, amplitude_config["quantile"]))


def estimate_channel_hilbert(
    signal: np.ndarray,
    sampling_rate_hz: float,
    start_s: float,
    provenance: PhaseProvenance,
    config: Mapping[str, Any],
    profile_name: str | None = None,
    invalid_time_masks: Sequence[Mapping[str, float]] | None = None,
) -> HilbertChannelPhase:
    """Estimate continuous offline Hilbert phase for one channel."""
    original = np.asarray(signal, dtype=float)
    if original.ndim != 1:
        raise ValueError("Hilbert input signal must be one-dimensional")
    if original.size == 0:
        raise ValueError("Hilbert input signal cannot be empty")
    selected_name, parameters = _validated_profile(config, profile_name, sampling_rate_hz)
    duration_s = original.size / sampling_rate_hz
    if duration_s < parameters["min_signal_duration_s"]:
        raise ValueError("Hilbert input signal is shorter than configured minimum")
    finite_values = original[np.isfinite(original)]
    if finite_values.size < 2:
        raise ValueError("Hilbert input signal has insufficient finite samples")
    if np.std(finite_values) <= parameters["constant_std_tolerance"]:
        raise ValueError("Hilbert input signal is constant within configured tolerance")

    filled, nonfinite_mask = _interpolate_nonfinite(original)
    band = parameters["phase_band"]
    phase_signal = mne.filter.filter_data(
        filled,
        sfreq=sampling_rate_hz,
        l_freq=band["low_hz"],
        h_freq=band["high_hz"],
        method=band["method"],
        phase=band["phase"],
        copy=True,
        verbose=False,
    )
    analytic_signal = hilbert(phase_signal)
    raw_phase = np.angle(analytic_signal)
    wrapped_phase = np.asarray(wrap_phase(raw_phase + parameters["project_phase_offset_rad"]))
    unwrapped_phase = np.unwrap(wrapped_phase)
    envelope_uv = np.abs(analytic_signal) * parameters["amplitude_scale_to_uv"]

    frequency_config = parameters["instantaneous_frequency"]
    if frequency_config["enabled"]:
        instantaneous_frequency_hz = np.gradient(unwrapped_phase) * sampling_rate_hz / (2.0 * np.pi)
    else:
        instantaneous_frequency_hz = np.full(original.shape, np.nan, dtype=float)

    boundary_mask = np.zeros(original.size, dtype=bool)
    boundary_samples = int(round(parameters["boundary_invalid_s"] * sampling_rate_hz))
    if 2 * boundary_samples >= original.size:
        raise ValueError("Configured Hilbert boundary invalidates the entire signal")
    if boundary_samples:
        boundary_mask[:boundary_samples] = True
        boundary_mask[-boundary_samples:] = True

    masks = [
        *parameters["invalid_time_masks"],
        *_normalize_masks(invalid_time_masks or []),
    ]
    parameters["invalid_time_masks"] = masks
    invalid_time_mask = _mask_from_ranges(original.size, sampling_rate_hz, start_s, masks)
    envelope_eligible = ~(boundary_mask | nonfinite_mask | invalid_time_mask)
    amplitude_threshold_uv = _envelope_threshold(
        envelope_uv, envelope_eligible, parameters["amplitude_envelope"]
    )
    low_envelope_mask = np.zeros(original.size, dtype=bool)
    if amplitude_threshold_uv is not None:
        low_envelope_mask = envelope_uv < amplitude_threshold_uv

    frequency_mask = np.zeros(original.size, dtype=bool)
    if frequency_config["enabled"]:
        frequency_mask = (
            ~np.isfinite(instantaneous_frequency_hz)
            | (instantaneous_frequency_hz < frequency_config["min_hz"])
            | (instantaneous_frequency_hz > frequency_config["max_hz"])
        )
    invalid_reason_masks = {
        "boundary": boundary_mask,
        "nan_or_nonfinite": nonfinite_mask,
        "invalid_time_mask": invalid_time_mask,
        "low_amplitude_envelope": low_envelope_mask,
        "instantaneous_frequency_out_of_range": frequency_mask,
    }
    invalid = np.logical_or.reduce(tuple(invalid_reason_masks.values()))
    valid_phase_mask = ~invalid
    return HilbertChannelPhase(
        provenance=provenance,
        phase_profile=selected_name,
        sampling_rate_hz=sampling_rate_hz,
        start_s=start_s,
        end_s=start_s + duration_s,
        phase_signal=phase_signal,
        wrapped_phase=wrapped_phase,
        unwrapped_phase=unwrapped_phase,
        amplitude_envelope=envelope_uv,
        instantaneous_frequency_hz=instantaneous_frequency_hz,
        valid_phase_mask=valid_phase_mask,
        invalid_reason_masks=invalid_reason_masks,
        amplitude_threshold_uv=amplitude_threshold_uv,
        parameters=parameters,
    )


def estimate_hilbert_phase(
    eeg: PreprocessedEEG,
    detection: SlowOscillationDetection,
    subject_id: str,
    recording_id: str,
    config: Mapping[str, Any],
    profile_name: str | None = None,
    invalid_time_masks: Sequence[Mapping[str, float]] | None = None,
) -> HilbertPhaseResult:
    """Estimate independent channel phases while retaining pipeline provenance."""
    if eeg.segment_id != detection.segment_id:
        raise ValueError("Preprocessed and detection segment IDs do not match")
    if eeg.channel_names != detection.channel_names:
        raise ValueError("Preprocessed and detection channel names do not match")
    if not np.isclose(eeg.output_sampling_rate_hz, detection.sampling_rate_hz):
        raise ValueError("Preprocessed and detection sampling rates do not match")
    if not np.isclose(eeg.start_s, detection.start_s) or not np.isclose(eeg.end_s, detection.end_s):
        raise ValueError("Preprocessed and detection time ranges do not match")

    channel_results = []
    for index, channel in enumerate(eeg.channel_names):
        provenance = PhaseProvenance(
            subject_id=str(subject_id),
            recording_id=str(recording_id),
            segment_id=eeg.segment_id,
            channel=channel,
            preprocessing_profile=eeg.profile_name,
            detector_profile=detection.detector_profile,
        )
        channel_results.append(
            estimate_channel_hilbert(
                eeg.data[index],
                eeg.output_sampling_rate_hz,
                eeg.start_s,
                provenance,
                config,
                profile_name,
                invalid_time_masks,
            )
        )
    selected_name = channel_results[0].phase_profile
    return HilbertPhaseResult(
        segment_id=eeg.segment_id,
        channel_names=eeg.channel_names,
        channels=tuple(channel_results),
        phase_profile=selected_name,
        parameters=channel_results[0].parameters,
    )


def _sample_at_time(
    channel_phase: HilbertChannelPhase, time_s: float
) -> tuple[float, float, float | None, bool]:
    position = (time_s - channel_phase.start_s) * channel_phase.sampling_rate_hz
    if position < 0 or position > channel_phase.wrapped_phase.size - 1:
        raise ValueError("Landmark time falls outside phase signal")
    left = int(np.floor(position))
    right = int(np.ceil(position))
    fraction = position - left
    unwrapped = (1.0 - fraction) * channel_phase.unwrapped_phase[left] + fraction * (
        channel_phase.unwrapped_phase[right]
    )
    envelope = (1.0 - fraction) * channel_phase.amplitude_envelope[left] + fraction * (
        channel_phase.amplitude_envelope[right]
    )
    frequency_values = channel_phase.instantaneous_frequency_hz[[left, right]]
    frequency = None
    if np.all(np.isfinite(frequency_values)):
        frequency = float((1.0 - fraction) * frequency_values[0] + fraction * frequency_values[1])
    valid = bool(channel_phase.valid_phase_mask[left] and channel_phase.valid_phase_mask[right])
    return float(wrap_phase(unwrapped)), float(envelope), frequency, valid


def _event_phase_validation(
    event: SlowOscillationEvent,
    channel_phase: HilbertChannelPhase,
) -> EventPhaseValidation:
    config = channel_phase.parameters["event_validation"]
    start_index = max(
        0,
        int(
            np.floor((event.event_start_s - channel_phase.start_s) * channel_phase.sampling_rate_hz)
        ),
    )
    stop_index = min(
        channel_phase.unwrapped_phase.size,
        int(np.ceil((event.event_end_s - channel_phase.start_s) * channel_phase.sampling_rate_hz))
        + 1,
    )
    event_valid_mask = channel_phase.valid_phase_mask[start_index:stop_index]
    valid_fraction = float(np.mean(event_valid_mask)) if event_valid_mask.size else 0.0
    landmark_times = (
        event.downward_zero_crossing_s,
        event.trough_time_s,
        event.upward_zero_crossing_s,
        event.positive_peak_time_s,
    )
    landmarks_valid = all(_sample_at_time(channel_phase, time_s)[3] for time_s in landmark_times)
    valid_indices = np.flatnonzero(event_valid_mask) + start_index
    if valid_indices.size < 2:
        return EventPhaseValidation(
            segment_id=event.segment_id,
            channel=event.channel,
            event_id=event.event_id,
            event_phase_valid=False,
            phase_forward=False,
            valid_sample_fraction=valid_fraction,
            net_phase_advance_rad=None,
            reverse_step_count=0,
            total_step_count=0,
            reverse_step_fraction=None,
        )
    phase_values = channel_phase.unwrapped_phase[valid_indices]
    steps = np.diff(phase_values)
    reverse_count = int(np.count_nonzero(steps < -config["reverse_step_tolerance_rad"]))
    reverse_fraction = reverse_count / steps.size
    net_advance = float(phase_values[-1] - phase_values[0])
    event_phase_valid = bool(
        landmarks_valid and valid_fraction >= config["min_event_valid_fraction"]
    )
    phase_forward = bool(
        event_phase_valid
        and net_advance >= config["min_forward_advance_rad"]
        and reverse_fraction <= config["max_reverse_step_fraction"]
    )
    return EventPhaseValidation(
        segment_id=event.segment_id,
        channel=event.channel,
        event_id=event.event_id,
        event_phase_valid=event_phase_valid,
        phase_forward=phase_forward,
        valid_sample_fraction=valid_fraction,
        net_phase_advance_rad=net_advance,
        reverse_step_count=reverse_count,
        total_step_count=int(steps.size),
        reverse_step_fraction=float(reverse_fraction),
    )


def validate_event_landmarks(
    phase_result: HilbertPhaseResult,
    detection: SlowOscillationDetection,
) -> tuple[list[PhaseLandmark], list[EventPhaseValidation]]:
    """Validate accepted detector landmarks against the fixed phase convention."""
    landmarks = []
    event_validations = []
    landmark_attributes = {
        "downward_zero_crossing": "downward_zero_crossing_s",
        "trough": "trough_time_s",
        "upward_zero_crossing": "upward_zero_crossing_s",
        "positive_peak": "positive_peak_time_s",
    }
    expected = phase_result.parameters["expected_landmark_phases_rad"]
    for event in detection.events:
        if not event.accepted:
            continue
        channel_phase = phase_result.channel(event.channel)
        event_validations.append(_event_phase_validation(event, channel_phase))
        for landmark_type, attribute in landmark_attributes.items():
            time_s = float(getattr(event, attribute))
            phase, envelope, frequency, valid = _sample_at_time(channel_phase, time_s)
            error_rad = circular_error(phase, expected[landmark_type])
            landmarks.append(
                PhaseLandmark(
                    segment_id=event.segment_id,
                    channel=event.channel,
                    event_id=event.event_id,
                    landmark_type=landmark_type,
                    landmark_time_s=time_s,
                    expected_phase_rad=expected[landmark_type],
                    estimated_phase_rad=phase,
                    circular_error_rad=error_rad,
                    circular_error_deg=float(np.degrees(error_rad)),
                    amplitude_envelope=envelope,
                    instantaneous_frequency_hz=frequency,
                    phase_valid=valid,
                    preprocessing_profile=channel_phase.provenance.preprocessing_profile,
                    detector_profile=channel_phase.provenance.detector_profile,
                    phase_profile=channel_phase.phase_profile,
                )
            )
    return landmarks, event_validations


def compare_overlapping_channel_phases(
    phase_result: HilbertPhaseResult,
    detection: SlowOscillationDetection,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compare phase at overlap midpoints without interpreting synchrony."""
    comparison = _required_mapping(config, "hilbert_phase")["cross_channel"]
    if not isinstance(comparison, Mapping):
        raise TypeError("hilbert_phase.cross_channel must be a mapping")
    accepted_only = bool(comparison["accepted_only"])
    min_overlap_s = float(comparison["min_overlap_s"])
    comparison_time = str(comparison["comparison_time"])
    if min_overlap_s < 0:
        raise ValueError("Cross-channel minimum overlap must be non-negative")
    if comparison_time != "overlap_midpoint":
        raise ValueError("Only overlap_midpoint cross-channel comparison is supported")

    summaries = []
    for first_channel, second_channel in combinations(phase_result.channel_names, 2):
        first_events = [
            event
            for event in detection.events
            if event.channel == first_channel and (event.accepted or not accepted_only)
        ]
        second_events = [
            event
            for event in detection.events
            if event.channel == second_channel and (event.accepted or not accepted_only)
        ]
        differences = []
        overlapping_pair_count = 0
        invalid_pair_count = 0
        for first_event in first_events:
            for second_event in second_events:
                overlap_start = max(first_event.event_start_s, second_event.event_start_s)
                overlap_end = min(first_event.event_end_s, second_event.event_end_s)
                if overlap_end - overlap_start <= min_overlap_s:
                    continue
                overlapping_pair_count += 1
                midpoint = (overlap_start + overlap_end) / 2.0
                first_phase, _, _, first_valid = _sample_at_time(
                    phase_result.channel(first_channel), midpoint
                )
                second_phase, _, _, second_valid = _sample_at_time(
                    phase_result.channel(second_channel), midpoint
                )
                if not first_valid or not second_valid:
                    invalid_pair_count += 1
                    continue
                differences.append(circular_error(first_phase, second_phase))
        if differences:
            values = np.asarray(differences)
            mean_sin = float(np.mean(np.sin(values)))
            mean_cos = float(np.mean(np.cos(values)))
            mean_direction = float(np.arctan2(mean_sin, mean_cos))
            resultant_length = float(np.hypot(mean_sin, mean_cos))
            dispersion = 1.0 - resultant_length
        else:
            mean_direction = None
            resultant_length = None
            dispersion = None
        summaries.append(
            {
                "channels": [first_channel, second_channel],
                "difference_definition": f"{first_channel} minus {second_channel}",
                "comparison_time": comparison_time,
                "accepted_only": accepted_only,
                "min_overlap_s": min_overlap_s,
                "overlapping_pair_count": overlapping_pair_count,
                "valid_pair_count": len(differences),
                "invalid_pair_count": invalid_pair_count,
                "circular_mean_direction_rad": mean_direction,
                "circular_mean_direction_deg": (
                    float(np.degrees(mean_direction)) if mean_direction is not None else None
                ),
                "mean_resultant_length": resultant_length,
                "circular_dispersion": dispersion,
            }
        )
    return summaries
