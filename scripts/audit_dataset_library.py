"""Write a reproducible metadata-only audit of the local Dataset Library."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from dreamcore.api.http import build_registry
from dreamcore.datasets.models import CapabilityName, CapabilityState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/dataset_library_v1.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    raw_root = project_root / config["raw_root"]
    registry = build_registry(project_root / config["session_package_root"])
    datasets = []
    for dataset in registry.list_datasets():
        recordings = []
        summaries = registry.list_dataset_sessions(dataset.id)
        for summary in summaries:
            manifest = registry.get_session(dataset.id, summary.session.session_id)
            recordings.append(
                {
                    "recording_id": manifest.session.session_id,
                    "subject_id": manifest.session.subject_id,
                    "duration_seconds": manifest.recording.duration_seconds,
                    "channels": [
                        {
                            "original_channel_name": signal.original_channel_name,
                            "canonical_role": signal.canonical_role.value,
                            "sampling_rate_hz": signal.sampling_rate_hz,
                            "unit": signal.unit,
                        }
                        for signal in manifest.signals
                    ],
                    "annotation_types": sorted(manifest.annotations),
                    "eeg_available": manifest.capability(CapabilityName.EEG).status
                    is CapabilityState.AVAILABLE,
                    "eog_available": manifest.capability(CapabilityName.EOG).status
                    is CapabilityState.AVAILABLE,
                    "derived_available": sorted(
                        name
                        for name, descriptor in manifest.derived.items()
                        if descriptor.available
                    ),
                    "derived_not_computed": sorted(
                        name
                        for name, descriptor in manifest.derived.items()
                        if not descriptor.available
                        and descriptor.metadata.get("availability_state") == "not_computed"
                    ),
                }
            )
        datasets.append(
            {
                "dataset_id": dataset.id,
                "display_name": dataset.display_name,
                "version": dataset.version,
                "official_source": dataset.official_source,
                "subject_count": len({item["subject_id"] for item in recordings}),
                "recording_count": len(recordings),
                "recordings": recordings,
            }
        )
    raw_files = tuple(path for path in raw_root.rglob("*") if path.is_file())
    payload = {
        "catalog_version": config["catalog_version"],
        "raw_root": str(raw_root.relative_to(project_root)),
        "raw_file_count": len(raw_files),
        "raw_size_bytes": sum(path.stat().st_size for path in raw_files),
        "datasets": datasets,
    }
    output = project_root / config["audit_output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"datasets={len(datasets)} recordings={sum(item['recording_count'] for item in datasets)}"
    )
    print(f"raw_files={payload['raw_file_count']} raw_size_bytes={payload['raw_size_bytes']}")
    print(f"audit={output}")


if __name__ == "__main__":
    main()
