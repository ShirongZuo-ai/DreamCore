"""Non-blocking, de-duplicated local analyses for the product Viewer."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import threading
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

import numpy as np

from dreamcore.alpha.features import extract_alpha_features
from dreamcore.alpha.trend import estimate_alpha_trend
from dreamcore.datasets.models import CanonicalSignalRole, ContentDescriptor, ProvenanceClass
from dreamcore.datasets.registry import DatasetRegistry
from dreamcore.eye_movement.features import extract_eye_movement_track
from dreamcore.k_complex.annotations import KComplexAnnotationStore
from dreamcore.k_complex.detector import detect_k_complexes, segment_stage_bouts
from dreamcore.k_complex.verifier import load_morphology_b1_verifier
from dreamcore.wake_music.mapping import (
    WakeWindowUnavailableError,
    build_profile,
    select_wake_window,
    summarize_physiology,
)

PRODUCT_ANALYSIS_API_VERSION = "dreamcore.automatic_analysis.v1"
FEATURE_ALPHA = "alpha"
FEATURE_EYE_MOVEMENT = "eye_movement"
FEATURE_WAKE_PROFILE = "wake_music_profile"
FEATURE_K_COMPLEX = "k_complex"
FEATURES = (FEATURE_EYE_MOVEMENT, FEATURE_ALPHA, FEATURE_K_COMPLEX, FEATURE_WAKE_PROFILE)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _safe(value: str) -> str:
    if not value or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in value
    ):
        raise ValueError("unsafe analysis identifier")
    return value


def _write_json(path: Path, value: Mapping[str, Any], indent: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=indent, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = list(rows[0]) if rows else []
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        if fieldnames:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def _coerce_row(row: Mapping[str, str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        stripped = value.strip()
        if not stripped:
            output[key] = None
        elif stripped.casefold() in {"true", "false"}:
            output[key] = stripped.casefold() == "true"
        else:
            try:
                number = float(stripped)
            except ValueError:
                output[key] = value
            else:
                output[key] = number if math.isfinite(number) else None
    return output


class FeatureUnavailableError(RuntimeError):
    """The recording genuinely lacks a source required by a local feature."""


class AutomaticAnalysisManager:
    """Ensure local derived products without blocking the initial HTTP response."""

    def __init__(
        self,
        project_root: Path,
        registry: DatasetRegistry,
        config: Mapping[str, Any],
    ) -> None:
        self.project_root = Path(project_root)
        self.registry = registry
        self.full_config = config
        self.config = config["automatic_analysis"]
        self.cache_root = self.project_root / str(self.config["cache_root"])
        self._executor = ThreadPoolExecutor(
            max_workers=int(self.config["maximum_workers"]),
            thread_name_prefix="dreamcore-analysis",
        )
        self._lock = threading.RLock()
        self._jobs: dict[tuple[str, str, str], Future[dict[str, Any]]] = {}
        self._states: dict[tuple[str, str], dict[str, Any]] = {}
        self._submissions: Counter[tuple[str, str]] = Counter()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def ensure_session(self, session_id: str) -> dict[str, Any]:
        manifest = self.registry.get_session_by_id(session_id)
        for feature in FEATURES:
            self._ensure_feature(manifest, feature)
        return self.status(session_id)

    def status(self, session_id: str) -> dict[str, Any]:
        manifest = self.registry.get_session_by_id(session_id)
        with self._lock:
            features = {
                feature: dict(
                    self._states.get(
                        (session_id, feature),
                        self._initial_state(manifest, feature),
                    )
                )
                for feature in FEATURES
            }
        return {
            "analysis_api_version": PRODUCT_ANALYSIS_API_VERSION,
            "session_id": session_id,
            "features": features,
            "poll_interval_ms": int(self.config["status_poll_interval_ms"]),
        }

    def submission_count(self, session_id: str, feature: str) -> int:
        with self._lock:
            return self._submissions[(session_id, feature)]

    def _initial_state(self, manifest, feature: str) -> dict[str, Any]:
        available = bool(self._source_signals(manifest, feature))
        if feature == FEATURE_WAKE_PROFILE:
            available = bool(self._source_signals(manifest, FEATURE_EYE_MOVEMENT))
        if feature == FEATURE_K_COMPLEX:
            annotation_type = str(self.config[feature]["stage_annotation_type"])
            descriptor = manifest.annotations.get(annotation_type)
            available = available and bool(descriptor and descriptor.available)
        return {
            "feature": feature,
            "state": "NOT_AVAILABLE" if not available else "ANALYZING",
            "summary": "Not available" if not available else "Analyzing...",
        }

    def _ensure_feature(self, manifest, feature: str) -> None:
        session_id = manifest.session.session_id
        sources = self._source_signals(
            manifest, FEATURE_EYE_MOVEMENT if feature == FEATURE_WAKE_PROFILE else feature
        )
        if not sources:
            with self._lock:
                self._states[(session_id, feature)] = self._initial_state(manifest, feature)
            return
        existing = self._existing_session_state(manifest, feature)
        if existing is not None:
            with self._lock:
                self._states[(session_id, feature)] = existing
            return
        if feature == FEATURE_WAKE_PROFILE:
            eye_state = self._states.get((session_id, FEATURE_EYE_MOVEMENT), {})
            if eye_state.get("state") == "ERROR":
                with self._lock:
                    self._states[(session_id, feature)] = {
                        "feature": feature,
                        "state": "ERROR",
                        "summary": "Error",
                    }
                return
            if eye_state.get("state") != "READY":
                with self._lock:
                    self._states[(session_id, feature)] = {
                        "feature": feature,
                        "state": "ANALYZING",
                        "summary": "Analyzing...",
                    }
                return
        identity = self._identity(manifest, feature, sources)
        cache_path = self._metadata_path(session_id, feature)
        cached = self._load_cache(cache_path, identity["cache_key"])
        if cached:
            with self._lock:
                self._states[(session_id, feature)] = self._ready_state(cached, cache_hit=True)
            return
        if feature == FEATURE_EYE_MOVEMENT:
            reused = self._validation_artifacts(manifest, sources, identity)
            if reused:
                metadata = self._finalize_output(
                    manifest,
                    feature,
                    identity,
                    reused,
                    duration_ms=0,
                )
                with self._lock:
                    current = self._load_cache(cache_path, identity["cache_key"])
                    if current is None:
                        _write_json(cache_path, metadata, int(self.config["json_indent"]))
                        current = metadata
                    self._states[(session_id, feature)] = self._ready_state(current, cache_hit=True)
                return
        key = (session_id, feature, identity["cache_key"])
        with self._lock:
            existing = self._jobs.get(key)
            # The completion callback owns removal. A Future can be done for a
            # short interval before that callback persists state; resubmitting
            # in that interval would violate identity-based de-duplication.
            if existing is not None:
                return
            self._states[(session_id, feature)] = {
                "feature": feature,
                "state": "ANALYZING",
                "summary": "Analyzing...",
                "started_at": _now(),
                "cache_key": identity["cache_key"],
            }
            self._submissions[(session_id, feature)] += 1
            future = self._executor.submit(self._run, manifest, feature, sources, identity)
            self._jobs[key] = future
            future.add_done_callback(
                lambda completed, job_key=key, path=cache_path: self._complete(
                    job_key, path, completed
                )
            )

    def _existing_session_state(self, manifest, feature: str) -> dict[str, Any] | None:
        if feature == FEATURE_ALPHA:
            descriptor = manifest.derived.get("alpha_power")
            if descriptor and descriptor.available:
                return {
                    "feature": feature,
                    "state": "READY",
                    "summary": "Ready",
                    "cache_hit": True,
                    "reuse_kind": "session_package_artifact",
                }
            return None
        if feature != FEATURE_EYE_MOVEMENT:
            return None
        activity = manifest.derived.get("eye_movement_activity_v1")
        events = manifest.derived.get("eye_movement_events_v1")
        expected_version = str(self.config[FEATURE_EYE_MOVEMENT]["algorithm_version"])
        if not activity or not events or not activity.available or not events.available:
            return None
        if activity.version != expected_version or events.version != expected_version:
            return None
        processing = activity.metadata.get("processing", {})
        detector = events.metadata.get("detector", {})
        eye = self.full_config["eye_movement"]
        if (
            any(
                processing.get(key) != eye[key]
                for key in ("filtering", "windowing", "quality", "normalization", "local_baseline")
            )
            or detector != eye["event_detection"]
        ):
            return None
        coverage = activity.metadata.get("coverage", {})
        if float(coverage.get("coverage_end_s", 0.0)) < manifest.recording.duration_seconds:
            return None
        count = int(activity.metadata.get("analysis", {}).get("event_count", 0))
        channel = str(coverage.get("source_channel", "EOG"))
        return {
            "feature": feature,
            "state": "READY",
            "summary": f"Ready · {count} {channel} detections",
            "cache_hit": True,
            "reuse_kind": "session_package_artifact",
            "channels": [{"channel": channel, "candidate_count": count}],
        }

    def _complete(
        self,
        key: tuple[str, str, str],
        cache_path: Path,
        future: Future[dict[str, Any]],
    ) -> None:
        session_id, feature, _ = key
        try:
            metadata = future.result()
            _write_json(cache_path, metadata, int(self.config["json_indent"]))
            state = self._ready_state(metadata, cache_hit=False)
        except FeatureUnavailableError:
            state = {"feature": feature, "state": "NOT_AVAILABLE", "summary": "Not available"}
        except Exception:
            state = {"feature": feature, "state": "ERROR", "summary": "Error"}
        with self._lock:
            self._states[(session_id, feature)] = state
            self._jobs.pop(key, None)

    def _run(self, manifest, feature: str, sources, identity) -> dict[str, Any]:
        started = monotonic()
        if feature == FEATURE_ALPHA:
            output = self._run_alpha(manifest, sources, identity)
        elif feature == FEATURE_EYE_MOVEMENT:
            output = self._run_eye_movement(manifest, sources, identity)
        elif feature == FEATURE_WAKE_PROFILE:
            output = self._run_wake_profile(manifest, identity)
        elif feature == FEATURE_K_COMPLEX:
            output = self._run_k_complex(manifest, sources, identity)
        else:  # pragma: no cover - registry boundary for future features
            raise ValueError(f"unsupported automatic feature {feature!r}")
        return self._finalize_output(
            manifest,
            feature,
            identity,
            output,
            duration_ms=round((monotonic() - started) * 1000),
        )

    def _finalize_output(
        self,
        manifest,
        feature: str,
        identity: Mapping[str, str],
        output: dict[str, Any],
        *,
        duration_ms: int,
    ) -> dict[str, Any]:
        output.update(
            {
                "schema_version": str(self.config["schema_version"]),
                "feature": feature,
                "session_id": manifest.session.session_id,
                "cache_key": identity["cache_key"],
                "configuration_hash": identity["configuration_hash"],
                "source_fingerprint": identity["source_fingerprint"],
                "algorithm_version": identity["algorithm_version"],
                "completed_at": _now(),
                "duration_ms": duration_ms,
            }
        )
        return output

    def _source_signals(self, manifest, feature: str):
        modality = "eeg" if feature in {FEATURE_ALPHA, FEATURE_K_COMPLEX} else "eog"
        signals = [
            signal
            for signal in manifest.signals
            if signal.available and signal.modality == modality
        ]
        feature_config = self.config[feature]
        if feature in {FEATURE_ALPHA, FEATURE_K_COMPLEX}:
            priorities = {
                CanonicalSignalRole(value): index
                for index, value in enumerate(feature_config["canonical_role_priority"])
            }
            signals.sort(
                key=lambda signal: (
                    priorities.get(signal.canonical_role, len(priorities)),
                    signal.id,
                )
            )
        return tuple(signals[: int(feature_config.get("maximum_channels", len(signals)))])

    def _identity(self, manifest, feature: str, sources) -> dict[str, str]:
        feature_config = dict(self.config[feature])
        algorithm_version = str(feature_config["algorithm_version"])
        if feature == FEATURE_ALPHA:
            algorithm_config = {"product": feature_config, "alpha": self.full_config["alpha"]}
        elif feature == FEATURE_EYE_MOVEMENT:
            algorithm_config = {
                key: self.full_config["eye_movement"][key]
                for key in (
                    "filtering",
                    "windowing",
                    "quality",
                    "normalization",
                    "local_baseline",
                    "event_detection",
                )
            }
        elif feature == FEATURE_WAKE_PROFILE:
            algorithm_config = {
                "product": feature_config,
                "wake_music": {
                    key: self.full_config["wake_music"][key]
                    for key in (
                        "profile_version",
                        "mapping_version",
                        "source_feature_metric",
                        "wake_window",
                        "mapping",
                        "constraints",
                        "styles",
                        "default_generation_seed",
                    )
                },
            }
        else:
            algorithm_config = {
                "product": feature_config,
                "detector": self.full_config["k_complex_v0"],
            }
        source = {
            "dataset": manifest.dataset.id,
            "dataset_version": manifest.dataset.version,
            "session": manifest.session.session_id,
            "duration_s": manifest.recording.duration_seconds,
            "signals": [
                {
                    "id": signal.id,
                    "channel": signal.channel_name,
                    "role": signal.canonical_role.value,
                    "rate": signal.sampling_rate_hz,
                    "unit": signal.unit,
                    "storage": signal.metadata.get("storage"),
                    "source_file": signal.metadata.get("source_file"),
                }
                for signal in sources
            ],
            "source_files": manifest.provenance.metadata.get("source_files", []),
        }
        configuration_hash = _hash(algorithm_config)
        source_fingerprint = _hash(source)
        return {
            "algorithm_version": algorithm_version,
            "configuration_hash": configuration_hash,
            "source_fingerprint": source_fingerprint,
            "cache_key": _hash(
                {
                    "product_cache_schema": self.config["schema_version"],
                    "session": manifest.session.session_id,
                    "algorithm_version": algorithm_version,
                    "configuration_hash": configuration_hash,
                    "source_fingerprint": source_fingerprint,
                }
            ),
        }

    def _run_eye_movement(self, manifest, sources, identity) -> dict[str, Any]:
        reused = self._validation_artifacts(manifest, sources, identity)
        if reused:
            return reused
        feature_rows: list[dict[str, Any]] = []
        event_rows: list[dict[str, Any]] = []
        channel_summary = []
        for signal in sources:
            window = self.registry.load_signal_window(
                manifest.session.session_id,
                signal.id,
                0.0,
                manifest.recording.duration_seconds,
            )
            track = extract_eye_movement_track(
                window.samples,
                signal.sampling_rate_hz,
                signal.channel_name,
                manifest.session.session_id,
                manifest.recording.start_time,
                self.full_config,
            )
            feature_rows.extend(item.to_dict() for item in track.features)
            event_rows.extend(item.to_dict() for item in track.events)
            channel_summary.append(
                {
                    "channel": signal.channel_name,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                    "feature_windows": len(track.features),
                    "candidate_count": len(track.events),
                    "accepted_windows": track.accepted_windows,
                    "rejected_windows": track.rejected_windows,
                }
            )
        directory = self._feature_directory(manifest.session.session_id, FEATURE_EYE_MOVEMENT)
        features_path = directory / "feature_windows.csv"
        events_path = directory / "candidate_events.csv"
        _write_csv(features_path, feature_rows)
        _write_csv(events_path, event_rows)
        coverage = self._eye_coverage(
            manifest.recording.duration_seconds,
            channel_summary,
            len(feature_rows),
        )
        return {
            "reuse_kind": "computed_product_cache",
            "artifacts": {"features": str(features_path), "events": str(events_path)},
            "channels": channel_summary,
            "coverage": coverage,
            "summary": self._eye_summary(channel_summary),
        }

    def _validation_artifacts(self, manifest, sources, identity) -> dict[str, Any] | None:
        config = self.config[FEATURE_EYE_MOVEMENT]
        contract_path = self.project_root / str(config["validation_contract"])
        root = (
            self.project_root
            / str(config["reusable_validation_root"])
            / manifest.session.session_id
        )
        if not contract_path.is_file() or not root.is_dir():
            return None
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        current_detector = {
            key: self.full_config["eye_movement"][key]
            for key in (
                "filtering",
                "windowing",
                "quality",
                "normalization",
                "local_baseline",
                "event_detection",
            )
        }
        if (
            contract.get("detector_version") != identity["algorithm_version"]
            or contract.get("detector_configuration") != current_detector
        ):
            return None
        expected = {signal.channel_name: signal for signal in sources}
        artifacts = []
        channel_summary = []
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            metadata_path = directory / "metadata.json"
            features_path = directory / "feature_windows.csv"
            events_path = directory / "candidate_events.csv"
            if not all(path.is_file() for path in (metadata_path, features_path, events_path)):
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            channel = str(metadata.get("source_channel"))
            signal = expected.get(channel)
            if (
                signal is None
                or metadata.get("detector_version") != identity["algorithm_version"]
                or float(metadata.get("sampling_rate_hz", 0.0)) != signal.sampling_rate_hz
                or float(metadata.get("coverage_end_s", 0.0))
                < manifest.recording.duration_seconds
                - float(self.full_config["eye_movement"]["windowing"]["step_s"])
            ):
                continue
            artifacts.append(
                {
                    "channel": channel,
                    "features": str(features_path),
                    "events": str(events_path),
                    "validation_metadata": str(metadata_path),
                }
            )
            channel_summary.append(
                {
                    "channel": channel,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                    "feature_windows": int(metadata.get("feature_windows", 0)),
                    "candidate_count": int(metadata.get("candidate_count", 0)),
                    "accepted_windows": int(metadata.get("accepted_windows", 0)),
                    "rejected_windows": int(metadata.get("rejected_windows", 0)),
                }
            )
        if set(expected) != {item["channel"] for item in artifacts}:
            return None
        coverage = self._eye_coverage(
            manifest.recording.duration_seconds,
            channel_summary,
            sum(item["feature_windows"] for item in channel_summary),
        )
        return {
            "reuse_kind": "compatible_eog_validation_reference",
            "validation_contract_sha256": contract.get("contract_sha256"),
            "artifacts": artifacts,
            "channels": channel_summary,
            "coverage": coverage,
            "summary": self._eye_summary(channel_summary),
        }

    def _eye_coverage(
        self,
        recording_duration_s: float,
        channels: list[dict[str, Any]],
        row_count: int,
    ) -> dict[str, Any]:
        windowing = self.full_config["eye_movement"]["windowing"]
        window_s = float(windowing["analysis_window_s"])
        return {
            "coverage_start_s": min(window_s, recording_duration_s),
            "coverage_end_s": recording_duration_s,
            "window_s": window_s,
            "step_s": float(windowing["step_s"]),
            "row_count": row_count,
            "source_channel": " / ".join(item["channel"] for item in channels),
            "time_reference": "recording_relative",
            "timestamp_semantics": "window_end",
            "timestamp_unit": "seconds",
        }

    @staticmethod
    def _eye_summary(channels: list[dict[str, Any]]) -> str:
        counts = " / ".join(
            f"{item['candidate_count']} {item['channel']} detections" for item in channels
        )
        return f"Ready · {counts}" if counts else "Ready"

    def _run_alpha(self, manifest, sources, identity) -> dict[str, Any]:
        configuration = deepcopy(self.full_config)
        product = self.config[FEATURE_ALPHA]
        rows: list[dict[str, Any]] = []
        channel_summary = []
        annotations = self.registry.load_annotations(
            manifest.session.session_id, str(product["stage_annotation_type"])
        )
        for signal in sources:
            scales = product["input_scale_to_uv_by_unit"]
            if signal.unit not in scales:
                raise FeatureUnavailableError("unsupported EEG unit")
            configuration["alpha"]["input_scale_to_uv"] = float(scales[signal.unit])
            window = self.registry.load_signal_window(
                manifest.session.session_id,
                signal.id,
                0.0,
                manifest.recording.duration_seconds,
            )
            values = np.asarray(window.samples, dtype=float)
            rate = signal.sampling_rate_hz
            window_s = float(product["analysis_window_s"])
            step_s = float(product["step_s"])
            window_samples = int(round(window_s * rate))
            step_samples = int(round(step_s * rate))
            channel_rows = []
            for start_sample in range(0, max(0, values.size - window_samples + 1), step_samples):
                start_s = start_sample / rate
                end_s = start_s + window_s
                feature = extract_alpha_features(
                    values[start_sample : start_sample + window_samples],
                    rate,
                    signal.channel_name,
                    start_s,
                    end_s,
                    self._stage_at(annotations, (start_s + end_s) / 2),
                    configuration,
                )
                row = feature.to_dict()
                quality = row.pop("signal_quality")
                row.update(
                    {
                        "signal_quality": "valid" if quality["valid"] else "invalid",
                        "signal_quality_score": quality["score"],
                        "signal_quality_reasons": ";".join(quality["reason_codes"]),
                        "window_iaf_hz": row["individual_alpha_frequency_hz"],
                        "window_iaf_confidence": row["iaf_confidence"],
                    }
                )
                channel_rows.append(row)
            trends = estimate_alpha_trend(
                [row["window_end_s"] for row in channel_rows],
                [row["relative_alpha_power"] for row in channel_rows],
                [row["signal_quality"] == "valid" for row in channel_rows],
                configuration,
            )
            for row, trend in zip(channel_rows, trends, strict=True):
                row.update(
                    {
                        "alpha_trend": trend.alpha_trend,
                        "alpha_trend_slope": trend.alpha_trend_slope,
                        "alpha_change_from_baseline": trend.alpha_change_from_baseline,
                        "drowsiness_score": None,
                        "state_confidence": trend.confidence,
                        "stimulation_demand": None,
                        "demand_available": False,
                        "ready_to_remove": False,
                        "feature_provenance": "derived",
                        "demand_provenance": "not_computed",
                    }
                )
            rows.extend(channel_rows)
            channel_summary.append(
                {
                    "channel": signal.channel_name,
                    "sampling_rate_hz": rate,
                    "feature_windows": len(channel_rows),
                    "valid_windows": sum(row["signal_quality"] == "valid" for row in channel_rows),
                }
            )
        if not rows:
            raise FeatureUnavailableError("recording is shorter than the configured Alpha window")
        alpha_profile = configuration["alpha"]["profiles"][configuration["alpha"]["active_profile"]]
        path = (
            self._feature_directory(manifest.session.session_id, FEATURE_ALPHA)
            / "alpha_features.csv"
        )
        _write_csv(path, rows)
        attempted_windows = sum(item["feature_windows"] for item in channel_summary)
        accepted_windows = sum(item["valid_windows"] for item in channel_summary)
        rejection_reasons = Counter(
            reason
            for row in rows
            if row["signal_quality"] != "valid"
            for reason in str(row["signal_quality_reasons"]).split(";")
            if reason
        )
        return {
            "reuse_kind": "computed_product_cache",
            "artifacts": {"features": str(path)},
            "channels": channel_summary,
            "analysis": {
                "time_reference": "recording_relative",
                "timestamp_field": "window_end_s",
                "timestamp_unit": "seconds",
                "evaluation_start_s": 0.0,
                "evaluation_end_s": manifest.recording.duration_seconds,
                "analysis_window_s": float(product["analysis_window_s"]),
                "step_s": float(product["step_s"]),
                "attempted_windows": attempted_windows,
                "accepted_windows": accepted_windows,
                "rejected_windows": attempted_windows - accepted_windows,
                "rejection_reasons": dict(sorted(rejection_reasons.items())),
                "feature_row_count": len(rows),
                "first_feature_time_s": min(float(row["window_end_s"]) for row in rows),
                "last_feature_time_s": max(float(row["window_end_s"]) for row in rows),
                "channels": [item["channel"] for item in channel_summary],
                "product_display_min_iaf_confidence": float(
                    alpha_profile["iaf"]["product_display_min_confidence"]
                ),
                "product_display_context_s": float(
                    self.full_config["alpha"]["history"]["trend_window_s"]
                ),
            },
            "summary": "Ready",
        }

    @staticmethod
    def _stage_at(annotations, timestamp: float) -> str:
        for annotation in annotations:
            start = float(annotation.get("start_seconds", 0.0))
            if start <= timestamp < start + float(annotation.get("duration_seconds", 0.0)):
                return str(annotation.get("normalized_label", annotation.get("label", "UNKNOWN")))
        return "UNKNOWN"

    def _run_wake_profile(self, manifest, identity) -> dict[str, Any]:
        wake_config = self.full_config["wake_music"]
        annotations = self.registry.load_annotations(
            manifest.session.session_id, str(wake_config["wake_window"]["annotation_type"])
        )
        try:
            source_window = select_wake_window(annotations, wake_config["wake_window"])
        except WakeWindowUnavailableError as error:
            raise FeatureUnavailableError(str(error)) from error
        metric = str(wake_config["source_feature_metric"])
        rows = self.load_derived_window(
            manifest.session.session_id, metric, source_window.start_s, source_window.end_s
        )
        try:
            physiology = summarize_physiology(
                rows, metric, int(wake_config["wake_window"]["minimum_feature_rows"])
            )
        except WakeWindowUnavailableError as error:
            raise FeatureUnavailableError(str(error)) from error
        profile = build_profile(
            session_id=manifest.session.session_id,
            source_window=source_window,
            physiology=physiology,
            requested_style="auto",
            generation_seed=int(wake_config["default_generation_seed"]),
            config=wake_config,
        )
        profile_path = (
            self._feature_directory(manifest.session.session_id, FEATURE_WAKE_PROFILE)
            / "profile.json"
        )
        _write_json(profile_path, profile.to_dict(), int(self.config["json_indent"]))
        return {
            "reuse_kind": "computed_product_cache",
            "artifacts": {"profile": str(profile_path)},
            "profile": profile.to_dict(),
            "summary": "Ready to generate",
        }

    def _run_k_complex(self, manifest, sources, identity) -> dict[str, Any]:
        product = self.config[FEATURE_K_COMPLEX]
        detector_config = self.full_config["k_complex_v0"]
        verifier_config = product["verifier"]
        if not bool(verifier_config["default_enabled"]):
            raise RuntimeError("the configured default K-complex morphology verifier is disabled")
        verifier = load_morphology_b1_verifier(
            self.project_root / str(verifier_config["artifact_path"]),
            expected_version=str(verifier_config["version"]),
            expected_checksum=str(verifier_config["artifact_checksum"]),
            expected_threshold=float(verifier_config["decision_threshold"]),
        )
        annotations = self.registry.load_annotations(
            manifest.session.session_id, str(product["stage_annotation_type"])
        )
        bouts = segment_stage_bouts(annotations, detector_config)
        if not bouts:
            raise FeatureUnavailableError("recording has no configured target-stage bouts")
        signal = sources[0]
        scales = product["input_scale_to_uv_by_unit"]
        if signal.unit not in scales:
            raise FeatureUnavailableError("unsupported K-complex EEG unit")
        window = self.registry.load_signal_window(
            manifest.session.session_id,
            signal.id,
            0.0,
            manifest.recording.duration_seconds,
        )
        values_uv = np.asarray(window.samples, dtype=float) * float(scales[signal.unit])
        events = detect_k_complexes(
            values_uv,
            signal.sampling_rate_hz,
            str(signal.original_channel_name or signal.channel_name),
            bouts,
            detector_config,
            dataset_id=manifest.dataset.id,
            subject_id=manifest.session.subject_id,
            recording_id=manifest.session.session_id,
            detector_version=str(detector_config["detector_version"]),
            config_hash=_hash(detector_config),
            source_fingerprint=identity["source_fingerprint"],
        )
        event_rows = [verifier.apply(event) for event in events]
        verified_rows = [row for row in event_rows if row["verification_accepted"]]
        rejected_count = len(event_rows) - len(verified_rows)
        bout_rows = [bout.to_dict() for bout in bouts]
        directory = self._feature_directory(manifest.session.session_id, FEATURE_K_COMPLEX)
        events_path = directory / "events.json"
        bouts_path = directory / "n2_bouts.json"
        _write_json(events_path, {"events": event_rows}, int(self.config["json_indent"]))
        _write_json(bouts_path, {"bouts": bout_rows}, int(self.config["json_indent"]))
        by_bout = Counter(str(row["n2_bout_id"]) for row in verified_rows)
        n2_duration_s = sum(bout.duration_s for bout in bouts)
        focus_priorities = {
            CanonicalSignalRole(value): index
            for index, value in enumerate(product["focus_role_priority"])
        }
        focus_signals = sorted(
            (
                item
                for item in manifest.signals
                if item.available
                and item.modality == "eeg"
                and item.canonical_role in focus_priorities
            ),
            key=lambda item: (focus_priorities[item.canonical_role], item.id),
        )[: int(product["maximum_focus_channels"])]
        analysis = {
            "recording_duration_s": manifest.recording.duration_seconds,
            "primary_stage": detector_config["stage_gating"]["primary_stage"],
            "n2_duration_s": n2_duration_s,
            "n2_bout_count": len(bouts),
            "candidate_count": len(event_rows),
            "verified_count": len(verified_rows),
            "rejected_count": rejected_count,
            "event_count": len(verified_rows),
            "events_per_hour_n2": len(verified_rows) / (n2_duration_s / 3600.0),
            "n2_bouts_with_events": sum(count >= 1 for count in by_bout.values()),
            "n2_bouts_with_at_least_two_events": sum(count >= 2 for count in by_bout.values()),
            "primary_channel": str(signal.original_channel_name or signal.channel_name),
            "primary_signal_id": signal.id,
            "focus_signals": [
                {
                    "signal_id": item.id,
                    "channel": str(item.original_channel_name or item.channel_name),
                    "canonical_role": item.canonical_role.value,
                    "sampling_rate_hz": item.sampling_rate_hz,
                    "unit": item.unit,
                }
                for item in focus_signals
            ],
            "focus_half_window_s": float(product["focus_half_window_s"]),
            "candidate_detector": str(detector_config["detector_version"]),
            "verification_method": str(verifier_config["method"]),
            "verifier_version": verifier.version,
            "verification_threshold": verifier.threshold,
            "retrospective_only": True,
            "causal_lead_time": None,
        }
        return {
            "reuse_kind": "computed_product_cache",
            "artifacts": {"events": str(events_path), "bouts": str(bouts_path)},
            "channels": [
                {
                    "channel": str(signal.original_channel_name or signal.channel_name),
                    "signal_id": signal.id,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                    "canonical_role": signal.canonical_role.value,
                    "candidate_count": len(event_rows),
                    "verified_count": len(verified_rows),
                    "rejected_count": rejected_count,
                }
            ],
            "analysis": analysis,
            "summary": f"{len(verified_rows)} verified",
        }

    def load_derived_window(
        self, session_id: str, result_type: str, start_s: float, end_s: float
    ) -> tuple[dict[str, Any], ...] | None:
        feature = {
            "alpha_power": FEATURE_ALPHA,
            "eye_movement_activity_v1": FEATURE_EYE_MOVEMENT,
            "eye_movement_events_v1": FEATURE_EYE_MOVEMENT,
            "k_complex_events_v0": FEATURE_K_COMPLEX,
        }.get(result_type)
        if feature is None:
            return None
        metadata = self._ready_metadata(session_id, feature)
        if metadata is None:
            return None
        if result_type == "k_complex_events_v0":
            path = self._artifact_paths(metadata, "events")[0]
            records = json.loads(path.read_text(encoding="utf-8"))["events"]
            return tuple(
                row for row in records if start_s <= float(row["negative_trough_s"]) < end_s
            )
        artifact_key = "events" if result_type.endswith("events_v1") else "features"
        paths = self._artifact_paths(metadata, artifact_key)
        time_key = "timestamp" if artifact_key == "events" else "window_end_s"
        rows = []
        for path in paths:
            with path.open(newline="", encoding="utf-8") as handle:
                for raw in csv.DictReader(handle):
                    timestamp = float(raw[time_key])
                    if start_s <= timestamp < end_s:
                        rows.append(_coerce_row(raw))
        return tuple(rows)

    def descriptor(self, session_id: str, result_type: str) -> ContentDescriptor | None:
        feature = {
            "alpha_power": FEATURE_ALPHA,
            "eye_movement_activity_v1": FEATURE_EYE_MOVEMENT,
            "eye_movement_events_v1": FEATURE_EYE_MOVEMENT,
            "k_complex_events_v0": FEATURE_K_COMPLEX,
        }.get(result_type)
        metadata = self._ready_metadata(session_id, feature) if feature else None
        if metadata is None:
            return None
        viewer = self._viewer_metadata(session_id)
        return ContentDescriptor(
            available=True,
            source=ProvenanceClass.DERIVED,
            derived_by=str(metadata["algorithm_version"]),
            version=str(metadata["algorithm_version"]),
            metadata={
                "viewer": viewer,
                "configuration_hash": metadata["configuration_hash"],
                "cache_key": metadata["cache_key"],
                "reuse_kind": metadata.get("reuse_kind"),
                "channels": metadata.get("channels", []),
                **({"coverage": metadata["coverage"]} if "coverage" in metadata else {}),
                **({"analysis": metadata["analysis"]} if "analysis" in metadata else {}),
            },
        )

    def _viewer_metadata(self, session_id: str) -> Mapping[str, Any]:
        manifest = self.registry.get_session_by_id(session_id)
        for descriptor in manifest.derived.values():
            viewer = descriptor.metadata.get("viewer")
            if isinstance(viewer, Mapping):
                return viewer
        return self.full_config["alpha"]["session_package"]["viewer"]

    def _artifact_paths(self, metadata: Mapping[str, Any], key: str) -> tuple[Path, ...]:
        artifacts = metadata["artifacts"]
        if isinstance(artifacts, Mapping):
            raw = [artifacts[key]] if key in artifacts else []
        else:
            raw = [item[key] for item in artifacts if key in item]
        return tuple(Path(item) for item in raw)

    def _ready_metadata(self, session_id: str, feature: str | None) -> dict[str, Any] | None:
        if feature is None:
            return None
        state = self._states.get((session_id, feature))
        if state and state.get("state") != "READY":
            return None
        path = self._metadata_path(session_id, feature)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _ready_state(self, metadata: Mapping[str, Any], *, cache_hit: bool) -> dict[str, Any]:
        descriptor_metadata = {
            key: metadata[key] for key in ("coverage", "analysis") if key in metadata
        }
        if metadata.get("feature") == FEATURE_ALPHA and "analysis" in descriptor_metadata:
            descriptor_metadata["analysis"] = {
                **descriptor_metadata["analysis"],
                "product_display_context_s": float(
                    self.full_config["alpha"]["history"]["trend_window_s"]
                ),
            }
        return {
            "feature": metadata["feature"],
            "state": "READY",
            "summary": metadata.get("summary", "Ready"),
            "cache_hit": cache_hit,
            "reuse_kind": metadata.get("reuse_kind"),
            "duration_ms": metadata.get("duration_ms"),
            "completed_at": metadata.get("completed_at"),
            "profile": metadata.get("profile"),
            "channels": metadata.get("channels", []),
            "descriptor_metadata": descriptor_metadata,
        }

    def k_complex_payload(self, session_id: str) -> dict[str, Any]:
        metadata = self._ready_metadata(session_id, FEATURE_K_COMPLEX)
        if metadata is None:
            raise LookupError("K-complex analysis is not ready")
        events = json.loads(
            self._artifact_paths(metadata, "events")[0].read_text(encoding="utf-8")
        )["events"]
        bouts = json.loads(self._artifact_paths(metadata, "bouts")[0].read_text(encoding="utf-8"))[
            "bouts"
        ]
        store = self._k_complex_annotation_store(session_id, events)
        foundation = self.full_config.get("cbramod_kc_v1", {})
        prediction_name = foundation.get("cached_session_predictions", {}).get(session_id)
        verifier_status: dict[str, Any] = {"status": "not_computed"}
        if prediction_name:
            prediction_path = (
                self.project_root / str(foundation["output_root"]) / str(prediction_name)
            )
            if prediction_path.is_file():
                with prediction_path.open(newline="", encoding="utf-8") as handle:
                    prediction_rows = list(csv.DictReader(handle))
                predictions = {row["event_id"]: row for row in prediction_rows}
                predictions_by_trough = {
                    float(row["negative_trough_s"]): row for row in prediction_rows
                }
                for event in events:
                    prediction = predictions.get(
                        str(event["event_id"])
                    ) or predictions_by_trough.get(
                        float(event["negative_trough_s"]),
                    )
                    if prediction is None:
                        continue
                    probability = prediction.get("cbramod_probability")
                    event.update(
                        cbramod_probability=float(probability) if probability else None,
                        cbramod_status=str(prediction["status"]),
                        cbramod_verifier_version=str(foundation["verifier_version"]),
                    )
                verifier_status = {
                    "status": "ready",
                    "verifier_version": str(foundation["verifier_version"]),
                }
        analysis = {**metadata["analysis"], "cbramod": verifier_status}
        return {
            "session_id": session_id,
            "detector_version": analysis["candidate_detector"],
            "verifier_version": analysis["verifier_version"],
            "verification_method": analysis["verification_method"],
            "candidate_count": analysis["candidate_count"],
            "verified_count": analysis["verified_count"],
            "rejected_count": analysis["rejected_count"],
            "config_hash": metadata["configuration_hash"],
            "source_fingerprint": metadata["source_fingerprint"],
            "analysis": analysis,
            "events": events,
            "bouts": bouts,
            "reviews": store.reviews(),
            "manual_events": store.manual_events(),
            "review_progress": store.progress(),
        }

    def save_k_complex_review(
        self, session_id: str, event_id: str, review_label: str, notes: str
    ) -> dict[str, Any]:
        payload = self.k_complex_payload(session_id)
        store = self._k_complex_annotation_store(session_id, payload["events"])
        return store.save_review(event_id, review_label, notes)

    def save_manual_k_complex(
        self, session_id: str, negative_trough_s: float, notes: str
    ) -> dict[str, Any]:
        payload = self.k_complex_payload(session_id)
        manifest = self.registry.get_session_by_id(session_id)
        timestamp = float(negative_trough_s)
        if not 0 <= timestamp < manifest.recording.duration_seconds:
            raise ValueError("manual K-complex trough is outside the recording")
        bout = next(
            (
                item
                for item in payload["bouts"]
                if float(item["start_s"]) <= timestamp < float(item["end_s"])
            ),
            None,
        )
        if bout is None:
            raise ValueError("manual K-complex trough must be inside configured N2")
        channel = str(payload["analysis"]["primary_channel"])
        manual_id = (
            "manual-kc-"
            + _hash({"session_id": session_id, "channel": channel, "trough_s": timestamp})[:20]
        )
        store = self._k_complex_annotation_store(session_id, payload["events"])
        return store.save_manual(
            manual_event_id=manual_id,
            recording_id=session_id,
            channel=channel,
            stage=str(bout["stage"]),
            n2_bout_id=str(bout["bout_id"]),
            negative_trough_s=timestamp,
            notes=notes,
        )

    def _k_complex_annotation_store(
        self, session_id: str, events: list[dict[str, Any]]
    ) -> KComplexAnnotationStore:
        product = self.config[FEATURE_K_COMPLEX]
        return KComplexAnnotationStore(
            self._feature_directory(session_id, FEATURE_K_COMPLEX) / "annotations.sqlite",
            events,
            review_labels=product["review_labels"],
            maximum_notes_characters=int(product["maximum_notes_characters"]),
        )

    @staticmethod
    def _load_cache(path: Path, cache_key: str) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("cache_key") != cache_key:
            return None
        artifacts = metadata.get("artifacts")
        raw_paths = []
        if isinstance(artifacts, Mapping):
            raw_paths.extend(artifacts.values())
        elif isinstance(artifacts, list):
            for item in artifacts:
                raw_paths.extend(value for key, value in item.items() if key != "channel")
        return metadata if all(Path(path).is_file() for path in raw_paths) else None

    def _feature_directory(self, session_id: str, feature: str) -> Path:
        return self.cache_root / _safe(session_id) / _safe(feature)

    def _metadata_path(self, session_id: str, feature: str) -> Path:
        return self._feature_directory(session_id, feature) / "metadata.json"
