"""Dataset-specific ingestion into canonical DreamCore Session Packages."""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import mne

from dreamcore.datasets.edf import EdfRecordingHeader, inspect_edf
from dreamcore.datasets.models import CanonicalSignalRole, CapabilityName


@dataclass(frozen=True)
class IndexedRecording:
    dataset_id: str
    subject_id: str
    recording_id: str
    manifest_path: Path
    source_files: tuple[Path, ...]


class DatasetSourceIndexer(ABC):
    """Inspect one official source format and write only lightweight metadata."""

    def __init__(
        self,
        dataset_config: Mapping[str, Any],
        *,
        project_root: Path,
        raw_root: Path,
        package_root: Path,
        role_rules: tuple[Mapping[str, str], ...],
        viewer_config: Mapping[str, Any],
        download_audit: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.config = dataset_config
        self.project_root = project_root
        self.raw_root = raw_root
        self.package_root = package_root
        self.role_rules = role_rules
        self.viewer_config = viewer_config
        self.download_audit = download_audit

    @abstractmethod
    def index(self) -> tuple[IndexedRecording, ...]:
        """Inspect local source files and create canonical session manifests."""

    def _edf_manifest(
        self,
        *,
        recording_id: str,
        subject_id: str,
        psg_path: Path,
        annotation_descriptors: Mapping[str, Any],
        source_files: tuple[Path, ...],
        visit_id: str | None = None,
    ) -> IndexedRecording | None:
        try:
            header = inspect_edf(psg_path)
        except OSError:
            # Resumable downloads are visible at their final path while incomplete.
            # They are not locally available recordings until the EDF opens cleanly.
            return None
        signal_rows = self._signals(header)
        has_eeg = any(row["modality"] == "eeg" for row in signal_rows)
        has_eog = any(row["modality"] == "eog" for row in signal_rows)
        has_stages = bool(annotation_descriptors)
        manifest_dir = self.package_root / str(self.config["dataset_id"]) / recording_id
        manifest_path = manifest_dir / "manifest.json"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "dreamcore.session.v1",
            "dataset": {
                "id": self.config["dataset_id"],
                "display_name": self.config["display_name"],
                "version": self.config["version"],
                "official_source": self.config["official_source"],
                "license_source": self.config["license_source"],
                "metadata": {
                    "official_title": self.config["title"],
                    "scoring_standard": self.config["scoring_standard"],
                    "local_status": "available_locally",
                },
            },
            "session": {
                "session_id": recording_id,
                "subject_id": subject_id,
                "visit_id": visit_id or recording_id,
                "night_id": recording_id,
            },
            "recording": {
                "duration_seconds": header.duration_seconds,
                "start_time": header.start_datetime.isoformat(),
            },
            "signals": signal_rows,
            "annotations": dict(annotation_descriptors),
            "derived": self._derived_descriptors(has_eeg=has_eeg, has_eog=has_eog),
            "capabilities": self._capabilities(
                has_eeg=has_eeg, has_eog=has_eog, has_stages=has_stages
            ),
            "provenance": {
                "classification": "imported",
                "source_dataset_uri": self.config["official_source"],
                "imported_by": "scripts/index_datasets.py",
                "notes": "Official public source files; DreamCore metadata normalization only",
                "metadata": {"source_files": [self._source_file(path) for path in source_files]},
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return IndexedRecording(
            dataset_id=str(self.config["dataset_id"]),
            subject_id=subject_id,
            recording_id=recording_id,
            manifest_path=manifest_path,
            source_files=source_files,
        )

    def _signals(self, header: EdfRecordingHeader) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        output = []
        for channel in header.channels:
            role, modality = self._role(channel.original_name)
            counts[modality] = counts.get(modality, 0) + 1
            output.append(
                {
                    "id": f"{modality}-{counts[modality]}",
                    "modality": modality,
                    "channel_name": channel.original_name,
                    "original_channel_name": channel.original_name,
                    "canonical_role": role.value,
                    "unit": channel.unit,
                    "sampling_rate_hz": channel.sampling_rate_hz,
                    "source": "raw",
                    "available": True,
                    "metadata": {
                        "native_sample_count": channel.sample_count,
                        "source_file": header.path.name,
                        "storage": {
                            "kind": "edf",
                            "reader_backend": "pyedflib_native",
                            "path": self._relative_to_manifest(header.path),
                            "channel_name": channel.original_name,
                            "sampling_rate_tolerance_hz": 0.000001,
                            "scale_to_unit": 1.0,
                        },
                    },
                }
            )
        return output

    def _role(self, channel_name: str) -> tuple[CanonicalSignalRole, str]:
        for rule in self.role_rules:
            if re.search(rule["pattern"], channel_name):
                return CanonicalSignalRole(rule["canonical_role"]), rule["modality"]
        return CanonicalSignalRole.OTHER, "other"

    def _annotation_descriptor(
        self,
        path: Path,
        *,
        scorer: str,
        primary: bool,
        storage_kind: str = "edf_annotations",
        contains_stages: list[str] | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "primary_for_viewer": primary,
            "scorer": scorer,
            "scoring_standard": self.config["scoring_standard"],
            "raw_labels_preserved": True,
            "contains_stages": contains_stages or [],
            "storage": {
                "kind": storage_kind,
                "path": self._relative_to_manifest(path),
                "label_map": dict(self.config["stage_label_map"]),
                "scoring_standard": self.config["scoring_standard"],
                "scorer": scorer,
                "skip_unmapped": True,
            },
        }
        if storage_kind == "epoch_labels_text":
            metadata["storage"]["epoch_duration_s"] = float(
                self.config["annotation_epoch_duration_s"]
            )
        return {"available": True, "source": "imported", "metadata": metadata}

    def _edf_stage_descriptor(self, path: Path, *, scorer: str = "official") -> dict[str, Any]:
        annotations = mne.read_annotations(path)
        normalized = {
            self.config["stage_label_map"][str(label)]
            for label in annotations.description
            if str(label) in self.config["stage_label_map"]
        }
        return self._annotation_descriptor(
            path,
            scorer=scorer,
            primary=True,
            contains_stages=sorted(normalized),
        )

    def _relative_to_manifest(self, path: Path) -> str:
        example_dir = self.package_root / str(self.config["dataset_id"]) / "recording"
        return os.path.relpath(path.resolve(), example_dir.resolve())

    def _source_file(self, path: Path) -> dict[str, Any]:
        audit = self.download_audit.get(str(path.resolve()), {})
        return {
            "local_path": self._project_relative(path),
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
            "sha256": audit.get("sha256"),
            "downloaded_at": audit.get("downloaded_at"),
            "official_source": self.config["official_source"],
        }

    def _project_relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.project_root.resolve()))
        except ValueError:
            return str(path.resolve())

    def _derived_descriptors(self, *, has_eeg: bool, has_eog: bool) -> dict[str, Any]:
        return {
            "eye_movement_activity_v1": {
                "available": False,
                "source": "derived",
                "reason": (
                    "Available EOG source; Eye Movement analysis not computed"
                    if has_eog
                    else "No suitable EOG source for Eye Movement analysis"
                ),
                "version": "eye-movement-v1",
                "metadata": {"availability_state": "not_computed" if has_eog else "unsupported"},
            },
            "eye_movement_events_v1": {
                "available": False,
                "source": "derived",
                "reason": (
                    "Available EOG source; candidate events not computed"
                    if has_eog
                    else "No suitable EOG source for candidate events"
                ),
                "version": "eye-movement-v1",
                "metadata": {"availability_state": "not_computed" if has_eog else "unsupported"},
            },
            "alpha_power": {
                "available": False,
                "source": "derived",
                "reason": (
                    "Available EEG source; Alpha diagnostic not computed"
                    if has_eeg
                    else "No EEG source for Alpha diagnostic"
                ),
                "version": "alpha-v1",
                "metadata": {
                    "availability_state": "not_computed" if has_eeg else "unsupported",
                    "viewer": dict(self.viewer_config),
                },
            },
        }

    @staticmethod
    def _capabilities(*, has_eeg: bool, has_eog: bool, has_stages: bool) -> dict[str, Any]:
        capabilities = {
            name.value: {
                "status": "UNAVAILABLE",
                "source": "unknown",
                "reason": "Not available or not computed for this recording",
            }
            for name in CapabilityName
        }
        capabilities["eeg"] = {
            "status": "AVAILABLE" if has_eeg else "UNAVAILABLE",
            "source": "raw" if has_eeg else "unknown",
            "reason": None if has_eeg else "No EEG channel identified from source metadata",
        }
        capabilities["eog"] = {
            "status": "AVAILABLE" if has_eog else "UNAVAILABLE",
            "source": "raw" if has_eog else "unknown",
            "reason": None if has_eog else "No EOG channel identified from source metadata",
        }
        capabilities["sleep_stage_labels"] = {
            "status": "AVAILABLE" if has_stages else "UNAVAILABLE",
            "source": "imported" if has_stages else "unknown",
            "reason": None if has_stages else "No local official stage annotation",
        }
        for name, source_exists, label in (
            ("eye_movement_activity", has_eog, "Eye Movement"),
            ("eye_movement_events", has_eog, "Eye Movement candidate events"),
            ("sonification_controls", has_eog, "Research Sonification controls"),
            ("alpha_power", has_eeg, "Alpha diagnostic"),
            ("relative_alpha_power", has_eeg, "Relative Alpha diagnostic"),
            ("individual_alpha_frequency", has_eeg, "IAF diagnostic"),
            ("alpha_trend", has_eeg, "Alpha trend"),
        ):
            capabilities[name] = {
                "status": "PLANNED" if source_exists else "UNAVAILABLE",
                "source": "derived" if source_exists else "unknown",
                "reason": (
                    f"Source available; {label} not computed"
                    if source_exists
                    else f"Required source unavailable for {label}"
                ),
            }
        return capabilities


