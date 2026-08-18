"""Build real Sleep-EDF EOG features and deterministic sonification controls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from dreamcore.config import load_config
from dreamcore.data.reader import load_edf
from dreamcore.datasets.models import parse_session_manifest
from dreamcore.eye_movement import discover_eog_channels, extract_eye_movement_track
from dreamcore.sonification import SonificationMapper


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Config section {key!r} must be a mapping")
    return value


def _relative_path(target: Path, manifest_path: Path) -> str:
    return os.path.relpath(target.resolve(), manifest_path.parent.resolve())


def _fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "size_bytes": stat.st_size,
        "modified_time_ns": stat.st_mtime_ns,
    }


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as input_file:
        return [dict(row) for row in csv.DictReader(input_file)]


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to create empty artifact: {path}")
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_indexed_artifacts(
    path: Path,
    metrics: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    """Atomically build a recording-relative time index for bounded replay reads."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.building")
    if temporary.exists():
        temporary.unlink()
    with sqlite3.connect(temporary) as database:
        database.execute(
            """
            CREATE TABLE derived_rows (
                metric TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                window_start_s REAL NOT NULL,
                window_end_s REAL NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (metric, sequence)
            )
            """
        )
        for metric, rows in metrics.items():
            database.executemany(
                "INSERT INTO derived_rows VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        metric,
                        sequence,
                        float(row.get("window_start_s", row.get("timestamp", 0.0))),
                        float(
                            row.get(
                                "window_end_s",
                                row.get("timestamp", row.get("window_start_s", 0.0)),
                            )
                        ),
                        json.dumps(row, sort_keys=True, allow_nan=False),
                    )
                    for sequence, row in enumerate(rows)
                ),
            )
        database.execute(
            "CREATE INDEX derived_rows_time ON derived_rows(metric, window_end_s, window_start_s)"
        )
    os.replace(temporary, path)


def _coverage(
    start_s: float | None,
    end_s: float | None,
    *,
    window_s: float,
    step_s: float,
    row_count: int,
    source_channel: str,
) -> dict[str, Any]:
    return {
        "coverage_start_s": start_s,
        "coverage_end_s": end_s,
        "window_s": window_s,
        "step_s": step_s,
        "timestamp_semantics": "window_end",
        "timestamp_unit": "seconds",
        "time_reference": "recording_relative",
        "row_count": row_count,
        "source_channel": source_channel,
    }


