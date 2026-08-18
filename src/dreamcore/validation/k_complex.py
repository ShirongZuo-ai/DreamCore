"""Frozen K-complex V0 validation against independent DREAMS experts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from dreamcore.k_complex import detect_k_complexes
from dreamcore.validation.dreams import (
    excerpt_index,
    load_k_complex_signal,
    load_n2_bouts,
    parse_interval_annotations,
    recording_paths,
)
from dreamcore.validation.matching import detection_metrics, match_intervals
from dreamcore.validation.metrics import finite_summary
from dreamcore.validation.models import BenchmarkInterval, ValidationPoint


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _detector_points(events) -> tuple[ValidationPoint, ...]:
    return tuple(
        ValidationPoint(
            event.event_id,
            event.negative_trough_s,
            event.onset_s,
            event.end_s,
        )
        for event in events
    )


def _signal_minimum_within(reference: BenchmarkInterval, signal: np.ndarray, rate: float) -> float:
    start = max(0, int(round(reference.onset_s * rate)))
    end = min(signal.size, int(round(reference.end_s * rate)))
    if end <= start:
        raise ValueError(f"Expert interval has no signal samples: {reference.event_id}")
    return (start + int(np.argmin(signal[start:end]))) / rate


def run_dreams_k_complex(
    project_root: Path, full_config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validation = full_config["signal_validation_v1"]
    dreams = validation["dreams"]
    config = dreams["k_complex"]
    match_config = validation["matching"]["k_complex"]
    detector_config = full_config["k_complex_v0"]
    detector_version = str(detector_config["detector_version"])
    config_hash = _canonical_hash(detector_config)
    rate = float(config["sampling_rate_hz"])
    root = project_root / str(config["extracted_root"])
    match_rows: dict[str, list[dict[str, Any]]] = {"expert_1": [], "expert_2": []}
    per_recording: dict[str, list[dict[str, Any]]] = {"expert_1": [], "expert_2": []}
    totals = {
        "expert_1": {"references": 0, "detections": 0, "matched": 0},
        "expert_2": {"references": 0, "detections": 0, "matched": 0},
    }
    timing: dict[str, list[float]] = {"expert_1": [], "expert_2": []}
    trough_offsets: dict[str, list[float]] = {"expert_1": [], "expert_2": []}
    interexpert_rows: list[dict[str, Any]] = []
    interexpert_totals = {"expert_1": 0, "expert_2": 0, "matched": 0}
    recording_metadata = []
    for edf_path in recording_paths(root, str(config["recording_glob"])):
        index = excerpt_index(edf_path)
        recording_id = f"dreams-kc-excerpt{index}"
        signal_path = root / str(config["signal_text_template"]).format(index=index)
        channel, signal = load_k_complex_signal(signal_path, expected_rate_hz=rate)
        if channel != str(config["channel"]):
            raise ValueError(f"Unexpected DREAMS K-complex channel: {channel}")
        hypnogram_path = root / str(config["hypnogram_template"]).format(index=index)
        bouts = load_n2_bouts(hypnogram_path, dreams, detector_config)
        events = detect_k_complexes(
            signal,
            rate,
            channel,
            bouts,
            detector_config,
            dataset_id="dreams-k-complexes",
            subject_id=f"excerpt{index}",
            recording_id=recording_id,
            detector_version=detector_version,
            config_hash=config_hash,
            source_fingerprint=_source_fingerprint(signal_path),
        )
        points = _detector_points(events)
        event_by_id = {event.event_id: event for event in events}
        expert_annotations: dict[str, tuple[BenchmarkInterval, ...]] = {}
        for scorer in ("expert_1", "expert_2"):
            template = str(
                config["expert_1_template"] if scorer == "expert_1" else config["expert_2_template"]
            )
            path = root / template.format(index=index)
            if not path.is_file():
                continue
            references = parse_interval_annotations(path, recording_id=recording_id, scorer=scorer)
            valid = tuple(reference for reference in references if reference.valid)
            expert_annotations[scorer] = valid
            matches = match_intervals(
                valid,
                points,
                minimum_overlap_s=float(match_config["minimum_overlap_s"]),
            )
            reference_by_id = {reference.event_id: reference for reference in valid}
            for match in matches:
                reference = reference_by_id[match.reference_id]
                event = event_by_id[match.detection_id]
                operational_trough = _signal_minimum_within(reference, signal, rate)
                offset = event.negative_trough_s - operational_trough
                timing[scorer].append(match.timing_offset_s)
                trough_offsets[scorer].append(offset)
                match_rows[scorer].append(
                    {
                        "recording_id": recording_id,
                        "expert_event_id": reference.event_id,
                        "detector_event_id": event.event_id,
                        "expert_onset_s": reference.onset_s,
                        "expert_end_s": reference.end_s,
                        "detector_onset_s": event.onset_s,
                        "detector_trough_s": event.negative_trough_s,
                        "detector_end_s": event.end_s,
                        "overlap_s": match.overlap_s,
                        "detector_trough_minus_expert_interval_midpoint_s": match.timing_offset_s,
                        "signal_derived_trough_within_expert_interval_s": operational_trough,
                        "detector_minus_signal_derived_trough_s": offset,
                        "trough_reference_semantics": (
                            "raw CZ-A1 minimum within expert-annotated interval; "
                            "not expert trough ground truth"
                        ),
                    }
                )
            metrics = detection_metrics(len(valid), len(points), len(matches))
            per_recording[scorer].append({"recording_id": recording_id, **metrics})
            totals[scorer]["references"] += len(valid)
            totals[scorer]["detections"] += len(points)
            totals[scorer]["matched"] += len(matches)
        if "expert_1" in expert_annotations and "expert_2" in expert_annotations:
            expert_2_points = tuple(
                ValidationPoint(
                    item.event_id, (item.onset_s + item.end_s) / 2.0, item.onset_s, item.end_s
                )
                for item in expert_annotations["expert_2"]
            )
            matches = match_intervals(
                expert_annotations["expert_1"],
                expert_2_points,
                minimum_overlap_s=float(match_config["minimum_overlap_s"]),
            )
            expert_1_by_id = {item.event_id: item for item in expert_annotations["expert_1"]}
            expert_2_by_id = {item.event_id: item for item in expert_annotations["expert_2"]}
            for match in matches:
                first = expert_1_by_id[match.reference_id]
                second = expert_2_by_id[match.detection_id]
                interexpert_rows.append(
                    {
                        "recording_id": recording_id,
                        "expert_1_event_id": first.event_id,
                        "expert_2_event_id": second.event_id,
                        "expert_1_onset_s": first.onset_s,
                        "expert_2_onset_s": second.onset_s,
                        "overlap_s": match.overlap_s,
                        "interval_midpoint_offset_s": match.timing_offset_s,
                    }
                )
            interexpert_totals["expert_1"] += len(expert_annotations["expert_1"])
            interexpert_totals["expert_2"] += len(expert_annotations["expert_2"])
            interexpert_totals["matched"] += len(matches)
        recording_metadata.append(
            {
                "recording_id": recording_id,
                "sampling_rate_hz": rate,
                "duration_s": signal.size / rate,
                "channel": channel,
                "unit": str(config["unit"]),
                "n2_bout_count": len(bouts),
                "n2_duration_s": sum(bout.duration_s for bout in bouts),
                "detector_event_count": len(events),
                "expert_2_available": "expert_2" in expert_annotations,
            }
        )
    expert_summaries = {}
    for scorer in ("expert_1", "expert_2"):
        value = totals[scorer]
        expert_summaries[scorer] = {
            **detection_metrics(value["references"], value["detections"], value["matched"]),
            "timing_offset_from_expert_interval_midpoint_s": finite_summary(timing[scorer]),
            "operational_trough_timing_s": finite_summary(trough_offsets[scorer]),
            "per_recording": per_recording[scorer],
        }
    interexpert_metrics = detection_metrics(
        interexpert_totals["expert_1"],
        interexpert_totals["expert_2"],
        interexpert_totals["matched"],
    )
    summary = {
        "detector_version": detector_version,
        "detector_config_hash": config_hash,
        "matching_rule": dict(match_config),
        "experts": expert_summaries,
        "inter_expert_agreement": interexpert_metrics,
        "recordings": recording_metadata,
        "trough_validation_status": (
            "No expert trough landmark exists. Reported trough offsets use the raw CZ-A1 minimum "
            "inside each expert interval as an operational signal-derived reference only."
        ),
    }
    return match_rows["expert_1"], match_rows["expert_2"], interexpert_rows, summary
