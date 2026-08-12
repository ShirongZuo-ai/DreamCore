"""Minimal versioned read-only WSGI API for canonical Session Packages."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

from dreamcore.datasets.models import CapabilityName, ContentDescriptor, SessionManifest
from dreamcore.datasets.registry import DatasetRegistry
from dreamcore.datasets.repository import SessionPackageRepository

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


@dataclass(frozen=True)
class ApiSettings:
    """Transport settings supplied by configuration."""

    max_signal_window_seconds: float
    cors_allowed_origins: tuple[str, ...]


class ApiError(Exception):
    """Structured client-facing API failure."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def build_registry(package_root: str | Path) -> DatasetRegistry:
    """Discover Session Packages and register their existing adapters."""

    registry = DatasetRegistry()
    for adapter in SessionPackageRepository(Path(package_root)).adapters():
        registry.register(adapter)
    return registry


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(_jsonable(key)): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _descriptor_payload(descriptor: ContentDescriptor) -> dict[str, Any]:
    return _jsonable(descriptor)


def _coerce_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    lowered = stripped.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        number = float(stripped)
    except ValueError:
        return value
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() and "." not in stripped else number


def _coerce_record(record: Any) -> Any:
    if isinstance(record, dict):
        return {str(key): _coerce_csv_value(value) for key, value in record.items()}
    return record


