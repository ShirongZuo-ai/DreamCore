"""Replay source contract and deterministic Session Package fixture source."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from dreamcore.datasets.adapter import DatasetAdapter, SignalWindow
from dreamcore.datasets.models import SessionManifest, SignalMetadata


class ReplaySource(ABC):
    """Windowed, clock-free replay access. Playback timing is deliberately absent."""

    @abstractmethod
    def get_session(self) -> SessionManifest:
        pass

    @abstractmethod
    def get_duration(self) -> float:
        pass

    @abstractmethod
    def get_signal_metadata(self) -> tuple[SignalMetadata, ...]:
        pass

    @abstractmethod
    def read_signal_window(
        self, signal_id: str, start_seconds: float, duration_seconds: float
    ) -> SignalWindow:
        pass

    @abstractmethod
    def get_annotations(self, annotation_type: str) -> tuple[Any, ...]:
        pass

    @abstractmethod
    def get_derived_events(self, result_type: str) -> tuple[Any, ...]:
        pass


class FixtureReplaySource(ReplaySource):
    """Expose one fixture session through the future replay boundary."""

    def __init__(self, adapter: DatasetAdapter, session_id: str) -> None:
        self._adapter = adapter
        self._session_id = session_id

    def get_session(self) -> SessionManifest:
        return self._adapter.get_session_metadata(self._session_id)

    def get_duration(self) -> float:
        return self.get_session().recording.duration_seconds

    def get_signal_metadata(self) -> tuple[SignalMetadata, ...]:
        return self.get_session().signals

    def read_signal_window(
        self, signal_id: str, start_seconds: float, duration_seconds: float
    ) -> SignalWindow:
        return self._adapter.load_signal_window(
            self._session_id, signal_id, start_seconds, duration_seconds
        )

    def get_annotations(self, annotation_type: str) -> tuple[Any, ...]:
        return self._adapter.load_annotations(self._session_id, annotation_type)

    def get_derived_events(self, result_type: str) -> tuple[Any, ...]:
        return self._adapter.load_derived_results(self._session_id, result_type)