class SleepEdfExpandedIndexer(DatasetSourceIndexer):
    def index(self) -> tuple[IndexedRecording, ...]:
        source_root = self.raw_root / str(self.config["raw_subdirectory"])
        output = []
        for recording_id, entry in self.config["recordings"].items():
            psg = source_root / entry["psg"]["name"]
            annotations = source_root / entry["annotations"]["name"]
            if not psg.is_file() or not annotations.is_file():
                continue
            indexed = self._edf_manifest(
                recording_id=recording_id,
                subject_id=str(entry["subject_id"]),
                psg_path=psg,
                annotation_descriptors={"sleep_stages": self._edf_stage_descriptor(annotations)},
                source_files=(psg, annotations),
            )
            if indexed is not None:
                output.append(indexed)
        return tuple(output)


class HmcSleepStagingIndexer(DatasetSourceIndexer):
    def index(self) -> tuple[IndexedRecording, ...]:
        source_root = self.raw_root / str(self.config["raw_subdirectory"])
        output = []
        for recording_id, entry in self.config["recordings"].items():
            psg = source_root / entry["psg"]["name"]
            annotations = source_root / entry["annotations"]["name"]
            audit_text = source_root / entry["annotation_audit"]["name"]
            if not psg.is_file() or not annotations.is_file() or not audit_text.is_file():
                continue
            descriptor = self._edf_stage_descriptor(annotations)
            descriptor["metadata"]["audit_text_path"] = self._relative_to_manifest(audit_text)
            indexed = self._edf_manifest(
                recording_id=recording_id,
                subject_id=str(entry["subject_id"]),
                psg_path=psg,
                annotation_descriptors={"sleep_stages": descriptor},
                source_files=(psg, annotations, audit_text),
            )
            if indexed is not None:
                output.append(indexed)
        return tuple(output)


