"""Read-only Signal Validation summary transport tests."""

from __future__ import annotations

import io
import json
from pathlib import Path

from dreamcore.api.signal_validation import SignalValidationApiApplication


def _request(app, path: str, method: str = "GET") -> tuple[str, dict | None]:
    captured = {}

    def start_response(status, headers):
        captured["status"] = status

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "REQUEST_METHOD": method,
                "wsgi.input": io.BytesIO(),
            },
            start_response,
        )
    )
    return str(captured["status"]), json.loads(body) if body else None


def test_validation_summary_is_read_only_and_does_not_run_work(tmp_path: Path) -> None:
    fallback_called = []

    def fallback(environ, start_response):
        fallback_called.append(environ["PATH_INFO"])
        start_response("418 Teapot", [])
        return [b""]

    summary = tmp_path / "summary.json"
    app = SignalValidationApiApplication(fallback, summary, path="/api/validation/v1/summary")
    status, payload = _request(app, "/api/validation/v1/summary")
    assert status.startswith("404")
    assert payload["error"]["code"] == "validation_pending"
    assert not summary.exists()

    summary.write_text('{"validation_version":"v1"}\n', encoding="utf-8")
    status, payload = _request(app, "/api/validation/v1/summary")
    assert status.startswith("200")
    assert payload == {"data": {"validation_version": "v1"}}

    status, payload = _request(app, "/api/validation/v1/summary", "POST")
    assert status.startswith("405")
    assert payload["error"]["code"] == "method_not_allowed"

    assert _request(app, "/api/v1/datasets")[0].startswith("418")
    assert fallback_called == ["/api/v1/datasets"]
