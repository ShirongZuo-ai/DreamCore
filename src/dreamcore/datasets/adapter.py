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

    @abstractmethod
    def load_annotations(self, session_id: str, annotation_type: str) -> tuple[Any, ...]:
        """Load one annotation type without coupling to a dataset format."""

    @abstractmethod
    def load_derived_results(self, session_id: str, result_type: str) -> tuple[Any, ...]:
        """Load one derived result type."""