class SessionApiApplication:
    """Read-only WSGI application backed exclusively by ``DatasetRegistry``."""

    def __init__(self, registry: DatasetRegistry, settings: ApiSettings) -> None:
        if settings.max_signal_window_seconds <= 0:
            raise ValueError("max_signal_window_seconds must be positive")
        self.registry = registry
        self.settings = settings

    def __call__(self, environ, start_response):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = unquote(str(environ.get("PATH_INFO", "")))
        origin = str(environ.get("HTTP_ORIGIN", ""))
        try:
            if method == "OPTIONS":
                status, payload = 204, None
            elif method not in {"GET", "HEAD"}:
                raise ApiError(
                    405,
                    "method_not_allowed",
                    "This API is read-only; only GET is supported",
                )
            else:
                query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
                payload = self._dispatch(path, query)
                status = 200
        except ApiError as error:
            status = error.status
            payload = {
                "api_version": API_VERSION,
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
            }
        except LookupError as error:
            status = 404
            payload = self._error_payload("not_found", str(error))
        except (FileNotFoundError, OSError) as error:
            status = 503
            payload = self._error_payload("source_unavailable", str(error))
        except ValueError as error:
            status = 400
            payload = self._error_payload("invalid_request", str(error))
        except Exception as error:  # pragma: no cover - defensive transport boundary
            status = 500
            payload = self._error_payload("internal_error", str(error))

        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("X-DreamCore-API-Version", API_VERSION),
            ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ]
        if origin and origin in self.settings.cors_allowed_origins:
            headers.append(("Access-Control-Allow-Origin", origin))
            headers.append(("Vary", "Origin"))
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        headers.append(("Content-Length", str(len(body))))
        start_response(f"{status} {self._status_text(status)}", headers)
        return [b"" if method == "HEAD" else body]

    def _dispatch(self, path: str, query: dict[str, list[str]]) -> dict[str, Any]:
        if path == f"{API_PREFIX}/datasets":
            return self._ok(self._datasets())

        match = re.fullmatch(rf"{API_PREFIX}/datasets/([^/]+)/sessions", path)
        if match:
            return self._ok(self._dataset_sessions(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)", path)
        if match:
            return self._ok(_jsonable(self.registry.get_session_by_id(match.group(1))))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)/signals", path)
        if match:
            return self._ok(self._signals(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)/signals/([^/]+)/window", path)
        if match:
            return self._ok(self._signal_window(match.group(1), match.group(2), query))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)/annotations", path)
        if match:
            return self._ok(self._annotations(match.group(1), query))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)/derived", path)
        if match:
            return self._ok(self._derived(match.group(1), query))

        match = re.fullmatch(rf"{API_PREFIX}/sessions/([^/]+)/events", path)
        if match:
            return self._ok(self._events(match.group(1), query))

        raise ApiError(404, "not_found", f"No API route for {path!r}")

    def _datasets(self) -> list[dict[str, Any]]:
        output = []
        for dataset in self.registry.list_datasets():
            sessions = self.registry.list_dataset_sessions(dataset.id)
            capabilities = sorted(
                {
                    name.value
                    for session in sessions
                    for name, descriptor in session.capabilities.items()
                    if descriptor.status.value == "AVAILABLE"
                }
            )
            output.append(
                {
                    **_jsonable(dataset),
                    "session_count": len(sessions),
                    "available_capabilities": capabilities,
                }
            )
        return output

    def _dataset_sessions(self, dataset_id: str) -> list[dict[str, Any]]:
        return [_jsonable(item) for item in self.registry.list_dataset_sessions(dataset_id)]

    def _signals(self, session_id: str) -> dict[str, Any]:
        manifest = self.registry.get_session_by_id(session_id)
        return {
            "session_id": session_id,
            "capability": _jsonable(manifest.capability(CapabilityName.EEG)),
            "signals": [_jsonable(signal) for signal in manifest.signals],
        }

    def _signal_window(
        self,
        session_id: str,
        signal_id: str,
        query: dict[str, list[str]],
    ) -> dict[str, Any]:
        start_s = self._required_float(query, "start_s")
        duration_s = self._required_float(query, "duration_s")
        if start_s < 0 or duration_s <= 0:
            raise ApiError(
                400,
                "invalid_time_range",
                "start_s must be non-negative and duration_s must be positive",
            )
        if duration_s > self.settings.max_signal_window_seconds:
            raise ApiError(
                400,
                "window_too_large",
                "Requested signal window exceeds the configured maximum",
                {"max_duration_s": self.settings.max_signal_window_seconds},
            )
        manifest = self.registry.get_session_by_id(session_id)
        if start_s >= manifest.recording.duration_seconds:
            raise ApiError(
                400,
                "invalid_time_range",
                "start_s must be before the end of the recording",
            )
        clipped_duration = min(duration_s, manifest.recording.duration_seconds - start_s)
        window = self.registry.load_signal_window(
            session_id,
            signal_id,
            start_s,
            clipped_duration,
        )
        rate = window.signal.sampling_rate_hz
        timestamps = [start_s + index / rate for index in range(len(window.samples))]
        end_s = start_s + len(window.samples) / rate
        return {
            "session_id": session_id,
            "signal_id": signal_id,
            "channel": window.signal.channel_name,
            "provenance": window.signal.source.value,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "sampling_rate_hz": rate,
            "unit": window.signal.unit,
            "n_samples": len(window.samples),
            "timestamps": timestamps,
            "samples": list(window.samples),
        }

    def _annotations(self, session_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        manifest = self.registry.get_session_by_id(session_id)
        start_s, end_s = self._optional_range(query, manifest)
        results = []
        descriptors: dict[str, Any] = {}
        for annotation_type, descriptor in manifest.annotations.items():
            descriptors[annotation_type] = _descriptor_payload(descriptor)
            if not descriptor.available:
                continue
            for item in self.registry.load_annotations(session_id, annotation_type):
                item_start = float(item.get("start_seconds", 0.0))
                item_end = item_start + float(item.get("duration_seconds", 0.0))
                if item_end > start_s and item_start < end_s:
                    results.append({"annotation_type": annotation_type, **_jsonable(item)})
        return {
            "session_id": session_id,
            "start_s": start_s,
            "end_s": end_s,
            "descriptors": descriptors,
            "annotations": results,
        }

    def _derived(self, session_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        metric = self._required_string(query, "metric")
        manifest = self.registry.get_session_by_id(session_id)
        descriptor = manifest.derived.get(metric)
        if descriptor is None:
            raise ApiError(404, "metric_not_found", f"Derived metric {metric!r} is not declared")
        start_s, end_s = self._optional_range(query, manifest)
        records = []
        if descriptor.available:
            for raw in self.registry.load_derived_window(session_id, metric, start_s, end_s):
                record = _coerce_record(raw)
                records.append(record)
        return {
            "session_id": session_id,
            "metric": metric,
            "start_s": start_s,
            "end_s": end_s,
            "descriptor": _descriptor_payload(descriptor),
            "records": records,
        }

    def _events(self, session_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        result_type = "simulated_stimulation_events"
        manifest = self.registry.get_session_by_id(session_id)
        descriptor = manifest.derived.get(result_type)
        if descriptor is None:
            return {
                "session_id": session_id,
                "start_s": 0.0,
                "end_s": manifest.recording.duration_seconds,
                "descriptor": None,
                "events": [],
            }
        start_s, end_s = self._optional_range(query, manifest)
        events = []
        if descriptor.available:
            for event in self.registry.load_derived_results(session_id, result_type):
                timestamp = float(event.get("timestamp", 0.0))
                if start_s <= timestamp < end_s:
                    events.append(_jsonable(event))
        return {
            "session_id": session_id,
            "start_s": start_s,
            "end_s": end_s,
            "descriptor": _descriptor_payload(descriptor),
            "events": events,
        }

    @staticmethod
    def _required_float(query: dict[str, list[str]], name: str) -> float:
        raw = SessionApiApplication._required_string(query, name)
        try:
            value = float(raw)
        except ValueError as error:
            raise ApiError(400, "invalid_query", f"{name} must be a number") from error
        if not math.isfinite(value):
            raise ApiError(400, "invalid_query", f"{name} must be finite")
        return value

    @staticmethod
    def _required_string(query: dict[str, list[str]], name: str) -> str:
        values = query.get(name, [])
        if len(values) != 1 or not values[0]:
            raise ApiError(400, "invalid_query", f"Exactly one non-empty {name} is required")
        return values[0]

    def _optional_range(
        self,
        query: dict[str, list[str]],
        manifest: SessionManifest,
    ) -> tuple[float, float]:
        start_s = self._required_float(query, "start_s") if "start_s" in query else 0.0
        end_s = (
            self._required_float(query, "end_s")
            if "end_s" in query
            else manifest.recording.duration_seconds
        )
        if start_s < 0 or end_s <= start_s:
            raise ApiError(
                400,
                "invalid_time_range",
                "start_s must be non-negative and end_s must be greater than start_s",
            )
        return start_s, min(end_s, manifest.recording.duration_seconds)

    @staticmethod
    def _ok(data: Any) -> dict[str, Any]:
        return {"api_version": API_VERSION, "data": data}

    @staticmethod
    def _error_payload(code: str, message: str) -> dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "error": {"code": code, "message": message, "details": {}},
        }

    @staticmethod
    def _status_text(status: int) -> str:
        return {
            200: "OK",
            204: "No Content",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
            503: "Service Unavailable",
        }.get(status, "Error")
