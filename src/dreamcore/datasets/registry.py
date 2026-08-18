"""Multi-dataset session catalog, filtering, search, and seeded selection."""

from __future__ import annotations

import random
from dataclasses import dataclass

from dreamcore.datasets.adapter import DatasetAdapter
from dreamcore.datasets.models import (
    CapabilityName,
    CapabilityState,
    DatasetMetadata,
    SessionManifest,
    SessionSummary,
)


class DatasetRegistrationError(ValueError):
    """Raised for duplicate or inconsistent adapter registration."""


class NoSessionCandidatesError(LookupError):
    """Raised when seeded selection has no candidates."""


@dataclass(frozen=True)
class SessionFilter:
    dataset_id: str | None = None
    required_capabilities: tuple[CapabilityName, ...] = ()
    optional_capabilities: tuple[CapabilityName, ...] = ()
    minimum_duration_seconds: float | None = None
    has_sleep_stage: bool | None = None
    has_n3: bool | None = None
    subject_id: str | None = None

    def matches(self, summary: SessionSummary) -> bool:
        if self.dataset_id is not None and summary.dataset.id != self.dataset_id:
            return False
        if self.subject_id is not None and summary.session.subject_id != self.subject_id:
            return False
        if (
            self.minimum_duration_seconds is not None
            and summary.recording.duration_seconds < self.minimum_duration_seconds
        ):
            return False
        if self.has_sleep_stage is not None and summary.has_sleep_stage is not self.has_sleep_stage:
            return False
        if self.has_n3 is not None and summary.has_n3 is not self.has_n3:
            return False
        return all(
            summary.capability(name).status is CapabilityState.AVAILABLE
            for name in self.required_capabilities
        )

    def optional_score(self, summary: SessionSummary) -> int:
        """Count preferred capabilities without excluding otherwise valid sessions."""

        return sum(
            summary.capability(name).status is CapabilityState.AVAILABLE
            for name in self.optional_capabilities
        )

    def describe_requirements(self) -> tuple[str, ...]:
        requirements = [f"{name.value} available" for name in self.required_capabilities]
        if self.dataset_id:
            requirements.append(f"dataset {self.dataset_id}")
        if self.minimum_duration_seconds is not None:
            requirements.append(f"duration >= {self.minimum_duration_seconds:g} seconds")
        if self.has_sleep_stage:
            requirements.append("sleep-stage labels available")
        if self.has_n3:
            requirements.append("N3 present")
        if self.subject_id:
            requirements.append(f"subject {self.subject_id}")
        return tuple(requirements)


