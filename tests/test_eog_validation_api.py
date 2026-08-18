"""Local EOG validation API input and routing boundaries."""

from __future__ import annotations

import io
import json

from dreamcore.api.eog_validation import EogValidationApiApplication


class StubService:
    def __init__(self) -> None:
        self.saved = None

    def recording(self, session_id):
        return {"recording_id": session_id}

    def samples(self, session_id, kind):
        return [{"recording_id": session_id, "sample_kind": kind}]

    def focus(self, review_id):
        return {"review_id": review_id, "focus_start_s": 5.0, "focus_end_s": 15.0}

    def filtered_window(self, session_id, channel, start_s, duration_s):
        return {
            "session_id": session_id,
            "channel": channel,
            "start_s": start_s,
            "duration_s": duration_s,
            "samples": [0.0],
        }

    def progress(self):
        return {"candidate_reviewed": 0}

    def metrics(self):
        return {"candidate_review": {"reviewed": 0}}

    def save_review(self, review_id, label, notes):
        self.saved = (review_id, label, notes)
        return {"review_id": review_id, "review_label": label, "notes": notes}


def _call(app, path, *, method="GET", query="", payload=None):
    body = b"" if payload is None else json.dumps(payload).encode()
    status = []
    headers = []

    def start_response(value, response_headers):
        status.append(value)
        headers.extend(response_headers)

    environ = {
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    response = b"".join(app(environ, start_response))
    return status[0], dict(headers), json.loads(response) if response else None


def test_validation_api_reads_bounded_focus_and_writes_only_known_review_shape():
    service = StubService()
    fallback_calls = []

    def fallback(environ, start_response):
        fallback_calls.append(environ["PATH_INFO"])
        start_response("200 OK", [("Content-Length", "0")])
        return [b""]

    app = EogValidationApiApplication(
        fallback,
        service,
        prefix="/api/eog-validation/v1",
        maximum_request_bytes=1024,
        maximum_focus_window_s=30.0,
    )
    status, _, payload = _call(
        app,
        "/api/eog-validation/v1/filtered-window",
        query="session_id=SN001&channel=EOG+E1-M2&start_s=5&duration_s=10",
    )
    assert status.startswith("200")
    assert payload["data"]["duration_s"] == 10.0

    status, _, payload = _call(
        app,
        "/api/eog-validation/v1/reviews",
        method="POST",
        payload={
            "review_id": "candidate:hmc:001",
            "review_label": "Uncertain",
            "notes": "review note",
            "ignored_path": "/tmp/arbitrary",
        },
    )
    assert status.startswith("200")
    assert service.saved == ("candidate:hmc:001", "Uncertain", "review note")
    assert "ignored_path" not in payload["data"]

    _call(app, "/api/v1/datasets")
    assert fallback_calls == ["/api/v1/datasets"]


def test_validation_api_rejects_oversized_focus_and_malformed_review():
    app = EogValidationApiApplication(
        lambda _environ, _start: [b""],
        StubService(),
        prefix="/api/eog-validation/v1",
        maximum_request_bytes=64,
        maximum_focus_window_s=30.0,
    )
    status, _, payload = _call(
        app,
        "/api/eog-validation/v1/filtered-window",
        query="session_id=SN001&channel=EOG&start_s=0&duration_s=31",
    )
    assert status.startswith("400")
    assert payload["data"]["error"]["code"] == "invalid_request"

    status, _, _ = _call(
        app,
        "/api/eog-validation/v1/reviews",
        method="POST",
        payload={"review_id": "x", "review_label": "Uncertain", "notes": "x" * 100},
    )
    assert status.startswith("400")
