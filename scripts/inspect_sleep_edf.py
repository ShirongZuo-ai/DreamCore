"""Inspect one real Sleep-EDF PSG and hypnogram pair."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import mne
import numpy as np
import yaml

from dreamcore.data.reader import check_quality, load_edf


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a YAML inspection configuration."""
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise TypeError("Inspection config must contain a top-level mapping")
    return config


def _required_mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a required mapping from the inspection configuration."""
    try:
        value = config[key]
    except KeyError as error:
        raise ValueError(f"Missing required config section: {key}") from error
    if not isinstance(value, Mapping):
        raise TypeError(f"Config section '{key}' must be a mapping")
    return value


def _stage_durations(annotations: np.ndarray) -> dict[str, float]:
    """Sum durations for each unmodified Sleep-EDF annotation description."""
    durations: dict[str, float] = {}
    for description, duration in zip(
        annotations["description"], annotations["duration"], strict=True
    ):
        stage = str(description)
        durations[stage] = durations.get(stage, 0.0) + float(duration)
    return dict(sorted(durations.items()))


def build_summary(
    raw: mne.io.BaseRaw,
    annotations: np.ndarray,
    quality_report: Mapping[str, Any],
    config: Mapping[str, Any],
    psg_path: Path,
    hypnogram_path: Path,
) -> dict[str, Any]:
    """Build a JSON-compatible validation summary."""
    if len(annotations) == 0:
        raise ValueError("Hypnogram contains no annotations")

    dataset_config = _required_mapping(config, "dataset")
    inspection_config = _required_mapping(config, "inspection")
    required_stages = inspection_config.get("required_stage_descriptions")
    if not isinstance(required_stages, Sequence) or isinstance(required_stages, str):
        raise TypeError("inspection.required_stage_descriptions must be a sequence")

    sfreq = float(raw.info["sfreq"])
    psg_start_s = float(raw.first_time)
    psg_end_s = float(psg_start_s + (raw.n_times / sfreq))
    annotation_start_s = float(np.min(annotations["onset"]))
    annotation_end_s = float(np.max(annotations["onset"] + annotations["duration"]))
    overlap_start_s = float(max(psg_start_s, annotation_start_s))
    overlap_end_s = float(min(psg_end_s, annotation_end_s))
    overlap_duration_s = float(max(0.0, overlap_end_s - overlap_start_s))
    has_valid_overlap = bool(overlap_duration_s > 0.0)

    stage_durations_s = _stage_durations(annotations)
    stage_presence = {str(stage): str(stage) in stage_durations_s for stage in required_stages}
    meas_date = raw.info.get("meas_date")

    return {
        "dataset": str(dataset_config["name"]),
        "files": {
            "psg": psg_path.name,
            "hypnogram": hypnogram_path.name,
        },
        "recording": {
            "sampling_rate_hz": sfreq,
            "duration_s": psg_end_s - psg_start_s,
            "n_samples": int(raw.n_times),
            "n_channels": len(raw.ch_names),
            "channel_names": list(raw.ch_names),
            "measurement_start": meas_date.isoformat() if meas_date is not None else None,
        },
        "annotations": {
            "count": len(annotations),
            "stage_durations_s": stage_durations_s,
            "required_stages_present": stage_presence,
            "all_required_stages_present": all(stage_presence.values()),
        },
        "alignment": {
            "psg_range_s": {"start": psg_start_s, "end": psg_end_s},
            "annotation_range_s": {
                "start": annotation_start_s,
                "end": annotation_end_s,
            },
            "overlap_range_s": {
                "start": overlap_start_s,
                "end": overlap_end_s,
            },
            "overlap_duration_s": overlap_duration_s,
            "has_valid_overlap": has_valid_overlap,
        },
        "quality": dict(quality_report),
    }


def inspect_sleep_edf(
    psg_path: Path,
    hypnogram_path: Path,
    output_path: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Load, validate, summarize, and persist one Sleep-EDF pair."""
    raw, annotations = load_edf(psg_path, hypnogram_path, config)
    quality_report = check_quality(raw, config)
    summary = build_summary(
        raw,
        annotations,
        quality_report,
        config,
        psg_path,
        hypnogram_path,
    )

    inspection_config = _required_mapping(config, "inspection")
    json_indent = int(inspection_config["json_indent"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(summary, output_file, indent=json_indent, sort_keys=True, allow_nan=False)
        output_file.write("\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Dataset YAML config")
    parser.add_argument("--psg", type=Path, required=True, help="PSG EDF path")
    parser.add_argument("--hypnogram", type=Path, required=True, help="Hypnogram EDF path")
    parser.add_argument(
        "--output",
        type=Path,
        help="Summary JSON path; overrides inspection.output_path from config",
    )
    return parser.parse_args()


def main() -> int:
    """Run the Sleep-EDF inspection CLI."""
    args = _parse_args()
    config = load_config(args.config)
    inspection_config = _required_mapping(config, "inspection")
    output_path = args.output or Path(str(inspection_config["output_path"]))
    summary = inspect_sleep_edf(args.psg, args.hypnogram, output_path, config)

    recording = summary["recording"]
    annotation_summary = summary["annotations"]
    alignment = summary["alignment"]
    print(f"Sampling rate: {recording['sampling_rate_hz']} Hz")
    print(f"Recording duration: {recording['duration_s']} s")
    print(f"Channels: {', '.join(recording['channel_names'])}")
    print(f"Annotation count: {annotation_summary['count']}")
    print("Raw sleep-stage durations (s):")
    for stage, duration_s in annotation_summary["stage_durations_s"].items():
        print(f"  {stage}: {duration_s}")
    print(f"Valid PSG/hypnogram overlap: {alignment['has_valid_overlap']}")
    print(f"Required stages present: {annotation_summary['required_stages_present']}")
    print(f"Quality passed: {summary['quality']['passed']}")
    print(f"Summary written to: {output_path}")

    validation_passed = (
        alignment["has_valid_overlap"]
        and annotation_summary["all_required_stages_present"]
        and summary["quality"]["passed"]
    )
    return 0 if validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
