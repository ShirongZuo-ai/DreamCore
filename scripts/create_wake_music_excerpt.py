"""Create or reuse a local Wake Version for an existing generated master."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from dreamcore.wake_music.postprocess import (
    WakeAudioPlaybackSettings,
    WakeAudioPostprocessor,
)
from dreamcore.wake_music.storage import WakeMusicStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation_id")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["wake_music"]
    storage_config = config["storage"]
    provider_config = config["provider"]
    storage = WakeMusicStorage(
        config_path.parent.parent / storage_config["root"],
        audio_filename=str(storage_config["audio_filename"]),
        profile_filename=str(storage_config["profile_filename"]),
        prompt_filename=str(storage_config["prompt_filename"]),
        metadata_filename=str(storage_config["metadata_filename"]),
        json_indent=int(storage_config["json_indent"]),
        download_timeout_s=float(provider_config["download_timeout_s"]),
        maximum_download_bytes=int(provider_config["maximum_download_bytes"]),
        postprocessor=WakeAudioPostprocessor(
            WakeAudioPlaybackSettings.from_config(config["playback"])
        ),
    )
    record = storage.get(args.generation_id)
    print(f"generation_id={record.generation_id}")
    print(f"master={record.master_audio.path}")
    print(f"wake_version={record.wake_version.path}")
    print(f"wake_duration_s={record.wake_version.encoded_duration_s:.6f}")


if __name__ == "__main__":
    main()
