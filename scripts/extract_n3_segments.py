"""Extract continuous N3 EEG segments from one Sleep-EDF recording."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dreamcore.config import load_config
from dreamcore.data.reader import load_edf
from dreamcore.sleep_staging.labels import (
    StageInterval,
    merge_adjacent_intervals,
    normalize_annotations,
)
from dreamcore.sleep_staging.segments import (
    N3Segment,
    extract_n3_segments,
    resolve_eeg_channels,
)


def _extraction_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("n3_extraction")
    if not isinstance(section, Mapping):
        raise TypeError("Config section 'n3_extraction' must be a mapping")
    return section


def _segment_metadata(segment: N3Segment, psg_path: Path, hypnogram_path: Path) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "source_psg": psg_path.name,
        "source_hypnogram": hypnogram_path.name,
        "start_s": segment.start_s,
        "end_s": segment.end_s,
        "duration_s": segment.duration_s,
        "raw_label_sources": list(segment.raw_labels),
        "normalized_label": segment.normalized_label,
        "channels": list(segment.channel_names),
        "sampling_rate_hz": segment.sampling_rate_hz,
        "n_samples": segment.n_samples,
    }


def build_extraction_summary(
    original_annotation_count: int,
    normalized_intervals: Sequence[StageInterval],
    merged_intervals: Sequence[StageInterval],
    segments: Sequence[N3Segment],
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build JSON-compatible extraction metadata and aggregate statistics."""
    extraction_config = _extraction_config(config)
    target_label = str(extraction_config["target_label"])
    before_merge = [interval for interval in normalized_intervals if interval.label == target_label]
    after_merge = [interval for interval in merged_intervals if interval.label == target_label]
    total_duration_s = sum(interval.duration_s for interval in after_merge)
    longest_duration_s = max((interval.duration_s for interval in after_merge), default=0.0)
    segment_metadata = [
        _segment_metadata(segment, psg_path, hypnogram_path) for segment in segments
    ]

    return {
        "source": {
            "psg": psg_path.name,
            "hypnogram": hypnogram_path.name,
        },
        "parameters": {
            "target_label": target_label,
            "min_segment_duration_s": float(extraction_config["min_segment_duration_s"]),
            "merge_tolerance_s": float(config["sleep_staging"]["merge_tolerance_s"]),
            "selected_eeg_channels": list(segments[0].channel_names if segments else ()),
        },
        "statistics": {
            "original_annotation_count": original_annotation_count,
            "clipped_annotation_count": len(normalized_intervals),
            "n3_interval_count_before_merge": len(before_merge),
            "n3_interval_count_after_merge": len(after_merge),
            "n3_total_duration_s": total_duration_s,
            "longest_n3_interval_s": longest_duration_s,
            "retained_segment_count": len(segments),
        },
        "segments": segment_metadata,
    }


def write_metadata(
    summary: Mapping[str, Any],
    csv_path: Path,
    json_path: Path,
    config: Mapping[str, Any],
) -> None:
    """Write N3 segment metadata as CSV and JSON."""
    extraction_config = _extraction_config(config)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(
            summary,
            json_file,
            indent=int(extraction_config["json_indent"]),
            sort_keys=True,
            allow_nan=False,
        )
        json_file.write("\n")

    fieldnames = [
        "segment_id",
        "source_psg",
        "source_hypnogram",
        "start_s",
        "end_s",
        "duration_s",
        "raw_label_sources",
        "normalized_label",
        "channels",
        "sampling_rate_hz",
        "n_samples",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for segment in summary["segments"]:
            row = dict(segment)
            row["raw_label_sources"] = "|".join(row["raw_label_sources"])
            row["channels"] = "|".join(row["channels"])
            writer.writerow(row)


def run_extraction(
    psg_path: Path,
    hypnogram_path: Path,
    csv_path: Path,
    json_path: Path,
    config: Mapping[str, Any],
    channel_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Load one record, extract N3 EEG segments, and persist metadata."""
    raw, annotations = load_edf(psg_path, hypnogram_path, config)
    raw_duration_s = float(raw.n_times / raw.info["sfreq"])
    normalized = normalize_annotations(annotations, raw_duration_s, config)
    merged = merge_adjacent_intervals(normalized, config)
    selected_channels = resolve_eeg_channels(raw, config, channel_names)
    segments = extract_n3_segments(
        raw,
        merged,
        psg_path.stem,
        config,
        selected_channels,
    )
    summary = build_extraction_summary(
        len(annotations),
        normalized,
        merged,
        segments,
        psg_path,
        hypnogram_path,
        config,
    )
    summary["parameters"]["selected_eeg_channels"] = list(selected_channels)
    write_metadata(summary, csv_path, json_path, config)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Dataset YAML config")
    parser.add_argument("--psg", type=Path, required=True, help="PSG EDF path")
    parser.add_argument("--hypnogram", type=Path, required=True, help="Hypnogram EDF path")
    parser.add_argument("--channels", nargs="+", help="EEG channels; overrides config")
    parser.add_argument("--output-csv", type=Path, help="CSV metadata output path")
    parser.add_argument("--output-json", type=Path, help="JSON metadata output path")
    return parser.parse_args()


def main() -> int:
    """Run the N3 extraction CLI."""
    args = _parse_args()
    config = load_config(args.config)
    extraction_config = _extraction_config(config)
    csv_path = args.output_csv or Path(str(extraction_config["output_csv"]))
    json_path = args.output_json or Path(str(extraction_config["output_json"]))
    summary = run_extraction(
        args.psg,
        args.hypnogram,
        csv_path,
        json_path,
        config,
        args.channels,
    )

    statistics = summary["statistics"]
    print(
        "N3 intervals before/after merge: "
        f"{statistics['n3_interval_count_before_merge']}/"
        f"{statistics['n3_interval_count_after_merge']}"
    )
    print(f"N3 total duration: {statistics['n3_total_duration_s']} s")
    print(f"Longest N3 interval: {statistics['longest_n3_interval_s']} s")
    print(f"Retained N3 segments: {statistics['retained_segment_count']}")
    print(f"EEG channels: {', '.join(summary['parameters']['selected_eeg_channels'])}")
    print(f"CSV metadata: {csv_path}")
    print(f"JSON metadata: {json_path}")
    return 0 if statistics["retained_segment_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
