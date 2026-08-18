"""Read-only transport for explicit Signal Validation V1 results."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote


class SignalValidationApiApplication:
    """Expose a completed validation summary without starting benchmark work."""

    def __init__(self, fallback, summary_path: Path, *, path: str) -> None:
        self.fallback = fallback
        self.summary_path = Path(summary_path)
        self.path = path

    def __call__(self, environ, start_response: Callable):
        path = unquote(str(environ.get("PATH_INFO", "")))
        if path != self.path:
            return self.fallback(environ, start_response)
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if method == "OPTIONS":
            return self._response(start_response, 204, None)
        if method not in {"GET", "HEAD"}:
            return self._response(
                start_response,
                405,
                {"error": {"code": "method_not_allowed", "message": "Read-only endpoint"}},
            )
        if not self.summary_path.is_file():
            return self._response(
                start_response,
                404,
                {
                    "error": {
                        "code": "validation_pending",
                        "message": "Signal Validation V1 has not been run locally",
                    }
                },
            )
        try:
            payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._response(
                start_response,
                500,
                {
                    "error": {
                        "code": "invalid_validation_summary",
                        "message": "Local Signal Validation V1 summary is unreadable",
                    }
                },
            )
        return self._response(
            start_response,
            200,
            None if method == "HEAD" else {"data": payload},
        )

    @staticmethod
    def _response(start_response: Callable, status: int, payload):
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode()
        labels = {
            200: "OK",
            204: "No Content",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }
        start_response(
            f"{status} {labels[status]}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type"),
            ],
        )
        return [body]
