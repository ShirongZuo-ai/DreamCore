"""Serve read-only Sessions plus the separated local Wake Music API."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

import yaml

from dreamcore.analysis import AutomaticAnalysisManager
from dreamcore.api.analysis import AutomaticAnalysisApiApplication
from dreamcore.api.eog_validation import EogValidationApiApplication
from dreamcore.api.http import ApiSettings, SessionApiApplication, build_registry
from dreamcore.api.signal_validation import SignalValidationApiApplication
from dreamcore.api.wake_music import DreamCoreApiApplication
from dreamcore.eog_validation.service import EogValidationService
from dreamcore.wake_music.postprocess import (
    WakeAudioPlaybackSettings,
    WakeAudioPostprocessor,
)
from dreamcore.wake_music.provider import MiniMaxMusicProvider, MiniMaxSettings
from dreamcore.wake_music.service import WakeMusicService
from dreamcore.wake_music.storage import WakeMusicStorage


class ThreadingWsgiServer(ThreadingMixIn, WSGIServer):
    """Serve independent bounded replay reads concurrently."""

    daemon_threads = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    transport = config["session_transport"]
    project_root = config_path.parent.parent
    package_root = project_root / transport["session_package_root"]
    settings = ApiSettings(
        max_signal_window_seconds=float(transport["max_signal_window_s"]),
        cors_allowed_origins=tuple(transport["cors_allowed_origins"]),
    )
    registry = build_registry(package_root)
    analysis_manager = AutomaticAnalysisManager(project_root, registry, config)
    registry.set_runtime_derived_provider(analysis_manager)
    session_api = SessionApiApplication(registry, settings)
    wake_config = config["wake_music"]
    provider_config = wake_config["provider"]
    storage_config = wake_config["storage"]
    postprocessor = WakeAudioPostprocessor(
        WakeAudioPlaybackSettings.from_config(wake_config["playback"])
    )
    api_base_url = os.environ.get("MINIMAX_API_BASE_URL", str(provider_config["api_base_url"]))
    provider = MiniMaxMusicProvider(
        MiniMaxSettings(
            api_base_url=api_base_url,
            endpoint_path=str(provider_config["endpoint_path"]),
            model=str(provider_config["model"]),
            stream=bool(provider_config["stream"]),
            output_format=str(provider_config["output_format"]),
            is_instrumental=bool(provider_config["is_instrumental"]),
            lyrics_optimizer=bool(provider_config["lyrics_optimizer"]),
            request_timeout_s=float(provider_config["request_timeout_s"]),
            audio_setting=dict(provider_config["audio_setting"]),
        ),
        os.environ.get("MINIMAX_API_KEY"),
    )
    storage = WakeMusicStorage(
        project_root / storage_config["root"],
        audio_filename=str(storage_config["audio_filename"]),
        profile_filename=str(storage_config["profile_filename"]),
        prompt_filename=str(storage_config["prompt_filename"]),
        metadata_filename=str(storage_config["metadata_filename"]),
        json_indent=int(storage_config["json_indent"]),
        download_timeout_s=float(provider_config["download_timeout_s"]),
        maximum_download_bytes=int(provider_config["maximum_download_bytes"]),
        postprocessor=postprocessor,
    )
    wake_service = WakeMusicService(registry, wake_config, provider, storage)
    wake_api_config = wake_config["api"]
    combined_app = DreamCoreApiApplication(
        session_api,
        wake_service,
        wake_music_prefix=str(wake_api_config["prefix"]),
        maximum_request_bytes=int(wake_api_config["maximum_request_bytes"]),
    )
    validation_path = project_root / config["eog_validation"]["config_path"]
    validation_config = yaml.safe_load(validation_path.read_text(encoding="utf-8"))
    validation_api = validation_config["api"]
    validation_service = EogValidationService(project_root, registry, validation_config)
    validation_app = EogValidationApiApplication(
        combined_app,
        validation_service,
        prefix=str(validation_api["prefix"]),
        maximum_request_bytes=int(validation_api["maximum_request_bytes"]),
        maximum_focus_window_s=float(validation_api["maximum_focus_window_s"]),
    )
    automatic_config = config["automatic_analysis"]
    analysis_app = AutomaticAnalysisApiApplication(
        validation_app,
        analysis_manager,
        prefix=str(automatic_config["api_prefix"]),
    )
    signal_validation = config["signal_validation_v1"]
    app = SignalValidationApiApplication(
        analysis_app,
        project_root
        / str(signal_validation["output_root"])
        / str(signal_validation["summary_filename"]),
        path=str(signal_validation["dashboard"]["api_path"]),
    )
    host = str(transport["host"])
    port = int(transport["port"])
    print(
        f"DreamCore Session API {transport['api_version']} + Wake Music + EOG Validation "
        f"on http://{host}:{port}"
    )
    try:
        with make_server(host, port, app, server_class=ThreadingWsgiServer) as server:
            server.serve_forever()
    finally:
        analysis_manager.shutdown()


if __name__ == "__main__":
    main()
