"""Estimate and audit offline Hilbert phase in one configured N3 segment."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from dreamcore.config import load_config
from dreamcore.data.reader import load_edf
from dreamcore.phase_prediction.hilbert import (
    EventPhaseValidation,
    HilbertChannelPhase,
    HilbertPhaseResult,
    PhaseLandmark,
    compare_overlapping_channel_phases,
    estimate_hilbert_phase,
    validate_event_landmarks,
)
from dreamcore.preprocessing.eeg import PreprocessedEEG, preprocess_n3_segment
from dreamcore.sleep_staging.labels import merge_adjacent_intervals, normalize_annotations
from dreamcore.sleep_staging.segments import N3Segment, extract_n3_segments
from dreamcore.slow_oscillation.detector import (
    SlowOscillationDetection,
    SlowOscillationEvent,
    detect_slow_oscillations,
)

LANDMARK_FIELDS = [
    "segment_id",
    "channel",
    "event_id",
    "landmark_type",
    "landmark_time_s",
    "expected_phase_rad",
    "estimated_phase_rad",
    "circular_error_rad",
    "circular_error_deg",
    "amplitude_envelope",
    "instantaneous_frequency_hz",
    "phase_valid",
    "preprocessing_profile",
    "detector_profile",
    "phase_profile",
]


def _phase_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("hilbert_phase")
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'hilbert_phase' must be a mapping")
    return section


def _qa_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    qa = _phase_config(config).get("qa")
    if not isinstance(qa, Mapping):
        raise TypeError("Config section 'hilbert_phase.qa' must be a mapping")
    return qa


def _select_segment(segments: Sequence[N3Segment], segment_id: str) -> N3Segment:
    for segment in segments:
        if segment.segment_id == segment_id:
            return segment
    available = [segment.segment_id for segment in segments]
    raise ValueError(f"Configured N3 segment '{segment_id}' not found; available: {available}")


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "q25": None,
            "median": None,
            "mean": None,
            "q75": None,
            "max": None,
            "std": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "q25": float(np.quantile(array, 0.25)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "q75": float(np.quantile(array, 0.75)),
        "max": float(np.max(array)),
        "std": float(np.std(array)),
    }


def _landmark_error_summary(landmarks: Sequence[PhaseLandmark]) -> dict[str, Any]:
    valid = [landmark for landmark in landmarks if landmark.phase_valid]
    absolute_rad = [abs(landmark.circular_error_rad) for landmark in valid]
    absolute_deg = [abs(landmark.circular_error_deg) for landmark in valid]
    return {
        "landmark_count": len(landmarks),
        "valid_landmark_count": len(valid),
        "invalid_landmark_count": len(landmarks) - len(valid),
        "circular_absolute_error_rad": _distribution(absolute_rad),
        "circular_absolute_error_deg": _distribution(absolute_deg),
        "circular_mae_rad": float(np.mean(absolute_rad)) if absolute_rad else None,
        "circular_mae_deg": float(np.mean(absolute_deg)) if absolute_deg else None,
        "median_absolute_error_rad": float(np.median(absolute_rad)) if absolute_rad else None,
        "median_absolute_error_deg": float(np.median(absolute_deg)) if absolute_deg else None,
    }


def _phase_channel_summary(
    channel_phase: HilbertChannelPhase,
    landmarks: Sequence[PhaseLandmark],
    validations: Sequence[EventPhaseValidation],
) -> dict[str, Any]:
    channel = channel_phase.provenance.channel
    channel_landmarks = [landmark for landmark in landmarks if landmark.channel == channel]
    channel_validations = [
        validation for validation in validations if validation.channel == channel
    ]
    valid_frequency = channel_phase.instantaneous_frequency_hz[
        channel_phase.valid_phase_mask & np.isfinite(channel_phase.instantaneous_frequency_hz)
    ]
    invalid_counts = {
        reason: int(np.count_nonzero(mask))
        for reason, mask in channel_phase.invalid_reason_masks.items()
    }
    return {
        "phase_sample_count": int(channel_phase.wrapped_phase.size),
        "valid_phase_sample_count": int(np.count_nonzero(channel_phase.valid_phase_mask)),
        "invalid_phase_sample_count": int(np.count_nonzero(~channel_phase.valid_phase_mask)),
        "valid_phase_ratio": channel_phase.valid_phase_ratio,
        "amplitude_envelope_threshold_uv": channel_phase.amplitude_threshold_uv,
        "invalid_reason_sample_counts": invalid_counts,
        "instantaneous_frequency_hz_valid_samples": _distribution(valid_frequency.tolist()),
        "landmarks": _landmark_error_summary(channel_landmarks),
        "landmarks_by_type": {
            landmark_type: _landmark_error_summary(
                [
                    landmark
                    for landmark in channel_landmarks
                    if landmark.landmark_type == landmark_type
                ]
            )
            for landmark_type in channel_phase.parameters["expected_landmark_phases_rad"]
        },
        "events": {
            "event_count": len(channel_validations),
            "valid_event_count": sum(
                validation.event_phase_valid for validation in channel_validations
            ),
            "invalid_event_count": sum(
                not validation.event_phase_valid for validation in channel_validations
            ),
            "forward_phase_event_count": sum(
                validation.phase_forward for validation in channel_validations
            ),
            "nonforward_phase_event_count": sum(
                not validation.phase_forward for validation in channel_validations
            ),
            "total_reverse_step_count": sum(
                validation.reverse_step_count for validation in channel_validations
            ),
            "total_phase_step_count": sum(
                validation.total_step_count for validation in channel_validations
            ),
            "valid_sample_fraction": _distribution(
                [validation.valid_sample_fraction for validation in channel_validations]
            ),
            "net_phase_advance_rad": _distribution(
                [
                    validation.net_phase_advance_rad
                    for validation in channel_validations
                    if validation.net_phase_advance_rad is not None
                ]
            ),
            "reverse_step_fraction": _distribution(
                [
                    validation.reverse_step_fraction
                    for validation in channel_validations
                    if validation.reverse_step_fraction is not None
                ]
            ),
        },
    }


def build_summary(
    phase_result: HilbertPhaseResult,
    detection: SlowOscillationDetection,
    processed: PreprocessedEEG,
    selected_segment: N3Segment,
    landmarks: Sequence[PhaseLandmark],
    validations: Sequence[EventPhaseValidation],
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a JSON-compatible phase and landmark validation summary."""
    dataset = config.get("dataset", {})
    if not isinstance(dataset, Mapping):
        raise TypeError("Config section 'dataset' must be a mapping")
    return {
        "dataset": {
            "name": str(dataset.get("name", "unknown")),
            "subject_id": str(dataset.get("subject_id", psg_path.stem)),
            "recording_id": str(dataset.get("recording_id", psg_path.stem)),
        },
        "source": {"psg": psg_path.name, "hypnogram": hypnogram_path.name},
        "segment": {
            "segment_id": selected_segment.segment_id,
            "original_start_s": selected_segment.start_s,
            "original_end_s": selected_segment.end_s,
            "original_duration_s": selected_segment.duration_s,
            "raw_label_sources": list(selected_segment.raw_labels),
            "analyzed_start_s": detection.start_s,
            "analyzed_end_s": detection.end_s,
            "analyzed_duration_s": detection.end_s - detection.start_s,
        },
        "channels": list(phase_result.channel_names),
        "sampling_rate_hz": detection.sampling_rate_hz,
        "preprocessing": processed.metadata,
        "detector": {
            "profile": detection.detector_profile,
            "parameters": detection.parameters,
            "accepted_event_count": sum(event.accepted for event in detection.events),
        },
        "hilbert_phase": {
            "profile": phase_result.phase_profile,
            "parameters": phase_result.parameters,
            "phase_convention": {
                "raw_hilbert_phase_transform": "wrap(raw_phase + fixed_offset)",
                "fixed_offset_rad": phase_result.parameters["project_phase_offset_rad"],
                "wrapped_range": "[-pi, pi)",
                "expected_landmarks_rad": phase_result.parameters["expected_landmark_phases_rad"],
                "processing_mode": "offline zero-phase; future samples available",
            },
        },
        "per_channel": {
            channel_phase.provenance.channel: _phase_channel_summary(
                channel_phase, landmarks, validations
            )
            for channel_phase in phase_result.channels
        },
        "landmarks_all_channels": _landmark_error_summary(landmarks),
        "landmarks_by_type_all_channels": {
            landmark_type: _landmark_error_summary(
                [landmark for landmark in landmarks if landmark.landmark_type == landmark_type]
            )
            for landmark_type in phase_result.parameters["expected_landmark_phases_rad"]
        },
        "cross_channel_phase_difference": compare_overlapping_channel_phases(
            phase_result, detection, config
        ),
        "interpretation_boundary": (
            "Detector landmarks are algorithmic candidates, not physiological phase truth; "
            "cross-channel phase proximity is not evidence of synchrony or causality."
        ),
    }