def _update_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    psg_path: Path,
    source_channel: str,
    sampling_rate_hz: float,
    sample_count: int,
    recording_start_time: str | None,
    features_path: Path,
    events_path: Path,
    controls_path: Path,
    filtered_path: Path,
    indexed_path: Path,
    summary_path: Path,
    feature_coverage: Mapping[str, Any],
    event_count: int,
    control_coverages: Mapping[str, Any],
    analysis: Mapping[str, Any],
    mapper_metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    eye = _section(config, "eye_movement")
    viewer_config = _section(_section(eye, "session_package"), "viewer")
    alpha_viewer = (
        manifest.get("derived", {}).get("alpha_power", {}).get("metadata", {}).get("viewer", {})
    )
    replay = dict(alpha_viewer.get("replay", {}))
    viewer = {
        "default_start_s": float(viewer_config["default_start_s"]),
        "default_time_s": float(viewer_config["default_time_s"]),
        "default_window_duration_s": float(viewer_config["default_window_duration_s"]),
        "window_duration_options_s": [
            float(value) for value in viewer_config["window_duration_options_s"]
        ],
        "display_max_points_per_signal": int(viewer_config["display_max_points_per_signal"]),
        "feature_timestamp_semantics": str(viewer_config["feature_timestamp_semantics"]),
        "activity_jump_time_s": float(viewer_config["activity_jump_time_s"]),
        "stage_jump_time_s": alpha_viewer.get("stage_jump_time_s"),
        "replay": replay,
        "audio": dict(_section(_section(config, "sonification"), "audio")),
        "baseline_controls": dict(_section(_section(config, "sonification"), "baseline")),
    }
    storage_common = {
        "source_file_fingerprint": _fingerprint(psg_path),
        "created_at": created_at,
        "artifact_schema_version": "dreamcore.eye_movement_feature.v1",
    }
    signals = [
        signal
        for signal in manifest["signals"]
        if signal.get("id") not in {"eog-1", "eog-filtered-1"}
    ]
    tolerance = float(_section(config, "data")["sampling_rate_tolerance_hz"])
    signals.extend(
        [
            {
                "id": "eog-1",
                "modality": "eog",
                "channel_name": source_channel,
                "unit": "uV",
                "sampling_rate_hz": sampling_rate_hz,
                "source": "raw",
                "available": True,
                "metadata": {
                    "notice": "REAL PUBLIC SLEEP-EDF EOG",
                    "storage": {
                        "kind": "edf",
                        "path": _relative_path(psg_path, manifest_path),
                        "channel_name": source_channel,
                        "scale_to_unit": float(eye["input_scale_to_uv"]),
                        "sampling_rate_tolerance_hz": tolerance,
                    },
                    "coverage_start_s": 0.0,
                    "coverage_end_s": sample_count / sampling_rate_hz,
                },
            },
            {
                "id": "eog-filtered-1",
                "modality": "eog",
                "channel_name": f"{source_channel} · filtered",
                "unit": "uV",
                "sampling_rate_hz": sampling_rate_hz,
                "source": "derived",
                "available": True,
                "metadata": {
                    "source_channel": source_channel,
                    "feature_version": str(eye["feature_version"]),
                    "processing": dict(_section(eye, "filtering")),
                    "storage": {
                        "kind": "float32_binary",
                        "path": _relative_path(filtered_path, manifest_path),
                        "dtype": "<f4",
                        "sample_count": sample_count,
                    },
                    "coverage_start_s": 0.0,
                    "coverage_end_s": sample_count / sampling_rate_hz,
                },
            },
        ]
    )
    manifest["signals"] = signals
    manifest["recording"]["start_time"] = recording_start_time

    feature_descriptor = {
        "available": True,
        "source": "derived",
        "derived_by": "dreamcore-eye-movement-classical-v1",
        "version": str(eye["feature_version"]),
        "metadata": {
            **storage_common,
            "storage": {
                "kind": "sqlite_rows",
                "path": _relative_path(indexed_path, manifest_path),
                "metric": "eye_movement_activity_v1",
            },
            "audit_export": {
                "kind": "csv",
                "path": _relative_path(features_path, manifest_path),
            },
            "coverage": dict(feature_coverage),
            "analysis": dict(analysis),
            "viewer": viewer,
            "processing": {
                "filtering": dict(_section(eye, "filtering")),
                "windowing": dict(_section(eye, "windowing")),
                "quality": dict(_section(eye, "quality")),
                "normalization": dict(_section(eye, "normalization")),
                "local_baseline": dict(_section(eye, "local_baseline")),
                "stage_gating": False,
            },
        },
    }
    manifest["derived"]["eye_movement_activity_v1"] = feature_descriptor
    manifest["derived"]["eye_movement_events_v1"] = {
        "available": True,
        "source": "derived",
        "derived_by": "dreamcore-eye-movement-classical-v1",
        "version": str(eye["feature_version"]),
        "metadata": {
            **storage_common,
            "storage": {
                "kind": "sqlite_rows",
                "path": _relative_path(indexed_path, manifest_path),
                "metric": "eye_movement_events_v1",
            },
            "audit_export": {
                "kind": "csv",
                "path": _relative_path(events_path, manifest_path),
            },
            "coverage": {**dict(feature_coverage), "row_count": event_count},
            "event_semantics": "Eye Movement Candidate; not REM or dream detection",
            "detector": dict(_section(eye, "event_detection")),
        },
    }
    manifest["derived"]["sonification_control_v1"] = {
        "available": True,
        "source": "derived",
        "derived_by": "dreamcore-sonification-mapper-v1",
        "version": str(_section(config, "sonification")["control_version"]),
        "metadata": {
            "artifact_schema_version": "dreamcore.sonification_control.v1",
            "created_at": created_at,
            "storage": {
                "kind": "sqlite_rows",
                "path": _relative_path(indexed_path, manifest_path),
                "metric": "sonification_control_v1",
            },
            "audit_export": {
                "kind": "csv",
                "path": _relative_path(controls_path, manifest_path),
            },
            "coverage_by_source": dict(control_coverages),
            "mapping": dict(mapper_metadata),
            "source_feature": "eye_movement_activity_v1",
            "default_source": "eye_movement",
            "viewer": viewer,
        },
    }
    manifest["derived"]["eye_movement_summary_v1"] = {
        "available": True,
        "source": "derived",
        "derived_by": "scripts/analyze_eye_movement_v1.py",
        "version": str(eye["feature_version"]),
        "metadata": {
            "storage": {"kind": "json", "path": _relative_path(summary_path, manifest_path)},
            "created_at": created_at,
        },
    }
    manifest["capabilities"].update(
        {
            "eog": {
                "status": "AVAILABLE",
                "source": "raw",
                "reason": f"Discovered from EDF metadata label {source_channel!r}",
            },
            "eye_movement_activity": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-eye-movement-classical-v1",
                "version": str(eye["feature_version"]),
            },
            "eye_movement_events": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-eye-movement-classical-v1",
                "version": str(eye["feature_version"]),
            },
            "sonification_controls": {
                "status": "AVAILABLE",
                "source": "derived",
                "derived_by": "dreamcore-sonification-mapper-v1",
                "version": str(_section(config, "sonification")["control_version"]),
            },
        }
    )
    manifest["provenance"]["imported_by"] = (
        "scripts/analyze_alpha_v1.py; scripts/analyze_eye_movement_v1.py"
    )
    manifest["provenance"]["notes"] = (
        "REAL PUBLIC EEG DATA AND EOG DATA; DERIVED EYE-MOVEMENT CANDIDATES AND ALPHA "
        "FEATURES; SONIFICATION CONTROLS ARE EXPLORATORY; SIMULATED STIMULATION EVENTS "
        "AND INTERVENTION MARKERS NEVER MODIFY OBSERVED SIGNALS"
    )
    return manifest


