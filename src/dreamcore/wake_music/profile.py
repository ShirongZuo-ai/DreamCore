"""Versioned typed records for Wake Music V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceWindow:
    start_s: float
    end_s: float
    selection: str
    transition_time_s: float | None
    preceding_stage: str | None
    wake_stage: str | None


@dataclass(frozen=True)
class PhysiologySummary:
    activity_level: float
    event_rate_level: float
    event_rate_per_min: float
    activity_trend: float
    amplitude_level: float
    feature_row_count: int
    source_channel: str
    source_feature: str


@dataclass(frozen=True)
class MusicDirections:
    register: str
    density: str
    brightness: str
    expressive_strength: str
    energy: str
    energy_curve: str
    style_family: str
    style_label: str
    tempo_character: str


@dataclass(frozen=True)
class GenerationConstraints:
    max_energy: str
    max_percussiveness: str
    allow_aggressive_styles: bool
    allow_vocals: bool


@dataclass(frozen=True)
class WakeMusicProfile:
    profile_version: str
    session_id: str
    source_window: SourceWindow
    physiology: PhysiologySummary
    music: MusicDirections
    constraints: GenerationConstraints
    mapping_version: str
    generation_seed: int
    variation_id: str
    style_selection: str
    mapping_context: str = "exploratory physiology-to-music mapping"

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass(frozen=True)
class PromptConfiguration:
    prompt: str
    prompt_hash: str
    style_family: str
    style_label: str
    variation_id: str
    variation_description: str
    generation_seed: int


@dataclass(frozen=True)
class ProviderResult:
    audio_url: str
    trace_id: str | None
    provider_status: int
    duration_seconds: float | None
    sample_rate_hz: int | None
    channels: int | None
    bitrate: int | None
    provider_size_bytes: int | None
    safe_metadata: dict[str, Any]


@dataclass(frozen=True)
class MasterAudio:
    path: str
    audio_url_path: str
    duration_s: float
    file_size_bytes: int
    sample_rate_hz: int
    channels: int
    bitrate: int | None


@dataclass(frozen=True)
class WakeVersion:
    strategy: str
    start_s: float
    duration_s: float
    encoded_duration_s: float
    fade_out_s: float
    fade_out_start_s: float
    path: str
    audio_url_path: str
    file_size_bytes: int
    sample_rate_hz: int
    channels: int
    bitrate: int | None


@dataclass(frozen=True)
class GenerationRecord:
    generation_id: str
    cache_key: str
    session_id: str
    profile: WakeMusicProfile
    prompt_configuration: PromptConfiguration
    provider: str
    model: str
    generated_at: str
    master_audio: MasterAudio
    wake_version: WakeVersion
    trace_id: str | None
    cached: bool
    external_generation_stochastic: bool = True

    def to_api_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        payload = asdict(self)
        payload["master_audio"]["audio_url"] = payload["master_audio"].pop("audio_url_path")
        payload["wake_version"]["audio_url"] = payload["wake_version"].pop("audio_url_path")
        payload["audio_url"] = payload["wake_version"]["audio_url"]
        return payload
