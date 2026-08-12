"""Detect and audit slow-oscillation candidates in one configured N3 segment."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
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
from dreamcore.preprocessing.eeg import PreprocessedEEG, preprocess_n3_segment
from dreamcore.sleep_staging.labels import merge_adjacent_intervals, normalize_annotations
from dreamcore.sleep_staging.segments import N3Segment, extract_n3_segments
from dreamcore.slow_oscillation.detector import (
    SlowOscillationDetection,
    SlowOscillationEvent,
    detect_slow_oscillations,
)

EVENT_FIELDS = [
    "event_id",
    "segment_id",
    "channel",
    "event_start_s",
    "event_end_s",
    "downward_zero_crossing_s",
    "trough_time_s",
    "trough_amplitude_uv",
    "upward_zero_crossing_s",
    "positive_peak_time_s",
    "positive_peak_amplitude_uv",
    "peak_to_peak_amplitude_uv",
    "negative_halfwave_duration_s",
    "full_cycle_duration_s",
    "estimated_frequency_hz",
    "down_slope",
    "up_slope",
    "accepted",
    "rejection_reasons",
    "detector_profile",
    "amplitude_threshold_uv",
]


def _detection_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("slow_oscillation")
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'slow_oscillation' must be a mapping")
    return section


def _qa_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    qa = _detection_config(config).get("qa")
    if not isinstance(qa, Mapping):
        raise TypeError("Config section 'slow_oscillation.qa' must be a mapping")
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


def _rejection_counts(events: Sequence[SlowOscillationEvent]) -> dict[str, int]:
    counts = Counter(reason for event in events for reason in event.rejection_reasons)
    return dict(sorted(counts.items()))


def _channel_summary(
    channel: str,
    events: Sequence[SlowOscillationEvent],
    analyzed_duration_s: float,
) -> dict[str, Any]:
    channel_events = [event for event in events if event.channel == channel]
    accepted = [event for event in channel_events if event.accepted]
    minutes = analyzed_duration_s / 60.0
    return {
        "candidate_event_count": len(channel_events),
        "accepted_event_count": len(accepted),
        "rejected_event_count": len(channel_events) - len(accepted),
        "accepted_events_per_minute": len(accepted) / minutes,
        "amplitude_threshold_uv": (
            channel_events[0].amplitude_threshold_uv if channel_events else None
        ),
        "accepted_event_distributions": {
            "negative_halfwave_duration_s": _distribution(
                [event.negative_halfwave_duration_s for event in accepted]
            ),
            "full_cycle_duration_s": _distribution(
                [event.full_cycle_duration_s for event in accepted]
            ),
            "peak_to_peak_amplitude_uv": _distribution(
                [event.peak_to_peak_amplitude_uv for event in accepted]
            ),
            "estimated_frequency_hz": _distribution(
                [event.estimated_frequency_hz for event in accepted]
            ),
        },
        "rejection_reason_counts": _rejection_counts(channel_events),
    }


def _overlap_summary(
    detection: SlowOscillationDetection, config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    overlap_config = _detection_config(config)["overlap"]
    if not isinstance(overlap_config, Mapping):
        raise TypeError("slow_oscillation.overlap must be a mapping")
    accepted_only = bool(overlap_config["accepted_only"])
    min_overlap_s = float(overlap_config["min_overlap_s"])
    if min_overlap_s < 0:
        raise ValueError("slow_oscillation.overlap.min_overlap_s must be non-negative")

    summaries = []
    for first_channel, second_channel in combinations(detection.channel_names, 2):
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
        overlapping_pairs = []
        first_ids: set[str] = set()
        second_ids: set[str] = set()
        for first_event in first_events:
            for second_event in second_events:
                overlap_s = min(first_event.event_end_s, second_event.event_end_s) - max(
                    first_event.event_start_s, second_event.event_start_s
                )
                if overlap_s > min_overlap_s:
                    overlapping_pairs.append(overlap_s)
                    first_ids.add(first_event.event_id)
                    second_ids.add(second_event.event_id)
        summaries.append(
            {
                "channels": [first_channel, second_channel],
                "accepted_only": accepted_only,
                "min_overlap_s": min_overlap_s,
                "overlapping_event_pair_count": len(overlapping_pairs),
                "total_pairwise_overlap_s": float(sum(overlapping_pairs)),
                "event_counts": {
                    first_channel: len(first_events),
                    second_channel: len(second_events),
                },
                "events_with_overlap": {
                    first_channel: len(first_ids),
                    second_channel: len(second_ids),
                },
                "event_overlap_percent": {
                    first_channel: (
                        100.0 * len(first_ids) / len(first_events) if first_events else None
                    ),
                    second_channel: (
                        100.0 * len(second_ids) / len(second_events) if second_events else None
                    ),
                },
            }
        )
    return summaries


def build_summary(
    detection: SlowOscillationDetection,
    processed: PreprocessedEEG,
    selected_segment: N3Segment,
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the JSON-compatible candidate detection summary."""
    dataset = config.get("dataset", {})
    if not isinstance(dataset, Mapping):
        raise TypeError("Config section 'dataset' must be a mapping")
    duration_s = detection.end_s - detection.start_s
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
            "analyzed_duration_s": duration_s,
        },
        "channels": list(detection.channel_names),
        "sampling_rate_hz": detection.sampling_rate_hz,
        "preprocessing": processed.metadata,
        "detector": {
            "profile": detection.detector_profile,
            "parameters": detection.parameters,
            "amplitude_thresholds_uv": detection.amplitude_thresholds_uv,
            "event_boundary_definition": "downward -> upward -> next downward zero crossing",
            "slope_units": "microvolts_per_second",
        },
        "event_population": "all candidates are exported; distributions use accepted events",
        "per_channel": {
            channel: _channel_summary(channel, detection.events, duration_s)
            for channel in detection.channel_names
        },
        "overlap": _overlap_summary(detection, config),
        "global_rejection_reason_counts": _rejection_counts(detection.events),
        "total_candidate_event_count": len(detection.events),
        "total_accepted_event_count": sum(event.accepted for event in detection.events),
    }


