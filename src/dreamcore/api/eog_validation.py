"""Separated local mutation API for Cross-Dataset EOG Validation V1."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, unquote

from dreamcore.api.http import ApiError
from dreamcore.eog_validation.reviews import ReviewValidationError
from dreamcore.eog_validation.service import EogValidationService


class EogValidationApiApplication:
    """Route bounded validation reads/reviews before the existing DreamCore app."""

    def __init__(
        self,
        fallback_application,
        service: EogValidationService,
        *,
        prefix: str,
        maximum_request_bytes: int,
        maximum_focus_window_s: float,
    ) -> None:
        self.fallback = fallback_application
        self.service = service
        self.prefix = prefix.rstrip("/")
        self.maximum_request_bytes = maximum_request_bytes
        self.maximum_focus_window_s = maximum_focus_window_s

    def __call__(self, environ, start_response: Callable):
        path = unquote(str(environ.get("PATH_INFO", "")))
        if not path.startswith(self.prefix):
            return self.fallback(environ, start_response)
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        try:
            if method == "OPTIONS":
                return self._response(start_response, 204, None)
            if path == f"{self.prefix}/recording":
                self._require_method(method, "GET")
                return self._response(
                    start_response,
                    200,
                    self.service.recording(self._query_string(query, "session_id")),
                )
            if path == f"{self.prefix}/samples":
                self._require_method(method, "GET")
                kind = self._query_string(query, "kind")
                if kind not in {"candidate", "control"}:
                    raise ValueError("kind must be candidate or control")
                return self._response(
                    start_response,
                    200,
                    self.service.samples(self._query_string(query, "session_id"), kind),
                )
            if path == f"{self.prefix}/focus":
                self._require_method(method, "GET")
                return self._response(
                    start_response,
                    200,
                    self.service.focus(self._query_string(query, "review_id")),
                )
            if path == f"{self.prefix}/filtered-window":
                self._require_method(method, "GET")
                start_s = self._query_float(query, "start_s")
                duration_s = self._query_float(query, "duration_s")
                if start_s < 0 or duration_s <= 0 or duration_s > self.maximum_focus_window_s:
                    raise ValueError("filtered focus window is outside configured bounds")
                return self._response(
                    start_response,
                    200,
                    self.service.filtered_window(
                        self._query_string(query, "session_id"),
                        self._query_string(query, "channel"),
                        start_s,
                        duration_s,
                    ),
                )
            if path == f"{self.prefix}/progress":
                self._require_method(method, "GET")
                return self._response(start_response, 200, self.service.progress())
            if path == f"{self.prefix}/metrics":
                self._require_method(method, "GET")
                return self._response(start_response, 200, self.service.metrics())
            if path == f"{self.prefix}/reviews":
                self._require_method(method, "POST")
                body = self._json_body(environ)
                return self._response(
                    start_response,
                    200,
                    self.service.save_review(
                        self._body_string(body, "review_id"),
                        self._body_string(body, "review_label"),
                        body.get("notes", ""),
                    ),
                )
            raise ApiError(404, "not_found", "No EOG Validation V1 route")
        except ApiError as error:
            return self._error(start_response, error.status, error.code, error.message)
        except LookupError as error:
            return self._error(start_response, 404, "not_found", str(error))
        except (ReviewValidationError, ValueError, json.JSONDecodeError) as error:
            return self._error(start_response, 400, "invalid_request", str(error))
        except Exception:  # pragma: no cover - local defensive boundary
            return self._error(
                start_response,
                500,
                "internal_error",
                "EOG validation request failed unexpectedly",
            )

    def _json_body(self, environ) -> dict[str, Any]:
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "0") or "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length <= 0 or length > self.maximum_request_bytes:
            raise ValueError("request body size is invalid")
        payload = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    @staticmethod
    def _query_string(query: dict[str, list[str]], name: str) -> str:
        values = query.get(name, [])
        if len(values) != 1 or not values[0]:
            raise ValueError(f"exactly one {name} is required")
        return values[0]

    @classmethod
    def _query_float(cls, query: dict[str, list[str]], name: str) -> float:
        return float(cls._query_string(query, name))

    @staticmethod
    def _body_string(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _require_method(actual: str, expected: str) -> None:
        if actual != expected:
            raise ApiError(405, "method_not_allowed", f"route requires {expected}")

    @staticmethod
    def _response(start_response: Callable, status: int, data: Any):
        payload = None if data is None else {"eog_validation_api_version": "v1", "data": data}
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        start_response(
            f"{status} {_status_text(status)}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type"),
            ],
        )
        return [body]

    @classmethod
    def _error(cls, start_response: Callable, status: int, code: str, message: str):
        return cls._response(
            start_response,
            status,
            {"error": {"code": code, "message": message}},
        )


def _status_text(status: int) -> str:
    return {
        200: "OK",
        204: "No Content",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }.get(status, "Error")
