"""Dataset adapter abstraction independent of storage format and UI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dreamcore.datasets.models import (
    Capability,
    CapabilityName,
    DatasetMetadata,
    SessionManifest,
    SessionSummary,
    SignalMetadata,
)


@dataclass(frozen=True)
class SignalWindow:
    session_id: str
    signal: SignalMetadata
    start_seconds: float
    duration_seconds: float
    samples: tuple[float, ...]


class DatasetAdapter(ABC):
    """Normalize one dataset into DreamCore Session Package concepts."""

    @abstractmethod
    def dataset_metadata(self) -> DatasetMetadata:
        """Return stable metadata for this dataset."""

    @abstractmethod
    def list_sessions(self) -> tuple[SessionSummary, ...]:
        """List metadata only; implementations must not load full signals."""

    @abstractmethod
    def get_session_metadata(self, session_id: str) -> SessionManifest:
        """Return the canonical manifest for one session."""

    @abstractmethod
    def get_capabilities(self, session_id: str) -> Mapping[CapabilityName, Capability]:
        """Return the session capability set."""

    @abstractmethod
    def load_signal_window(
        self,
        session_id: str,
        signal_id: str,
        start_seconds: float,
        duration_seconds: float,
    ) -> SignalWindow:
        """Read only the requested time window for one signal."""

    def load_signal_windows(
        self,
        session_id: str,
        signal_ids: tuple[str, ...],
        start_seconds: float,
        duration_seconds: float,
    ) -> tuple[SignalWindow, ...]:
        """Read bounded signals, with storage-aware adapters free to batch I/O."""

        return tuple(
            self.load_signal_window(
                session_id,
                signal_id,
                start_seconds,
                duration_seconds,
            )
            for signal_id in signal_ids
        )

    @abstractmethod
    def load_annotations(self, session_id: str, annotation_type: str) -> tuple[Any, ...]:
        """Load one annotation type without coupling to a dataset format."""

    @abstractmethod
    def load_derived_results(self, session_id: str, result_type: str) -> tuple[Any, ...]:
        """Load one derived result type."""

    def load_derived_window(
        self,
        session_id: str,
        result_type: str,
        start_seconds: float,
        end_seconds: float,
    ) -> tuple[Any, ...]:
        """Read a bounded derived window, with a storage-specific override when available."""

        output = []
        for item in self.load_derived_results(session_id, result_type):
            if not isinstance(item, Mapping):
                continue
            item_start = float(item.get("window_start_s", item.get("timestamp", 0.0)))
            item_end = float(item.get("window_end_s", item_start))
            if item_end >= start_seconds and item_start < end_seconds:
                output.append(item)
        return tuple(output)
