from __future__ import annotations

import io
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from dreamcore.api.wake_music import DreamCoreApiApplication
from dreamcore.wake_music.mapping import (
    build_profile,
    manual_window,
    select_wake_window,
)
from dreamcore.wake_music.postprocess import (
    AudioProperties,
    WakeAudioPlaybackSettings,
    WakeAudioPostprocessor,
    WakeVersionResult,
)
from dreamcore.wake_music.profile import PhysiologySummary, ProviderResult
from dreamcore.wake_music.prompt import build_prompt
from dreamcore.wake_music.provider import (
    MiniMaxMusicProvider,
    MiniMaxSettings,
    ProviderError,
)
from dreamcore.wake_music.service import WakeMusicService
from dreamcore.wake_music.storage import WakeMusicStorage


@pytest.fixture(scope="module")
def wake_config():
    return yaml.safe_load(Path("configs/default.yaml").read_text())["wake_music"]


def physiology(
    *, activity: float = 0.5, event_rate: float = 5.0, trend: float = 0.0, amplitude: float = 0.5
) -> PhysiologySummary:
    return PhysiologySummary(
        activity_level=activity,
        event_rate_level=min(event_rate / 10.0, 1.0),
        event_rate_per_min=event_rate,
        activity_trend=trend,
        amplitude_level=amplitude,
        feature_row_count=60,
        source_channel="configured EOG fixture",
        source_feature="eye_movement_activity_v1",
    )


def profile(wake_config, **changes):
    return build_profile(
        session_id="session-fixture",
        source_window=manual_window(100.0, 200.0, 300.0),
        physiology=changes.pop("physiology", physiology()),
        requested_style=changes.pop("style", "soft_piano_ambient"),
        generation_seed=changes.pop("seed", 42),
        config=wake_config,
    )


def test_last_annotation_confirmed_wake_transition_is_selected(wake_config):
    annotations = [
        {"start_seconds": 0.0, "duration_seconds": 300.0, "label": "N2"},
        {"start_seconds": 300.0, "duration_seconds": 60.0, "label": "W"},
        {"start_seconds": 360.0, "duration_seconds": 120.0, "label": "N1"},
        {"start_seconds": 480.0, "duration_seconds": 600.0, "label": "W"},
    ]
    selected = select_wake_window(annotations, wake_config["wake_window"])
    assert selected.end_s == 480.0
    assert selected.start_s == 0.0
    assert selected.preceding_stage == "N1"
    assert selected.wake_stage == "W"


def test_mapping_is_monotonic_and_energy_is_capped(wake_config):
    low = profile(wake_config, physiology=physiology(activity=0.1, event_rate=0.5))
    high = profile(
        wake_config,
        physiology=physiology(activity=0.9, event_rate=20.0, trend=0.2, amplitude=0.9),
    )
    registers = ["low", "mid", "high"]
    densities = ["sparse", "moderate", "moderately_active"]
    brightness = ["warm", "gradually_brighter", "noticeably_brighter"]
    assert registers.index(high.music.register) >= registers.index(low.music.register)
    assert densities.index(high.music.density) >= densities.index(low.music.density)
    assert brightness.index(high.music.brightness) >= brightness.index(low.music.brightness)
    assert high.music.energy in {"gentle", "calm_to_moderately_awake"}
    assert high.constraints.max_energy == wake_config["constraints"]["max_energy"]
    assert not high.constraints.allow_vocals
    assert not high.constraints.allow_aggressive_styles


@pytest.mark.parametrize("style", ["auto", *range(6)])
def test_every_style_prompt_enforces_instrumental_and_gentle_constraints(wake_config, style):
    style_name = "auto" if style == "auto" else tuple(wake_config["styles"])[style]
    built = build_prompt(profile(wake_config, style=style_name), wake_config)
    lowered = built.prompt.casefold()
    assert "instrumental" in lowered
    assert "no vocals" in lowered
    assert "never aggressive" in lowered
    assert "no dramatic climax" in lowered


def test_prompt_configuration_is_seeded_and_bounded(wake_config):
    first = build_prompt(profile(wake_config, seed=42), wake_config)
    repeated = build_prompt(profile(wake_config, seed=42), wake_config)
    varied = build_prompt(profile(wake_config, seed=43), wake_config)
    assert first == repeated
    assert first.prompt_hash != varied.prompt_hash
    assert varied.variation_description in wake_config["styles"]["soft_piano_ambient"]["variants"]