def write_events_csv(events: Sequence[SlowOscillationEvent], output_path: Path) -> None:
    """Write every accepted and rejected candidate event to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for event in events:
            row = event.to_dict()
            row["rejection_reasons"] = "|".join(row["rejection_reasons"])
            writer.writerow(row)


def _window(
    data: np.ndarray,
    sfreq: float,
    data_start_s: float,
    window_start_s: float,
    duration_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    start_sample = int(round((window_start_s - data_start_s) * sfreq))
    sample_count = int(round(duration_s * sfreq))
    stop_sample = start_sample + sample_count
    if start_sample < 0 or stop_sample > data.shape[1]:
        raise ValueError("QA window falls outside retained preprocessing data")
    times_s = np.arange(sample_count, dtype=float) / sfreq
    return times_s, data[:, start_sample:stop_sample]


def plot_qa(
    processed: PreprocessedEEG,
    detection: SlowOscillationDetection,
    config: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    """Plot raw/detection signals and event landmarks for manual QA."""
    qa = _qa_config(config)
    offset_s = float(qa["offset_s"])
    duration_s = float(qa["duration_s"])
    if offset_s < 0 or duration_s <= 0:
        raise ValueError("QA offset_s must be non-negative and duration_s positive")
    segment_start_s = float(processed.metadata["input"]["start_s"])
    window_start_s = segment_start_s + offset_s
    window_end_s = window_start_s + duration_s
    if window_start_s < detection.start_s or window_end_s > detection.end_s:
        raise ValueError("QA window falls outside the analyzed detector range")

    raw_times, raw_window = _window(
        processed.raw_data,
        processed.original_sampling_rate_hz,
        processed.start_s,
        window_start_s,
        duration_s,
    )
    detection_times, detection_window = _window(
        detection.detection_data,
        detection.sampling_rate_hz,
        detection.start_s,
        window_start_s,
        duration_s,
    )
    scale = float(qa["amplitude_scale"])
    if not np.isclose(scale, detection.parameters["amplitude_scale_to_uv"]):
        raise ValueError("QA and detector amplitude scales must match")

    channel_count = len(detection.channel_names)
    figure, axes = plt.subplots(
        channel_count,
        1,
        sharex=True,
        squeeze=False,
        figsize=(
            float(qa["figure_width_inches"]),
            float(qa["figure_height_per_channel_inches"]) * channel_count,
        ),
    )
    axes_flat = axes[:, 0]
    qa_events = [
        event
        for event in detection.events
        if event.event_start_s < window_end_s and event.event_end_s > window_start_s
    ]
    for channel_index, (axis, channel) in enumerate(
        zip(axes_flat, detection.channel_names, strict=True)
    ):
        axis.plot(
            raw_times,
            raw_window[channel_index] * scale,
            color=str(qa["raw_color"]),
            linewidth=0.7,
            linestyle=":",
            alpha=0.75,
        )
        axis.plot(
            detection_times,
            detection_window[channel_index] * scale,
            color=str(qa["detection_color"]),
            linewidth=1.2,
        )
        channel_events = [event for event in qa_events if event.channel == channel]
        for event in channel_events:
            color = str(qa["accepted_color"] if event.accepted else qa["rejected_color"])
            start = max(0.0, event.event_start_s - window_start_s)
            end = min(duration_s, event.event_end_s - window_start_s)
            if event.accepted:
                axis.axvspan(start, end, facecolor=color, alpha=0.09, linewidth=0.0)
            downward_time = event.downward_zero_crossing_s - window_start_s
            upward_time = event.upward_zero_crossing_s - window_start_s
            if 0 <= downward_time <= duration_s:
                axis.scatter(
                    downward_time,
                    0.0,
                    marker="|",
                    s=55,
                    color="#111827",
                    linewidths=1.0,
                    zorder=5,
                )
            if 0 <= upward_time <= duration_s:
                axis.scatter(
                    upward_time,
                    0.0,
                    marker="|",
                    s=55,
                    color="#111827",
                    linewidths=1.0,
                    zorder=5,
                )
            axis.scatter(
                event.trough_time_s - window_start_s,
                event.trough_amplitude_uv,
                marker="v",
                s=44,
                facecolors=color if event.accepted else "white",
                edgecolors=color,
                linewidths=1.1,
                zorder=6,
            )
            axis.scatter(
                event.positive_peak_time_s - window_start_s,
                event.positive_peak_amplitude_uv,
                marker="^",
                s=44,
                facecolors=color if event.accepted else "white",
                edgecolors=color,
                linewidths=1.1,
                zorder=6,
            )
        axis.axhline(0.0, color="#111827", linewidth=0.6, alpha=0.5)
        axis.set_ylabel(f"{channel}\nAmplitude ({qa['amplitude_unit']})")
        axis.grid(alpha=float(qa["grid_alpha"]), linewidth=0.6)
        axis.spines[["top", "right"]].set_visible(False)
    axes_flat[-1].set_xlim(0.0, duration_s)
    axes_flat[-1].set_xlabel("Time from QA window start (s)")

    legend = [
        Line2D([0], [0], color=str(qa["raw_color"]), linestyle=":", label="Raw EEG"),
        Line2D([0], [0], color=str(qa["detection_color"]), label="Detection-band EEG"),
        Line2D(
            [0],
            [0],
            marker="|",
            color="none",
            markeredgecolor="#111827",
            label="Zero crossing",
        ),
        Line2D(
            [0],
            [0],
            marker="v",
            color="none",
            markeredgecolor="#111827",
            markerfacecolor="#111827",
            label="Trough",
        ),
        Line2D(
            [0],
            [0],
            marker="^",
            color="none",
            markeredgecolor="#111827",
            markerfacecolor="#111827",
            label="Positive peak",
        ),
        Patch(color=str(qa["accepted_color"]), alpha=0.22, label="Accepted candidate"),
        Line2D(
            [0],
            [0],
            marker="v",
            color="none",
            markeredgecolor=str(qa["rejected_color"]),
            markerfacecolor="white",
            label="Rejected feature",
        ),
    ]
    axes_flat[0].legend(handles=legend, loc="upper right", frameon=False, ncols=3)
    band = detection.parameters["detection_band"]
    figure.suptitle(
        "Slow-oscillation candidate detection QA",
        x=0.06,
        y=0.985,
        ha="left",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.94,
        (
            f"{detection.segment_id} | PSG {window_start_s:.1f}–{window_end_s:.1f} s | "
            f"{detection.detector_profile}: {band['low_hz']:g}–{band['high_hz']:g} Hz | "
            f"accepted/rejected in window: "
            f"{sum(event.accepted for event in qa_events)}/"
            f"{sum(not event.accepted for event in qa_events)}"
        ),
        ha="left",
        va="top",
        fontsize=9,
        color="#374151",
    )
    figure.tight_layout(rect=(0.04, 0.03, 0.99, 0.89))
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
        "candidate_event_count": len(qa_events),
        "accepted_event_count": sum(event.accepted for event in qa_events),
        "rejected_event_count": sum(not event.accepted for event in qa_events),
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


def run_detection(
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
    *,
    segment_id: str | None = None,
    detector_profile: str | None = None,
    preprocessing_profile: str | None = None,
    channel_names: Sequence[str] | None = None,
    invalid_time_masks: Sequence[Mapping[str, float]] | None = None,
    events_csv_path: Path | None = None,
    summary_json_path: Path | None = None,
    qa_output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the existing N3 pipeline, detect candidates, and persist audit outputs."""
    section = _detection_config(config)
    qa = _qa_config(config)
    selected_segment_id = segment_id or qa["segment_id"]
    if selected_segment_id is None:
        raise ValueError("slow_oscillation.qa.segment_id must select an N3 segment")
    selected_preprocessing = preprocessing_profile or str(qa["preprocessing_profile"])

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
        detector_profile,
        invalid_time_masks,
    )

    csv_path = events_csv_path or Path(str(section["output_csv"]))
    summary_path = summary_json_path or Path(str(section["summary_json"]))
    figure_path = qa_output_path or Path(str(qa["output_path"]))
    write_events_csv(detection.events, csv_path)
    summary = build_summary(
        detection,
        processed,
        selected_segment,
        psg_path,
        hypnogram_path,
        config,
    )
    summary["qa_figure"] = plot_qa(processed, detection, config, figure_path)
    summary["outputs"] = {
        "events_csv": str(csv_path),
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
    parser.add_argument("--detector-profile", help="Detector profile; overrides config")
    parser.add_argument("--preprocessing-profile", help="Preprocessing profile override")
    parser.add_argument("--channels", nargs="+", help="EEG channels; overrides config")
    parser.add_argument("--invalid-mask-json", type=Path, help="Additional invalid ranges")
    parser.add_argument("--events-csv", type=Path, help="Candidate event CSV output")
    parser.add_argument("--summary-json", type=Path, help="Summary JSON output")
    parser.add_argument("--qa-output", type=Path, help="QA figure output")
    return parser.parse_args()


def main() -> int:
    """Run the slow-oscillation candidate detection CLI."""
    args = _parse_args()
    config = load_config(args.config)
    summary = run_detection(
        args.psg,
        args.hypnogram,
        config,
        segment_id=args.segment_id,
        detector_profile=args.detector_profile,
        preprocessing_profile=args.preprocessing_profile,
        channel_names=args.channels,
        invalid_time_masks=_load_masks(args.invalid_mask_json),
        events_csv_path=args.events_csv,
        summary_json_path=args.summary_json,
        qa_output_path=args.qa_output,
    )
    print(f"Detector profile: {summary['detector']['profile']}")
    for channel, channel_summary in summary["per_channel"].items():
        print(
            f"{channel}: {channel_summary['accepted_event_count']}/"
            f"{channel_summary['candidate_event_count']} accepted, "
            f"{channel_summary['accepted_events_per_minute']:.3f}/min"
        )
    print(f"Events CSV: {summary['outputs']['events_csv']}")
    print(f"Summary JSON: {summary['outputs']['summary_json']}")
    print(f"QA figure: {summary['outputs']['qa_figure']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