class DatasetRegistry:
    """Catalog adapters while keeping signal payload reads explicit and windowed."""

    def __init__(self) -> None:
        self._adapters: dict[str, DatasetAdapter] = {}
        self._runtime_derived_provider = None

    def set_runtime_derived_provider(self, provider) -> None:
        """Attach one local cache provider without changing source adapters."""

        self._runtime_derived_provider = provider

    def runtime_derived_descriptor(self, session_id: str, result_type: str):
        if self._runtime_derived_provider is None:
            return None
        return self._runtime_derived_provider.descriptor(session_id, result_type)

    def register(self, adapter: DatasetAdapter) -> None:
        metadata = adapter.dataset_metadata()
        if metadata.id in self._adapters:
            raise DatasetRegistrationError(f"dataset {metadata.id!r} is already registered")
        self._adapters[metadata.id] = adapter

    def list_datasets(self) -> tuple[DatasetMetadata, ...]:
        return tuple(
            self._adapters[dataset_id].dataset_metadata() for dataset_id in sorted(self._adapters)
        )

    def get_dataset_metadata(self, dataset_id: str) -> DatasetMetadata:
        try:
            return self._adapters[dataset_id].dataset_metadata()
        except KeyError as error:
            raise LookupError(f"dataset {dataset_id!r} is not registered") from error

    def list_sessions(
        self, session_filter: SessionFilter | None = None
    ) -> tuple[SessionSummary, ...]:
        summaries = [
            summary
            for dataset_id in sorted(self._adapters)
            for summary in self._adapters[dataset_id].list_sessions()
        ]
        if session_filter is not None:
            summaries = [summary for summary in summaries if session_filter.matches(summary)]
            if session_filter.optional_capabilities:
                summaries.sort(
                    key=lambda summary: (
                        -session_filter.optional_score(summary),
                        summary.dataset.id,
                        summary.session.session_id,
                    )
                )
                return tuple(summaries)
        return tuple(sorted(summaries, key=lambda item: (item.dataset.id, item.session.session_id)))

    def search_sessions(self, query: str) -> tuple[SessionSummary, ...]:
        normalized = query.strip().casefold()
        if not normalized:
            return self.list_sessions()
        return tuple(
            summary
            for summary in self.list_sessions()
            if normalized
            in " ".join(
                (
                    summary.dataset.id,
                    summary.dataset.display_name,
                    summary.session.session_id,
                    summary.session.subject_id,
                    summary.session.visit_id or "",
                    summary.session.night_id or "",
                )
            ).casefold()
        )

    def get_session(self, dataset_id: str, session_id: str) -> SessionManifest:
        try:
            adapter = self._adapters[dataset_id]
        except KeyError as error:
            raise LookupError(f"dataset {dataset_id!r} is not registered") from error
        return adapter.get_session_metadata(session_id)

    def list_dataset_sessions(self, dataset_id: str) -> tuple[SessionSummary, ...]:
        """List one dataset without exposing its adapter to transport callers."""

        try:
            adapter = self._adapters[dataset_id]
        except KeyError as error:
            raise LookupError(f"dataset {dataset_id!r} is not registered") from error
        return adapter.list_sessions()

    def list_dataset_subjects(self, dataset_id: str) -> tuple[dict[str, object], ...]:
        sessions = self.list_dataset_sessions(dataset_id)
        subjects = sorted({session.session.subject_id for session in sessions})
        return tuple(
            {
                "subject_id": subject_id,
                "recording_count": sum(
                    session.session.subject_id == subject_id for session in sessions
                ),
                "local_status": "available_locally",
            }
            for subject_id in subjects
        )

    def list_subject_recordings(
        self, dataset_id: str, subject_id: str
    ) -> tuple[SessionSummary, ...]:
        recordings = tuple(
            session
            for session in self.list_dataset_sessions(dataset_id)
            if session.session.subject_id == subject_id
        )
        if not recordings:
            raise LookupError(f"subject {subject_id!r} not found in dataset {dataset_id!r}")
        return recordings

    def get_session_by_id(self, session_id: str) -> SessionManifest:
        """Resolve a globally unique session identifier."""

        _, adapter = self._resolve_session(session_id)
        return adapter.get_session_metadata(session_id)

    def load_signal_window(
        self,
        session_id: str,
        signal_id: str,
        start_seconds: float,
        duration_seconds: float,
    ):
        """Delegate one bounded signal read to the owning dataset adapter."""

        _, adapter = self._resolve_session(session_id)
        return adapter.load_signal_window(
            session_id,
            signal_id,
            start_seconds,
            duration_seconds,
        )

    def load_signal_windows(
        self,
        session_id: str,
        signal_ids: tuple[str, ...],
        start_seconds: float,
        duration_seconds: float,
    ):
        """Delegate one bounded multi-signal read to the owning adapter."""

        _, adapter = self._resolve_session(session_id)
        return adapter.load_signal_windows(
            session_id,
            signal_ids,
            start_seconds,
            duration_seconds,
        )

    def load_annotations(self, session_id: str, annotation_type: str):
        """Delegate annotation loading to the owning dataset adapter."""

        _, adapter = self._resolve_session(session_id)
        return adapter.load_annotations(session_id, annotation_type)

    def load_derived_results(self, session_id: str, result_type: str):
        """Delegate derived-result loading to the owning dataset adapter."""

        _, adapter = self._resolve_session(session_id)
        return adapter.load_derived_results(session_id, result_type)

    def load_derived_window(
        self,
        session_id: str,
        result_type: str,
        start_seconds: float,
        end_seconds: float,
    ):
        """Delegate a bounded derived-result read to the owning adapter."""

        if self._runtime_derived_provider is not None:
            runtime = self._runtime_derived_provider.load_derived_window(
                session_id, result_type, start_seconds, end_seconds
            )
            if runtime is not None:
                return runtime
        _, adapter = self._resolve_session(session_id)
        return adapter.load_derived_window(
            session_id,
            result_type,
            start_seconds,
            end_seconds,
        )

    def _resolve_session(self, session_id: str) -> tuple[str, DatasetAdapter]:
        matches = [
            (dataset_id, adapter)
            for dataset_id, adapter in self._adapters.items()
            if any(summary.session.session_id == session_id for summary in adapter.list_sessions())
        ]
        if not matches:
            raise LookupError(f"session {session_id!r} is not registered")
        if len(matches) > 1:
            dataset_ids = ", ".join(sorted(dataset_id for dataset_id, _ in matches))
            raise LookupError(
                f"session id {session_id!r} is ambiguous across datasets: {dataset_ids}"
            )
        return matches[0]

    def random_session(
        self, seed: int, candidates: tuple[SessionSummary, ...] | None = None
    ) -> SessionSummary:
        pool = self.list_sessions() if candidates is None else tuple(candidates)
        if not pool:
            raise NoSessionCandidatesError("no session candidates are available")
        ordered = sorted(pool, key=lambda item: (item.dataset.id, item.session.session_id))
        return random.Random(seed).choice(ordered)

    def random_valid_session(self, session_filter: SessionFilter, seed: int) -> SessionSummary:
        candidates = self.list_sessions(session_filter)
        if not candidates:
            requirements = ", ".join(session_filter.describe_requirements()) or "current filter"
            raise NoSessionCandidatesError(f"no session satisfies: {requirements}")
        return self.random_session(seed, candidates)
