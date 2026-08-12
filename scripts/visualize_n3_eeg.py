"""Compare raw and preprocessed EEG in configured windows of one N3 segment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from dreamcore.config import load_config
from dreamcore.data.reader import load_edf
from dreamcore.preprocessing.eeg import (
    PreprocessedEEG,
    preprocess_n3_segment,
    signal_statistics,
)
from dreamcore.sleep_staging.labels import merge_adjacent_intervals, normalize_annotations
from dreamcore.sleep_staging.segments import N3Segment, extract_n3_segments


def _visualization_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("n3_visualization")
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'n3_visualization' must be a mapping")
    return section


def _select_segment(segments: Sequence[N3Segment], segment_id: str) -> N3Segment:
    for segment in segments:
        if segment.segment_id == segment_id:
            return segment
    available = [segment.segment_id for segment in segments]
    raise ValueError(f"Configured N3 segment '{segment_id}' not found; available: {available}")


def _window_data(
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
        raise ValueError("Visualization window falls outside retained preprocessing data")
    times_s = np.arange(sample_count, dtype=float) / sfreq
    return times_s, data[:, start_sample:stop_sample]


def _filter_description(parameters: Mapping[str, Any]) -> str:
    bandpass = parameters["bandpass"]
    if bandpass["low_hz"] is None:
        bandpass_text = "bandpass off"
    else:
        bandpass_text = f"bandpass {bandpass['low_hz']:g}–{bandpass['high_hz']:g} Hz"
    notch = parameters["notch_freqs_hz"]
    notch_text = "notch off" if not notch else f"notch {','.join(f'{f:g}' for f in notch)} Hz"
    return (
        f"{bandpass_text}; {notch_text}; reference {parameters['reference']['mode']}; "
        f"detrend {parameters['detrend']}"
    )


def _plot_window(
    processed: PreprocessedEEG,
    window_name: str,
    window_config: Mapping[str, Any],
    visual_config: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    offset_s = float(window_config["offset_s"])
    duration_s = float(window_config["duration_s"])
    if offset_s < 0 or duration_s <= 0:
        raise ValueError("Visualization offset_s must be non-negative and duration_s positive")
    segment_start_s = float(processed.metadata["input"]["start_s"])
    window_start_s = segment_start_s + offset_s
    window_end_s = window_start_s + duration_s
    if window_start_s < processed.start_s or window_end_s > processed.end_s:
        raise ValueError(
            f"Visualization window [{window_start_s}, {window_end_s}) falls outside "
            f"retained range [{processed.start_s}, {processed.end_s})"
        )

    raw_times, raw_window = _window_data(
        processed.raw_data,
        processed.original_sampling_rate_hz,
        processed.start_s,
        window_start_s,
        duration_s,
    )
    output_times, output_window = _window_data(
        processed.data,
        processed.output_sampling_rate_hz,
        processed.start_s,
        window_start_s,
        duration_s,
    )
    scale = float(visual_config["amplitude_scale"])
    unit = str(visual_config["amplitude_unit"])
    channel_count = len(processed.channel_names)
    figure, axes = plt.subplots(
        channel_count,
        1,
        sharex=True,
        squeeze=False,
        figsize=(
            float(visual_config["figure_width_inches"]),
            float(visual_config["figure_height_per_channel_inches"]) * channel_count,
        ),
    )
    axes_flat = axes[:, 0]
    channel_axes = zip(axes_flat, processed.channel_names, strict=True)
    for index, (axis, channel_name) in enumerate(channel_axes):
        axis.plot(
            raw_times,
            raw_window[index] * scale,
            color=str(visual_config["raw_color"]),
            linewidth=float(visual_config["raw_line_width"]),
            linestyle=str(visual_config["raw_line_style"]),
            alpha=0.78,
            label=f"Raw ({processed.original_sampling_rate_hz:g} Hz)",
        )
        axis.plot(
            output_times,
            output_window[index] * scale,
            color=str(visual_config["processed_color"]),
            linewidth=float(visual_config["processed_line_width"]),
            linestyle=str(visual_config["processed_line_style"]),
            label=f"Processed ({processed.output_sampling_rate_hz:g} Hz)",
        )
        axis.set_ylabel(f"{channel_name}\nAmplitude ({unit})")
        axis.grid(axis="both", alpha=float(visual_config["grid_alpha"]), linewidth=0.6)
        axis.spines[["top", "right"]].set_visible(False)
        if index == 0:
            axis.legend(loc="upper right", frameon=False, ncols=2)
    axes_flat[-1].set_xlabel("Time from window start (s)")
    axes_flat[-1].set_xlim(0.0, duration_s)

    parameters = processed.metadata["parameters"]
    figure.suptitle(
        f"N3 EEG raw vs processed — {window_name} window",
        x=0.06,
        y=0.98,
        ha="left",
        fontsize=14,
        fontweight="semibold",
    )
    figure.text(
        0.06,
        0.935,
        (
            f"{processed.segment_id} | PSG {window_start_s:.1f}–{window_end_s:.1f} s | "
            f"profile: {processed.profile_name} | {_filter_description(parameters)}"
        ),
        ha="left",
        va="top",
        fontsize=9,
        color="#374151",
    )
    figure.tight_layout(rect=(0.04, 0.03, 0.99, 0.90))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=int(visual_config["dpi"]),
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)

    return {
        "name": window_name,
        "offset_s": offset_s,
        "start_s": window_start_s,
        "end_s": window_end_s,
        "duration_s": duration_s,
        "output_path": str(output_path),
        "statistics": {
            "unit": unit,
            "raw": signal_statistics(raw_window, processed.channel_names, scale),
            "processed": signal_statistics(output_window, processed.channel_names, scale),
        },
    }


def _dataset_metadata(config: Mapping[str, Any], psg_path: Path) -> dict[str, str]:
    dataset = config.get("dataset", {})
    if not isinstance(dataset, Mapping):
        raise TypeError("Config section 'dataset' must be a mapping")
    return {
        "name": str(dataset.get("name", "unknown")),
        "subject_id": str(dataset.get("subject_id", psg_path.stem)),
        "recording_id": str(dataset.get("recording_id", psg_path.stem)),
    }


def run_visualization(
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
    *,
    segment_id: str | None = None,
    profile_name: str | None = None,
    channel_names: Sequence[str] | None = None,
    output_paths: Mapping[str, Path] | None = None,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    """Run the reusable Sleep-EDF-to-N3 preprocessing visualization pipeline."""
    visual_config = _visualization_config(config)
    selected_segment_id = segment_id or visual_config["segment_id"]
    if selected_segment_id is None:
        raise ValueError("n3_visualization.segment_id must select a representative segment")
    selected_profile = profile_name or str(visual_config["preprocessing_profile"])

    raw, annotations = load_edf(psg_path, hypnogram_path, config)
    raw_duration_s = float(raw.n_times / raw.info["sfreq"])
    normalized = normalize_annotations(annotations, raw_duration_s, config)
    merged = merge_adjacent_intervals(normalized, config)
    segments = extract_n3_segments(
        raw,
        merged,
        psg_path.stem,
        config,
        channel_names,
    )
    selected_segment = _select_segment(segments, str(selected_segment_id))
    processed = preprocess_n3_segment(
        selected_segment,
        config,
        selected_profile,
        channel_names,
    )

    windows = visual_config["windows"]
    if not isinstance(windows, Mapping) or not windows:
        raise TypeError("n3_visualization.windows must be a non-empty mapping")
    figure_metadata = []
    for window_name, window_config in windows.items():
        if not isinstance(window_config, Mapping):
            raise TypeError(f"n3_visualization.windows.{window_name} must be a mapping")
        configured_path = Path(str(window_config["output_path"]))
        output_path = (output_paths or {}).get(str(window_name), configured_path)
        figure_metadata.append(
            _plot_window(
                processed,
                str(window_name),
                window_config,
                visual_config,
                output_path,
            )
        )

    scale = float(visual_config["amplitude_scale"])
    unit = str(visual_config["amplitude_unit"])
    summary = {
        "dataset": _dataset_metadata(config, psg_path),
        "source": {
            "psg": psg_path.name,
            "hypnogram": hypnogram_path.name,
        },
        "segment": {
            "segment_id": selected_segment.segment_id,
            "original_start_s": selected_segment.start_s,
            "original_end_s": selected_segment.end_s,
            "original_duration_s": selected_segment.duration_s,
            "raw_label_sources": list(selected_segment.raw_labels),
            "retained_start_s": processed.start_s,
            "retained_end_s": processed.end_s,
            "retained_duration_s": processed.duration_s,
        },
        "channels": list(processed.channel_names),
        "sampling_rates_hz": {
            "original": processed.original_sampling_rate_hz,
            "output": processed.output_sampling_rate_hz,
        },
        "preprocessing": processed.metadata,
        "statistics": {
            "unit": unit,
            "raw_retained_segment": signal_statistics(
                processed.raw_data, processed.channel_names, scale
            ),
            "processed_retained_segment": signal_statistics(
                processed.data, processed.channel_names, scale
            ),
        },
        "figures": figure_metadata,
    }
    output_summary_path = summary_path or Path(str(visual_config["summary_json"]))
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    with output_summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(
            summary,
            summary_file,
            indent=int(visual_config["json_indent"]),
            sort_keys=True,
            allow_nan=False,
        )
        summary_file.write("\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Dataset YAML config")
    parser.add_argument("--psg", type=Path, required=True, help="PSG EDF path")
    parser.add_argument("--hypnogram", type=Path, required=True, help="Hypnogram EDF path")
    parser.add_argument("--segment-id", help="Representative N3 segment; overrides config")
    parser.add_argument("--profile", help="Preprocessing profile; overrides config")
    parser.add_argument("--channels", nargs="+", help="EEG channels; overrides config")
    parser.add_argument("--long-output", type=Path, help="Long-window figure path")
    parser.add_argument("--short-output", type=Path, help="Short-window figure path")
    parser.add_argument("--summary-json", type=Path, help="JSON summary path")
    return parser.parse_args()


def main() -> int:
    """Run the N3 EEG visualization CLI."""
    args = _parse_args()
    config = load_config(args.config)
    output_paths = {
        name: path
        for name, path in {"long": args.long_output, "short": args.short_output}.items()
        if path is not None
    }
    summary = run_visualization(
        args.psg,
        args.hypnogram,
        config,
        segment_id=args.segment_id,
        profile_name=args.profile,
        channel_names=args.channels,
        output_paths=output_paths,
        summary_path=args.summary_json,
    )
    segment = summary["segment"]
    print(f"N3 segment: {segment['segment_id']}")
    print(f"Retained PSG range: {segment['retained_start_s']}–{segment['retained_end_s']} s")
    print(f"EEG channels: {', '.join(summary['channels'])}")
    rates = summary["sampling_rates_hz"]
    print(f"Sampling rate (original/output): {rates['original']}/{rates['output']} Hz")
    for figure in summary["figures"]:
        print(f"{figure['name'].capitalize()} figure: {figure['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
