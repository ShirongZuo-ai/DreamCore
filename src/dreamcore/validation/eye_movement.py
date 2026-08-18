"""Frozen Eye Movement V1 agreement with expert DREAMS REM intervals."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dreamcore.eye_movement import extract_eye_movement_track
from dreamcore.validation.dreams import (
    excerpt_index,
    inspect_edf_compatibly,
    load_edf_channel_uv,
    parse_interval_annotations,
    recording_paths,
    select_eog_channels,
)
from dreamcore.validation.matching import detection_metrics, match_points_to_intervals
from dreamcore.validation.metrics import finite_summary
from dreamcore.validation.models import ValidationPoint


def _human_qc_status(project_root: Path) -> dict[str, Any]:
    path = project_root / "results/eog_validation_v1/human_reviews.csv"
    if not path.is_file():
        return {"status": "Human QC pending", "review_count": 0, "labels": {}}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels: dict[str, int] = {}
    for row in rows:
        label = str(row.get("review_label", ""))
        if label:
            labels[label] = labels.get(label, 0) + 1
    return {
        "status": "Human QC pending" if not rows else "Human QC in progress",
        "review_count": len(rows),
        "labels": dict(sorted(labels.items())),
    }


def run_dreams_rem(
    project_root: Path, full_config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validation = full_config["signal_validation_v1"]
    dreams = validation["dreams"]
    config = dreams["rem"]
    matching = validation["matching"]["eye_movement"]
    root = project_root / str(config["extracted_root"])
    primary_tolerance = float(matching["primary_tolerance_s"])
    primary_match_rows: list[dict[str, Any]] = []
    recording_rows: list[dict[str, Any]] = []
    tolerance_totals = {
        float(value): {"references": 0, "detections": 0, "matched": 0}
        for value in matching["sensitivity_tolerances_s"]
    }
    native_expert_count = 0
    valid_expert_count = 0
    invalid_annotations = []
    total_candidates = 0
    all_offsets = []
    channel_metadata = {}
    for edf_path in recording_paths(root, str(config["recording_glob"])):
        index = excerpt_index(edf_path)
        recording_id = f"dreams-rem-excerpt{index}"
        metadata = inspect_edf_compatibly(edf_path)
        primary_channel, compatible = select_eog_channels(metadata.channel_names, config)
        rate, signal_uv, unit = load_edf_channel_uv(edf_path, primary_channel)
        if abs(rate - float(config["sampling_rate_hz"])) > 1.0e-9 or unit != str(config["unit"]):
            raise ValueError(f"Unexpected DREAMS REM rate/unit in {edf_path.name}")
        expert_path = root / str(config["expert_template"]).format(index=index)
        annotations = parse_interval_annotations(
            expert_path, recording_id=recording_id, scorer="expert_1"
        )
        native_expert_count += len(annotations)
        valid = tuple(item for item in annotations if item.valid)
        valid_expert_count += len(valid)
        invalid_annotations.extend(item.to_dict() for item in annotations if not item.valid)
        track = extract_eye_movement_track(
            signal_uv,
            rate,
            primary_channel,
            recording_id,
            None,
            full_config,
        )
        points = tuple(
            ValidationPoint(
                event.event_id, event.timestamp, event.window_start_s, event.window_end_s
            )
            for event in track.events
        )
        total_candidates += len(points)
        matches_by_tolerance = {}
        for tolerance in tolerance_totals:
            matches = match_points_to_intervals(valid, points, tolerance_s=tolerance)
            tolerance_totals[tolerance]["references"] += len(valid)
            tolerance_totals[tolerance]["detections"] += len(points)
            tolerance_totals[tolerance]["matched"] += len(matches)
            matches_by_tolerance[tolerance] = matches
        primary_matches = matches_by_tolerance[primary_tolerance]
        reference_by_id = {item.event_id: item for item in valid}
        detection_by_id = {item.event_id: item for item in track.events}
        all_offsets.extend(match.timing_offset_s for match in primary_matches)
        for match in primary_matches:
            reference = reference_by_id[match.reference_id]
            event = detection_by_id[match.detection_id]
            primary_match_rows.append(
                {
                    "recording_id": recording_id,
                    "expert_event_id": reference.event_id,
                    "candidate_event_id": event.event_id,
                    "expert_onset_s": reference.onset_s,
                    "expert_end_s": reference.end_s,
                    "candidate_peak_s": event.timestamp,
                    "timing_offset_from_expert_interval_midpoint_s": match.timing_offset_s,
                    "candidate_confidence": event.confidence,
                    "candidate_amplitude_uv": event.amplitude_uv,
                    "source_channel": primary_channel,
                    "match_tolerance_s": primary_tolerance,
                }
            )
        per_metrics = detection_metrics(len(valid), len(points), len(primary_matches))
        recording_rows.append(
            {
                "recording_id": recording_id,
                "duration_s": metadata.duration_s,
                "sampling_rate_hz": rate,
                "primary_eog_channel": primary_channel,
                "compatible_eog_channels": list(compatible),
                "expert_events_native": len(annotations),
                "expert_events_evaluable": len(valid),
                "invalid_expert_rows": len(annotations) - len(valid),
                "dreamcore_candidates": len(points),
                **per_metrics,
            }
        )
        channel_metadata[recording_id] = {
            "all_channels": list(metadata.channel_names),
            "native_units": list(metadata.channel_units),
            "compatible_eog_channels": list(compatible),
            "primary_eog_channel": primary_channel,
        }
    pooled = detection_metrics(
        valid_expert_count,
        total_candidates,
        tolerance_totals[primary_tolerance]["matched"],
    )
    sensitivity = {}
    for tolerance, totals in sorted(tolerance_totals.items()):
        sensitivity[str(tolerance)] = detection_metrics(
            totals["references"], totals["detections"], totals["matched"]
        )
    summary = {
        "semantic_target": "expert rapid-eye-movement intervals",
        "dreamcore_output": "general EOG-derived Eye Movement V1 candidates",
        "recording_count": len(recording_rows),
        "expert_events_native": native_expert_count,
        "expert_events_evaluable": valid_expert_count,
        "invalid_expert_annotation_count": len(invalid_annotations),
        "invalid_expert_annotations": invalid_annotations,
        "dreamcore_candidate_count": total_candidates,
        "primary_tolerance_s": primary_tolerance,
        "pooled_candidate_agreement_with_expert_rem_labels": pooled,
        "timing_offset_from_expert_interval_midpoint_s": finite_summary(all_offsets),
        "tolerance_sensitivity": sensitivity,
        "recordings": recording_rows,
        "channel_metadata": channel_metadata,
        "human_qc": _human_qc_status(project_root),
        "semantic_limitation": (
            "An unmatched generic DreamCore candidate is not automatically a false eye movement; "
            "the benchmark labels only expert rapid eye movements."
        ),
    }
    return primary_match_rows, recording_rows, summary