def test_provider_requires_backend_key_and_sends_instrumental_without_lyrics(wake_config):
    raw = wake_config["provider"]
    settings = MiniMaxSettings(
        api_base_url=raw["api_base_url"],
        endpoint_path=raw["endpoint_path"],
        model=raw["model"],
        stream=raw["stream"],
        output_format=raw["output_format"],
        is_instrumental=raw["is_instrumental"],
        lyrics_optimizer=raw["lyrics_optimizer"],
        request_timeout_s=raw["request_timeout_s"],
        audio_setting=raw["audio_setting"],
    )
    with pytest.raises(ProviderError, match="not configured") as missing:
        MiniMaxMusicProvider(settings, None).generate("gentle instrumental")
    assert missing.value.code == "missing_api_key"

    response = io.BytesIO(
        json.dumps(
            {
                "data": {"audio": "https://audio.example/test.mp3", "status": 2},
                "trace_id": "safe-trace",
                "extra_info": {"music_duration": 1000},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }
        ).encode()
    )
    response.__enter__ = lambda value: value
    response.__exit__ = lambda *_: None
    with patch("dreamcore.wake_music.provider.urlopen", return_value=response) as opened:
        MiniMaxMusicProvider(settings, "test-only-secret").generate("gentle instrumental")
    request = opened.call_args.args[0]
    payload = json.loads(request.data)
    assert payload["model"] == "music-2.6-free"
    assert payload["is_instrumental"] is True
    assert payload["stream"] is False
    assert payload["output_format"] == "url"
    assert "lyrics" not in payload


class FakeProvider:
    name = "minimax"
    model = "music-2.6-free"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return ProviderResult(
            audio_url="https://audio.example/generated.mp3",
            trace_id="trace-fixture",
            provider_status=2,
            duration_seconds=1.0,
            sample_rate_hz=44100,
            channels=2,
            bitrate=256000,
            provider_size_bytes=8,
            safe_metadata={"trace_id": "trace-fixture"},
        )


class FakeRegistry:
    def get_session_by_id(self, session_id):
        return SimpleNamespace(recording=SimpleNamespace(duration_seconds=500.0))

    def load_annotations(self, session_id, annotation_type):
        return (
            {"start_seconds": 0.0, "duration_seconds": 200.0, "label": "N2"},
            {"start_seconds": 200.0, "duration_seconds": 300.0, "label": "W"},
        )

    def load_derived_window(self, session_id, metric, start_s, end_s):
        return tuple(
            {
                "source_channel": "fixture EOG",
                "window_end_s": float(index),
                "activity_score": index / 100.0,
                "amplitude_score": 0.4,
                "event_rate_per_min": 4.0,
                "signal_quality": "valid",
            }
            for index in range(1, 101)
        )


class FakePostprocessor:
    def __init__(self, wake_config):
        self.settings = WakeAudioPlaybackSettings.from_config(wake_config["playback"])
        self.created = 0

    def ensure_wake_version(self, master_path, destination, existing_metadata=None):
        master = AudioProperties(120.0, master_path.stat().st_size, 44100, 2, 256000)
        expected = {
            "strategy": self.settings.strategy,
            "start_s": self.settings.excerpt_start_s,
            "duration_s": self.settings.default_excerpt_seconds,
            "fade_out_s": self.settings.fade_out_seconds,
        }
        reused = (
            destination.is_file()
            and existing_metadata
            and all(existing_metadata.get(key) == value for key, value in expected.items())
        )
        if not reused:
            destination.write_bytes(b"ID3wake-version")
            self.created += 1
        properties = AudioProperties(
            self.settings.default_excerpt_seconds,
            destination.stat().st_size,
            44100,
            2,
            256000,
        )
        return master, WakeVersionResult(
            strategy=self.settings.strategy,
            start_s=self.settings.excerpt_start_s,
            duration_s=self.settings.default_excerpt_seconds,
            fade_out_s=self.settings.fade_out_seconds,
            fade_out_start_s=self.settings.fade_out_start_s,
            properties=properties,
            reused=bool(reused),
        )


