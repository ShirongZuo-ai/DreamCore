"""Separated local generation API for exploratory AI Wake Music."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from dreamcore.api.http import ApiError, SessionApiApplication
from dreamcore.wake_music.mapping import WakeWindowUnavailableError
from dreamcore.wake_music.postprocess import WakeAudioPostprocessingError
from dreamcore.wake_music.provider import ProviderError
from dreamcore.wake_music.service import WakeMusicService

WAKE_MUSIC_API_VERSION = "v1"


class DreamCoreApiApplication:
    """Route Session reads and Wake Music generation through distinct services."""

    def __init__(
        self,
        session_api: SessionApiApplication,
        wake_music_service: WakeMusicService,
        *,
        wake_music_prefix: str,
        maximum_request_bytes: int,
    ) -> None:
        self.session_api = session_api
        self.wake_music_service = wake_music_service
        self.prefix = wake_music_prefix.rstrip("/")
        self.maximum_request_bytes = maximum_request_bytes

    def __call__(self, environ, start_response: Callable):
        path = unquote(str(environ.get("PATH_INFO", "")))
        if not path.startswith(self.prefix):
            return self.session_api(environ, start_response)
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        try:
            if method == "OPTIONS":
                return self._json_response(start_response, 204, None)
            if path == f"{self.prefix}/generate":
                if method != "POST":
                    raise ApiError(405, "method_not_allowed", "Wake Music generation requires POST")
                payload = self._request_json(environ)
                variation_of = payload.get("new_variation_of")
                if variation_of is not None:
                    if not isinstance(variation_of, str) or not variation_of:
                        raise ValueError("new_variation_of must be a generation ID")
                    style = payload.get("style")
                    if style is not None and not isinstance(style, str):
                        raise ValueError("style must be a string")
                    record = self.wake_music_service.new_variation(
                        generation_id=variation_of, style=style
                    )
                else:
                    requested_seed = self._optional_integer(payload, "generation_seed")
                    record = self.wake_music_service.generate(
                        session_id=self._string(payload, "session_id"),
                        style=str(payload.get("style", "auto")),
                        seed=(
                            requested_seed
                            if requested_seed is not None
                            else int(self.wake_music_service.config["default_generation_seed"])
                        ),
                        force_new=bool(payload.get("force_new", False)),
                        window_start_s=self._optional_float(payload, "window_start_s"),
                        window_end_s=self._optional_float(payload, "window_end_s"),
                    )
                return self._json_response(start_response, 200, self._ok(record.to_api_dict()))
            match = re.fullmatch(rf"{re.escape(self.prefix)}/sessions/([^/]+)/latest", path)
            if match:
                if method not in {"GET", "HEAD"}:
                    raise ApiError(405, "method_not_allowed", "Wake Music metadata supports GET")
                record = self.wake_music_service.latest(match.group(1))
                data = record.to_api_dict() if record is not None else None
                return self._json_response(
                    start_response, 200, None if method == "HEAD" else self._ok(data)
                )
            match = re.fullmatch(rf"{re.escape(self.prefix)}/([^/]+)/audio/master", path)
            if match:
                if method not in {"GET", "HEAD"}:
                    raise ApiError(405, "method_not_allowed", "Wake Music audio supports GET")
                return self._audio_response(
                    start_response,
                    self.wake_music_service.storage.audio_path(match.group(1), version="master"),
                    method,
                    str(environ.get("HTTP_RANGE", "")),
                )
            match = re.fullmatch(rf"{re.escape(self.prefix)}/([^/]+)/audio", path)
            if match:
                if method not in {"GET", "HEAD"}:
                    raise ApiError(405, "method_not_allowed", "Wake Music audio supports GET")
                return self._audio_response(
                    start_response,
                    self.wake_music_service.storage.audio_path(match.group(1)),
                    method,
                    str(environ.get("HTTP_RANGE", "")),
                )
            match = re.fullmatch(rf"{re.escape(self.prefix)}/([^/]+)", path)
            if match:
                if method not in {"GET", "HEAD"}:
                    raise ApiError(405, "method_not_allowed", "Wake Music metadata supports GET")
                record = self.wake_music_service.get(match.group(1))
                payload = self._ok(record.to_api_dict())
                if method == "HEAD":
                    payload = None
                return self._json_response(start_response, 200, payload)
            raise ApiError(404, "not_found", f"No Wake Music route for {path!r}")
        except ProviderError as error:
            return self._json_response(
                start_response,
                error.http_status,
                self._error(error.code, str(error)),
            )
        except WakeWindowUnavailableError as error:
            return self._json_response(
                start_response, 422, self._error("wake_window_unavailable", str(error))
            )
        except WakeAudioPostprocessingError as error:
            return self._json_response(
                start_response,
                500,
                self._error("audio_postprocessing_failed", str(error)),
            )
        except ApiError as error:
            return self._json_response(
                start_response, error.status, self._error(error.code, error.message, error.details)
            )
        except LookupError as error:
            return self._json_response(start_response, 404, self._error("not_found", str(error)))
        except (ValueError, json.JSONDecodeError) as error:
            return self._json_response(
                start_response, 400, self._error("invalid_request", str(error))
            )
        except Exception:  # pragma: no cover - defensive boundary; never leak secret context
            return self._json_response(
                start_response,
                500,
                self._error("internal_error", "Wake Music generation failed unexpectedly"),
            )

    def _request_json(self, environ) -> dict[str, Any]:
        raw_length = str(environ.get("CONTENT_LENGTH", "0") or "0")
        try:
            content_length = int(raw_length)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if content_length <= 0 or content_length > self.maximum_request_bytes:
            raise ValueError("request body size is invalid")
        body = environ["wsgi.input"].read(content_length)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    @staticmethod
    def _string(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _integer(payload: dict[str, Any], name: str) -> int:
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        return value

    @staticmethod
    def _optional_integer(payload: dict[str, Any], name: str) -> int | None:
        if payload.get(name) is None:
            return None
        return DreamCoreApiApplication._integer(payload, name)

    @staticmethod
    def _optional_float(payload: dict[str, Any], name: str) -> float | None:
        value = payload.get(name)
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} must be a number")
        return float(value)

    @staticmethod
    def _ok(data: Any) -> dict[str, Any]:
        return {"wake_music_api_version": WAKE_MUSIC_API_VERSION, "data": data}

    @staticmethod
    def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "wake_music_api_version": WAKE_MUSIC_API_VERSION,
            "error": {"code": code, "message": message, "details": details or {}},
        }

    @staticmethod
    def _json_response(start_response: Callable, status: int, payload: Any):
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ]
        start_response(f"{status} {_status_text(status)}", headers)
        return [body]

    @staticmethod
    def _audio_response(start_response: Callable, path: Path, method: str, range_header: str):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or (not match.group(1) and not match.group(2)):
                raise ApiError(416, "invalid_range", "Unsupported audio byte range")
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix_size = int(match.group(2))
                start = max(0, size - suffix_size)
            if start >= size or end < start:
                raise ApiError(416, "invalid_range", "Audio byte range is outside the file")
            end = min(end, size - 1)
            status = 206
        content_length = end - start + 1
        headers = [
            ("Content-Type", "audio/mpeg"),
            ("Content-Length", str(content_length)),
            ("Accept-Ranges", "bytes"),
            ("Cache-Control", "private, max-age=3600"),
        ]
        if status == 206:
            headers.append(("Content-Range", f"bytes {start}-{end}/{size}"))
        start_response(f"{status} {_status_text(status)}", headers)
        if method == "HEAD":
            return [b""]
        with path.open("rb") as audio_file:
            audio_file.seek(start)
            return [audio_file.read(content_length)]


def _status_text(status: int) -> str:
    return {
        200: "OK",
        206: "Partial Content",
        204: "No Content",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        416: "Range Not Satisfiable",
        422: "Unprocessable Content",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }.get(status, "Error")
