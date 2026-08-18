"""Product orchestration, cache, validation reuse, and status transport tests."""

from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path
from types import MethodType

import yaml

from dreamcore.analysis.manager import AutomaticAnalysisManager
from dreamcore.api.analysis import AutomaticAnalysisApiApplication
from dreamcore.api.http import build_registry


def _configuration(tmp_path: Path) -> dict:
    config = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    config["automatic_analysis"]["cache_root"] = str(tmp_path / "cache")
    config["automatic_analysis"]["status_poll_interval_ms"] = 1
    return config


def _wait(manager: AutomaticAnalysisManager, session_id: str) -> dict:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = manager.ensure_session(session_id)
        if all(item["state"] != "ANALYZING" for item in status["features"].values()):
            return status
        time.sleep(0.01)
    raise AssertionError("automatic analysis did not finish")


def _install_small_jobs(manager: AutomaticAnalysisManager, tmp_path: Path) -> None:
    def run(self, manifest, feature, sources, identity):
        time.sleep(0.03)
        artifact = tmp_path / f"{manifest.session.session_id}-{feature}.json"
        artifact.write_text("{}", encoding="utf-8")
        result = {
            "schema_version": self.config["schema_version"],
            "feature": feature,
            "session_id": manifest.session.session_id,
            "cache_key": identity["cache_key"],
            "configuration_hash": identity["configuration_hash"],
            "source_fingerprint": identity["source_fingerprint"],
            "algorithm_version": identity["algorithm_version"],
            "completed_at": "test",
            "duration_ms": 30,
            "reuse_kind": "test_cache",
            "artifacts": {
                "profile" if feature == "wake_music_profile" else "features": str(artifact)
            },
            "summary": "Ready to generate" if feature == "wake_music_profile" else "Ready",
        }
        if feature == "wake_music_profile":
            result["profile"] = {"profile_version": "test"}
        return result

    manager._run = MethodType(run, manager)


def test_jobs_are_non_blocking_deduplicated_and_persisted(tmp_path: Path):
    root = Path.cwd()
    config = _configuration(tmp_path)
    registry = build_registry(root / config["session_transport"]["session_package_root"])
    manager = AutomaticAnalysisManager(root, registry, config)
    _install_small_jobs(manager, tmp_path)
    try:
        started = time.monotonic()
        first = manager.ensure_session("SC4011")
        assert time.monotonic() - started < 0.5
        assert first["features"]["eye_movement"]["state"] == "ANALYZING"
        for _ in range(5):
            manager.ensure_session("SC4011")
        assert manager.submission_count("SC4011", "eye_movement") == 1
        assert manager.submission_count("SC4011", "alpha") == 1
        ready = _wait(manager, "SC4011")
        assert {item["state"] for item in ready["features"].values()} == {"READY"}
        assert manager.submission_count("SC4011", "wake_music_profile") == 1
    finally:
        manager.shutdown()

    reloaded = AutomaticAnalysisManager(root, registry, config)
    try:
        cached = reloaded.ensure_session("SC4011")
        assert {item["state"] for item in cached["features"].values()} == {"READY"}
        assert all(item["cache_hit"] for item in cached["features"].values())
        assert all(
            reloaded.submission_count("SC4011", feature) == 0 for feature in cached["features"]
        )
    finally:
        reloaded.shutdown()


def test_compatible_full_night_validation_artifacts_are_referenced(tmp_path: Path):
    root = Path.cwd()
    config = _configuration(tmp_path)
    registry = build_registry(root / config["session_transport"]["session_package_root"])
    manager = AutomaticAnalysisManager(root, registry, config)
    try:
        manifest = registry.get_session_by_id("SN001")
        sources = manager._source_signals(manifest, "eye_movement")
        identity = manager._identity(manifest, "eye_movement", sources)
        result = manager._validation_artifacts(manifest, sources, identity)
        assert result is not None
        assert result["reuse_kind"] == "compatible_eog_validation_reference"
        assert [item["candidate_count"] for item in result["channels"]] == [403, 366]
        assert all(
            "results/eog_validation_v1/derived" in item["features"] for item in result["artifacts"]
        )
        assert not (tmp_path / "cache" / "SN001" / "eye_movement" / "feature_windows.csv").exists()
    finally:
        manager.shutdown()


def test_status_api_is_get_only_and_never_calls_music_provider(tmp_path: Path):
    root = Path.cwd()
    config = _configuration(tmp_path)
    registry = build_registry(root / config["session_transport"]["session_package_root"])
    manager = AutomaticAnalysisManager(root, registry, config)
    _install_small_jobs(manager, tmp_path)

    def fallback(_environ, _start):
        return []

    app = AutomaticAnalysisApiApplication(
        fallback,
        manager,
        prefix=config["automatic_analysis"]["api_prefix"],
    )

    def request(method: str):
        status_line = ""

        def start_response(status, _headers):
            nonlocal status_line
            status_line = status

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": method,
                    "PATH_INFO": "/api/analysis/v1/sessions/SC4002",
                    "wsgi.input": BytesIO(),
                },
                start_response,
            )
        )
        return int(status_line.split()[0]), json.loads(body) if body else None

    try:
        status, payload = request("GET")
        assert status == 200
        assert payload["data"]["features"]["alpha"]["state"] == "ANALYZING"
        status, payload = request("POST")
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"
    finally:
        manager.shutdown()
