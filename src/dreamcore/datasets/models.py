"""Canonical DreamCore Session Package models and manifest validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CANONICAL_SCHEMA_VERSION = "dreamcore.session.v1"


class ManifestValidationError(ValueError):
    """Raised when a Session Package manifest violates the canonical contract."""


class UnknownSchemaVersionError(ManifestValidationError):
    """Raised when a manifest declares an unsupported schema version."""


class CapabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PLANNED = "PLANNED"
    UNKNOWN = "UNKNOWN"


class ProvenanceClass(StrEnum):
    RAW = "raw"
    IMPORTED = "imported"
    DERIVED = "derived"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


class CapabilityName(StrEnum):
    EEG = "eeg"
    EOG = "eog"
    EYE_MOVEMENT_ACTIVITY = "eye_movement_activity"
    EYE_MOVEMENT_EVENTS = "eye_movement_events"
    SONIFICATION_CONTROLS = "sonification_controls"
    ALPHA_POWER = "alpha_power"
    RELATIVE_ALPHA_POWER = "relative_alpha_power"
    INDIVIDUAL_ALPHA_FREQUENCY = "individual_alpha_frequency"
    ALPHA_TREND = "alpha_trend"
    DROWSINESS_SCORE = "drowsiness_score"
    STIMULATION_DEMAND = "stimulation_demand"
    READY_TO_REMOVE = "ready_to_remove"
    SLEEP_STAGE_LABELS = "sleep_stage_labels"
    SLEEP_STAGE_PREDICTIONS = "sleep_stage_predictions"
    SLOW_OSCILLATION_DETECTION = "slow_oscillation_detection"
    PHASE_ESTIMATION = "phase_estimation"
    PHASE_PRECISION = "phase_precision"
    DECISION_SIMULATION = "decision_simulation"
    HEART_RATE = "heart_rate"
    PPG = "ppg"
    SPO2 = "spo2"
    MOVEMENT = "movement"
    SNORING = "snoring"
    AROUSALS = "arousals"
    ARTIFACTS = "artifacts"
    STIMULATION_EVENTS = "stimulation_events"
    HARDWARE_TELEMETRY = "hardware_telemetry"
    NAVIGATION_ALIGNMENT = "navigation_alignment"


@dataclass(frozen=True)
class Capability:
    name: CapabilityName
    status: CapabilityState
    source: ProvenanceClass
    reason: str | None = None
    derived_by: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class DatasetMetadata:
    id: str
    display_name: str
    version: str | None = None


@dataclass(frozen=True)
class SessionIdentity:
    session_id: str
    subject_id: str
    visit_id: str | None = None
    night_id: str | None = None


@dataclass(frozen=True)
class RecordingMetadata:
    duration_seconds: float
    start_time: str | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class SignalMetadata:
    id: str
    modality: str
    channel_name: str
    unit: str
    sampling_rate_hz: float
    source: ProvenanceClass
    available: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentDescriptor:
    available: bool
    source: ProvenanceClass
    reason: str | None = None
    derived_by: str | None = None
    version: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionProvenance:
    classification: ProvenanceClass
    source_dataset_uri: str | None = None
    imported_by: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SessionManifest:
    schema_version: str
    dataset: DatasetMetadata
    session: SessionIdentity
    recording: RecordingMetadata
    signals: tuple[SignalMetadata, ...]
    annotations: Mapping[str, ContentDescriptor]
    derived: Mapping[str, ContentDescriptor]
    capabilities: Mapping[CapabilityName, Capability]
    provenance: SessionProvenance

    def capability(self, name: CapabilityName) -> Capability:
        return self.capabilities.get(
            name,
            Capability(
                name=name,
                status=CapabilityState.UNKNOWN,
                source=ProvenanceClass.UNKNOWN,
                reason="Capability not declared by session package",
            ),
        )

    @property
    def has_sleep_stage(self) -> bool:
        descriptor = self.annotations.get("sleep_stages")
        return bool(descriptor and descriptor.available)

    @property
    def has_n3(self) -> bool:
        descriptor = self.annotations.get("sleep_stages")
        if not descriptor or not descriptor.available:
            return False
        stages = descriptor.metadata.get("contains_stages", [])
        return isinstance(stages, list) and "N3" in stages


@dataclass(frozen=True)
class SessionSummary:
    dataset: DatasetMetadata
    session: SessionIdentity
    recording: RecordingMetadata
    capabilities: Mapping[CapabilityName, Capability]
    has_sleep_stage: bool
    has_n3: bool
    provenance: ProvenanceClass

    def capability(self, name: CapabilityName) -> Capability:
        return self.capabilities.get(
            name,
            Capability(
                name=name,
                status=CapabilityState.UNKNOWN,
                source=ProvenanceClass.UNKNOWN,
                reason="Capability not declared by session package",
            ),
        )


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ManifestValidationError(f"{key} must be an object")
    return value


def _required_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{key} must be a non-empty string")
    return value


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ManifestValidationError(f"{key} must be a string or null")
    return value


def _parse_provenance(value: Any, path: str) -> ProvenanceClass:
    try:
        return ProvenanceClass(value)
    except (TypeError, ValueError) as error:
        raise ManifestValidationError(f"{path} has unsupported provenance {value!r}") from error


def _parse_content_map(data: Mapping[str, Any], key: str) -> dict[str, ContentDescriptor]:
    output: dict[str, ContentDescriptor] = {}
    for name, raw in _required_mapping(data, key).items():
        if not isinstance(raw, Mapping):
            raise ManifestValidationError(f"{key}.{name} must be an object")
        available = raw.get("available")
        if not isinstance(available, bool):
            raise ManifestValidationError(f"{key}.{name}.available must be boolean")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ManifestValidationError(f"{key}.{name}.metadata must be an object")
        output[str(name)] = ContentDescriptor(
            available=available,
            source=_parse_provenance(raw.get("source"), f"{key}.{name}.source"),
            reason=_optional_string(raw, "reason"),
            derived_by=_optional_string(raw, "derived_by"),
            version=_optional_string(raw, "version"),
            metadata=dict(metadata),
        )
    return output


def parse_session_manifest(data: Mapping[str, Any]) -> SessionManifest:
    """Validate and parse a canonical ``dreamcore.session.v1`` manifest."""

    schema_version = _required_string(data, "schema_version")
    if schema_version != CANONICAL_SCHEMA_VERSION:
        raise UnknownSchemaVersionError(
            f"unsupported schema_version {schema_version!r}; expected {CANONICAL_SCHEMA_VERSION!r}"
        )

    dataset_raw = _required_mapping(data, "dataset")
    session_raw = _required_mapping(data, "session")
    recording_raw = _required_mapping(data, "recording")
    provenance_raw = _required_mapping(data, "provenance")

    duration = recording_raw.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        raise ManifestValidationError("recording.duration_seconds must be positive")

    raw_signals = data.get("signals")
    if not isinstance(raw_signals, list):
        raise ManifestValidationError("signals must be an array")
    signals: list[SignalMetadata] = []
    signal_ids: set[str] = set()
    for index, raw in enumerate(raw_signals):
        if not isinstance(raw, Mapping):
            raise ManifestValidationError(f"signals[{index}] must be an object")
        signal_id = _required_string(raw, "id")
        if signal_id in signal_ids:
            raise ManifestValidationError(f"duplicate signal id {signal_id!r}")
        signal_ids.add(signal_id)
        sampling_rate = raw.get("sampling_rate_hz")
        if (
            not isinstance(sampling_rate, (int, float))
            or isinstance(sampling_rate, bool)
            or sampling_rate <= 0
        ):
            raise ManifestValidationError(f"signals[{index}].sampling_rate_hz must be positive")
        available = raw.get("available")
        if not isinstance(available, bool):
            raise ManifestValidationError(f"signals[{index}].available must be boolean")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ManifestValidationError(f"signals[{index}].metadata must be an object")
        signals.append(
            SignalMetadata(
                id=signal_id,
                modality=_required_string(raw, "modality"),
                channel_name=_required_string(raw, "channel_name"),
                unit=_required_string(raw, "unit"),
                sampling_rate_hz=float(sampling_rate),
                source=_parse_provenance(raw.get("source"), f"signals[{index}].source"),
                available=available,
                metadata=dict(metadata),
            )
        )

    raw_capabilities = _required_mapping(data, "capabilities")
    capabilities: dict[CapabilityName, Capability] = {}
    for raw_name, raw in raw_capabilities.items():
        try:
            name = CapabilityName(raw_name)
        except ValueError as error:
            raise ManifestValidationError(f"unknown capability {raw_name!r}") from error
        if not isinstance(raw, Mapping):
            raise ManifestValidationError(f"capabilities.{name.value} must be an object")
        try:
            status = CapabilityState(raw.get("status"))
        except (TypeError, ValueError) as error:
            raise ManifestValidationError(f"capabilities.{name.value}.status is invalid") from error
        capabilities[name] = Capability(
            name=name,
            status=status,
            source=_parse_provenance(raw.get("source"), f"capabilities.{name.value}.source"),
            reason=_optional_string(raw, "reason"),
            derived_by=_optional_string(raw, "derived_by"),
            version=_optional_string(raw, "version"),
        )

    classification = _parse_provenance(
        provenance_raw.get("classification"), "provenance.classification"
    )
    return SessionManifest(
        schema_version=schema_version,
        dataset=DatasetMetadata(
            id=_required_string(dataset_raw, "id"),
            display_name=_required_string(dataset_raw, "display_name"),
            version=_optional_string(dataset_raw, "version"),
        ),
        session=SessionIdentity(
            session_id=_required_string(session_raw, "session_id"),
            subject_id=_required_string(session_raw, "subject_id"),
            visit_id=_optional_string(session_raw, "visit_id"),
            night_id=_optional_string(session_raw, "night_id"),
        ),
        recording=RecordingMetadata(
            duration_seconds=float(duration),
            start_time=_optional_string(recording_raw, "start_time"),
            timezone=_optional_string(recording_raw, "timezone"),
        ),
        signals=tuple(signals),
        annotations=_parse_content_map(data, "annotations"),
        derived=_parse_content_map(data, "derived"),
        capabilities=capabilities,
        provenance=SessionProvenance(
            classification=classification,
            source_dataset_uri=_optional_string(provenance_raw, "source_dataset_uri"),
            imported_by=_optional_string(provenance_raw, "imported_by"),
            notes=_optional_string(provenance_raw, "notes"),
        ),
    )


def summarize_manifest(manifest: SessionManifest) -> SessionSummary:
    return SessionSummary(
        dataset=manifest.dataset,
        session=manifest.session,
        recording=manifest.recording,
        capabilities=manifest.capabilities,
        has_sleep_stage=manifest.has_sleep_stage,
        has_n3=manifest.has_n3,
        provenance=manifest.provenance.classification,
    )