class IsrucCohortIIIIndexer(DatasetSourceIndexer):
    def index(self) -> tuple[IndexedRecording, ...]:
        source_root = self.raw_root / str(self.config["raw_subdirectory"])
        output = []
        for subject_id in self.config["expected_subjects"]:
            candidates = tuple(
                path
                for path in source_root.rglob("*")
                if path.is_file()
                and path.suffix.casefold() in {".edf", ".rec"}
                and subject_id in path.parts
            )
            if not candidates:
                continue
            psg = max(candidates, key=lambda path: path.stat().st_size)
            annotation_files = self._annotation_files(source_root, subject_id)
            descriptors = {}
            for scorer, annotation_path in annotation_files.items():
                descriptors[f"sleep_stages_scorer_{scorer}"] = self._annotation_descriptor(
                    annotation_path,
                    scorer=scorer,
                    primary=False,
                    storage_kind="epoch_labels_text",
                    contains_stages=self._text_contains_stages(annotation_path),
                )
            primary_key = f"sleep_stages_scorer_{self.config['primary_scorer']}"
            if primary_key in descriptors:
                descriptors["sleep_stages"] = {
                    **descriptors[primary_key],
                    "metadata": {
                        **descriptors[primary_key]["metadata"],
                        "primary_for_viewer": True,
                    },
                }
            indexed = self._edf_manifest(
                recording_id=f"isruc-c3-{int(subject_id):02d}",
                subject_id=f"ISRUC-C3-{int(subject_id):02d}",
                psg_path=psg,
                annotation_descriptors=descriptors,
                source_files=(psg, *annotation_files.values()),
            )
            if indexed is not None:
                output.append(indexed)
        return tuple(output)

    def _annotation_files(self, source_root: Path, subject_id: str) -> dict[str, Path]:
        subject_files = tuple(
            path for path in source_root.rglob("*.txt") if subject_id in path.parts
        )
        return {
            str(scorer): matches[0]
            for scorer, pattern in self.config["annotation_filename_patterns"].items()
            if (
                matches := sorted(
                    path for path in subject_files if re.search(str(pattern), path.name)
                )
            )
        }

    def _text_contains_stages(self, path: Path) -> list[str]:
        values = re.findall(r"-?\d+|REM|N[123]|W", path.read_text(errors="replace"))
        return sorted(
            {str(self.config["stage_label_map"].get(value, "UNKNOWN")) for value in values}
        )


INDEXERS = {
    "sleep_edfx": SleepEdfExpandedIndexer,
    "hmc": HmcSleepStagingIndexer,
    "isruc": IsrucCohortIIIIndexer,
}


def catalog_payload(records: tuple[IndexedRecording, ...], *, project_root: Path) -> dict[str, Any]:
    return {
        "catalog_version": "dreamcore.dataset_library.v1",
        "recordings": [
            {
                **asdict(record),
                "manifest_path": str(
                    record.manifest_path.resolve().relative_to(project_root.resolve())
                ),
                "source_files": [
                    str(path.resolve().relative_to(project_root.resolve()))
                    for path in record.source_files
                ],
                "local_status": "available_locally",
            }
            for record in records
        ],
    }
