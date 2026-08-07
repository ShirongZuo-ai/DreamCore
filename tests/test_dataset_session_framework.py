from __future__ import annotations

import json
from pathlib import Path

import pytest

from dreamcore.datasets.adapter import DatasetAdapter
from dreamcore.datasets.models import (
    CANONICAL_SCHEMA_VERSION,
    CapabilityName,
    CapabilityState,
    ManifestValidationError,
    UnknownSchemaVersionError,
    parse_session_manifest,
)
from dreamcore.datasets.registry import (
    DatasetRegistry,
    NoSessionCandidatesError,
    SessionFilter,
)
from dreamcore.datasets.replay import FixtureReplaySource
from dreamcore.datasets.repository import SessionPackageRepository

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "session_packages"


@pytest.fixture
def repository() -> SessionPackageRepository:
    return SessionPackageRepository(FIXTURE_ROOT)


@pytest.fixture
def registry(repository: SessionPackageRepository) -> DatasetRegistry:
    catalog = DatasetRegistry()
    for adapter in repository.adapters():
        catalog.register(adapter)
    return catalog


def test_fixture_adapter_implements_contract(repository: SessionPackageRepository) -> None:
    adapters = repository.adapters()
    assert len(adapters) == 2
    assert all(isinstance(adapter, DatasetAdapter) for adapter in adapters)
    assert all(adapter.list_sessions() for adapter in adapters)


def test_repository_discovers_and_validates_three_sessions(
    repository: SessionPackageRepository,
) -> None:
    manifests = repository.discover()
    assert len(manifests) == 3
    assert all(manifest.schema_version == CANONICAL_SCHEMA_VERSION for manifest in manifests)
    assert all(
        manifest.provenance.notes == "TEST FIXTURE — NOT REAL SUBJECT DATA"
        for manifest in manifests
    )


def test_registry_lists_datasets_sessions_and_lookup(registry: DatasetRegistry) -> None:
    assert [dataset.id for dataset in registry.list_datasets()] == [
        "fixture-neuro",
        "fixture-physiology",
    ]
    assert [summary.session.session_id for summary in registry.list_sessions()] == [
        "fixture-a",
        "fixture-b",
        "fixture-c",
    ]
    manifest = registry.get_session("fixture-neuro", "fixture-a")
    assert manifest.session.subject_id == "TEST-SUBJECT-A"


def test_search_is_dataset_agnostic(registry: DatasetRegistry) -> None:
    assert [item.session.session_id for item in registry.search_sessions("physiology")] == [
        "fixture-c"
    ]
    assert [item.session.session_id for item in registry.search_sessions("subject-b")] == [
        "fixture-b"
    ]


def test_filter_required_capabilities_duration_stage_and_subject(
    registry: DatasetRegistry,
) -> None:
    session_filter = SessionFilter(
        dataset_id="fixture-neuro",
        required_capabilities=(CapabilityName.EEG, CapabilityName.PHASE_ESTIMATION),
        optional_capabilities=(CapabilityName.PHASE_PRECISION,),
        minimum_duration_seconds=25000,
        has_sleep_stage=True,
        has_n3=True,
        subject_id="TEST-SUBJECT-A",
    )
    assert [item.session.session_id for item in registry.list_sessions(session_filter)] == [
        "fixture-a"
    ]


def test_optional_capabilities_rank_but_do_not_exclude(registry: DatasetRegistry) -> None:
    session_filter = SessionFilter(optional_capabilities=(CapabilityName.PHASE_ESTIMATION,))
    assert [item.session.session_id for item in registry.list_sessions(session_filter)] == [
        "fixture-a",
        "fixture-b",
        "fixture-c",
    ]


def test_random_selection_is_reproducible(registry: DatasetRegistry) -> None:
    first = registry.random_session(seed=42)
    second = registry.random_session(seed=42)
    assert first == second
    assert first.session.session_id in {"fixture-a", "fixture-b", "fixture-c"}


def test_random_valid_selection_only_uses_filter_candidates(registry: DatasetRegistry) -> None:
    session_filter = SessionFilter(
        required_capabilities=(CapabilityName.EEG, CapabilityName.SLEEP_STAGE_LABELS),
        has_n3=True,
    )
    selected = registry.random_valid_session(session_filter, seed=42)
    assert selected.session.session_id in {"fixture-a", "fixture-b"}
    assert selected.capability(CapabilityName.EEG).status is CapabilityState.AVAILABLE
    assert selected.has_n3


def test_empty_candidate_errors_are_explicit(registry: DatasetRegistry) -> None:
    impossible = SessionFilter(
        required_capabilities=(CapabilityName.EEG, CapabilityName.PPG),
        has_n3=True,
    )
    with pytest.raises(NoSessionCandidatesError, match="no session satisfies"):
        registry.random_valid_session(impossible, seed=42)
    with pytest.raises(NoSessionCandidatesError, match="no session candidates"):
        registry.random_session(seed=42, candidates=())


def test_capability_parsing_preserves_semantics(registry: DatasetRegistry) -> None:
    manifest = registry.get_session("fixture-neuro", "fixture-a")
    phase = manifest.capability(CapabilityName.PHASE_ESTIMATION)
    assert phase.status is CapabilityState.AVAILABLE
    assert phase.source.value == "derived"
    assert phase.derived_by == "fixture-hilbert-v1"
    assert manifest.capability(CapabilityName.SPO2).status is CapabilityState.UNAVAILABLE


def test_missing_optional_fields_are_supported() -> None:
    path = FIXTURE_ROOT / "fixture-neuro" / "fixture-b" / "manifest.json"
    manifest = parse_session_manifest(json.loads(path.read_text(encoding="utf-8")))
    assert manifest.dataset.version == "test-1"
    assert manifest.session.visit_id is None
    assert manifest.session.night_id is None
    assert manifest.recording.start_time is None
    assert manifest.recording.timezone is None


def test_unknown_schema_version_is_rejected() -> None:
    path = FIXTURE_ROOT / "fixture-neuro" / "fixture-a" / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = "dreamcore.session.v999"
    with pytest.raises(UnknownSchemaVersionError, match="unsupported schema_version"):
        parse_session_manifest(raw)


def test_invalid_manifest_is_rejected() -> None:
    path = FIXTURE_ROOT / "fixture-neuro" / "fixture-a" / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["recording"]["duration_seconds"] = 0
    with pytest.raises(ManifestValidationError, match="duration_seconds"):
        parse_session_manifest(raw)


def test_fixture_replay_source_reads_only_requested_window(
    repository: SessionPackageRepository,
) -> None:
    adapter = next(
        item for item in repository.adapters() if item.dataset_metadata().id == "fixture-neuro"
    )
    source = FixtureReplaySource(adapter, "fixture-a")
    signal = source.get_signal_metadata()[0]
    window = source.read_signal_window(signal.id, start_seconds=1.0, duration_seconds=2.0)
    assert len(window.samples) == int(signal.sampling_rate_hz * 2.0)
    assert window.start_seconds == 1.0
    assert source.get_annotations("sleep_stages")
    assert source.get_derived_events("phase_estimates") == ()