def write_landmarks_csv(landmarks: Sequence[PhaseLandmark], output_path: Path) -> None:
    """Write accepted-event phase landmarks to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=LANDMARK_FIELDS)
        writer.writeheader()
        for landmark in landmarks:
            writer.writerow(landmark.to_dict())


def _window_indices(
    channel_phase: HilbertChannelPhase,
    window_start_s: float,
    duration_s: float,
) -> tuple[np.ndarray, slice]:
    start = int(round((window_start_s - channel_phase.start_s) * channel_phase.sampling_rate_hz))
    count = int(round(duration_s * channel_phase.sampling_rate_hz))
    stop = start + count
    if start < 0 or stop > channel_phase.wrapped_phase.size:
        raise ValueError("Phase QA window falls outside retained signal")
    return np.arange(count) / channel_phase.sampling_rate_hz, slice(start, stop)


def _plot_invalid_regions(
    axis: plt.Axes,
    times: np.ndarray,
    invalid: np.ndarray,
    color: str,
) -> None:
    axis.fill_between(
        times,
        0.0,
        1.0,
        where=invalid,
        transform=axis.get_xaxis_transform(),
        color=color,
        alpha=0.07,
        step="mid",
        linewidth=0.0,
    )


def _accepted_window_events(
    detection: SlowOscillationDetection,
    channel: str,
    start_s: float,
    end_s: float,
) -> list[SlowOscillationEvent]:
    return [
        event
        for event in detection.events
        if event.accepted
        and event.channel == channel
        and event.event_start_s < end_s
        and event.event_end_s > start_s
    ]


def plot_qa(
    phase_result: HilbertPhaseResult,
    detection: SlowOscillationDetection,
    processed: PreprocessedEEG,
    config: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    """Render aligned signal, wrapped phase, envelope, and validity panels."""
    qa = _qa_config(config)
    segment_start_s = float(processed.metadata["input"]["start_s"])
    offset_s = float(qa["offset_s"])
    duration_s = float(qa["duration_s"])
    if offset_s < 0 or duration_s <= 0:
        raise ValueError("Phase QA offset must be non-negative and duration positive")
    window_start_s = segment_start_s + offset_s
    window_end_s = window_start_s + duration_s

    figure, axes = plt.subplots(
        3,
        len(phase_result.channel_names),
        sharex=True,
        squeeze=False,
        figsize=(float(qa["figure_width_inches"]), float(qa["figure_height_inches"])),
    )
    scale = float(_phase_config(config)["amplitude_scale_to_uv"])
    landmark_markers = {
        "downward_zero_crossing": "|",
        "trough": "v",
        "upward_zero_crossing": "+",
        "positive_peak": "^",
    }
    window_event_count = 0
    window_valid_landmark_count = 0
    for column, channel in enumerate(phase_result.channel_names):
        channel_phase = phase_result.channel(channel)
        times, window_slice = _window_indices(channel_phase, window_start_s, duration_s)
        invalid = ~channel_phase.valid_phase_mask[window_slice]
        signal_axis, phase_axis, envelope_axis = axes[:, column]
        signal = channel_phase.phase_signal[window_slice] * scale
        wrapped = channel_phase.wrapped_phase[window_slice]
        envelope = channel_phase.amplitude_envelope[window_slice]
        valid = ~invalid

        signal_axis.plot(
            times,
            signal,
            color=str(qa["signal_color"]),
            linewidth=1.1,
            label="Phase-band EEG",
        )
        events = _accepted_window_events(detection, channel, window_start_s, window_end_s)
        window_event_count += len(events)
        for event in events:
            signal_axis.axvspan(
                max(0.0, event.event_start_s - window_start_s),
                min(duration_s, event.event_end_s - window_start_s),
                facecolor=str(qa["accepted_color"]),
                alpha=0.08,
                linewidth=0.0,
            )
            event_landmarks = {
                "downward_zero_crossing": (
                    event.downward_zero_crossing_s,
                    0.0,
                ),
                "trough": (event.trough_time_s, event.trough_amplitude_uv),
                "upward_zero_crossing": (event.upward_zero_crossing_s, 0.0),
                "positive_peak": (
                    event.positive_peak_time_s,
                    event.positive_peak_amplitude_uv,
                ),
            }
            for landmark_type, (time_s, amplitude_uv) in event_landmarks.items():
                relative_time = time_s - window_start_s
                if not 0 <= relative_time <= duration_s:
                    continue
                marker = landmark_markers[landmark_type]
                signal_axis.scatter(
                    relative_time,
                    amplitude_uv,
                    marker=marker,
                    s=44,
                    color="#111827",
                    zorder=5,
                )
                sample = int(
                    round((time_s - channel_phase.start_s) * channel_phase.sampling_rate_hz)
                )
                sample = min(max(sample, 0), channel_phase.wrapped_phase.size - 1)
                phase_axis.scatter(
                    relative_time,
                    channel_phase.wrapped_phase[sample],
                    marker=marker,
                    s=38,
                    color="#111827",
                    zorder=5,
                )
                window_valid_landmark_count += int(channel_phase.valid_phase_mask[sample])

        phase_axis.plot(
            times,
            np.where(valid, wrapped, np.nan),
            color=str(qa["phase_color"]),
            linewidth=1.0,
            label="Valid wrapped phase",
        )
        phase_axis.plot(
            times,
            np.where(invalid, wrapped, np.nan),
            color=str(qa["invalid_color"]),
            linewidth=0.8,
            linestyle=":",
            label="Invalid wrapped phase",
        )
        envelope_axis.plot(
            times,
            envelope,
            color=str(qa["envelope_color"]),
            linewidth=1.0,
            label="Amplitude envelope",
        )
        if channel_phase.amplitude_threshold_uv is not None:
            envelope_axis.axhline(
                channel_phase.amplitude_threshold_uv,
                color=str(qa["invalid_color"]),
                linewidth=0.8,
                linestyle="--",
                label="Envelope threshold",
            )
        for axis in (signal_axis, phase_axis, envelope_axis):
            _plot_invalid_regions(axis, times, invalid, str(qa["invalid_color"]))
            axis.grid(alpha=float(qa["grid_alpha"]), linewidth=0.6)
            axis.spines[["top", "right"]].set_visible(False)
            axis.set_xlim(0.0, duration_s)
        signal_axis.set_title(channel)
        signal_axis.set_ylabel(f"EEG ({qa['amplitude_unit']})")
        phase_axis.set_ylabel("Wrapped phase (rad)")
        phase_axis.set_ylim(-np.pi, np.pi)
        phase_axis.set_yticks(
            [-np.pi, -np.pi / 2, 0.0, np.pi / 2, np.pi],
            ["−π", "−π/2", "0", "π/2", "π"],
        )
        envelope_axis.set_ylabel(f"Envelope ({qa['amplitude_unit']})")
        envelope_axis.set_xlabel("Time from QA window start (s)")

    legend = [
        Line2D([0], [0], color=str(qa["signal_color"]), label="Phase-band EEG"),
        Line2D([0], [0], color=str(qa["phase_color"]), label="Valid wrapped phase"),
        Patch(color=str(qa["accepted_color"]), alpha=0.2, label="Accepted event"),
        Patch(color=str(qa["invalid_color"]), alpha=0.15, label="Invalid phase region"),
        Line2D([0], [0], marker="|", color="none", markeredgecolor="#111827", label="Down zero"),
        Line2D([0], [0], marker="v", color="none", markeredgecolor="#111827", label="Trough"),
        Line2D([0], [0], marker="+", color="none", markeredgecolor="#111827", label="Up zero"),
        Line2D(
            [0], [0], marker="^", color="none", markeredgecolor="#111827", label="Positive peak"
        ),
    ]
    figure.legend(
        handles=legend, loc="upper right", bbox_to_anchor=(0.98, 0.975), ncols=4, frameon=False
    )
    figure.suptitle(
        "Offline Hilbert phase QA",
        x=0.055,
        y=0.985,
        ha="left",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.055,
        0.947,
        (
            f"{phase_result.segment_id} | PSG {window_start_s:.1f}–{window_end_s:.1f} s | "
            f"phase profile: {phase_result.phase_profile} | accepted events only"
        ),
        ha="left",
        va="top",
        fontsize=9,
        color="#374151",
    )
    figure.text(
        0.055,
        0.92,
        "Offline zero-phase baseline — not causal or real-time",
        ha="left",
        va="top",
        fontsize=9,
        color=str(qa["invalid_color"]),
        fontweight="bold",
    )
    figure.tight_layout(rect=(0.035, 0.03, 0.99, 0.88))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=int(qa["dpi"]),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)
    return {
        "output_path": str(output_path),
        "start_s": window_start_s,
        "end_s": window_end_s,
        "duration_s": duration_s,
        "accepted_event_count": window_event_count,
        "valid_landmark_count": window_valid_landmark_count,
    }


def _load_masks(path: Path | None) -> list[Mapping[str, float]]:
    if path is None:
        return []
    with path.open(encoding="utf-8") as input_file:
        content = json.load(input_file)
    if isinstance(content, Mapping):
        content = content["invalid_time_masks"]
    if not isinstance(content, list):
        raise TypeError("Invalid-mask JSON must contain a list or invalid_time_masks key")
    return content


def run_phase_estimation(
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
    *,
    segment_id: str | None = None,
    preprocessing_profile: str | None = None,
    detector_profile: str | None = None,
    phase_profile: str | None = None,
    channel_names: Sequence[str] | None = None,
    invalid_time_masks: Sequence[Mapping[str, float]] | None = None,
    landmarks_csv_path: Path | None = None,
    summary_json_path: Path | None = None,
    qa_output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the existing N3 and detector pipeline, then estimate offline phase."""
    section = _phase_config(config)
    qa = _qa_config(config)
    selected_segment_id = segment_id or qa["segment_id"]
    if selected_segment_id is None:
        raise ValueError("hilbert_phase.qa.segment_id must select an N3 segment")
    selected_preprocessing = preprocessing_profile or str(qa["preprocessing_profile"])
    selected_detector = detector_profile or str(qa["detector_profile"])
    selected_phase = phase_profile or str(qa["phase_profile"])

    raw, annotations = load_edf(psg_path, hypnogram_path, config)
    raw_duration_s = float(raw.n_times / raw.info["sfreq"])
    normalized = normalize_annotations(annotations, raw_duration_s, config)
    merged = merge_adjacent_intervals(normalized, config)
    segments = extract_n3_segments(raw, merged, psg_path.stem, config, channel_names)
    selected_segment = _select_segment(segments, str(selected_segment_id))
    processed = preprocess_n3_segment(
        selected_segment,
        config,
        selected_preprocessing,
        channel_names,
    )
    detection = detect_slow_oscillations(
        processed,
        config,
        selected_detector,
        invalid_time_masks,
    )
    dataset = config.get("dataset", {})
    if not isinstance(dataset, Mapping):
        raise TypeError("Config section 'dataset' must be a mapping")
    phase_result = estimate_hilbert_phase(
        processed,
        detection,
        str(dataset.get("subject_id", psg_path.stem)),
        str(dataset.get("recording_id", psg_path.stem)),
        config,
        selected_phase,
        invalid_time_masks,
    )
    landmarks, validations = validate_event_landmarks(phase_result, detection)

    csv_path = landmarks_csv_path or Path(str(section["landmarks_csv"]))
    summary_path = summary_json_path or Path(str(section["summary_json"]))
    figure_path = qa_output_path or Path(str(qa["output_path"]))
    write_landmarks_csv(landmarks, csv_path)
    summary = build_summary(
        phase_result,
        detection,
        processed,
        selected_segment,
        landmarks,
        validations,
        psg_path,
        hypnogram_path,
        config,
    )
    summary["qa_figure"] = plot_qa(phase_result, detection, processed, config, figure_path)
    summary["outputs"] = {
        "landmarks_csv": str(csv_path),
        "summary_json": str(summary_path),
        "qa_figure": str(figure_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as output_file:
        json.dump(
            summary,
            output_file,
            indent=int(section["json_indent"]),
            sort_keys=True,
            allow_nan=False,
        )
        output_file.write("\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Dataset YAML config")
    parser.add_argument("--psg", type=Path, required=True, help="PSG EDF path")
    parser.add_argument("--hypnogram", type=Path, required=True, help="Hypnogram EDF path")
    parser.add_argument("--segment-id", help="N3 segment ID; overrides config")
    parser.add_argument("--preprocessing-profile", help="Preprocessing profile override")
    parser.add_argument("--detector-profile", help="Detector profile override")
    parser.add_argument("--phase-profile", help="Hilbert phase profile override")
    parser.add_argument("--channels", nargs="+", help="EEG channels; overrides config")
    parser.add_argument("--invalid-mask-json", type=Path, help="Additional invalid ranges")
    parser.add_argument("--landmarks-csv", type=Path, help="Landmark CSV output")
    parser.add_argument("--summary-json", type=Path, help="Summary JSON output")
    parser.add_argument("--qa-output", type=Path, help="QA figure output")
    return parser.parse_args()


def main() -> int:
    """Run the offline Hilbert phase CLI."""
    args = _parse_args()
    config = load_config(args.config)
    summary = run_phase_estimation(
        args.psg,
        args.hypnogram,
        config,
        segment_id=args.segment_id,
        preprocessing_profile=args.preprocessing_profile,
        detector_profile=args.detector_profile,
        phase_profile=args.phase_profile,
        channel_names=args.channels,
        invalid_time_masks=_load_masks(args.invalid_mask_json),
        landmarks_csv_path=args.landmarks_csv,
        summary_json_path=args.summary_json,
        qa_output_path=args.qa_output,
    )
    print(f"Phase profile: {summary['hilbert_phase']['profile']}")
    for channel, channel_summary in summary["per_channel"].items():
        print(
            f"{channel}: valid phase {channel_summary['valid_phase_ratio']:.3%}, "
            f"valid events {channel_summary['events']['valid_event_count']}/"
            f"{channel_summary['events']['event_count']}"
        )
    print(f"Landmarks CSV: {summary['outputs']['landmarks_csv']}")
    print(f"Summary JSON: {summary['outputs']['summary_json']}")
    print(f"QA figure: {summary['outputs']['qa_figure']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