def run_eye_movement_analysis(
    psg_path: Path,
    hypnogram_path: Path,
    config: Mapping[str, Any],
    *,
    manifest_output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate full-record EOG features and extend the existing session package."""

    eye = _section(config, "eye_movement")
    output = _section(eye, "output")
    package = _section(eye, "session_package")
    manifest_path = manifest_output_path or Path(str(package["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["session"]["session_id"] != str(package["session_id"]):
        raise ValueError("Configured session ID differs from the existing Session Package")

    raw, _ = load_edf(psg_path, hypnogram_path, config)
    channels = discover_eog_channels(raw.ch_names, raw.get_channel_types(), config)
    if not channels:
        raise ValueError(
            "No EOG channel matched configured metadata rules; refusing EEG substitution"
        )
    if len(channels) != 1:
        raise ValueError(f"Eye Movement V1 requires one unambiguous EOG channel: {channels}")
    source_channel = channels[0]
    sampling_rate_hz = float(raw.info["sfreq"])
    signal_uv = raw.get_data(picks=[source_channel])[0] * float(eye["input_scale_to_uv"])
    meas_date = raw.info.get("meas_date")
    recording_start_time = meas_date.isoformat() if meas_date is not None else None
    track = extract_eye_movement_track(
        signal_uv,
        sampling_rate_hz,
        source_channel,
        str(package["session_id"]),
        recording_start_time,
        config,
    )
    if not track.features:
        raise ValueError("No eye-movement feature rows were generated")

    features_path = Path(str(output["features_csv"]))
    events_path = Path(str(output["events_csv"]))
    filtered_path = Path(str(output["filtered_signal_binary"]))
    indexed_path = Path(str(output["indexed_artifact_database"]))
    summary_path = Path(str(output["summary_json"]))
    controls_path = Path(str(_section(_section(config, "sonification"), "output")["controls_csv"]))
    feature_rows = [feature.to_dict() for feature in track.features]
    event_rows = [event.to_dict() for event in track.events]
    _write_rows(features_path, feature_rows)
    _write_rows(events_path, event_rows)
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(track.filtered_signal_uv, dtype="<f4").tofile(filtered_path)

    mapper = SonificationMapper(config)
    eye_controls = mapper.eye_movement_frames(
        str(package["session_id"]), track.features, track.events
    )
    alpha_rows = _read_csv(Path(str(_section(_section(config, "alpha"), "output")["features_csv"])))
    alpha_controls = mapper.alpha_comparison_frames(str(package["session_id"]), alpha_rows)
    control_rows = [frame.to_dict() for frame in (*eye_controls, *alpha_controls)]
    control_rows.sort(key=lambda row: (float(row["window_end_s"]), str(row["source"])))
    _write_rows(controls_path, control_rows)
    _write_indexed_artifacts(
        indexed_path,
        {
            "eye_movement_activity_v1": feature_rows,
            "eye_movement_events_v1": event_rows,
            "sonification_control_v1": control_rows,
        },
    )

    windowing = _section(eye, "windowing")
    feature_coverage = _coverage(
        track.coverage_start_s,
        track.coverage_end_s,
        window_s=float(windowing["analysis_window_s"]),
        step_s=float(windowing["step_s"]),
        row_count=len(track.features),
        source_channel=source_channel,
    )
    control_coverages = {
        "eye_movement": {
            "coverage_start_s": eye_controls[0].window_end_s if eye_controls else None,
            "coverage_end_s": eye_controls[-1].window_end_s if eye_controls else None,
            "row_count": len(eye_controls),
            "source_feature": "eye_movement_activity_v1",
        },
        "alpha": {
            "coverage_start_s": alpha_controls[0].window_end_s if alpha_controls else None,
            "coverage_end_s": alpha_controls[-1].window_end_s if alpha_controls else None,
            "row_count": len(alpha_controls),
            "source_feature": "relative_alpha_power",
        },
    }
    analysis = {
        "raw_sample_count": int(signal_uv.size),
        "valid_sample_count": int(np.isfinite(signal_uv).sum()),
        "attempted_windows": track.attempted_windows,
        "accepted_windows": track.accepted_windows,
        "rejected_windows": track.rejected_windows,
        "rejection_reasons": dict(track.rejection_reasons),
        "feature_row_count": len(track.features),
        "event_count": len(track.events),
        "first_feature_time_s": track.coverage_start_s,
        "last_feature_time_s": track.coverage_end_s,
        "stage_gating": False,
        "source_channel_dictionary": {
            name: channel_type
            for name, channel_type in zip(raw.ch_names, raw.get_channel_types(), strict=True)
        },
        "selected_source_channel": source_channel,
    }
    created_at = datetime.now(UTC).isoformat()
    summary = {
        "dataset": manifest["dataset"],
        "session": manifest["session"],
        "recording": {
            "start_time": recording_start_time,
            "duration_seconds": signal_uv.size / sampling_rate_hz,
            "sampling_rate_hz": sampling_rate_hz,
        },
        "source": {
            "psg": psg_path.name,
            "hypnogram": hypnogram_path.name,
            "fingerprint": _fingerprint(psg_path),
            "channel": source_channel,
        },
        "analysis": analysis,
        "coverage": feature_coverage,
        "processing": dict(eye),
        "sonification": {
            "mapping": mapper.metadata(),
            "coverage_by_source": control_coverages,
            "control_row_count": len(control_rows),
        },
        "scientific_boundaries": [
            "Eye Movement Candidate does not mean REM or dream detection.",
            "A single differential EOG channel does not establish eye direction.",
            "Sonification mappings are exploratory and not therapeutic validation.",
        ],
        "created_at": created_at,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as output_file:
        json.dump(summary, output_file, indent=int(output["json_indent"]), allow_nan=False)
        output_file.write("\n")
    updated = _update_manifest(
        manifest,
        manifest_path=manifest_path,
        psg_path=psg_path,
        source_channel=source_channel,
        sampling_rate_hz=sampling_rate_hz,
        sample_count=int(signal_uv.size),
        recording_start_time=recording_start_time,
        features_path=features_path,
        events_path=events_path,
        controls_path=controls_path,
        filtered_path=filtered_path,
        indexed_path=indexed_path,
        summary_path=summary_path,
        feature_coverage=feature_coverage,
        event_count=len(track.events),
        control_coverages=control_coverages,
        analysis=analysis,
        mapper_metadata=mapper.metadata(),
        config=config,
        created_at=created_at,
    )
    parse_session_manifest(updated)
    with manifest_path.open("w", encoding="utf-8") as output_file:
        json.dump(updated, output_file, indent=2, sort_keys=True, allow_nan=False)
        output_file.write("\n")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--psg", type=Path, required=True)
    parser.add_argument("--hypnogram", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = run_eye_movement_analysis(
        args.psg,
        args.hypnogram,
        load_config(args.config),
        manifest_output_path=args.manifest_output,
    )
    print(f"EOG source: {summary['source']['channel']}")
    print(f"Feature rows: {summary['analysis']['feature_row_count']}")
    print(f"Candidate events: {summary['analysis']['event_count']}")
    print(
        "Coverage: "
        f"{summary['coverage']['coverage_start_s']}–{summary['coverage']['coverage_end_s']} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
