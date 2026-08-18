"""Local Wake Music artifacts, audio download, and exact-generation cache."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dreamcore.wake_music.postprocess import WakeAudioPostprocessor
from dreamcore.wake_music.profile import (
    GenerationRecord,
    MasterAudio,
    PromptConfiguration,
    ProviderResult,
    WakeMusicProfile,
    WakeVersion,
)
from dreamcore.wake_music.provider import ProviderError


class WakeMusicStorage:
    def __init__(
        self,
        root: Path,
        *,
        audio_filename: str,
        profile_filename: str,
        prompt_filename: str,
        metadata_filename: str,
        json_indent: int,
        download_timeout_s: float,
        maximum_download_bytes: int,
        postprocessor: WakeAudioPostprocessor,
    ) -> None:
        self.root = Path(root)
        self.audio_filename = audio_filename
        self.profile_filename = profile_filename
        self.prompt_filename = prompt_filename
        self.metadata_filename = metadata_filename
        self.json_indent = json_indent
        self.download_timeout_s = download_timeout_s
        self.maximum_download_bytes = maximum_download_bytes
        self.postprocessor = postprocessor

    def generation_id(self, cache_key: str) -> str:
        return f"wm-{cache_key[:16]}"

    def cache_key(
        self,
        profile: WakeMusicProfile,
        prompt: PromptConfiguration,
        provider: str,
        model: str,
    ) -> str:
        material = {
            "session_id": profile.session_id,
            "source_window": asdict(profile.source_window),
            "profile_version": profile.profile_version,
            "mapping_version": profile.mapping_version,
            "style": profile.music.style_family,
            "seed": profile.generation_seed,
            "provider": provider,
            "model": model,
            "prompt_hash": prompt.prompt_hash,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def lookup(self, session_id: str, cache_key: str) -> GenerationRecord | None:
        generation_id = self.generation_id(cache_key)
        directory = self._directory(session_id, generation_id)
        metadata_path = directory / self.metadata_filename
        audio_path = directory / self.audio_filename
        profile_path = directory / self.profile_filename
        prompt_path = directory / self.prompt_filename
        if not all(
            path.is_file() for path in (metadata_path, audio_path, profile_path, prompt_path)
        ):
            return None
        return self._load_record(directory, cached=True)

    def get(self, generation_id: str) -> GenerationRecord:
        matches = tuple(self.root.glob(f"*/{generation_id}/{self.metadata_filename}"))
        if len(matches) != 1:
            raise LookupError(f"Wake Music generation {generation_id!r} not found")
        metadata_path = matches[0]
        directory = metadata_path.parent
        return self._load_record(directory, cached=False)

    def latest(self, session_id: str) -> GenerationRecord | None:
        """Return the newest complete local generation for a session."""

        if not _safe_identifier(session_id):
            raise ValueError("session identifier contains unsafe characters")
        directory = self.root / session_id
        if not directory.is_dir():
            return None
        candidates = []
        for metadata_path in directory.glob(f"*/{self.metadata_filename}"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidates.append((str(metadata.get("generated_at", "")), metadata_path.parent))
        if not candidates:
            return None
        return self._load_record(max(candidates, key=lambda item: item[0])[1], cached=True)

    def audio_path(self, generation_id: str, *, version: str = "wake") -> Path:
        record = self.get(generation_id)
        if version == "wake":
            path = Path(record.wake_version.path)
        elif version == "master":
            path = Path(record.master_audio.path)
        else:
            raise ValueError(f"unsupported Wake Music audio version {version!r}")
        if not path.is_file():
            raise LookupError(f"Wake Music audio for {generation_id!r} not found")
        return path

    def save(
        self,
        *,
        generation_id: str,
        cache_key: str,
        profile: WakeMusicProfile,
        prompt: PromptConfiguration,
        provider_name: str,
        model: str,
        generated_at: str,
        provider_result: ProviderResult,
        audio_url_path: str,
    ) -> GenerationRecord:
        directory = self._directory(profile.session_id, generation_id)
        directory.mkdir(parents=True, exist_ok=True)
        audio_path = directory / self.audio_filename
        self._download(provider_result.audio_url, audio_path)
        metadata = {
            "generation_id": generation_id,
            "cache_key": cache_key,
            "session_id": profile.session_id,
            "source_window": asdict(profile.source_window),
            "profile_version": profile.profile_version,
            "mapping_version": profile.mapping_version,
            "style": profile.music.style_family,
            "style_label": profile.music.style_label,
            "variation_id": profile.variation_id,
            "generation_seed": profile.generation_seed,
            "provider": provider_name,
            "model": model,
            "generated_at": generated_at,
            "prompt_hash": prompt.prompt_hash,
            "audio_url_path": audio_url_path,
            "trace_id": provider_result.trace_id,
            "provider_audio_metadata": {
                "sample_rate_hz": provider_result.sample_rate_hz,
                "channels": provider_result.channels,
                "bitrate": provider_result.bitrate,
                "provider_size_bytes": provider_result.provider_size_bytes,
            },
            "provider_metadata": provider_result.safe_metadata,
            "provider_url_persisted": False,
            "external_generation_stochastic": True,
        }
        metadata = self._ensure_playback_metadata(directory, metadata)
        (directory / self.profile_filename).write_text(
            json.dumps(profile.to_dict(), indent=self.json_indent, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (directory / self.prompt_filename).write_text(prompt.prompt + "\n", encoding="utf-8")
        (directory / self.metadata_filename).write_text(
            json.dumps(metadata, indent=self.json_indent, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return _record_from_files(
            metadata, profile.to_dict(), prompt.prompt, directory=directory, cached=False
        )

    def _load_record(self, directory: Path, *, cached: bool) -> GenerationRecord:
        metadata_path = directory / self.metadata_filename
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        migrated = self._ensure_playback_metadata(directory, raw)
        if migrated != raw:
            metadata_path.write_text(
                json.dumps(migrated, indent=self.json_indent, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        profile_raw = json.loads((directory / self.profile_filename).read_text(encoding="utf-8"))
        prompt_text = (directory / self.prompt_filename).read_text(encoding="utf-8")
        return _record_from_files(
            migrated, profile_raw, prompt_text, directory=directory, cached=cached
        )

    def _ensure_playback_metadata(
        self, directory: Path, metadata: Mapping[str, Any]
    ) -> dict[str, Any]:
        master_path = directory / self.audio_filename
        wake_path = directory / self.postprocessor.settings.wake_audio_filename
        existing_wake = metadata.get("wake_version")
        master, wake = self.postprocessor.ensure_wake_version(
            master_path,
            wake_path,
            existing_wake if isinstance(existing_wake, Mapping) else None,
        )
        audio_url_path = str(
            metadata.get(
                "audio_url_path",
                existing_wake.get("audio_url_path") if isinstance(existing_wake, Mapping) else "",
            )
        )
        if not audio_url_path:
            audio_url_path = f"/api/wake-music/{metadata['generation_id']}/audio"
        migrated = dict(metadata)
        provider_audio_metadata = migrated.pop(
            "audio_metadata", migrated.get("provider_audio_metadata", {})
        )
        for legacy_key in (
            "audio_path",
            "audio_url_path",
            "file_size_bytes",
            "duration_seconds",
        ):
            migrated.pop(legacy_key, None)
        migrated["provider_audio_metadata"] = provider_audio_metadata
        migrated["master_audio"] = {
            "duration_s": master.duration_s,
            "path": self.audio_filename,
            "audio_url_path": f"{audio_url_path}/master",
            "file_size_bytes": master.file_size_bytes,
            "sample_rate_hz": master.sample_rate_hz,
            "channels": master.channels,
            "bitrate": master.bitrate,
        }
        migrated["wake_version"] = {
            "strategy": wake.strategy,
            "start_s": wake.start_s,
            "duration_s": wake.duration_s,
            "encoded_duration_s": wake.properties.duration_s,
            "fade_out_s": wake.fade_out_s,
            "fade_out_start_s": wake.fade_out_start_s,
            "path": self.postprocessor.settings.wake_audio_filename,
            "audio_url_path": audio_url_path,
            "file_size_bytes": wake.properties.file_size_bytes,
            "sample_rate_hz": wake.properties.sample_rate_hz,
            "channels": wake.properties.channels,
            "bitrate": wake.properties.bitrate,
        }
        return migrated

    def _directory(self, session_id: str, generation_id: str) -> Path:
        if not _safe_identifier(session_id) or not _safe_identifier(generation_id):
            raise ValueError("session and generation identifiers contain unsafe characters")
        return self.root / session_id / generation_id

    def _download(self, audio_url: str, destination: Path) -> None:
        request = Request(audio_url, method="GET")
        try:
            with urlopen(request, timeout=self.download_timeout_s) as response:
                declared_length = response.headers.get("Content-Length")
                if declared_length and int(declared_length) > self.maximum_download_bytes:
                    raise ProviderError(
                        "audio_download_too_large", "Generated audio exceeds local limit"
                    )
                content = response.read(self.maximum_download_bytes + 1)
        except HTTPError as error:
            code = (
                "expired_provider_url" if error.code in {403, 404, 410} else "audio_download_failed"
            )
            message = (
                "MiniMax audio URL expired before download"
                if code == "expired_provider_url"
                else f"Generated audio download returned HTTP {error.code}"
            )
            raise ProviderError(code, message) from error
        except TimeoutError as error:
            raise ProviderError(
                "audio_download_timeout", "Generated audio download timed out", 504
            ) from error
        except (URLError, OSError) as error:
            raise ProviderError(
                "audio_download_failed", "Generated audio download failed"
            ) from error
        if not content:
            raise ProviderError("audio_download_failed", "Generated audio download was empty")
        if len(content) > self.maximum_download_bytes:
            raise ProviderError("audio_download_too_large", "Generated audio exceeds local limit")
        destination.write_bytes(content)


def _safe_identifier(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in "-_." for character in value)


def _record_from_files(
    metadata: Mapping[str, Any],
    profile_raw: Mapping[str, Any],
    prompt_text: str,
    *,
    directory: Path,
    cached: bool,
) -> GenerationRecord:
    from dreamcore.wake_music.profile import (
        GenerationConstraints,
        MusicDirections,
        PhysiologySummary,
        SourceWindow,
    )

    profile = WakeMusicProfile(
        profile_version=str(profile_raw["profile_version"]),
        session_id=str(profile_raw["session_id"]),
        source_window=SourceWindow(**profile_raw["source_window"]),
        physiology=PhysiologySummary(**profile_raw["physiology"]),
        music=MusicDirections(**profile_raw["music"]),
        constraints=GenerationConstraints(**profile_raw["constraints"]),
        mapping_version=str(profile_raw["mapping_version"]),
        generation_seed=int(profile_raw["generation_seed"]),
        variation_id=str(profile_raw["variation_id"]),
        style_selection=str(profile_raw["style_selection"]),
        mapping_context=str(
            profile_raw.get("mapping_context", "exploratory physiology-to-music mapping")
        ),
    )
    prompt = PromptConfiguration(
        prompt=prompt_text.rstrip("\n"),
        prompt_hash=str(metadata["prompt_hash"]),
        style_family=str(metadata["style"]),
        style_label=str(metadata["style_label"]),
        variation_id=str(metadata["variation_id"]),
        variation_description="stored in prompt",
        generation_seed=int(metadata["generation_seed"]),
    )
    master_raw = metadata["master_audio"]
    wake_raw = metadata["wake_version"]
    return GenerationRecord(
        generation_id=str(metadata["generation_id"]),
        cache_key=str(metadata["cache_key"]),
        session_id=str(metadata["session_id"]),
        profile=profile,
        prompt_configuration=prompt,
        provider=str(metadata["provider"]),
        model=str(metadata["model"]),
        generated_at=str(metadata["generated_at"]),
        master_audio=MasterAudio(
            path=str((directory / str(master_raw["path"])).resolve()),
            audio_url_path=str(master_raw["audio_url_path"]),
            duration_s=float(master_raw["duration_s"]),
            file_size_bytes=int(master_raw["file_size_bytes"]),
            sample_rate_hz=int(master_raw["sample_rate_hz"]),
            channels=int(master_raw["channels"]),
            bitrate=int(master_raw["bitrate"]) if master_raw.get("bitrate") else None,
        ),
        wake_version=WakeVersion(
            strategy=str(wake_raw["strategy"]),
            start_s=float(wake_raw["start_s"]),
            duration_s=float(wake_raw["duration_s"]),
            encoded_duration_s=float(wake_raw["encoded_duration_s"]),
            fade_out_s=float(wake_raw["fade_out_s"]),
            fade_out_start_s=float(wake_raw["fade_out_start_s"]),
            path=str((directory / str(wake_raw["path"])).resolve()),
            audio_url_path=str(wake_raw["audio_url_path"]),
            file_size_bytes=int(wake_raw["file_size_bytes"]),
            sample_rate_hz=int(wake_raw["sample_rate_hz"]),
            channels=int(wake_raw["channels"]),
            bitrate=int(wake_raw["bitrate"]) if wake_raw.get("bitrate") else None,
        ),
        trace_id=str(metadata["trace_id"]) if metadata.get("trace_id") else None,
        cached=cached,
        external_generation_stochastic=bool(metadata.get("external_generation_stochastic", True)),
    )
