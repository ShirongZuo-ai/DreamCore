"""Local bounded access to validation artifacts and human QC state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from dreamcore.datasets.registry import DatasetRegistry
from dreamcore.eog_validation.reviews import HumanReviewStore, read_csv_rows


class EogValidationService:
    def __init__(
        self,
        project_root: Path,
        registry: DatasetRegistry,
        config: Mapping[str, Any],
    ) -> None:
        self.project_root = project_root
        self.registry = registry
        self.config = config
        self.root = project_root / str(config["output_root"])
        if not (self.root / config["summary_filename"]).is_file():
            self.available = False
            self.summary = {}
            self.candidate_samples = []
            self.control_samples = []
            self.review_store = None
            return
        self.available = True
        self.summary = json.loads(
            (self.root / config["summary_filename"]).read_text(encoding="utf-8")
        )
        outputs = config["csv_outputs"]
        self.candidate_samples = read_csv_rows(self.root / outputs["candidate_review_sample"])
        self.control_samples = read_csv_rows(self.root / outputs["control_review_sample"])
        self.agreement = read_csv_rows(self.root / outputs["channel_agreement"])
        self.stages = read_csv_rows(self.root / outputs["stage_distribution"])
        self.scorers = read_csv_rows(self.root / outputs["scorer_disagreement"])
        self.review_store = HumanReviewStore(
            self.root / config["review_database_filename"],
            self.root / config["review_export_filename"],
            [*self.candidate_samples, *self.control_samples],
            config["manual_qc"],
        )

    def recording(self, session_id: str) -> dict[str, Any]:
        self._require_available()
        channels = [
            row for row in self.summary["full_night_summary"] if row["recording_id"] == session_id
        ]
        if not channels:
            return {
                "available": False,
                "validation_version": self.config["validation_version"],
                "reason": "recording_not_selected_for_eog_validation_v1",
            }
        return {
            "available": True,
            "validation_version": self.config["validation_version"],
            "contract_sha256": self.summary["contract_sha256"],
            "manual_review_status": (
                "in_progress" if self.review_store and self.review_store.list() else "pending"
            ),
            "channels": channels,
            "agreement": [row for row in self.agreement if row["recording_id"] == session_id],
            "stage_distribution": [row for row in self.stages if row["recording_id"] == session_id],
            "scorer_disagreement": [
                row for row in self.scorers if row["recording_id"] == session_id
            ],
        }

    def samples(self, session_id: str, sample_kind: str) -> list[dict[str, Any]]:
        self._require_available()
        source = self.candidate_samples if sample_kind == "candidate" else self.control_samples
        return [row for row in source if row["recording_id"] == session_id]

    def focus(self, review_id: str) -> dict[str, Any]:
        self._require_available()
        sample = next(
            (
                row
                for row in (*self.candidate_samples, *self.control_samples)
                if row["review_id"] == review_id
            ),
            None,
        )
        if sample is None:
            raise LookupError("review sample not found")
        manifest = self.registry.get_session_by_id(str(sample["recording_id"]))
        half_window = float(self.config["manual_qc"]["focus_half_window_s"])
        timestamp = float(sample["timestamp"])
        start = max(0.0, timestamp - half_window)
        end = min(manifest.recording.duration_seconds, timestamp + half_window)
        return {
            "sample": sample,
            "focus_start_s": start,
            "focus_end_s": end,
            "candidate_timestamp": timestamp,
            "eog_signals": [
                {
                    "signal_id": signal.id,
                    "channel": signal.original_channel_name,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                }
                for signal in manifest.signals
                if signal.available and signal.modality == "eog"
            ],
            "eeg_signals": [
                {
                    "signal_id": signal.id,
                    "channel": signal.original_channel_name,
                    "sampling_rate_hz": signal.sampling_rate_hz,
                }
                for signal in manifest.signals
                if signal.available and signal.modality == "eeg"
            ],
            "review": next(
                (review for review in self.review_store.list() if review["review_id"] == review_id),
                None,
            )
            if self.review_store
            else None,
        }

    def filtered_window(
        self, session_id: str, channel: str, start_s: float, duration_s: float
    ) -> dict[str, Any]:
        self._require_available()
        metadata_path = self.root / "derived" / session_id / _slug(channel) / "metadata.json"
        if not metadata_path.is_file():
            raise LookupError("filtered validation channel not found")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filtered = metadata["filtered_signal"]
        rate = float(filtered["sampling_rate_hz"])
        start_sample = int(round(start_s * rate))
        count = int(round(duration_s * rate))
        path = metadata_path.parent / filtered["path"]
        values = np.fromfile(path, dtype="<f4", count=count, offset=start_sample * 4)
        timestamps = start_s + np.arange(values.size, dtype=float) / rate
        return {
            "session_id": session_id,
            "channel": channel,
            "start_s": start_s,
            "end_s": start_s + values.size / rate,
            "sampling_rate_hz": rate,
            "unit": "uV",
            "timestamps": timestamps.tolist(),
            "samples": values.astype(float).tolist(),
            "provenance": "derived",
        }

    def save_review(self, review_id: str, label: str, notes: str) -> dict[str, Any]:
        self._require_available()
        return self.review_store.save(review_id, label, notes)

    def progress(self) -> dict[str, Any]:
        self._require_available()
        return self.review_store.progress()

    def metrics(self) -> dict[str, Any]:
        self._require_available()
        return self.review_store.metrics(self.config["manual_qc"]["confidence_bins"])

    def _require_available(self) -> None:
        if not self.available:
            raise LookupError("EOG Validation V1 artifacts are unavailable")


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip(
        "-"
    )