def storage(tmp_path, wake_config, postprocessor=None):
    raw = wake_config["storage"]
    provider = wake_config["provider"]
    return WakeMusicStorage(
        tmp_path,
        audio_filename=raw["audio_filename"],
        profile_filename=raw["profile_filename"],
        prompt_filename=raw["prompt_filename"],
        metadata_filename=raw["metadata_filename"],
        json_indent=raw["json_indent"],
        download_timeout_s=provider["download_timeout_s"],
        maximum_download_bytes=provider["maximum_download_bytes"],
        postprocessor=postprocessor or FakePostprocessor(wake_config),
    )


class AudioResponse(io.BytesIO):
    headers = {"Content-Length": "8"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def test_storage_downloads_provider_url_and_cache_reuses_local_audio(tmp_path, wake_config):
    provider = FakeProvider()
    postprocessor = FakePostprocessor(wake_config)
    service = WakeMusicService(
        FakeRegistry(),
        wake_config,
        provider,
        storage(tmp_path, wake_config, postprocessor),
    )
    with patch(
        "dreamcore.wake_music.storage.urlopen",
        side_effect=lambda *_args, **_kwargs: AudioResponse(b"ID3audio"),
    ) as download:
        first = service.generate(session_id="session-fixture", style="classical_chamber", seed=42)
        cached = service.generate(session_id="session-fixture", style="classical_chamber", seed=42)
        varied = service.generate(session_id="session-fixture", style="classical_chamber", seed=43)
    assert provider.calls == 2
    assert download.call_count == 2
    assert cached.cached is True
    assert first.master_audio.path == cached.master_audio.path
    assert Path(first.master_audio.path).read_bytes() == b"ID3audio"
    assert Path(first.wake_version.path).read_bytes() == b"ID3wake-version"
    assert first.wake_version.duration_s == wake_config["playback"]["default_excerpt_seconds"]
    assert first.wake_version.fade_out_s == wake_config["playback"]["fade_out_seconds"]
    assert postprocessor.created == 2
    assert first.generation_id != varied.generation_id
    assert first.prompt_configuration.prompt_hash != varied.prompt_configuration.prompt_hash
    metadata = json.loads((Path(first.master_audio.path).parent / "metadata.json").read_text())
    assert metadata["provider_url_persisted"] is False
    assert "audio.example" not in json.dumps(metadata)
    assert metadata["master_audio"]["path"] == "wake_music.mp3"
    assert metadata["wake_version"]["path"] == "wake_music_60s.mp3"


def test_postprocessor_preserves_master_applies_config_and_reuses_excerpt(tmp_path, wake_config):
    raw = dict(wake_config["playback"])
    raw.update(default_excerpt_seconds=10.0, fade_out_seconds=2.0)
    processor = WakeAudioPostprocessor(WakeAudioPlaybackSettings.from_config(raw))
    master = tmp_path / "wake_music.mp3"
    wake = tmp_path / "wake_music_60s.mp3"
    master_bytes = b"untouched-provider-master"
    master.write_bytes(master_bytes)
    master_properties = AudioProperties(20.0, len(master_bytes), 44100, 2, 256000)
    wake_properties = AudioProperties(10.0, 320000, 44100, 2, 256000)

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"locally-derived-wake-version")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    with (
        patch.object(
            processor,
            "probe",
            side_effect=[master_properties, wake_properties],
        ),
        patch("dreamcore.wake_music.postprocess.subprocess.run", side_effect=fake_run) as run,
    ):
        _, created = processor.ensure_wake_version(master, wake)
    assert master.read_bytes() == master_bytes
    assert wake.read_bytes() == b"locally-derived-wake-version"
    assert created.duration_s == 10.0
    assert created.fade_out_start_s == 8.0
    command = run.call_args.args[0]
    assert "afade=t=out:st=8:d=2" in command[command.index("-af") + 1]

    metadata = {
        "strategy": created.strategy,
        "start_s": created.start_s,
        "duration_s": created.duration_s,
        "fade_out_s": created.fade_out_s,
    }
    with (
        patch.object(
            processor,
            "probe",
            side_effect=[master_properties, wake_properties],
        ),
        patch("dreamcore.wake_music.postprocess.subprocess.run") as rerun,
    ):
        _, reused = processor.ensure_wake_version(master, wake, metadata)
    assert reused.reused is True
    rerun.assert_not_called()


