"""Read-only HTTP contract tests using small canonical fixture packages."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from shutil import copytree

import pytest

from dreamcore.api.http import ApiSettings, SessionApiApplication, build_registry


@pytest.fixture
def api(tmp_path: Path) -> SessionApiApplication:
    package_root = tmp_path / "packages"
    copytree(Path("tests/fixtures/session_packages"), package_root)
    manifest_path = package_root / "fixture-neuro" / "fixture-a" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    secondary_signal = json.loads(json.dumps(manifest["signals"][0]))
    secondary_signal.update(
        {
            "id": "eog-test-primary",
            "modality": "eog",
            "channel_name": "TEST-EOG-A",
        }
    )
    manifest["signals"].append(secondary_signal)
    manifest["derived"]["alpha_power"] = {
        "available": True,
        "source": "derived",
        "derived_by": "fixture-alpha-v1",
        "version": "test-1",
        "metadata": {
            "events": [
                {
                    "window_start_s": 10.0,
                    "window_end_s": 40.0,
                    "channel": "TEST-EEG-A",
                    "absolute_alpha_power": 12.5,
                    "feature_provenance": "derived",
                },
                {
                    "window_start_s": 70.0,
                    "window_end_s": 100.0,
                    "channel": "TEST-EEG-A",
                    "absolute_alpha_power": 8.5,
                    "feature_provenance": "derived",
                },
            ]
        },
    }
    manifest["derived"]["simulated_stimulation_events"] = {
        "available": True,
        "source": "simulated",
        "derived_by": "fixture-demand-v1",
        "version": "test-1",
        "metadata": {
            "notice": "SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE",
            "events": [
                {
                    "timestamp": 25.0,
                    "event_type": "stimulation_reduced",
                    "provenance": "simulated",
                },
                {
                    "timestamp": 75.0,
                    "event_type": "stimulation_held",
                    "provenance": "simulated",
                },
            ],
        },
    }
    manifest["derived"]["eye_movement_activity_v1"] = {
        "available": True,
        "source": "derived",
        "derived_by": "fixture-eye-v1",
        "version": "test-1",
        "metadata": {
            "coverage": {
                "coverage_start_s": 4.0,
                "coverage_end_s": 100.0,
                "window_s": 4.0,
                "source_channel": "TEST-EOG",
            },
            "events": [
                {
                    "window_start_s": 10.0,
                    "window_end_s": 14.0,
                    "source_channel": "TEST-EOG",
                    "activity_score": 0.75,
                    "feature_provenance": "derived",
                }
            ],
        },
    }
    manifest["derived"]["eye_movement_events_v1"] = {
        "available": True,
        "source": "derived",
        "derived_by": "fixture-eye-v1",
        "version": "test-1",
        "metadata": {
            "events": [
                {
                    "timestamp": 12.0,
                    "window_start_s": 11.8,
                    "window_end_s": 12.2,
                    "event_type": "eye_movement_candidate",
                    "provenance": "derived",
                }
            ]
        },
    }
    manifest["derived"]["missing_eye_movement_fixture"] = {
        "available": True,
        "source": "derived",
        "metadata": {"storage": {"kind": "csv", "path": "missing-eye-feature.csv"}},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return SessionApiApplication(
        build_registry(package_root),
        ApiSettings(max_signal_window_seconds=120.0, cors_allowed_origins=()),
    )


def request(
    api: SessionApiApplication,
    path: str,
    query: str = "",
    method: str = "GET",
) -> tuple[int, dict]:
    status_line = ""

    def start_response(status, _headers):
        nonlocal status_line
        status_line = status

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "wsgi.input": BytesIO(),
    }
    body = b"".join(api(environ, start_response))
    payload = json.loads(body) if body else {}
    return int(status_line.split()[0]), payload


def test_dataset_list_and_session_metadata(api):
    status, payload = request(api, "/api/v1/datasets")
    assert status == 200
    assert payload["api_version"] == "v1"
    assert {item["id"] for item in payload["data"]} == {
        "fixture-neuro",
        "fixture-physiology",
    }

    status, payload = request(api, "/api/v1/sessions/fixture-a")
    assert status == 200
    assert payload["data"]["schema_version"] == "dreamcore.session.v1"
    assert payload["data"]["capabilities"]["eeg"]["source"] == "simulated"

    status, payload = request(api, "/api/v1/datasets/fixture-neuro")
    assert status == 200
    assert payload["data"]["subject_count"] == 2
    assert payload["data"]["local_recording_count"] == 2

    status, payload = request(api, "/api/v1/recordings/fixture-a")
    assert status == 200
    assert payload["data"]["session"]["subject_id"] == "TEST-SUBJECT-A"


def test_dataset_sessions_are_scoped(api):
    status, payload = request(api, "/api/v1/datasets/fixture-neuro/sessions")
    assert status == 200
    assert [item["session"]["session_id"] for item in payload["data"]] == [
        "fixture-a",
        "fixture-b",
    ]


def test_dataset_subject_and_recording_navigation_is_scoped(api):
    status, payload = request(api, "/api/v1/datasets/fixture-neuro/subjects")
    assert status == 200
    assert payload["data"] == [
        {
            "subject_id": "TEST-SUBJECT-A",
            "recording_count": 1,
            "local_status": "available_locally",
        },
        {
            "subject_id": "TEST-SUBJECT-B",
            "recording_count": 1,
            "local_status": "available_locally",
        },
    ]

    status, payload = request(
        api,
        "/api/v1/datasets/fixture-neuro/subjects/TEST-SUBJECT-B/recordings",
    )
    assert status == 200
    assert [item["session"]["session_id"] for item in payload["data"]] == ["fixture-b"]

    status, payload = request(
        api,
        "/api/v1/datasets/fixture-neuro/subjects/missing/recordings",
    )
    assert status == 404
    assert payload["error"]["code"] == "not_found"


def test_valid_signal_window_contract_preserves_unit_and_provenance(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/signals/eeg-test-primary/window",
        "start_s=2&duration_s=2",
    )
    assert status == 200
    window = payload["data"]
    assert window["channel"] == "TEST-EEG-A"
    assert window["unit"] == "uV"
    assert window["provenance"] == "simulated"
    assert window["sampling_rate_hz"] == 32
    assert window["n_samples"] == 64
    assert len(window["timestamps"]) == len(window["samples"]) == 64
    assert window["timestamps"][0] == 2.0
    assert window["end_s"] == 4.0


def test_bounded_multi_signal_window_preserves_order_and_contract(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/signals/window",
        "signal_id=eeg-test-primary&signal_id=eog-test-primary&start_s=2&duration_s=2",
    )
    assert status == 200
    data = payload["data"]
    assert [window["signal_id"] for window in data["windows"]] == [
        "eeg-test-primary",
        "eog-test-primary",
    ]
    assert all(window["start_s"] == 2.0 for window in data["windows"])
    assert all(window["duration_s"] == 2.0 for window in data["windows"])


def test_bounded_multi_signal_window_rejects_duplicate_signal_ids(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/signals/window",
        "signal_id=eeg-test-primary&signal_id=eeg-test-primary&start_s=2&duration_s=2",
    )
    assert status == 400
    assert payload["error"]["code"] == "invalid_query"


def test_signal_window_clips_at_recording_boundary(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/signals/eeg-test-primary/window",
        "start_s=28799&duration_s=2",
    )
    assert status == 200
    assert payload["data"]["duration_s"] == 1.0
    assert payload["data"]["n_samples"] == 32


@pytest.mark.parametrize(
    ("path", "query", "code"),
    [
        ("/api/v1/sessions/missing", "", "not_found"),
        (
            "/api/v1/sessions/fixture-a/signals/missing/window",
            "start_s=0&duration_s=1",
            "not_found",
        ),
        (
            "/api/v1/sessions/fixture-a/signals/eeg-test-primary/window",
            "start_s=-1&duration_s=1",
            "invalid_time_range",
        ),
        (
            "/api/v1/sessions/fixture-a/signals/eeg-test-primary/window",
            "start_s=0&duration_s=121",
            "window_too_large",
        ),
    ],
)
def test_structured_errors(api, path, query, code):
    status, payload = request(api, path, query)
    assert status in {400, 404}
    assert payload["api_version"] == "v1"
    assert payload["error"]["code"] == code


def test_annotation_window_preserves_imported_contract_shape(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/annotations",
        "start_s=850&end_s=950",
    )
    assert status == 200
    annotations = payload["data"]["annotations"]
    assert [item["label"] for item in annotations] == ["W", "N2"]
    assert payload["data"]["descriptors"]["sleep_stages"]["source"] == "simulated"


def test_derived_feature_window_and_provenance(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/derived",
        "metric=alpha_power&start_s=0&end_s=50",
    )
    assert status == 200
    assert payload["data"]["descriptor"]["source"] == "derived"
    assert len(payload["data"]["records"]) == 1
    assert payload["data"]["records"][0]["feature_provenance"] == "derived"


def test_simulated_event_window_preserves_provenance(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/events",
        "start_s=0&end_s=50",
    )
    assert status == 200
    assert payload["data"]["descriptor"]["source"] == "simulated"
    assert [event["provenance"] for event in payload["data"]["events"]] == ["simulated"]


def test_eye_movement_features_and_events_use_additive_derived_api(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/derived",
        "metric=eye_movement_activity_v1&start_s=0&end_s=20",
    )
    assert status == 200
    assert payload["data"]["descriptor"]["source"] == "derived"
    assert payload["data"]["descriptor"]["metadata"]["coverage"]["coverage_start_s"] == 4.0
    assert payload["data"]["records"][0]["activity_score"] == 0.75

    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/derived",
        "metric=eye_movement_events_v1&start_s=0&end_s=20",
    )
    assert status == 200
    assert payload["data"]["records"][0]["event_type"] == "eye_movement_candidate"
    assert payload["data"]["records"][0]["provenance"] == "derived"


def test_missing_derived_artifact_is_an_explicit_transport_error(api):
    status, payload = request(
        api,
        "/api/v1/sessions/fixture-a/derived",
        "metric=missing_eye_movement_fixture&start_s=0&end_s=20",
    )
    assert status == 503
    assert payload["error"]["code"] == "source_unavailable"


def test_api_has_no_full_record_or_mutating_endpoint(api):
    status, payload = request(api, "/api/v1/sessions/fixture-a/signals/eeg-test-primary")
    assert status == 404
    assert payload["error"]["code"] == "not_found"

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        status, payload = request(api, "/api/v1/datasets", method=method)
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"
