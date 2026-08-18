"""Local product-playback derivatives for generated Wake Music masters."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class WakeAudioPostprocessingError(RuntimeError):
    """A safe local audio-processing failure."""


@dataclass(frozen=True)
class AudioProperties:
    duration_s: float
    file_size_bytes: int
    sample_rate_hz: int
    channels: int
    bitrate: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WakeVersionResult:
    strategy: str
    start_s: float
    duration_s: float
    fade_out_s: float
    fade_out_start_s: float
    properties: AudioProperties
    reused: bool


@dataclass(frozen=True)
class WakeAudioPlaybackSettings:
    strategy: str
    excerpt_start_s: float
    default_excerpt_seconds: float
    fade_out_seconds: float
    wake_audio_filename: str
    audio_codec: str
    audio_bitrate: str
    ffmpeg_executable: str
    ffprobe_executable: str
    processing_timeout_s: float
    duration_tolerance_s: float

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> WakeAudioPlaybackSettings:
        settings = cls(
            strategy=str(config["strategy"]),
            excerpt_start_s=float(config["excerpt_start_s"]),
            default_excerpt_seconds=float(config["default_excerpt_seconds"]),
            fade_out_seconds=float(config["fade_out_seconds"]),
            wake_audio_filename=str(config["wake_audio_filename"]),
            audio_codec=str(config["audio_codec"]),
            audio_bitrate=str(config["audio_bitrate"]),
            ffmpeg_executable=str(config["ffmpeg_executable"]),
            ffprobe_executable=str(config["ffprobe_executable"]),
            processing_timeout_s=float(config["processing_timeout_s"]),
            duration_tolerance_s=float(config["duration_tolerance_s"]),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.strategy != "first_excerpt_v1":
            raise ValueError(f"unsupported Wake Music playback strategy {self.strategy!r}")
        if self.excerpt_start_s < 0 or self.default_excerpt_seconds <= 0:
            raise ValueError("Wake Music excerpt timing must be positive")
        if not 0 < self.fade_out_seconds <= self.default_excerpt_seconds:
            raise ValueError("Wake Music fade-out must fit within the excerpt")
        if self.processing_timeout_s <= 0 or self.duration_tolerance_s < 0:
            raise ValueError("Wake Music processing limits are invalid")
        if Path(self.wake_audio_filename).name != self.wake_audio_filename:
            raise ValueError("Wake Music derivative filename must not contain a directory")

    @property
    def excerpt_end_s(self) -> float:
        return self.excerpt_start_s + self.default_excerpt_seconds

    @property
    def fade_out_start_s(self) -> float:
        return self.default_excerpt_seconds - self.fade_out_seconds

    @property
    def filter_expression(self) -> str:
        return (
            f"atrim=start={self.excerpt_start_s:g}:duration={self.default_excerpt_seconds:g},"
            "asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={self.fade_out_start_s:g}:d={self.fade_out_seconds:g}"
        )


class WakeAudioPostprocessor:
    """Create and validate a bounded local excerpt without provider access."""

    def __init__(self, settings: WakeAudioPlaybackSettings) -> None:
        self.settings = settings

    def ensure_wake_version(
        self,
        master_path: Path,
        destination: Path,
        existing_metadata: Mapping[str, Any] | None = None,
    ) -> tuple[AudioProperties, WakeVersionResult]:
        master = self.probe(master_path)
        if master.duration_s + self.settings.duration_tolerance_s < self.settings.excerpt_end_s:
            raise WakeAudioPostprocessingError(
                "Wake Music master is shorter than the configured playback excerpt"
            )
        if destination.is_file() and self._metadata_matches(existing_metadata):
            derived = self.probe(destination)
            if self._duration_matches(derived.duration_s):
                return master, self._result(derived, reused=True)

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._temporary_path(destination)
        command = [
            self.settings.ffmpeg_executable,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(master_path),
            "-map",
            "0:a:0",
            "-af",
            self.settings.filter_expression,
            "-codec:a",
            self.settings.audio_codec,
            "-b:a",
            self.settings.audio_bitrate,
            str(temporary_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.settings.processing_timeout_s,
            )
            if completed.returncode != 0:
                raise WakeAudioPostprocessingError("FFmpeg could not create the Wake Version")
            derived = self.probe(temporary_path)
            if not self._duration_matches(derived.duration_s):
                raise WakeAudioPostprocessingError(
                    "FFmpeg produced a Wake Version with an unexpected duration"
                )
            temporary_path.replace(destination)
        except FileNotFoundError as error:
            raise WakeAudioPostprocessingError(
                "Configured FFmpeg executable is unavailable"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise WakeAudioPostprocessingError("Wake Version processing timed out") from error
        finally:
            temporary_path.unlink(missing_ok=True)
        return master, self._result(derived, reused=False)

    def probe(self, path: Path) -> AudioProperties:
        command = [
            self.settings.ffprobe_executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_type,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.settings.processing_timeout_s,
            )
        except FileNotFoundError as error:
            raise WakeAudioPostprocessingError(
                "Configured FFprobe executable is unavailable"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise WakeAudioPostprocessingError("Wake Music audio probe timed out") from error
        if completed.returncode != 0:
            raise WakeAudioPostprocessingError("FFprobe could not inspect Wake Music audio")
        try:
            payload = json.loads(completed.stdout)
            audio_stream = next(
                stream for stream in payload["streams"] if stream.get("codec_type") == "audio"
            )
            media_format = payload["format"]
            bitrate = media_format.get("bit_rate")
            return AudioProperties(
                duration_s=float(media_format["duration"]),
                file_size_bytes=int(media_format["size"]),
                sample_rate_hz=int(audio_stream["sample_rate"]),
                channels=int(audio_stream["channels"]),
                bitrate=int(bitrate) if bitrate is not None else None,
            )
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WakeAudioPostprocessingError(
                "FFprobe returned invalid Wake Music metadata"
            ) from error

    def _metadata_matches(self, metadata: Mapping[str, Any] | None) -> bool:
        if not metadata:
            return False
        expected = {
            "strategy": self.settings.strategy,
            "start_s": self.settings.excerpt_start_s,
            "duration_s": self.settings.default_excerpt_seconds,
            "fade_out_s": self.settings.fade_out_seconds,
        }
        return all(metadata.get(key) == value for key, value in expected.items())

    def _duration_matches(self, duration_s: float) -> bool:
        return (
            abs(duration_s - self.settings.default_excerpt_seconds)
            <= self.settings.duration_tolerance_s
        )

    def _result(self, properties: AudioProperties, *, reused: bool) -> WakeVersionResult:
        return WakeVersionResult(
            strategy=self.settings.strategy,
            start_s=self.settings.excerpt_start_s,
            duration_s=self.settings.default_excerpt_seconds,
            fade_out_s=self.settings.fade_out_seconds,
            fade_out_start_s=self.settings.fade_out_start_s,
            properties=properties,
            reused=reused,
        )

    @staticmethod
    def _temporary_path(destination: Path) -> Path:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{destination.stem}-", suffix=destination.suffix, dir=destination.parent
        )
        os.close(descriptor)
        Path(name).unlink(missing_ok=True)
        return Path(name)
