"""Backend-only MiniMax Music provider client."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPResponse
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from dreamcore.wake_music.profile import ProviderResult


class ProviderError(RuntimeError):
    """Safe provider failure suitable for conversion to a local API error."""

    def __init__(self, code: str, message: str, http_status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class WakeMusicProvider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str) -> ProviderResult: ...


@dataclass(frozen=True)
class MiniMaxSettings:
    api_base_url: str
    endpoint_path: str
    model: str
    stream: bool
    output_format: str
    is_instrumental: bool
    lyrics_optimizer: bool
    request_timeout_s: float
    audio_setting: Mapping[str, Any]


class MiniMaxMusicProvider:
    """Non-streaming URL-output integration following MiniMax's official contract."""

    name = "minimax"

    def __init__(self, settings: MiniMaxSettings, api_key: str | None) -> None:
        self.settings = settings
        self.model = settings.model
        self._api_key = api_key

    def generate(self, prompt: str) -> ProviderResult:
        if not self._api_key:
            raise ProviderError(
                "missing_api_key",
                "MiniMax API key is not configured in the backend environment",
                503,
            )
        payload = {
            "model": self.settings.model,
            "prompt": prompt,
            "stream": self.settings.stream,
            "output_format": self.settings.output_format,
            "audio_setting": dict(self.settings.audio_setting),
            "lyrics_optimizer": self.settings.lyrics_optimizer,
            "is_instrumental": self.settings.is_instrumental,
        }
        request = Request(
            urljoin(
                self.settings.api_base_url.rstrip("/") + "/",
                self.settings.endpoint_path.lstrip("/"),
            ),
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.request_timeout_s) as response:
                raw = _read_json(response)
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ProviderError(
                    "authentication_failed",
                    "MiniMax authentication failed; check the backend API key and configured host",
                    502,
                ) from error
            if error.code == 429:
                raise ProviderError(
                    "rate_limited", "Rate limited — please try again shortly", 429
                ) from error
            raise ProviderError(
                "provider_http_error", f"MiniMax returned HTTP {error.code}", 502
            ) from error
        except TimeoutError as error:
            raise ProviderError("provider_timeout", "MiniMax generation timed out", 504) from error
        except (URLError, OSError) as error:
            raise ProviderError(
                "provider_network_error", "MiniMax network request failed", 502
            ) from error

        if not isinstance(raw, Mapping):
            raise ProviderError("invalid_provider_response", "MiniMax returned invalid JSON")
        base_resp = raw.get("base_resp")
        if not isinstance(base_resp, Mapping):
            raise ProviderError(
                "invalid_provider_response", "MiniMax response omitted status metadata"
            )
        status_code = base_resp.get("status_code")
        if status_code != 0:
            message = str(base_resp.get("status_msg") or "MiniMax generation failed")
            lowered = message.casefold()
            if "rate" in lowered or "limit" in lowered:
                raise ProviderError("rate_limited", "Rate limited — please try again shortly", 429)
            if "auth" in lowered or "token" in lowered or "api key" in lowered:
                raise ProviderError("authentication_failed", "MiniMax authentication failed", 502)
            raise ProviderError("provider_status_error", f"MiniMax generation failed: {message}")
        data = raw.get("data")
        if not isinstance(data, Mapping):
            raise ProviderError("invalid_provider_response", "MiniMax response omitted audio data")
        audio_url = data.get("audio")
        if not isinstance(audio_url, str) or not audio_url.startswith(("https://", "http://")):
            raise ProviderError(
                "missing_audio_url", "MiniMax response did not contain an audio URL"
            )
        extra = raw.get("extra_info") if isinstance(raw.get("extra_info"), Mapping) else {}
        duration_ms = _optional_number(extra.get("music_duration"))
        safe_metadata = {
            "data_status": data.get("status"),
            "trace_id": raw.get("trace_id"),
            "extra_info": {
                key: extra.get(key)
                for key in (
                    "music_duration",
                    "music_sample_rate",
                    "music_channel",
                    "bitrate",
                    "music_size",
                )
            },
            "base_status_code": status_code,
            "base_status_message": base_resp.get("status_msg"),
        }
        return ProviderResult(
            audio_url=audio_url,
            trace_id=str(raw["trace_id"]) if raw.get("trace_id") else None,
            provider_status=int(data.get("status", 0)),
            duration_seconds=duration_ms / 1000.0 if duration_ms is not None else None,
            sample_rate_hz=_optional_int(extra.get("music_sample_rate")),
            channels=_optional_int(extra.get("music_channel")),
            bitrate=_optional_int(extra.get("bitrate")),
            provider_size_bytes=_optional_int(extra.get("music_size")),
            safe_metadata=safe_metadata,
        )


def _read_json(response: HTTPResponse) -> Any:
    try:
        return json.loads(response.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderError("invalid_provider_response", "MiniMax returned invalid JSON") from error


def _optional_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
