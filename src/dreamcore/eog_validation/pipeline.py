"""Frozen full-night Cross-Dataset EOG Validation V1 pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from dreamcore.config import load_config
from dreamcore.datasets.repository import SessionPackageRepository
from dreamcore.eog_validation.core import (
    assign_event_stage,
    build_control_sample,
    deterministic_stratified_sample,
    match_events,
    stage_exposure,
)
from dreamcore.eye_movement import extract_eye_movement_track


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip(
        "-"
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _find_adapter(repository: SessionPackageRepository, session_id: str):
    return next(
        adapter
        for adapter in repository.adapters()
        if any(summary.session.session_id == session_id for summary in adapter.list_sessions())
    )


def _relative(path: Path, root: Path) -> str:
    return os.path.relpath(path.resolve(), root.resolve())


def build_validation_contract(
    validation_config_path: Path,
) -> tuple[dict[str, Any], str, Path]:
    """Resolve actual indexed inputs and hash the frozen detector contract."""

    config_path = validation_config_path.resolve()
    validation = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    analysis_path = project_root / str(validation["analysis_config"])
    analysis = load_config(analysis_path)
    detector = analysis["eye_movement"]
    repository = SessionPackageRepository(project_root / validation["session_package_root"])
    selected = []
    for requested in validation["selected_recordings"]:
        session_id = str(requested["session_id"])
        adapter = _find_adapter(repository, session_id)
        manifest = adapter.get_session_metadata(session_id)
        if manifest.dataset.id != requested["dataset_id"]:
            raise ValueError(f"dataset mismatch for {session_id}")
        channels = []
        for channel_name in requested["channels"]:
            signal = next(
                (
                    signal
                    for signal in manifest.signals
                    if signal.original_channel_name == channel_name
                ),
                None,
            )
            if signal is None or signal.modality != "eog":
                raise ValueError(f"configured EOG channel {channel_name!r} missing in {session_id}")
            channels.append(
                {
                    "original_channel_name": signal.original_channel_name,
                    "canonical_role": signal.canonical_role.value,
                    "signal_id": signal.id,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                    "unit": signal.unit,
                }
            )
        selected.append(
            {
                "dataset_id": manifest.dataset.id,
                "dataset_version": manifest.dataset.version,
                "subject_id": manifest.session.subject_id,
                "recording_id": session_id,
                "recording_duration_s": manifest.recording.duration_seconds,
                "channels": channels,
                "scorers": list(requested.get("scorers", [])),
            }
        )
    payload = {
        "schema_version": validation["schema_version"],
        "validation_version": validation["validation_version"],
        "detector_version": detector["feature_version"],
        "detector_configuration": {
            key: detector[key]
            for key in (
                "filtering",
                "windowing",
                "quality",
                "normalization",
                "local_baseline",
                "event_detection",
            )
        },
        "selected_recordings": selected,
        "event_matching": validation["event_matching"],
        "stage_handling": validation["stage_handling"],
        "manual_qc_protocol": validation["manual_qc"],
        "sampling_strategy": validation["qc_sampling"],
        "metrics": [
            "full_night_coverage_and_quality",
            "candidate_rate_per_valid_hour",
            "stage_exposure_normalized_candidate_rate",
            "dual_eog_one_to_one_temporal_agreement",
            "isruc_epoch_and_candidate_stage_disagreement",
            "manual_candidate_precision_estimate_pending_review",
            "sampled_non_candidate_miss_proportion_pending_review",
            "confidence_bin_diagnostic_pending_review",
            "candidate_morphology_descriptive_summary_pending_review",
        ],
        "scientific_semantics": {
            "event_name": "Eye Movement Candidate",
            "not_ground_truth": [
                "REM event",
                "dream event",
                "saccade ground truth",
                "left-eye movement",
                "right-eye movement",
                "clinical eye movement",
            ],
            "polarity_direction_inference": False,
            "threshold_tuning_allowed": False,
        },
    }
    digest = _sha256_bytes(_canonical_json(payload))
    contract = {
        **payload,
        "contract_hash_algorithm": "sha256(canonical-json-without-hash-fields)",
        "contract_sha256": digest,
    }
    output_root = project_root / validation["output_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    contract_path = output_root / validation["contract_filename"]
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_root / validation["contract_hash_filename"]).write_text(
        f"{digest}  {validation['contract_filename']}\n", encoding="utf-8"
    )
    return contract, digest, contract_path


def verify_validation_contract(validation_config_path: Path) -> tuple[dict[str, Any], str]:
    config_path = validation_config_path.resolve()
    validation = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    contract_path = (
        config_path.parent.parent / validation["output_root"] / validation["contract_filename"]
    )
    if not contract_path.is_file():
        raise ValueError("validation contract is missing; run --contract-only first")
    stored = json.loads(contract_path.read_text(encoding="utf-8"))
    payload = {
        key: value
        for key, value in stored.items()
        if key not in {"contract_hash_algorithm", "contract_sha256"}
    }
    digest = _sha256_bytes(_canonical_json(payload))
    if digest != stored.get("contract_sha256"):
        raise ValueError("stored validation contract hash is invalid")
    return stored, digest


def _event_morphology(event, features) -> dict[str, Any]:
    candidates = [
        feature
        for feature in features
        if feature.event_candidate
        and feature.window_start_s <= event.timestamp <= feature.window_end_s
        and feature.robust_deviation_z is not None
    ]
    source = (
        min(
            candidates,
            key=lambda feature: (
                abs(float(feature.robust_deviation_z) - event.robust_deviation_z),
                abs(feature.window_end_s - event.timestamp),
            ),
        )
        if candidates
        else None
    )
    return {
        "peak_to_peak_uv": source.peak_to_peak_uv if source else None,
        "mean_absolute_derivative_uv_per_s": (
            source.mean_absolute_derivative_uv_per_s if source else None
        ),
        "local_rms_uv": source.eog_rms_uv if source else None,
    }


def _quantiles(values: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    array = np.asarray(values, dtype=float)
    return tuple(float(value) for value in np.quantile(array, [0.25, 0.5, 0.75]))


def _annotation_map(adapter, session_id: str, validation: Mapping[str, Any], scorers):
    annotations = {
        "primary": adapter.load_annotations(
            session_id, validation["stage_handling"]["default_annotation"]
        )
    }
    for scorer in scorers:
        annotation_type = validation["stage_handling"]["isruc_scorer_annotations"][str(scorer)]
        annotations[f"scorer_{scorer}"] = adapter.load_annotations(session_id, annotation_type)
    return annotations


def run_full_validation(validation_config_path: Path) -> dict[str, Any]:
    """Run the frozen detector full-night and create descriptive validation artifacts."""

    config_path = validation_config_path.resolve()
    validation = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    contract, contract_hash = verify_validation_contract(config_path)
    analysis = load_config(project_root / validation["analysis_config"])
    repository = SessionPackageRepository(project_root / validation["session_package_root"])
    output_root = project_root / validation["output_root"]
    derived_root = output_root / "derived"
    derived_root.mkdir(parents=True, exist_ok=True)
    stages = list(validation["stage_handling"]["canonical_labels"])
    step_s = float(analysis["eye_movement"]["windowing"]["step_s"])
    summary_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    agreement_rows: list[dict[str, Any]] = []
    scorer_rows: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    recording_context: dict[str, dict[str, Any]] = {}
    run_started = datetime.now(UTC).isoformat()

    for requested in validation["selected_recordings"]:
        session_id = str(requested["session_id"])
        adapter = _find_adapter(repository, session_id)
        manifest = adapter.get_session_metadata(session_id)
        annotations = _annotation_map(adapter, session_id, validation, requested.get("scorers", []))
        primary_annotations = annotations["primary"]
        exposure_by_source = {
            name: stage_exposure(
                rows,
                recording_duration_s=manifest.recording.duration_seconds,
                canonical_labels=stages,
            )
            for name, rows in annotations.items()
        }
        recording_events: dict[str, list[dict[str, Any]]] = {}
        channel_metadata: dict[str, dict[str, Any]] = {}
        for channel_name in requested["channels"]:
            signal = next(
                signal
                for signal in manifest.signals
                if signal.original_channel_name == channel_name
            )
            window = adapter.load_signal_window(
                session_id, signal.id, 0.0, manifest.recording.duration_seconds
            )
            track = extract_eye_movement_track(
                window.samples,
                signal.sampling_rate_hz,
                channel_name,
                session_id,
                manifest.recording.start_time,
                analysis,
            )
            channel_dir = derived_root / session_id / _slug(channel_name)
            channel_dir.mkdir(parents=True, exist_ok=True)
            filtered_path = channel_dir / "filtered_eog.f32"
            np.asarray(track.filtered_signal_uv, dtype="<f4").tofile(filtered_path)
            feature_rows = [
                {
                    "dataset_id": manifest.dataset.id,
                    "subject_id": manifest.session.subject_id,
                    "recording_id": session_id,
                    **feature.to_dict(),
                }
                for feature in track.features
            ]
            _write_csv(channel_dir / "feature_windows.csv", feature_rows)
            event_rows = []
            for event in track.events:
                candidate_id = f"{session_id}:{_slug(channel_name)}:{event.event_id}"
                primary_stage = assign_event_stage(
                    event.timestamp, primary_annotations, unknown_label="UNKNOWN"
                )
                row = {
                    "candidate_id": candidate_id,
                    "detector_event_id": event.event_id,
                    "dataset_id": manifest.dataset.id,
                    "dataset_version": manifest.dataset.version,
                    "subject_id": manifest.session.subject_id,
                    "recording_id": session_id,
                    "source_channel": channel_name,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                    **event.to_dict(),
                    **_event_morphology(event, track.features),
                    "raw_stage_label": primary_stage["raw_label"],
                    "normalized_stage": primary_stage["normalized_label"],
                    "scoring_standard": primary_stage["scoring_standard"],
                    "agreement_class": "single_channel",
                    "contract_sha256": contract_hash,
                }
                for scorer in requested.get("scorers", []):
                    assignment = assign_event_stage(
                        event.timestamp,
                        annotations[f"scorer_{scorer}"],
                        unknown_label="UNKNOWN",
                    )
                    row[f"scorer_{scorer}_raw_stage"] = assignment["raw_label"]
                    row[f"scorer_{scorer}_normalized_stage"] = assignment["normalized_label"]
                event_rows.append(row)
            recording_events[channel_name] = event_rows
            all_events.extend(event_rows)
            valid_duration_s = min(
                manifest.recording.duration_seconds,
                track.accepted_windows * step_s,
            )
            summary_row = {
                "dataset_id": manifest.dataset.id,
                "subject_id": manifest.session.subject_id,
                "recording_id": session_id,
                "source_channel": channel_name,
                "canonical_role": signal.canonical_role.value,
                "sampling_rate_hz": signal.sampling_rate_hz,
                "recording_duration_s": manifest.recording.duration_seconds,
                "valid_analysis_duration_s": valid_duration_s,
                "coverage_start_s": track.coverage_start_s,
                "coverage_end_s": track.coverage_end_s,
                "feature_windows": len(track.features),
                "accepted_windows": track.accepted_windows,
                "rejected_windows": track.rejected_windows,
                "rejection_reasons_json": json.dumps(track.rejection_reasons, sort_keys=True),
                "candidate_count": len(event_rows),
                "candidate_events_per_valid_hour": (
                    len(event_rows) * 3600.0 / valid_duration_s if valid_duration_s else None
                ),
                "median_absolute_candidate_amplitude_uv": (
                    float(np.median([abs(float(row["amplitude_uv"])) for row in event_rows]))
                    if event_rows
                    else None
                ),
                "median_candidate_confidence": (
                    float(np.median([float(row["confidence"]) for row in event_rows]))
                    if event_rows
                    else None
                ),
                "primary_matched_event_fraction": None,
                "detector_version": analysis["eye_movement"]["feature_version"],
                "contract_sha256": contract_hash,
                "filtered_path": _relative(filtered_path, output_root),
            }
            summary_rows.append(summary_row)
            channel_metadata[channel_name] = summary_row
            counts = Counter(str(row["normalized_stage"]) for row in event_rows)
            for stage in stages:
                minutes = exposure_by_source["primary"][stage] / 60.0
                stage_rows.append(
                    {
                        "dataset_id": manifest.dataset.id,
                        "subject_id": manifest.session.subject_id,
                        "recording_id": session_id,
                        "source_channel": channel_name,
                        "annotation_source": "primary",
                        "stage": stage,
                        "stage_minutes": minutes,
                        "candidate_count": counts[stage],
                        "candidate_events_per_minute": (
                            counts[stage] / minutes if minutes > 0 else None
                        ),
                    }
                )
            (channel_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        **summary_row,
                        "feature_version": analysis["eye_movement"]["feature_version"],
                        "contract_sha256": contract_hash,
                        "quality": dict(track.rejection_reasons),
                        "filtered_signal": {
                            "dtype": "<f4",
                            "sample_count": len(track.filtered_signal_uv),
                            "sampling_rate_hz": signal.sampling_rate_hz,
                            "path": filtered_path.name,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        channel_names = list(requested["channels"])
        primary_tolerance = float(validation["event_matching"]["primary_tolerance_s"])
        if len(channel_names) == 2:
            events_a = recording_events[channel_names[0]]
            events_b = recording_events[channel_names[1]]
            primary_matches = match_events(events_a, events_b, primary_tolerance)
            matched_ids = {
                candidate_id
                for match in primary_matches
                for candidate_id in (match.event_a_id, match.event_b_id)
            }
            for row in (*events_a, *events_b):
                row["agreement_class"] = (
                    "matched_dual_eog" if row["candidate_id"] in matched_ids else "channel_only"
                )
            channel_metadata[channel_names[0]]["primary_matched_event_fraction"] = (
                len(primary_matches) / len(events_a) if events_a else None
            )
            channel_metadata[channel_names[1]]["primary_matched_event_fraction"] = (
                len(primary_matches) / len(events_b) if events_b else None
            )
            for tolerance in validation["event_matching"]["sensitivity_tolerances_s"]:
                matches = match_events(events_a, events_b, float(tolerance))
                differences = [match.absolute_difference_s for match in matches]
                q1, median, q3 = _quantiles(differences)
                agreement_rows.append(
                    {
                        "dataset_id": manifest.dataset.id,
                        "subject_id": manifest.session.subject_id,
                        "recording_id": session_id,
                        "channel_a": channel_names[0],
                        "channel_b": channel_names[1],
                        "tolerance_s": tolerance,
                        "channel_a_events": len(events_a),
                        "channel_b_events": len(events_b),
                        "matched_events": len(matches),
                        "channel_a_only": len(events_a) - len(matches),
                        "channel_b_only": len(events_b) - len(matches),
                        "matched_proportion": (
                            len(matches) / max(len(events_a), len(events_b))
                            if max(len(events_a), len(events_b))
                            else None
                        ),
                        "timing_difference_median_s": median,
                        "timing_difference_q1_s": q1,
                        "timing_difference_q3_s": q3,
                    }
                )

        if requested.get("scorers"):
            scorer_one = annotations["scorer_1"]
            scorer_two = annotations["scorer_2"]
            scorer_two_by_start = {float(item["start_seconds"]): item for item in scorer_two}
            epoch_pairs = Counter()
            epoch_total = 0
            epoch_same = 0
            epoch_same_raw = 0
            for item in scorer_one:
                peer = scorer_two_by_start.get(float(item["start_seconds"]))
                if peer is None:
                    continue
                raw_stage_one = str(item["raw_label"])
                stage_one = str(item["normalized_label"])
                raw_stage_two = str(peer["raw_label"])
                stage_two = str(peer["normalized_label"])
                epoch_pairs[(raw_stage_one, stage_one, raw_stage_two, stage_two)] += 1
                epoch_total += 1
                epoch_same += int(stage_one == stage_two)
                epoch_same_raw += int(raw_stage_one == raw_stage_two)
            for (
                raw_stage_one,
                stage_one,
                raw_stage_two,
                stage_two,
            ), count in sorted(epoch_pairs.items()):
                scorer_rows.append(
                    {
                        "dataset_id": manifest.dataset.id,
                        "subject_id": manifest.session.subject_id,
                        "recording_id": session_id,
                        "source_channel": "all_epochs",
                        "scope": "epoch",
                        "scorer_1_raw_stage": raw_stage_one,
                        "scorer_1_stage": stage_one,
                        "scorer_2_raw_stage": raw_stage_two,
                        "scorer_2_stage": stage_two,
                        "count": count,
                        "same_stage": stage_one == stage_two,
                        "same_raw_stage": raw_stage_one == raw_stage_two,
                        "scope_total": epoch_total,
                        "scope_same_stage": epoch_same,
                        "scope_same_raw_stage": epoch_same_raw,
                    }
                )
            for channel_name, rows in recording_events.items():
                pairs = Counter(
                    (
                        str(row["scorer_1_raw_stage"]),
                        str(row["scorer_1_normalized_stage"]),
                        str(row["scorer_2_raw_stage"]),
                        str(row["scorer_2_normalized_stage"]),
                    )
                    for row in rows
                )
                same = sum(
                    count
                    for (_, stage_one, _, stage_two), count in pairs.items()
                    if stage_one == stage_two
                )
                same_raw = sum(
                    count
                    for (raw_stage_one, _, raw_stage_two, _), count in pairs.items()
                    if raw_stage_one == raw_stage_two
                )
                for (
                    raw_stage_one,
                    stage_one,
                    raw_stage_two,
                    stage_two,
                ), count in sorted(pairs.items()):
                    scorer_rows.append(
                        {
                            "dataset_id": manifest.dataset.id,
                            "subject_id": manifest.session.subject_id,
                            "recording_id": session_id,
                            "source_channel": channel_name,
                            "scope": "candidate",
                            "scorer_1_raw_stage": raw_stage_one,
                            "scorer_1_stage": stage_one,
                            "scorer_2_raw_stage": raw_stage_two,
                            "scorer_2_stage": stage_two,
                            "count": count,
                            "same_stage": stage_one == stage_two,
                            "same_raw_stage": raw_stage_one == raw_stage_two,
                            "scope_total": len(rows),
                            "scope_same_stage": same,
                            "scope_same_raw_stage": same_raw,
                        }
                    )
                for scorer in requested["scorers"]:
                    counts = Counter(str(row[f"scorer_{scorer}_normalized_stage"]) for row in rows)
                    for stage in stages:
                        minutes = exposure_by_source[f"scorer_{scorer}"][stage] / 60.0
                        stage_rows.append(
                            {
                                "dataset_id": manifest.dataset.id,
                                "subject_id": manifest.session.subject_id,
                                "recording_id": session_id,
                                "source_channel": channel_name,
                                "annotation_source": f"scorer_{scorer}",
                                "stage": stage,
                                "stage_minutes": minutes,
                                "candidate_count": counts[stage],
                                "candidate_events_per_minute": (
                                    counts[stage] / minutes if minutes > 0 else None
                                ),
                            }
                        )
        for channel_name, rows in recording_events.items():
            channel_dir = derived_root / session_id / _slug(channel_name)
            _write_csv(channel_dir / "candidate_events.csv", rows)
            metadata_path = channel_dir / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["primary_matched_event_fraction"] = channel_metadata[channel_name][
                "primary_matched_event_fraction"
            ]
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        recording_context[session_id] = {
            "dataset_id": manifest.dataset.id,
            "subject_id": manifest.session.subject_id,
            "recording_id": session_id,
            "duration_s": manifest.recording.duration_seconds,
            "channels": channel_names,
            "annotations": primary_annotations,
            "events": [row for rows in recording_events.values() for row in rows],
            "channel_metadata": channel_metadata,
        }

    # Agreement class is added after channel rows were initially copied into all_events.
    event_lookup = {
        row["candidate_id"]: row
        for context in recording_context.values()
        for row in context["events"]
    }
    all_events = [event_lookup[row["candidate_id"]] for row in all_events]
    candidate_sample = []
    seed = int(validation["qc_sampling"]["random_seed"])
    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in all_events:
        by_dataset[str(event["dataset_id"])].append(event)
    for dataset_index, (dataset_id, events) in enumerate(sorted(by_dataset.items())):
        selected = deterministic_stratified_sample(
            events,
            target=int(validation["qc_sampling"]["candidate_target_per_dataset"]),
            seed=seed + dataset_index,
            stratum=lambda row: (
                str(row["normalized_stage"]),
                str(row["agreement_class"]),
            ),
            identity=lambda row: str(row["candidate_id"]),
        )
        for sequence, row in enumerate(selected, start=1):
            candidate_sample.append(
                {
                    "review_id": f"candidate:{dataset_id}:{sequence:03d}",
                    "sample_kind": "candidate",
                    **row,
                }
            )

    control_sample = []
    target = int(validation["qc_sampling"]["control_target_per_major_stage_per_dataset"])
    for dataset_index, dataset_id in enumerate(sorted(by_dataset)):
        contexts = [
            context for context in recording_context.values() if context["dataset_id"] == dataset_id
        ]
        for stage_index, stage in enumerate(validation["qc_sampling"]["control_major_stages"]):
            pool = []
            for recording_index, context in enumerate(contexts):
                controls = build_control_sample(
                    context["annotations"],
                    (row["timestamp"] for row in context["events"]),
                    dataset_id=dataset_id,
                    stage=stage,
                    target=target,
                    seed=seed + dataset_index * 100 + stage_index * 10 + recording_index,
                    window_s=float(validation["qc_sampling"]["control_window_s"]),
                    exclusion_s=float(validation["qc_sampling"]["control_event_exclusion_s"]),
                    minimum_separation_s=float(
                        validation["qc_sampling"]["control_minimum_separation_s"]
                    ),
                )
                for row in controls:
                    pool.append({**row, **context})
            selected = deterministic_stratified_sample(
                pool,
                target=target,
                seed=seed + dataset_index * 1000 + stage_index,
                stratum=lambda row: (str(row["recording_id"]),),
                identity=lambda row: f"{row['recording_id']}:{row['center_s']}",
            )
            for sequence, row in enumerate(selected, start=1):
                control_sample.append(
                    {
                        "review_id": f"control:{dataset_id}:{stage}:{sequence:03d}",
                        "sample_kind": "control",
                        "dataset_id": dataset_id,
                        "subject_id": row["subject_id"],
                        "recording_id": row["recording_id"],
                        "source_channel": "all_native_eog",
                        "candidate_id": "",
                        "timestamp": row["center_s"],
                        "window_start_s": row["start_s"],
                        "window_end_s": row["end_s"],
                        "normalized_stage": stage,
                        "agreement_class": "non_candidate_control",
                    }
                )

    csv_outputs = validation["csv_outputs"]
    _write_csv(output_root / csv_outputs["full_night_summary"], summary_rows)
    _write_csv(output_root / csv_outputs["channel_agreement"], agreement_rows)
    _write_csv(output_root / csv_outputs["stage_distribution"], stage_rows)
    _write_csv(output_root / csv_outputs["candidate_review_sample"], candidate_sample)
    _write_csv(output_root / csv_outputs["control_review_sample"], control_sample)
    _write_csv(output_root / csv_outputs["scorer_disagreement"], scorer_rows)
    summary = {
        "schema_version": "dreamcore.eog_validation.summary.v1",
        "validation_version": validation["validation_version"],
        "contract_sha256": contract_hash,
        "run_started_at": run_started,
        "run_completed_at": datetime.now(UTC).isoformat(),
        "detector_parameters_frozen": True,
        "thresholds_tuned": False,
        "recording_count": len(validation["selected_recordings"]),
        "channel_count": len(summary_rows),
        "candidate_count": len(all_events),
        "candidate_review_sample_count": len(candidate_sample),
        "control_review_sample_count": len(control_sample),
        "manual_review_status": "pending",
        "full_night_summary": summary_rows,
        "channel_agreement": agreement_rows,
        "artifacts": {key: value for key, value in csv_outputs.items()},
    }
    (output_root / validation["summary_filename"]).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _update_manifests(
        project_root,
        validation,
        summary_rows,
        contract_hash,
        output_root,
    )
    return summary


def _update_manifests(
    project_root: Path,
    validation: Mapping[str, Any],
    summary_rows: Sequence[Mapping[str, Any]],
    contract_hash: str,
    output_root: Path,
) -> None:
    rows_by_session: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in summary_rows:
        rows_by_session[str(row["recording_id"])].append(row)
    repository = SessionPackageRepository(project_root / validation["session_package_root"])
    for session_id, rows in rows_by_session.items():
        adapter = _find_adapter(repository, session_id)
        manifest_path = adapter.get_manifest_path(session_id)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["derived"]["eog_validation_v1"] = {
            "available": True,
            "source": "derived",
            "derived_by": "dreamcore-eog-validation-v1",
            "version": validation["validation_version"],
            "metadata": {
                "contract_sha256": contract_hash,
                "channels": [row["source_channel"] for row in rows],
                "result_root": _relative(output_root, manifest_path.parent),
                "detector_parameters_frozen": True,
                "manual_review_status": "pending",
            },
        }
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
