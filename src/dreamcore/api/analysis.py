"""Local product-analysis status API; no provider or arbitrary write routes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

from dreamcore.analysis.manager import AutomaticAnalysisManager


class AutomaticAnalysisApiApplication:
    def __init__(
        self,
        fallback,
        manager: AutomaticAnalysisManager,
        *,
        prefix: str,
    ) -> None:
        self.fallback = fallback
        self.manager = manager
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response: Callable):
        path = unquote(str(environ.get("PATH_INFO", "")))
        if not path.startswith(self.prefix):
            return self.fallback(environ, start_response)
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if method == "OPTIONS":
            return self._response(start_response, 204, None)
        detail_match = re.fullmatch(rf"{re.escape(self.prefix)}/sessions/([^/]+)/k-complex", path)
        review_match = re.fullmatch(
            rf"{re.escape(self.prefix)}/sessions/([^/]+)/k-complex/reviews", path
        )
        manual_match = re.fullmatch(
            rf"{re.escape(self.prefix)}/sessions/([^/]+)/k-complex/manual-events", path
        )
        try:
            if detail_match:
                if method not in {"GET", "HEAD"}:
                    return self._response(start_response, 405, self._error("method_not_allowed"))
                payload = self.manager.k_complex_payload(detail_match.group(1))
                return self._response(
                    start_response, 200, None if method == "HEAD" else {"data": payload}
                )
            if review_match:
                if method != "POST":
                    return self._response(start_response, 405, self._error("method_not_allowed"))
                body = self._json_body(environ)
                payload = self.manager.save_k_complex_review(
                    review_match.group(1),
                    self._body_string(body, "event_id"),
                    self._body_string(body, "review_label"),
                    self._optional_notes(body),
                )
                return self._response(start_response, 200, {"data": payload})
            if manual_match:
                if method != "POST":
                    return self._response(start_response, 405, self._error("method_not_allowed"))
                body = self._json_body(environ)
                timestamp = body.get("negative_trough_s")
                if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
                    raise ValueError("negative_trough_s must be numeric")
                payload = self.manager.save_manual_k_complex(
                    manual_match.group(1), float(timestamp), self._optional_notes(body)
                )
                return self._response(start_response, 200, {"data": payload})
        except LookupError:
            return self._response(start_response, 404, self._error("not_found"))
        except (ValueError, json.JSONDecodeError):
            return self._response(start_response, 400, self._error("invalid_request"))
        except Exception:
            return self._response(start_response, 500, self._error("internal_error"))
        if method not in {"GET", "HEAD"}:
            return self._response(start_response, 405, self._error("method_not_allowed"))
        match = re.fullmatch(rf"{re.escape(self.prefix)}/sessions/([^/]+)", path)
        if not match:
            return self._response(start_response, 404, self._error("not_found"))
        try:
            payload = self.manager.ensure_session(match.group(1))
            return self._response(
                start_response, 200, None if method == "HEAD" else {"data": payload}
            )
        except LookupError:
            return self._response(start_response, 404, self._error("not_found"))
        except Exception:
            return self._response(start_response, 500, self._error("internal_error"))

    def _json_body(self, environ) -> dict[str, Any]:
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "0") or "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        maximum = int(self.manager.config["k_complex"]["maximum_request_bytes"])
        if length <= 0 or length > maximum:
            raise ValueError("request body size is invalid")
        payload = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    @staticmethod
    def _body_string(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _optional_notes(payload: dict[str, Any]) -> str:
        notes = payload.get("notes", "")
        if not isinstance(notes, str):
            raise ValueError("notes must be a string")
        return notes

    @staticmethod
    def _error(code: str) -> dict[str, object]:
        return {"error": {"code": code, "message": "Automatic analysis request failed"}}

    @staticmethod
    def _response(start_response: Callable, status: int, payload):
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode()
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ]
        labels = {
            200: "OK",
            204: "No Content",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }
        start_response(f"{status} {labels[status]}", headers)
        return [body]
