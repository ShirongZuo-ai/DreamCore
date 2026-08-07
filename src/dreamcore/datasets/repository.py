"""Filesystem-backed canonical Session Package repository and fixture adapter."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import mne

from dreamcore.datasets.adapter import DatasetAdapter, SignalWindow
from dreamcore.datasets.models import (
    Capability,
    CapabilityName,
    DatasetMetadata,
    ManifestValidationError,
    SessionManifest,
    SessionSummary,
    parse_session_manifest,
    summarize_manifest,
)


class SessionNotFoundError(LookupError):
    """Raised when a requested session is absent."""


class SessionPackageRepository:
    """Discover and validate small manifests without reading signal payloads."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def discover(self) -> tuple[SessionManifest, ...]:
        return tuple(manifest for manifest, _ in self._discover_records())

    def _discover_records(self) -> tuple[tuple[SessionManifest, Path], ...]:
        records: list[tuple[SessionManifest, Path]] = []
        identities: set[tuple[str, str]] = set()
        if not self._root.exists():
            return ()
        for path in sorted(self._root.rglob("manifest.json")):
            with path.open(encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, Mapping):
                raise ManifestValidationError(f"{path}: manifest root must be an object")
            manifest = parse_session_manifest(raw)
            identity = (manifest.dataset.id, manifest.session.session_id)
            if identity in identities:
                raise ManifestValidationError(
                    f"duplicate session package {identity[0]!r}/{identity[1]!r}"
                )
            identities.add(identity)
            records.append((manifest, path))
        return tuple(records)

    def adapters(self) -> tuple[SessionPackageDatasetAdapter, ...]:
        grouped: dict[str, list[tuple[SessionManifest, Path]]] = {}
        for manifest, path in self._discover_records():
            grouped.setdefault(manifest.dataset.id, []).append((manifest, path))
        return tuple(
            SessionPackageDatasetAdapter(tuple(grouped[dataset_id]))
            for dataset_id in sorted(grouped)
        )


