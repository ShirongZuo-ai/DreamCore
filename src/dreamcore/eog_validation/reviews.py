"""Validated local human-review layer, separate from detector outputs."""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ReviewValidationError(ValueError):
    """Raised when a requested human annotation violates the review schema."""


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or not path.stat().st_size:
        return []
    with path.open(encoding="utf-8", newline="") as source:
        return [dict(row) for row in csv.DictReader(source)]


class HumanReviewStore:
    """SQLite-backed updateable reviews with a transparent CSV export."""

    def __init__(
        self,
        database_path: Path,
        export_path: Path,
        samples: Sequence[Mapping[str, Any]],
        config: Mapping[str, Any],
    ) -> None:
        self.database_path = Path(database_path)
        self.export_path = Path(export_path)
        self.samples = {str(sample["review_id"]): dict(sample) for sample in samples}
        self.schema_version = str(config["review_schema_version"])
        self.maximum_notes_characters = int(config["maximum_notes_characters"])
        self.labels = {
            "candidate": set(str(label) for label in config["candidate_labels"]),
            "control": set(str(label) for label in config["control_labels"]),
        }
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        if not self.export_path.exists():
            self._export()

    def _initialize(self) -> None:
        with sqlite3.connect(self.database_path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS human_reviews (
                    review_id TEXT PRIMARY KEY,
                    sample_kind TEXT NOT NULL,
                    candidate_id TEXT,
                    dataset_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    recording_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    candidate_timestamp REAL NOT NULL,
                    candidate_confidence REAL,
                    candidate_amplitude REAL,
                    sleep_stage TEXT NOT NULL,
                    review_label TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    review_timestamp TEXT NOT NULL,
                    review_schema_version TEXT NOT NULL
                )
                """
            )

    def save(self, review_id: str, review_label: str, notes: str) -> dict[str, Any]:
        sample = self.samples.get(review_id)
        if sample is None:
            raise ReviewValidationError("review_id is not in the frozen review sample")
        sample_kind = str(sample["sample_kind"])
        if review_label not in self.labels[sample_kind]:
            raise ReviewValidationError(f"unsupported {sample_kind} review label")
        if not isinstance(notes, str) or len(notes) > self.maximum_notes_characters:
            raise ReviewValidationError("review notes exceed the configured maximum")
        row = {
            "review_id": review_id,
            "sample_kind": sample_kind,
            "candidate_id": sample.get("candidate_id") or None,
            "dataset_id": sample["dataset_id"],
            "subject_id": sample["subject_id"],
            "recording_id": sample["recording_id"],
            "channel": sample.get("source_channel", "all_native_eog"),
            "candidate_timestamp": float(sample["timestamp"]),
            "candidate_confidence": _optional_float(sample.get("confidence")),
            "candidate_amplitude": _optional_float(sample.get("amplitude_uv")),
            "sleep_stage": sample["normalized_stage"],
            "review_label": review_label,
            "notes": notes,
            "review_timestamp": datetime.now(UTC).isoformat(),
            "review_schema_version": self.schema_version,
        }
        columns = list(row)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
        with sqlite3.connect(self.database_path) as database:
            database.execute(
                f"INSERT INTO human_reviews ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(review_id) DO UPDATE SET {updates}",
                tuple(row[column] for column in columns),
            )
        self._export()
        return row

    def list(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as database:
            database.row_factory = sqlite3.Row
            return [dict(row) for row in database.execute("SELECT * FROM human_reviews")]

    def _export(self) -> None:
        rows = self.list()
        fieldnames = [
            "review_id",
            "sample_kind",
            "candidate_id",
            "dataset_id",
            "subject_id",
            "recording_id",
            "channel",
            "candidate_timestamp",
            "candidate_confidence",
            "candidate_amplitude",
            "sleep_stage",
            "review_label",
            "notes",
            "review_timestamp",
            "review_schema_version",
        ]
        with self.export_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def progress(self) -> dict[str, Any]:
        reviews = self.list()
        totals = Counter(str(sample["sample_kind"]) for sample in self.samples.values())
        reviewed = Counter(str(review["sample_kind"]) for review in reviews)
        labels = Counter(str(review["review_label"]) for review in reviews)
        dataset_totals = Counter(str(sample["dataset_id"]) for sample in self.samples.values())
        dataset_reviewed = Counter(str(review["dataset_id"]) for review in reviews)
        return {
            "candidate_reviewed": reviewed["candidate"],
            "candidate_total": totals["candidate"],
            "control_reviewed": reviewed["control"],
            "control_total": totals["control"],
            "label_counts": dict(labels),
            "datasets": {
                dataset: {
                    "reviewed": dataset_reviewed[dataset],
                    "total": dataset_totals[dataset],
                }
                for dataset in sorted(dataset_totals)
            },
        }

    def metrics(self, confidence_bins: Sequence[float]) -> dict[str, Any]:
        reviews = self.list()
        samples = self.samples
        candidate = [row for row in reviews if row["sample_kind"] == "candidate"]
        control = [row for row in reviews if row["sample_kind"] == "control"]
        candidate_counts = Counter(row["review_label"] for row in candidate)
        control_counts = Counter(row["review_label"] for row in control)
        decided = (
            candidate_counts["Likely Eye Movement"]
            + candidate_counts["Artifact / Non-eye-movement"]
        )
        control_decided = (
            control_counts["Possible missed eye movement"]
            + control_counts["No obvious eye movement"]
        )
        bins = []
        for low, high in zip(confidence_bins[:-1], confidence_bins[1:], strict=True):
            members = []
            for review in candidate:
                confidence = _optional_float(samples[review["review_id"]].get("confidence"))
                if confidence is None:
                    continue
                if low <= confidence < high or (confidence == high == confidence_bins[-1]):
                    members.append(review)
            counts = Counter(row["review_label"] for row in members)
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "reviewed": len(members),
                    "likely_proportion": _ratio(counts["Likely Eye Movement"], len(members)),
                    "artifact_proportion": _ratio(
                        counts["Artifact / Non-eye-movement"], len(members)
                    ),
                    "uncertain_proportion": _ratio(counts["Uncertain"], len(members)),
                }
            )
        by_dataset: dict[str, Counter] = defaultdict(Counter)
        by_channel: dict[str, Counter] = defaultdict(Counter)
        by_stage: dict[str, Counter] = defaultdict(Counter)
        for review in candidate:
            by_dataset[review["dataset_id"]][review["review_label"]] += 1
            by_channel[review["channel"]][review["review_label"]] += 1
            by_stage[review["sleep_stage"]][review["review_label"]] += 1
        return {
            "candidate_review": {
                "reviewed": len(candidate),
                "label_counts": dict(candidate_counts),
                "candidate_precision_estimate": _ratio(
                    candidate_counts["Likely Eye Movement"], decided
                ),
                "uncertain_excluded_from_precision_denominator": True,
                "by_dataset": _group_metrics(by_dataset),
                "by_channel": _group_metrics(by_channel),
                "by_stage": _group_metrics(by_stage),
                "confidence_bins": bins,
            },
            "control_review": {
                "reviewed": len(control),
                "label_counts": dict(control_counts),
                "sampled_non_candidate_miss_proportion": _ratio(
                    control_counts["Possible missed eye movement"], control_decided
                ),
                "uncertain_and_artifact_excluded_from_denominator": True,
                "formal_recall": None,
            },
        }


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _group_metrics(groups: Mapping[str, Counter]) -> dict[str, Any]:
    output = {}
    for name, counts in sorted(groups.items()):
        decided = counts["Likely Eye Movement"] + counts["Artifact / Non-eye-movement"]
        output[name] = {
            "reviewed": sum(counts.values()),
            "label_counts": dict(counts),
            "candidate_precision_estimate": _ratio(counts["Likely Eye Movement"], decided),
        }
    return output
