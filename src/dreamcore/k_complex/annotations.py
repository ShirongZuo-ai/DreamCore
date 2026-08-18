"""Local review and manual-event overlays for immutable detector output."""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class KComplexAnnotationError(ValueError):
    """Raised when a local review/manual annotation is invalid."""


class KComplexAnnotationStore:
    def __init__(
        self,
        path: Path,
        events: Sequence[Mapping[str, Any]],
        *,
        review_labels: Sequence[str],
        maximum_notes_characters: int,
    ) -> None:
        self.path = Path(path)
        self.events = {str(event["event_id"]): dict(event) for event in events}
        self.review_labels = set(review_labels)
        self.maximum_notes_characters = int(maximum_notes_characters)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    event_id TEXT PRIMARY KEY,
                    review_label TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                )
                """
            )
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_events (
                    manual_event_id TEXT PRIMARY KEY,
                    recording_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    n2_bout_id TEXT NOT NULL,
                    negative_trough_s REAL NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    event_type TEXT NOT NULL
                )
                """
            )

    def save_review(self, event_id: str, review_label: str, notes: str) -> dict[str, Any]:
        if event_id not in self.events:
            raise KComplexAnnotationError("event_id is not an automatic K-complex event")
        if review_label not in self.review_labels:
            raise KComplexAnnotationError("unsupported K-complex review label")
        self._validate_notes(notes)
        reviewed_at = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.path) as database:
            database.execute(
                """
                INSERT INTO reviews (event_id, review_label, notes, reviewed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    review_label=excluded.review_label,
                    notes=excluded.notes,
                    reviewed_at=excluded.reviewed_at
                """,
                (event_id, review_label, notes, reviewed_at),
            )
        return {
            "event_id": event_id,
            "review_label": review_label,
            "notes": notes,
            "reviewed_at": reviewed_at,
        }

    def save_manual(
        self,
        *,
        manual_event_id: str,
        recording_id: str,
        channel: str,
        stage: str,
        n2_bout_id: str,
        negative_trough_s: float,
        notes: str,
    ) -> dict[str, Any]:
        self._validate_notes(notes)
        created_at = datetime.now(UTC).isoformat()
        row = {
            "manual_event_id": manual_event_id,
            "recording_id": recording_id,
            "channel": channel,
            "stage": stage,
            "n2_bout_id": n2_bout_id,
            "negative_trough_s": float(negative_trough_s),
            "notes": notes,
            "created_at": created_at,
            "provenance": "manual",
            "event_type": "manual_k_complex_trough_candidate",
        }
        columns = tuple(row)
        with sqlite3.connect(self.path) as database:
            database.execute(
                f"INSERT INTO manual_events ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        return row

    def reviews(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM reviews ORDER BY reviewed_at, event_id")

    def manual_events(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM manual_events ORDER BY negative_trough_s, manual_event_id")

    def progress(self) -> dict[str, Any]:
        reviews = self.reviews()
        return {
            "reviewed": len(reviews),
            "total": len(self.events),
            "label_counts": dict(Counter(row["review_label"] for row in reviews)),
        }

    def _rows(self, query: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as database:
            database.row_factory = sqlite3.Row
            return [dict(row) for row in database.execute(query)]

    def _validate_notes(self, notes: str) -> None:
        if not isinstance(notes, str) or len(notes) > self.maximum_notes_characters:
            raise KComplexAnnotationError("K-complex notes exceed the configured maximum")