class SessionPackageDatasetAdapter(DatasetAdapter):
    """Read fixture or referenced-file content through one package contract."""

    def __init__(self, records: tuple[tuple[SessionManifest, Path], ...]) -> None:
        if not records:
            raise ValueError("SessionPackageDatasetAdapter requires at least one manifest")
        manifests = tuple(record[0] for record in records)
        dataset_ids = {manifest.dataset.id for manifest in manifests}
        if len(dataset_ids) != 1:
            raise ValueError("all fixture manifests must belong to one dataset")
        self._manifests = {
            manifest.session.session_id: manifest
            for manifest in sorted(manifests, key=lambda item: item.session.session_id)
        }
        self._manifest_paths = {manifest.session.session_id: path for manifest, path in records}
        self._dataset = manifests[0].dataset

    def dataset_metadata(self) -> DatasetMetadata:
        return self._dataset

    def list_sessions(self) -> tuple[SessionSummary, ...]:
        return tuple(summarize_manifest(manifest) for manifest in self._manifests.values())

    def get_session_metadata(self, session_id: str) -> SessionManifest:
        try:
            return self._manifests[session_id]
        except KeyError as error:
            raise SessionNotFoundError(
                f"session {session_id!r} not found in dataset {self._dataset.id!r}"
            ) from error

    def get_capabilities(self, session_id: str) -> Mapping[CapabilityName, Capability]:
        return self.get_session_metadata(session_id).capabilities

    def load_signal_window(
        self,
        session_id: str,
        signal_id: str,
        start_seconds: float,
        duration_seconds: float,
    ) -> SignalWindow:
        manifest = self.get_session_metadata(session_id)
        if start_seconds < 0 or duration_seconds <= 0:
            raise ValueError("signal window start must be non-negative and duration positive")
        if start_seconds + duration_seconds > manifest.recording.duration_seconds:
            raise ValueError("signal window exceeds session duration")
        signal = next((item for item in manifest.signals if item.id == signal_id), None)
        if signal is None:
            raise LookupError(f"signal {signal_id!r} not found")
        if not signal.available:
            raise ValueError(f"signal {signal_id!r} is unavailable")
        generator = signal.metadata.get("fixture_generation")
        sample_count = int(round(duration_seconds * signal.sampling_rate_hz))
        if isinstance(generator, Mapping) and generator.get("kind") == "sine":
            frequency_hz = float(generator["frequency_hz"])
            amplitude = float(generator["amplitude"])
            samples = tuple(
                amplitude
                * math.sin(
                    2 * math.pi * frequency_hz * (start_seconds + index / signal.sampling_rate_hz)
                )
                for index in range(sample_count)
            )
        elif isinstance(generator, Mapping) and generator.get("kind") == "constant":
            samples = (float(generator["value"]),) * sample_count
        else:
            storage = signal.metadata.get("storage")
            if not isinstance(storage, Mapping) or storage.get("kind") != "edf":
                raise ManifestValidationError(
                    f"signal {signal_id!r} has no supported fixture or EDF storage"
                )
            path = self._resolve_storage_path(session_id, storage)
            raw = mne.io.read_raw_edf(path, preload=False, verbose=False)
            actual_rate = float(raw.info["sfreq"])
            tolerance = float(storage["sampling_rate_tolerance_hz"])
            if abs(actual_rate - signal.sampling_rate_hz) > tolerance:
                raise ValueError("Referenced EDF sampling rate differs from manifest")
            channel_name = str(storage["channel_name"])
            if channel_name not in raw.ch_names:
                raise LookupError(f"EDF channel {channel_name!r} not found")
            start_sample = int(round(start_seconds * actual_rate))
            stop_sample = start_sample + sample_count
            scale = float(storage["scale_to_unit"])
            values = raw.get_data(picks=[channel_name], start=start_sample, stop=stop_sample)[0]
            samples = tuple((values * scale).astype(float).tolist())
        return SignalWindow(
            session_id=session_id,
            signal=signal,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            samples=samples,
        )

    def load_annotations(self, session_id: str, annotation_type: str) -> tuple[Any, ...]:
        descriptor = self.get_session_metadata(session_id).annotations.get(annotation_type)
        if descriptor is None:
            raise LookupError(f"annotation type {annotation_type!r} not declared")
        if not descriptor.available:
            return ()
        storage = descriptor.metadata.get("storage")
        if isinstance(storage, Mapping):
            if storage.get("kind") != "sleep_edf_annotations":
                raise ManifestValidationError(
                    f"unsupported annotation storage {storage.get('kind')!r}"
                )
            path = self._resolve_storage_path(session_id, storage)
            annotations = mne.read_annotations(path)
            label_map = storage.get("label_map")
            if not isinstance(label_map, Mapping):
                raise ManifestValidationError("Sleep-EDF annotation storage requires label_map")
            recording_end = self.get_session_metadata(session_id).recording.duration_seconds
            output = []
            for onset, duration, description in zip(
                annotations.onset,
                annotations.duration,
                annotations.description,
                strict=True,
            ):
                start_s = max(0.0, float(onset))
                end_s = min(recording_end, float(onset + duration))
                if end_s <= start_s:
                    continue
                output.append(
                    {
                        "start_seconds": start_s,
                        "duration_seconds": end_s - start_s,
                        "label": str(label_map.get(str(description), "UNKNOWN")),
                        "raw_label": str(description),
                        "provenance": "imported",
                    }
                )
            return tuple(output)
        events = descriptor.metadata.get("events", [])
        if not isinstance(events, list):
            raise ManifestValidationError(f"annotation {annotation_type!r} events must be an array")
        return tuple(events)

    def load_derived_results(self, session_id: str, result_type: str) -> tuple[Any, ...]:
        descriptor = self.get_session_metadata(session_id).derived.get(result_type)
        if descriptor is None:
            raise LookupError(f"derived result {result_type!r} not declared")
        if not descriptor.available:
            return ()
        storage = descriptor.metadata.get("storage")
        if isinstance(storage, Mapping):
            path = self._resolve_storage_path(session_id, storage)
            if storage.get("kind") == "csv":
                with path.open(encoding="utf-8", newline="") as input_file:
                    return tuple(dict(row) for row in csv.DictReader(input_file))
            if storage.get("kind") == "json":
                with path.open(encoding="utf-8") as input_file:
                    content = json.load(input_file)
                for key in storage.get("json_path", []):
                    if not isinstance(content, Mapping):
                        return ()
                    content = content.get(str(key))
                return tuple(content) if isinstance(content, list) else ()
            raise ManifestValidationError(f"unsupported derived storage {storage.get('kind')!r}")
        events = descriptor.metadata.get("events", [])
        if not isinstance(events, list):
            return ()
        return tuple(events)

    def _resolve_storage_path(self, session_id: str, storage: Mapping[str, Any]) -> Path:
        relative = storage.get("path")
        if not isinstance(relative, str) or not relative:
            raise ManifestValidationError("Referenced storage path must be a string")
        return (self._manifest_paths[session_id].parent / relative).resolve()


class FixtureDatasetAdapter(SessionPackageDatasetAdapter):
    """Backward-compatible adapter name for deterministic fixture packages."""

    def __init__(self, manifests: tuple[SessionManifest, ...]) -> None:
        records = tuple((manifest, Path("manifest.json")) for manifest in manifests)
        super().__init__(records)
