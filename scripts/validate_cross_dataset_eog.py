"""Run bounded, non-persistent Eye Movement V1 compatibility checks."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dreamcore.config import load_config
from dreamcore.datasets.repository import SessionPackageRepository
from dreamcore.eye_movement import extract_eye_movement_track


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--library-config", type=Path, default=Path("configs/dataset_library_v1.yaml")
    )
    parser.add_argument("--analysis-config", type=Path, default=Path("configs/default.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    library = yaml.safe_load(args.library_config.read_text(encoding="utf-8"))
    validation = library["cross_dataset_eog_validation"]
    analysis = load_config(args.analysis_config)
    repository = SessionPackageRepository(Path(library["session_package_root"]))
    adapters = repository.adapters()
    rows = []
    for request in validation["recordings"]:
        session_id = str(request["session_id"])
        adapter = next(
            adapter
            for adapter in adapters
            if any(item.session.session_id == session_id for item in adapter.list_sessions())
        )
        manifest = adapter.get_session_metadata(session_id)
        for channel_name in request["channels"]:
            signal = next(
                signal
                for signal in manifest.signals
                if signal.original_channel_name == channel_name
            )
            window = adapter.load_signal_window(
                session_id,
                signal.id,
                float(validation["window_start_s"]),
                float(validation["window_duration_s"]),
            )
            try:
                track = extract_eye_movement_track(
                    window.samples,
                    signal.sampling_rate_hz,
                    channel_name,
                    session_id,
                    None,
                    analysis,
                )
                rows.append(
                    {
                        "session_id": session_id,
                        "source_channel": channel_name,
                        "canonical_role": signal.canonical_role.value,
                        "sampling_rate_hz": signal.sampling_rate_hz,
                        "status": "compatible_bounded_window",
                        "attempted_windows": track.attempted_windows,
                        "accepted_windows": track.accepted_windows,
                        "rejected_windows": track.rejected_windows,
                        "candidate_events": len(track.events),
                    }
                )
            except (TypeError, ValueError) as error:
                rows.append(
                    {
                        "session_id": session_id,
                        "source_channel": channel_name,
                        "canonical_role": signal.canonical_role.value,
                        "sampling_rate_hz": signal.sampling_rate_hz,
                        "status": "error",
                        "error": str(error),
                    }
                )
    payload = {
        "schema_version": "dreamcore.cross_dataset_eog_validation.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "analysis_version": analysis["eye_movement"]["feature_version"],
        "window_start_s": validation["window_start_s"],
        "window_duration_s": validation["window_duration_s"],
        "thresholds_changed": False,
        "dual_eog_combination": None,
        "persistence": "validation_only; derived availability remains not_computed",
        "rows": rows,
    }
    output = Path(validation["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validated={len(rows)} output={output.resolve()}")


if __name__ == "__main__":
    main()