def test_existing_generation_excerpt_does_not_call_provider(tmp_path, wake_config):
    provider = FakeProvider()
    postprocessor = FakePostprocessor(wake_config)
    service = WakeMusicService(
        FakeRegistry(),
        wake_config,
        provider,
        storage(tmp_path, wake_config, postprocessor),
    )
    with patch(
        "dreamcore.wake_music.storage.urlopen",
        side_effect=lambda *_args, **_kwargs: AudioResponse(b"ID3audio"),
    ):
        generated = service.generate(
            session_id="session-fixture", style="classical_chamber", seed=42
        )
    calls_after_generation = provider.calls
    Path(generated.wake_version.path).unlink()
    loaded = service.get(generated.generation_id)
    assert provider.calls == calls_after_generation
    assert Path(loaded.wake_version.path).is_file()


def test_wake_and_master_audio_routes_support_byte_ranges(tmp_path, wake_config):
    provider = FakeProvider()
    service = WakeMusicService(
        FakeRegistry(), wake_config, provider, storage(tmp_path, wake_config)
    )
    with patch(
        "dreamcore.wake_music.storage.urlopen",
        side_effect=lambda *_args, **_kwargs: AudioResponse(b"ID3audio"),
    ):
        generated = service.generate(
            session_id="session-fixture", style="classical_chamber", seed=42
        )
    app = DreamCoreApiApplication(
        lambda environ, start_response: [],
        service,
        wake_music_prefix=wake_config["api"]["prefix"],
        maximum_request_bytes=wake_config["api"]["maximum_request_bytes"],
    )

    for suffix, expected in (("audio", b"ID3w"), ("audio/master", b"ID3a")):
        captured = {}

        def start_response(status, headers, captured=captured):
            captured["status"] = status
            captured["headers"] = dict(headers)

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": f"/api/wake-music/{generated.generation_id}/{suffix}",
                    "HTTP_RANGE": "bytes=0-3",
                },
                start_response,
            )
        )
        assert captured["status"].startswith("206")
        assert captured["headers"]["Accept-Ranges"] == "bytes"
        assert body == expected


def test_same_profile_seed_is_reproducible(wake_config):
    original = profile(wake_config, seed=55, style="auto")
    repeat = profile(wake_config, seed=55, style="auto")
    changed = replace(original, generation_seed=56)
    assert original == repeat
    assert build_prompt(original, wake_config) == build_prompt(repeat, wake_config)
    assert changed.generation_seed != original.generation_seed


def test_generation_api_returns_controlled_missing_key_without_secret(tmp_path, wake_config):
    raw = wake_config["provider"]
    provider = MiniMaxMusicProvider(
        MiniMaxSettings(
            api_base_url=raw["api_base_url"],
            endpoint_path=raw["endpoint_path"],
            model=raw["model"],
            stream=raw["stream"],
            output_format=raw["output_format"],
            is_instrumental=raw["is_instrumental"],
            lyrics_optimizer=raw["lyrics_optimizer"],
            request_timeout_s=raw["request_timeout_s"],
            audio_setting=raw["audio_setting"],
        ),
        None,
    )
    service = WakeMusicService(
        FakeRegistry(), wake_config, provider, storage(tmp_path, wake_config)
    )
    app = DreamCoreApiApplication(
        lambda environ, start_response: [],
        service,
        wake_music_prefix=wake_config["api"]["prefix"],
        maximum_request_bytes=wake_config["api"]["maximum_request_bytes"],
    )
    body = json.dumps({"session_id": "session-fixture", "style": "soft_piano_ambient"}).encode()
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    result = b"".join(
        app(
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/api/wake-music/generate",
                "CONTENT_LENGTH": str(len(body)),
                "wsgi.input": io.BytesIO(body),
            },
            start_response,
        )
    )
    payload = json.loads(result)
    assert captured["status"].startswith("503")
    assert payload["error"]["code"] == "missing_api_key"
    assert "Authorization" not in result.decode()
