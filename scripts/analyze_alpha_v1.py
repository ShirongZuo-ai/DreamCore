"""Analyze real pre-sleep Alpha and simulate abstract demand without EEG effects."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from dreamcore.alpha.features import AlphaWindowFeatures, extract_alpha_features
from dreamcore.alpha.iaf import IAFResult, estimate_iaf
from dreamcore.alpha.simulation import (
    SIMULATED_DEMAND_PROVENANCE,
    ControlObservation,
    DemandPoint,
    SimulationEvent,
    simulate_stimulation_demand,
)
from dreamcore.alpha.spectral import (
    alpha_filtered_envelope,
    estimate_welch_psd,
)
from dreamcore.alpha.state import ResearchState, estimate_research_state
from dreamcore.alpha.trend import AlphaTrendPoint, estimate_alpha_trend
from dreamcore.config import load_config
from dreamcore.data.reader import load_edf
from dreamcore.datasets.models import CapabilityName, parse_session_manifest
from dreamcore.sleep_staging.labels import StageInterval, normalize_annotations

FEATURE_FIELDS = [
    "subject_id",
    "recording_id",
    "channel",
    "window_start_s",
    "window_end_s",
    "stage",
    "absolute_alpha_power",
    "relative_alpha_power",
    "alpha_band_low_hz",
    "alpha_band_high_hz",
    "individual_alpha_frequency_hz",
    "iaf_confidence",
    "iaf_available",
    "iaf_reason",
    "window_iaf_hz",
    "window_iaf_confidence",
    "individualized_absolute_alpha_power",
    "individualized_relative_alpha_power",
    "alpha_envelope",
    "alpha_trend",
    "alpha_trend_slope",
    "alpha_change_from_baseline",
    "signal_quality",
    "signal_quality_score",
    "signal_quality_reasons",
    "awake_score",
    "drowsiness_score",
    "state_confidence",
    "stimulation_demand",
    "demand_available",
    "ready_to_remove",
    "demand_state",
    "feature_provenance",
    "demand_provenance",
]


def _alpha_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("alpha")
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'alpha' must be a mapping")
    return section


def _stage_interval_for_window(
    start_s: float,
    end_s: float,
    intervals: Sequence[StageInterval],
    allowed_stages: set[str],
) -> StageInterval | None:
    for interval in intervals:
        if (
            interval.label in allowed_stages
            and start_s >= interval.start_s
            and end_s <= interval.end_s
        ):
            return interval
    return None


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


def _relative_path(target: Path, manifest_path: Path) -> str:
    return os.path.relpath(target.resolve(), manifest_path.parent.resolve())


def _build_manifest(
    psg_path: Path,
    hypnogram_path: Path,
    features_path: Path,
    summary_path: Path,
    manifest_path: Path,
    raw_duration_s: float,
    sampling_rate_hz: float,
    channels: Sequence[str],
    contains_stages: Sequence[str],
    analysis_metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    alpha = _alpha_config(config)
    dataset = config["dataset"]
    label_map = {
        str(raw): str(normalized)
        for normalized, raw_labels in config["sleep_staging"]["stage_labels"].items()
        for raw in raw_labels
    }
    signal_ids = {channel: f"eeg-{index + 1}" for index, channel in enumerate(channels)}
    capabilities = {
        name.value: {
            "status": "UNAVAILABLE",
            "source": "unknown",
            "reason": "Not produced by the Alpha V1 offline package",
        }
        for name in CapabilityName
    }
    capabilities.update(
        {
            "eeg": {
                "status": "AVAILABLE",
                "source": "raw",
                "reason": "REAL PUBLIC EEG DATA referenced from Sleep-EDF",
            },
            "sleep_stage_labels": {
                "status": "AVAILABLE",
                "source": "imported",
                "reason": "Imported R&K hypnogram annotations",
            },
            "alpha_power": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-alpha-welch-v1",
                "version": "alpha-v1",
            },
            "relative_alpha_power": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-alpha-welch-v1",
                "version": "alpha-v1",
            },
            "individual_alpha_frequency": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-alpha-iaf-v1",
                "version": "alpha-v1",
            },
            "alpha_trend": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-alpha-trend-v1",
                "version": "alpha-v1",
            },
            "drowsiness_score": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-alpha-state-heuristic-v1",
                "version": "alpha-v1",
            },
            "stimulation_demand": {
                "status": "AVAILABLE",
                "source": "simulated",
                "derived_by": "dreamcore-simulated-demand-v1",
                "version": "alpha-v1",
            },
            "ready_to_remove": {
                "status": "AVAILABLE",
                "source": "simulated",
                "derived_by": "dreamcore-simulated-demand-v1",
                "version": "alpha-v1",
            },
            "decision_simulation": {
                "status": "AVAILABLE",
                "source": "simulated",
                "derived_by": "dreamcore-simulated-demand-v1",
                "version": "alpha-v1",
            },
            "stimulation_events": {
                "status": "AVAILABLE",
                "source": "simulated",
                "reason": SIMULATED_DEMAND_PROVENANCE,
                "derived_by": "dreamcore-simulated-demand-v1",
                "version": "alpha-v1",
            },
        }
    )
    feature_storage = {
        "kind": "csv",
        "path": _relative_path(features_path, manifest_path),
    }
    replay_config = alpha["session_package"]["viewer"]["replay"]
    viewer = {
        "default_start_s": alpha["session_package"]["viewer"]["default_start_s"],
        "default_time_s": alpha["session_package"]["viewer"]["default_time_s"],
        "default_window_duration_s": float(
            alpha["session_package"]["viewer"]["default_window_duration_s"]
        ),
        "window_duration_options_s": [
            float(value)
            for value in alpha["session_package"]["viewer"]["window_duration_options_s"]
        ],
        "display_max_points_per_signal": int(
            alpha["session_package"]["viewer"]["display_max_points_per_signal"]
        ),
        "feature_timestamp_semantics": str(
            alpha["session_package"]["viewer"]["feature_timestamp_semantics"]
        ),
        "stage_jump_time_s": alpha["session_package"]["viewer"]["stage_jump_time_s"],
        "replay": {
            "enabled": bool(replay_config["enabled"]),
            "tick_interval_ms": int(replay_config["tick_interval_ms"]),
            "default_speed": float(replay_config["default_speed"]),
            "speed_options": [float(value) for value in replay_config["speed_options"]],
            "cache_max_windows": int(replay_config["cache_max_windows"]),
            "prefetch_threshold_fraction": float(replay_config["prefetch_threshold_fraction"]),
            "seek_cursor_fraction": float(replay_config["seek_cursor_fraction"]),
            "intervention_notice_duration_ms": int(
                replay_config["intervention_notice_duration_ms"]
            ),
            "intervention_marker_color": str(replay_config["intervention_marker_color"]),
            "provenance_notice": str(replay_config["provenance_notice"]),
        },
    }
    derived = {
        name: {
            "available": True,
            "source": source,
            "derived_by": derived_by,
            "version": "alpha-v1",
            "metadata": {
                "storage": feature_storage,
                "viewer": viewer,
                "analysis": dict(analysis_metadata),
            },
        }
        for name, source, derived_by in (
            ("alpha_power", "derived", "dreamcore-alpha-welch-v1"),
            ("relative_alpha_power", "derived", "dreamcore-alpha-welch-v1"),
            ("individual_alpha_frequency", "derived", "dreamcore-alpha-iaf-v1"),
            ("alpha_trend", "derived", "dreamcore-alpha-trend-v1"),
            ("drowsiness_score", "derived", "dreamcore-alpha-state-heuristic-v1"),
            ("stimulation_demand", "simulated", "dreamcore-simulated-demand-v1"),
            ("ready_to_remove", "simulated", "dreamcore-simulated-demand-v1"),
        )
    }
    derived["simulated_stimulation_events"] = {
        "available": True,
        "source": "simulated",
        "derived_by": "dreamcore-simulated-demand-v1",
        "version": "alpha-v1",
        "metadata": {
            "notice": SIMULATED_DEMAND_PROVENANCE,
            "storage": {
                "kind": "json",
                "path": _relative_path(summary_path, manifest_path),
                "json_path": ["simulated_stimulation_events"],
            },
        },
    }
    return {
        "schema_version": "dreamcore.session.v1",
        "dataset": {
            "id": "sleep-edf-expanded-sc",
            "display_name": str(dataset["name"]),
            "version": "1.0.0",
        },
        "session": {
            "session_id": str(alpha["session_package"]["session_id"]),
            "subject_id": str(dataset["subject_id"]),
            "visit_id": str(dataset["recording_id"]),
            "night_id": str(dataset["recording_id"]),
        },
        "recording": {"duration_seconds": raw_duration_s},
        "signals": [
            {
                "id": signal_ids[channel],
                "modality": "eeg",
                "channel_name": channel,
                "unit": "uV",
                "sampling_rate_hz": sampling_rate_hz,
                "source": "raw",
                "available": True,
                "metadata": {
                    "notice": "REAL PUBLIC EEG DATA",
                    "storage": {
                        "kind": "edf",
                        "path": _relative_path(psg_path, manifest_path),
                        "channel_name": channel,
                        "scale_to_unit": float(alpha["input_scale_to_uv"]),
                        "sampling_rate_tolerance_hz": float(
                            config["data"]["sampling_rate_tolerance_hz"]
                        ),
                    },
                },
            }
            for channel in channels
        ],
        "annotations": {
            "sleep_stages": {
                "available": True,
                "source": "imported",
                "metadata": {
                    "contains_stages": list(contains_stages),
                    "storage": {
                        "kind": "sleep_edf_annotations",
                        "path": _relative_path(hypnogram_path, manifest_path),
                        "label_map": label_map,
                    },
                },
            }
        },
        "derived": derived,
        "capabilities": capabilities,
        "provenance": {
            "classification": "imported",
            "source_dataset_uri": "Sleep-EDF Expanded SC4001E0",
            "imported_by": "scripts/analyze_alpha_v1.py",
            "notes": (
                "REAL PUBLIC EEG DATA; DERIVED ALPHA FEATURES; "
                "SIMULATED STIMULATION EVENTS — NOT ULTRASOUND DOSE OR RESPONSE"
            ),
        },
    }


def _stage_summary(rows: Sequence[dict[str, Any]], channel: str) -> dict[str, Any]:
    output = {}
    stages = sorted({str(row["stage"]) for row in rows})
    for stage in stages:
        selected = [row for row in rows if row["channel"] == channel and row["stage"] == stage]
        output[stage] = {
            "window_count": len(selected),
            "valid_window_count": sum(row["signal_quality"] == "valid" for row in selected),
            "absolute_alpha_power_uv2": _distribution(
                [
                    row["absolute_alpha_power"]
                    for row in selected
                    if row["absolute_alpha_power"] is not None
                ]
            ),
            "relative_alpha_power": _distribution(
                [
                    row["relative_alpha_power"]
                    for row in selected
                    if row["relative_alpha_power"] is not None
                ]
            ),
            "window_iaf_hz": _distribution(
                [row["window_iaf_hz"] for row in selected if row["window_iaf_hz"] is not None]
            ),
        }
    return output


def _add_stage_backgrounds(
    axis: plt.Axes,
    intervals: Sequence[StageInterval],
    start_s: float,
    end_s: float,
    colors: Mapping[str, str],
) -> None:
    for interval in intervals:
        left = max(interval.start_s, start_s)
        right = min(interval.end_s, end_s)
        if right > left and interval.label in colors:
            axis.axvspan(
                left - start_s,
                right - start_s,
                color=str(colors[interval.label]),
                alpha=0.18,
                linewidth=0,
            )


def _plot_qa(
    raw,
    intervals: Sequence[StageInterval],
    rows: Sequence[dict[str, Any]],
    iaf_results: Mapping[str, IAFResult],
    events: Sequence[SimulationEvent],
    channels: Sequence[str],
    config: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    alpha = _alpha_config(config)
    qa = alpha["qa"]
    start_s = float(qa["start_s"])
    duration_s = float(qa["duration_s"])
    end_s = start_s + duration_s
    sfreq = float(raw.info["sfreq"])
    start_sample = int(round(start_s * sfreq))
    stop_sample = int(round(end_s * sfreq))
    observed = raw.get_data(picks=list(channels), start=start_sample, stop=stop_sample)
    times = np.arange(observed.shape[1]) / sfreq
    fixed = alpha["profiles"][alpha["active_profile"]]["fixed_band"]
    filtered = []
    for values in observed:
        alpha_signal, _ = alpha_filtered_envelope(
            values,
            sfreq,
            float(fixed["low_hz"]),
            float(fixed["high_hz"]),
            config,
            str(alpha["active_profile"]),
        )
        filtered.append(alpha_signal)
    scale = float(alpha["input_scale_to_uv"])
    figure, axes = plt.subplots(
        8,
        1,
        sharex=True,
        figsize=(float(qa["figure_width_inches"]), float(qa["figure_height_inches"])),
    )
    observed_color = str(qa["observed_color"])
    derived_color = str(qa["derived_color"])
    comparison_color = str(qa["comparison_color"])
    simulated_color = str(qa["simulated_color"])
    colors = qa["stage_colors"]

    axes[0].plot(times, observed[0] * scale, color=observed_color, linewidth=0.45)
    axes[0].plot(times, observed[1] * scale, color="#9CA3AF", linewidth=0.45, alpha=0.8)
    axes[0].set_ylabel("EEG (µV)")
    axes[0].set_title("[OBSERVED] Real public Sleep-EDF EEG", loc="left")

    for interval in intervals:
        left = max(interval.start_s, start_s)
        right = min(interval.end_s, end_s)
        if right > left and interval.label in colors:
            axes[1].barh(
                0,
                right - left,
                left=left - start_s,
                height=0.7,
                color=str(colors[interval.label]),
                edgecolor="#374151",
                linewidth=0.5,
            )
            axes[1].text(
                (left + right) / 2 - start_s,
                0,
                interval.label,
                ha="center",
                va="center",
                fontsize=8,
            )
    axes[1].set_ylim(-0.6, 0.6)
    axes[1].set_yticks([])
    axes[1].set_title("[OBSERVED] Imported R&K sleep-stage annotation", loc="left")

    axes[2].plot(times, filtered[0], color=derived_color, linewidth=0.65)
    axes[2].plot(times, filtered[1], color=comparison_color, linewidth=0.65, alpha=0.8)
    axes[2].set_ylabel("Alpha EEG (µV)")
    axes[2].set_title("[DERIVED] Fixed-band Alpha-filtered signal", loc="left")

    channel_styles = ((derived_color, "-"), (comparison_color, "--"))
    for channel, (color, line_style) in zip(channels, channel_styles, strict=True):
        selected = [
            row
            for row in rows
            if row["channel"] == channel and start_s <= row["window_center_s"] <= end_s
        ]
        x = [row["window_center_s"] - start_s for row in selected]
        axes[3].plot(
            x,
            [row["relative_alpha_power"] for row in selected],
            color=color,
            linestyle=line_style,
            marker="o",
            markersize=2.5,
            linewidth=1.0,
            label=channel,
        )
        axes[4].scatter(
            x,
            [row["window_iaf_hz"] for row in selected],
            color=color,
            s=11,
            alpha=0.8,
        )
        if iaf_results[channel].individual_alpha_frequency_hz is not None:
            axes[4].axhline(
                iaf_results[channel].individual_alpha_frequency_hz,
                color=color,
                linestyle=line_style,
                linewidth=1.0,
            )
        axes[5].plot(
            x,
            [row["alpha_change_from_baseline"] for row in selected],
            color=color,
            linestyle=line_style,
            linewidth=1.0,
        )
        axes[6].plot(
            x,
            [row["drowsiness_score"] for row in selected],
            color=color,
            linestyle=line_style,
            linewidth=1.0,
        )
    axes[3].set_ylabel("Relative Alpha")
    axes[3].set_title("[DERIVED] Absolute/relative Alpha features (relative shown)", loc="left")
    axes[3].legend(loc="upper right", frameon=False)
    axes[4].set_ylabel("IAF (Hz)")
    axes[4].set_title("[DERIVED] Window IAF peaks and session baseline IAF", loc="left")
    if not any(result.available for result in iaf_results.values()):
        axes[4].text(
            0.01,
            0.9,
            "Session baseline IAF unavailable in both channels",
            transform=axes[4].transAxes,
            ha="left",
            va="top",
            fontsize=8,
            color="#374151",
        )
    axes[5].axhline(0.0, color="#111827", linewidth=0.6)
    axes[5].set_ylabel("Change from baseline")
    axes[5].set_title("[DERIVED] History-aware Alpha trend", loc="left")
    axes[6].set_ylim(-0.03, 1.03)
    axes[6].set_ylabel("Drowsiness score")
    axes[6].set_title("[DERIVED] Research heuristic — not clinical staging", loc="left")

    control_channel = str(alpha["evaluation"]["control_channel"])
    control_rows = [
        row
        for row in rows
        if row["channel"] == control_channel and start_s <= row["window_center_s"] <= end_s
    ]
    axes[7].plot(
        [row["window_center_s"] - start_s for row in control_rows],
        [row["stimulation_demand"] for row in control_rows],
        color=simulated_color,
        linestyle="--",
        linewidth=1.4,
    )
    plotted_events = 0
    for event in events:
        if start_s <= event.timestamp <= end_s and event.event_type != "stimulation_held":
            axes[7].axvline(
                event.timestamp - start_s,
                color=simulated_color,
                linewidth=0.7,
                alpha=0.55,
            )
            plotted_events += 1
    axes[7].set_ylim(-0.03, 1.03)
    axes[7].set_ylabel("Demand [0,1]")
    axes[7].set_xlabel("Seconds from QA window start")
    axes[7].set_title(
        "[SIMULATED] Abstract stimulation demand/events — not ultrasound dose or effect",
        loc="left",
    )

    for axis in axes:
        if axis is not axes[1]:
            _add_stage_backgrounds(axis, intervals, start_s, end_s, colors)
        axis.grid(alpha=float(qa["grid_alpha"]), linewidth=0.5)
        axis.spines[["top", "right"]].set_visible(False)
        axis.set_xlim(0.0, duration_s)
    figure.suptitle(
        "DreamCore Alpha V1 — Observed EEG, Derived Alpha, Simulated Demand",
        x=0.06,
        y=0.995,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.977,
        (
            "REAL PUBLIC EEG DATA | DERIVED ALPHA FEATURES | "
            "SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE OR RESPONSE"
        ),
        ha="left",
        fontsize=9,
        color=simulated_color,
        fontweight="bold",
    )
    axes[0].legend(
        handles=[
            Line2D([0], [0], color=observed_color, label=f"Observed {channels[0]}"),
            Line2D([0], [0], color="#9CA3AF", label=f"Observed {channels[1]}"),
            Line2D([0], [0], color=derived_color, label="Derived"),
            Line2D([0], [0], color=simulated_color, linestyle="--", label="Simulated"),
        ],
        loc="upper right",
        ncols=4,
        frameon=False,
        fontsize=8,
    )
    figure.tight_layout(rect=(0.035, 0.02, 0.99, 0.955))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=int(qa["dpi"]), bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return {
        "output_path": str(output_path),
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": duration_s,
        "simulated_non_hold_event_markers": plotted_events,
    }


def run_alpha_analysis(
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
    *,
    features_csv_path: Path | None = None,
    summary_json_path: Path | None = None,
    qa_output_path: Path | None = None,
    manifest_output_path: Path | None = None,
) -> dict[str, Any]:
    """Run real Wake/N1/N2 Alpha analysis and simulated control demand."""
    alpha = _alpha_config(config)
    evaluation = alpha["evaluation"]
    start_s = float(evaluation["start_s"])
    end_s = float(evaluation["end_s"])
    channels = tuple(str(channel) for channel in alpha["channels"])
    if len(channels) != 2:
        raise ValueError("Alpha V1 real comparison requires exactly two configured channels")
    if str(evaluation["control_channel"]) not in channels:
        raise ValueError("Configured Alpha control channel is not selected")

    raw, annotations = load_edf(psg_path, hypnogram_path, config)
    sfreq = float(raw.info["sfreq"])
    raw_duration_s = float(raw.n_times / sfreq)
    if start_s < 0 or end_s <= start_s or end_s > raw_duration_s:
        raise ValueError("Configured Alpha evaluation range is outside the PSG")
    missing = [channel for channel in channels if channel not in raw.ch_names]
    if missing:
        raise ValueError(f"Configured Alpha channels are absent: {missing}")
    intervals = normalize_annotations(annotations, raw_duration_s, config)
    allowed_stages = {str(stage) for stage in evaluation["stages"]}

    baseline_start_s = float(evaluation["iaf_baseline_start_s"])
    baseline_end_s = float(evaluation["iaf_baseline_end_s"])
    baseline_data = raw.get_data(
        picks=list(channels),
        start=int(round(baseline_start_s * sfreq)),
        stop=int(round(baseline_end_s * sfreq)),
    )
    iaf_results = {
        channel: estimate_iaf(
            estimate_welch_psd(
                baseline_data[index], sfreq, config, str(alpha["comparison_profile"])
            ),
            config,
            str(alpha["comparison_profile"]),
        )
        for index, channel in enumerate(channels)
    }

    window_s = float(alpha["windowing"]["analysis_window_s"])
    step_s = float(alpha["windowing"]["step_s"])
    records: list[dict[str, Any]] = []
    attempted_window_count = 0
    accepted_window_count = 0
    rejected_window_reasons: Counter[str] = Counter()
    window_start = start_s
    while window_start + window_s <= end_s + 1e-9:
        attempted_window_count += 1
        window_end = window_start + window_s
        interval = _stage_interval_for_window(window_start, window_end, intervals, allowed_stages)
        if interval is not None:
            accepted_window_count += 1
            data = raw.get_data(
                picks=list(channels),
                start=int(round(window_start * sfreq)),
                stop=int(round(window_end * sfreq)),
            )
            for channel_index, channel in enumerate(channels):
                fixed = extract_alpha_features(
                    data[channel_index],
                    sfreq,
                    channel,
                    window_start,
                    window_end,
                    interval.label,
                    config,
                    str(alpha["active_profile"]),
                    iaf_results[channel],
                )
                individualized = extract_alpha_features(
                    data[channel_index],
                    sfreq,
                    channel,
                    window_start,
                    window_end,
                    interval.label,
                    config,
                    str(alpha["comparison_profile"]),
                    iaf_results[channel],
                )
                window_iaf = estimate_iaf(
                    estimate_welch_psd(
                        data[channel_index],
                        sfreq,
                        config,
                        str(alpha["comparison_profile"]),
                    ),
                    config,
                    str(alpha["comparison_profile"]),
                )
                records.append(
                    {
                        "feature": fixed,
                        "individualized": individualized,
                        "window_iaf": window_iaf,
                        "window_center_s": (window_start + window_end) / 2.0,
                    }
                )
        else:
            overlapping_labels = sorted(
                {
                    item.label
                    for item in intervals
                    if item.end_s > window_start and item.start_s < window_end
                }
            )
            if not overlapping_labels:
                reason = "no_annotation_coverage"
            elif any(label not in allowed_stages for label in overlapping_labels):
                reason = f"ineligible_stage:{'+'.join(overlapping_labels)}"
            elif len(overlapping_labels) > 1:
                reason = f"stage_transition:{'+'.join(overlapping_labels)}"
            else:
                reason = f"annotation_boundary:{overlapping_labels[0]}"
            rejected_window_reasons[reason] += 1
        window_start += step_s

    trends: dict[tuple[str, float], AlphaTrendPoint] = {}
    states: dict[tuple[str, float], ResearchState] = {}
    for channel in channels:
        selected = [record for record in records if record["feature"].channel == channel]
        selected.sort(key=lambda record: record["window_center_s"])
        channel_trends = estimate_alpha_trend(
            [record["window_center_s"] for record in selected],
            [record["feature"].relative_alpha_power for record in selected],
            [record["feature"].signal_quality.valid for record in selected],
            config,
        )
        for record, trend in zip(selected, channel_trends, strict=True):
            key = (channel, record["window_center_s"])
            trends[key] = trend
            states[key] = estimate_research_state(trend, record["feature"].signal_quality, config)

    control_channel = str(evaluation["control_channel"])
    control_records = sorted(
        [record for record in records if record["feature"].channel == control_channel],
        key=lambda record: record["window_center_s"],
    )
    observations = [
        ControlObservation(
            timestamp_s=record["window_center_s"],
            state=states[(control_channel, record["window_center_s"])],
            trend=trends[(control_channel, record["window_center_s"])],
            alpha_power=record["feature"].absolute_alpha_power,
            relative_alpha_power=record["feature"].relative_alpha_power,
            signal_quality_valid=record["feature"].signal_quality.valid,
        )
        for record in control_records
    ]
    demand_points, events = simulate_stimulation_demand(observations, config)
    demand_by_time: dict[float, DemandPoint] = {point.timestamp: point for point in demand_points}

    rows = []
    dataset = config["dataset"]
    for record in sorted(
        records,
        key=lambda item: (item["window_center_s"], item["feature"].channel),
    ):
        feature: AlphaWindowFeatures = record["feature"]
        individualized: AlphaWindowFeatures = record["individualized"]
        window_iaf: IAFResult = record["window_iaf"]
        key = (feature.channel, record["window_center_s"])
        trend = trends[key]
        state = states[key]
        demand = demand_by_time[record["window_center_s"]]
        rows.append(
            {
                "subject_id": str(dataset["subject_id"]),
                "recording_id": str(dataset["recording_id"]),
                "channel": feature.channel,
                "window_start_s": feature.window_start_s,
                "window_end_s": feature.window_end_s,
                "window_center_s": record["window_center_s"],
                "stage": feature.stage,
                "absolute_alpha_power": feature.absolute_alpha_power,
                "relative_alpha_power": feature.relative_alpha_power,
                "alpha_band_low_hz": feature.alpha_band_low_hz,
                "alpha_band_high_hz": feature.alpha_band_high_hz,
                "individual_alpha_frequency_hz": feature.individual_alpha_frequency_hz,
                "iaf_confidence": feature.iaf_confidence,
                "iaf_available": feature.iaf_available,
                "iaf_reason": feature.iaf_reason,
                "window_iaf_hz": window_iaf.individual_alpha_frequency_hz,
                "window_iaf_confidence": window_iaf.iaf_confidence,
                "individualized_absolute_alpha_power": individualized.absolute_alpha_power,
                "individualized_relative_alpha_power": individualized.relative_alpha_power,
                "alpha_envelope": feature.alpha_envelope,
                "alpha_trend": trend.alpha_trend,
                "alpha_trend_slope": trend.alpha_trend_slope,
                "alpha_change_from_baseline": trend.alpha_change_from_baseline,
                "signal_quality": "valid" if feature.signal_quality.valid else "invalid",
                "signal_quality_score": feature.signal_quality.score,
                "signal_quality_reasons": ";".join(feature.signal_quality.reason_codes),
                "awake_score": state.awake_score,
                "drowsiness_score": state.drowsiness_score,
                "state_confidence": state.state_confidence,
                "stimulation_demand": demand.stimulation_demand,
                "demand_available": demand.demand_available,
                "ready_to_remove": demand.ready_to_remove,
                "demand_state": demand.controller_state,
                "feature_provenance": "derived",
                "demand_provenance": demand.provenance,
            }
        )

    feature_times = [float(row["window_end_s"]) for row in rows]
    analysis_metadata = {
        "time_reference": "recording_relative",
        "timestamp_field": "window_end_s",
        "timestamp_unit": "seconds",
        "evaluation_start_s": start_s,
        "evaluation_end_s": end_s,
        "analysis_window_s": window_s,
        "step_s": step_s,
        "attempted_windows": attempted_window_count,
        "accepted_windows": accepted_window_count,
        "rejected_windows": attempted_window_count - accepted_window_count,
        "rejection_reasons": dict(rejected_window_reasons),
        "feature_row_count": len(rows),
        "first_feature_time_s": min(feature_times) if feature_times else None,
        "last_feature_time_s": max(feature_times) if feature_times else None,
        "channels": list(channels),
    }

    output = alpha["output"]
    features_path = features_csv_path or Path(str(output["features_csv"]))
    summary_path = summary_json_path or Path(str(output["summary_json"]))
    qa_path = qa_output_path or Path(str(output["qa_png"]))
    manifest_path = manifest_output_path or Path(str(alpha["session_package"]["manifest_path"]))
    features_path.parent.mkdir(parents=True, exist_ok=True)
    with features_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FEATURE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    stage_summaries = {channel: _stage_summary(rows, channel) for channel in channels}
    wake_medians = {
        channel: stage_summaries[channel].get("W", {}).get("relative_alpha_power", {}).get("median")
        for channel in channels
    }
    posterior = wake_medians[channels[1]]
    frontal = wake_medians[channels[0]]
    front_loss = (
        1.0 - frontal / posterior if frontal is not None and posterior not in (None, 0.0) else None
    )
    summary: dict[str, Any] = {
        "dataset": {
            "name": str(dataset["name"]),
            "subject_id": str(dataset["subject_id"]),
            "recording_id": str(dataset["recording_id"]),
            "source_notice": "REAL PUBLIC EEG DATA",
        },
        "source": {"psg": psg_path.name, "hypnogram": hypnogram_path.name},
        "evaluation": {
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "stages": list(allowed_stages),
            "channels": list(channels),
            "sampling_rate_hz": sfreq,
            "window_s": window_s,
            "step_s": step_s,
            "stage_pure_windows_only": True,
        },
        "analysis_windows": analysis_metadata,
        "algorithm": {
            "fixed_profile": str(alpha["active_profile"]),
            "individualized_profile": str(alpha["comparison_profile"]),
            "alpha_config": dict(alpha),
            "feature_provenance": "derived",
            "state_notice": "Research heuristic; not a clinically validated staging model",
        },
        "individual_alpha_frequency": {
            channel: {
                "frequency_hz": result.individual_alpha_frequency_hz,
                "confidence": result.iaf_confidence,
                "available": result.available,
                "reason": result.reason,
                "peak_prominence_db": result.peak_prominence_db,
                "total_window_count": sum(row["channel"] == channel for row in rows),
                "reliable_window_count": sum(
                    row["channel"] == channel and row["window_iaf_hz"] is not None for row in rows
                ),
                "unreliable_window_count": sum(
                    row["channel"] == channel and row["window_iaf_hz"] is None for row in rows
                ),
                "wake_window_stability": _distribution(
                    [
                        row["window_iaf_hz"]
                        for row in rows
                        if row["channel"] == channel
                        and row["stage"] == "W"
                        and row["window_iaf_hz"] is not None
                    ]
                ),
            }
            for channel, result in iaf_results.items()
        },
        "per_channel_stage": stage_summaries,
        "channel_comparison": {
            "wake_relative_alpha_median": wake_medians,
            "frontal_channel": channels[0],
            "posterior_channel": channels[1],
            "frontal_relative_alpha_loss_vs_posterior_fraction": front_loss,
            "interpretation": (
                "Descriptive bipolar-channel proxy only; not a validated information-loss metric "
                "for a future frontal wearable."
            ),
        },
        "signal_quality": {
            channel: {
                "valid_windows": sum(
                    row["signal_quality"] == "valid" for row in rows if row["channel"] == channel
                ),
                "invalid_windows": sum(
                    row["signal_quality"] != "valid" for row in rows if row["channel"] == channel
                ),
                "reason_counts": dict(
                    Counter(
                        reason
                        for row in rows
                        if row["channel"] == channel
                        for reason in str(row["signal_quality_reasons"]).split(";")
                        if reason
                    )
                ),
            }
            for channel in channels
        },
        "trend_counts": {
            channel: dict(Counter(row["alpha_trend"] for row in rows if row["channel"] == channel))
            for channel in channels
        },
        "simulated_control": {
            "control_channel": control_channel,
            "provenance": SIMULATED_DEMAND_PROVENANCE,
            "demand_distribution": _distribution(
                [point.stimulation_demand for point in demand_points]
            ),
            "demand_available_points": sum(point.demand_available for point in demand_points),
            "ready_to_remove_points": sum(point.ready_to_remove for point in demand_points),
            "event_type_counts": dict(Counter(event.event_type for event in events)),
            "scientific_boundary": (
                "No EEG samples were modified and no event represents ultrasound delivery, "
                "dose, response, or efficacy."
            ),
        },
        "simulated_stimulation_events": [event.to_dict() for event in events],
        "outputs": {
            "features_csv": str(features_path),
            "summary_json": str(summary_path),
            "qa_png": str(qa_path),
            "session_manifest": str(manifest_path),
        },
    }
    summary["qa"] = _plot_qa(raw, intervals, rows, iaf_results, events, channels, config, qa_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as output_file:
        json.dump(
            summary,
            output_file,
            indent=int(output["json_indent"]),
            sort_keys=True,
            allow_nan=False,
        )
        output_file.write("\n")

    manifest = _build_manifest(
        psg_path,
        hypnogram_path,
        features_path,
        summary_path,
        manifest_path,
        raw_duration_s,
        sfreq,
        channels,
        sorted({interval.label for interval in intervals}),
        analysis_metadata,
        config,
    )
    parse_session_manifest(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as output_file:
        json.dump(manifest, output_file, indent=2, sort_keys=True, allow_nan=False)
        output_file.write("\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--psg", type=Path, required=True)
    parser.add_argument("--hypnogram", type=Path, required=True)
    parser.add_argument("--features-csv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--qa-output", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_alpha_analysis(
        args.psg,
        args.hypnogram,
        load_config(args.config),
        features_csv_path=args.features_csv,
        summary_json_path=args.summary_json,
        qa_output_path=args.qa_output,
        manifest_output_path=args.manifest_output,
    )
    print(f"Evaluation: {summary['evaluation']['start_s']}–{summary['evaluation']['end_s']} s")
    for channel, result in summary["individual_alpha_frequency"].items():
        print(
            f"{channel}: IAF={result['frequency_hz']}, confidence={result['confidence']:.3f}, "
            f"available={result['available']}"
        )
    print(f"Features: {summary['outputs']['features_csv']}")
    print(f"Summary: {summary['outputs']['summary_json']}")
    print(f"QA: {summary['outputs']['qa_png']}")
    print(f"Session manifest: {summary['outputs']['session_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
