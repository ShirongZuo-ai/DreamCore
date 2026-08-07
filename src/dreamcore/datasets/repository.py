"""Filesystem-backed canonical Session Package repository and fixture adapter."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
        manifests: list[SessionManifest] = []
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
            manifests.append(manifest)
        return tuple(manifests)

    def adapters(self) -> tuple[FixtureDatasetAdapter, ...]:
        grouped: dict[str, list[SessionManifest]] = {}
        for manifest in self.discover():
            grouped.setdefault(manifest.dataset.id, []).append(manifest)
        return tuple(
            FixtureDatasetAdapter(tuple(grouped[dataset_id])) for dataset_id in sorted(grouped)
        )


class FixtureDatasetAdapter(DatasetAdapter):
    """Deterministic adapter for tiny contract fixtures, never real subject data."""

    def __init__(self, manifests: tuple[SessionManifest, ...]) -> None:
        if not manifests:
            raise ValueError("FixtureDatasetAdapter requires at least one manifest")
        dataset_ids = {manifest.dataset.id for manifest in manifests}
        if len(dataset_ids) != 1:
            raise ValueError("all fixture manifests must belong to one dataset")
        self._manifests = {
            manifest.session.session_id: manifest
            for manifest in sorted(manifests, key=lambda item: item.session.session_id)
        }
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
        if not isinstance(generator, Mapping):
            raise ManifestValidationError(f"fixture signal {signal_id!r} has no generation config")
        sample_count = int(round(duration_seconds * signal.sampling_rate_hz))
        kind = generator.get("kind")
        if kind == "sine":
            frequency_hz = float(generator["frequency_hz"])
            amplitude = float(generator["amplitude"])
            samples = tuple(
                amplitude
                * math.sin(
                    2 * math.pi * frequency_hz * (start_seconds + index / signal.sampling_rate_hz)
                )
                for index in range(sample_count)
            )
        elif kind == "constant":
            samples = (float(generator["value"]),) * sample_count
        else:
            raise ManifestValidationError(f"unsupported fixture generator {kind!r}")
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
        events = descriptor.metadata.get("events", [])
        if not isinstance(events, list):
            return ()
        return tuple(events)
