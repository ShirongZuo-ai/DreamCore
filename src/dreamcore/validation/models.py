"""Canonical validation records that retain native benchmark provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BenchmarkInterval:
    event_id: str
    recording_id: str
    scorer: str
    label: str
    channel: str
    onset_s: float
    duration_s: float
    source_file: str
    source_line: int
    raw_text: str

    @property
    def end_s(self) -> float:
        return self.onset_s + self.duration_s

    @property
    def valid(self) -> bool:
        return self.onset_s >= 0.0 and self.duration_s > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "end_s": self.end_s, "valid": self.valid}


@dataclass(frozen=True)
class ValidationPoint:
    event_id: str
    timestamp_s: float
    onset_s: float | None = None
    end_s: float | None = None
