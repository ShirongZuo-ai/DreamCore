"""K-Complex Detection V0 morphology, staging, identity, and review tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

from dreamcore.analysis.manager import FEATURE_K_COMPLEX, AutomaticAnalysisManager
from dreamcore.api.http import build_registry
from dreamcore.k_complex.annotations import KComplexAnnotationStore
from dreamcore.k_complex.detector import (
    N2Bout,
    detect_k_complexes,
    segment_stage_bouts,
    suppress_refractory,
)


def _config() -> dict:
    return yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))


def _waveform(*, artifact: bool = False) -> tuple[np.ndarray, float]:
    rate = 200.0
    timestamps = np.arange(0.0, 20.0, 1.0 / rate)
    values = np.random.default_rng(7).normal(0.0, 1.5, timestamps.size)
    amplitude = 1000.0 if artifact else 120.0
    values += -amplitude * np.exp(-0.5 * ((timestamps - 8.0) / 0.18) ** 2)
    values += 70.0 * np.exp(-0.5 * ((timestamps - 8.65) / 0.30) ** 2)
    return values, rate


def _detect(values: np.ndarray, rate: float, config: dict):
    return detect_k_complexes(
        values,
        rate,
        "F-test",
        (N2Bout("N2-0001", "N2", 0.0, 20.0, ("raw-N2",), ("scorer",)),),
        config,
        dataset_id="fixture",
        subject_id="subject",
        recording_id="recording",
        detector_version="k_complex_v0",
        config_hash="config-hash",
        source_fingerprint="source-fingerprint",
    )


def test_k_complex_channel_selection_is_frontal_then_central_and_separate_from_alpha(
    tmp_path: Path,
):
    config = _config()
    config["automatic_analysis"]["cache_root"] = str(tmp_path / "cache")
    registry = build_registry(Path(config["session_transport"]["session_package_root"]))
    manager = AutomaticAnalysisManager(Path.cwd(), registry, config)
    try:
        manifest = registry.get_session_by_id("SN001")
        k_source = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        alpha_source = manager._source_signals(manifest, "alpha")
        assert k_source[0].canonical_role.value == "EEG_FRONTAL"
        assert k_source[0].original_channel_name == "EEG F4-M1"
        assert alpha_source[0].canonical_role.value == "EEG_OCCIPITAL"
    finally:
        manager.shutdown()


def test_n2_gating_bout_segmentation_and_provenance():
    annotations = (
        {"start_seconds": 0.0, "duration_seconds": 30.0, "normalized_label": "W"},
        {
            "start_seconds": 30.0,
            "duration_seconds": 30.0,
            "normalized_label": "N2",
            "raw_label": "Sleep stage 2",
            "scorer": "A",
        },
        {
            "start_seconds": 60.0,
            "duration_seconds": 30.0,
            "normalized_label": "N2",
            "raw_label": "2",
            "scorer": "A",
        },
        {"start_seconds": 90.0, "duration_seconds": 30.0, "normalized_label": "N3"},
        {
            "start_seconds": 120.0,
            "duration_seconds": 30.0,
            "normalized_label": "N2",
            "raw_label": "N2",
            "scorer": "B",
        },
    )
    bouts = segment_stage_bouts(annotations, _config()["k_complex_v0"])
    assert [(item.start_s, item.end_s) for item in bouts] == [(30.0, 90.0), (120.0, 150.0)]
    assert bouts[0].raw_labels == ("2", "Sleep stage 2")
    assert bouts[1].scorers == ("B",)


def test_trough_peak_bounds_and_ordinal_are_localized_on_deterministic_waveform():
    values, rate = _waveform()
    events = _detect(values, rate, _config()["k_complex_v0"])
    assert len(events) == 1
    event = events[0]
    assert abs(event.negative_trough_s - 8.0) <= 0.03
    assert event.positive_peak_s is not None
    assert abs(event.positive_peak_s - 8.65) <= 0.08
    assert event.onset_s < event.negative_trough_s < event.positive_peak_s < event.end_s
    assert event.duration_s == pytest.approx(event.end_s - event.onset_s)
    assert event.ordinal_in_n2_bout == 1
    assert event.negative_trough_amplitude < 0


def test_multiple_events_receive_sequential_ordinals_within_their_n2_bout():
    values, rate = _waveform()
    timestamps = np.arange(values.size) / rate
    values += -130.0 * np.exp(-0.5 * ((timestamps - 14.0) / 0.18) ** 2)
    values += 75.0 * np.exp(-0.5 * ((timestamps - 14.65) / 0.30) ** 2)
    events = _detect(values, rate, _config()["k_complex_v0"])
    assert [event.ordinal_in_n2_bout for event in events] == list(range(1, len(events) + 1))
    assert len(events) >= 2


def test_positive_peak_is_optional_and_never_invented():
    values, rate = _waveform()
    config = deepcopy(_config()["k_complex_v0"])
    config["morphology"]["positive_peak_min_robust_z"] = 1000.0
    events = _detect(values, rate, config)
    assert events
    event = min(events, key=lambda item: abs(item.negative_trough_s - 8.0))
    assert event.positive_peak_s is None


def test_refractory_suppression_keeps_stronger_duplicate():
    events = [
        {"negative_trough_s": 1.0, "score": 0.4},
        {"negative_trough_s": 1.2, "score": 0.9},
        {"negative_trough_s": 3.0, "score": 0.5},
    ]
    kept = suppress_refractory(events, 0.8)
    assert kept == [events[1], events[2]]


def test_unreasonable_amplitude_is_rejected():
    values, rate = _waveform(artifact=True)
    assert _detect(values, rate, _config()["k_complex_v0"]) == ()


def test_k_complex_cache_identity_includes_detector_configuration(tmp_path: Path):
    config = _config()
    config["automatic_analysis"]["cache_root"] = str(tmp_path / "cache")
    registry = build_registry(Path(config["session_transport"]["session_package_root"]))
    manager = AutomaticAnalysisManager(Path.cwd(), registry, config)
    try:
        manifest = registry.get_session_by_id("SN001")
        sources = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        original = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
        config["k_complex_v0"]["candidate"]["negative_depth_robust_z"] += 0.5
        changed = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
        assert original["source_fingerprint"] == changed["source_fingerprint"]
        assert original["configuration_hash"] != changed["configuration_hash"]
        assert original["cache_key"] != changed["cache_key"]
    finally:
        manager.shutdown()


def test_review_and_manual_annotations_persist_separately(tmp_path: Path):
    events = [{"event_id": "kc-one"}, {"event_id": "kc-two"}]
    store = KComplexAnnotationStore(
        tmp_path / "annotations.sqlite",
        events,
        review_labels=("Looks right", "Wrong", "Uncertain"),
        maximum_notes_characters=100,
    )
    store.save_review("kc-one", "Uncertain", "borderline morphology")
    store.save_manual(
        manual_event_id="manual-one",
        recording_id="recording",
        channel="F-test",
        stage="N2",
        n2_bout_id="N2-0001",
        negative_trough_s=12.5,
        notes="detector miss",
    )
    reloaded = KComplexAnnotationStore(
        tmp_path / "annotations.sqlite",
        events,
        review_labels=("Looks right", "Wrong", "Uncertain"),
        maximum_notes_characters=100,
    )
    assert reloaded.progress() == {
        "reviewed": 1,
        "total": 2,
        "label_counts": {"Uncertain": 1},
    }
    assert reloaded.reviews()[0]["event_id"] == "kc-one"
    assert reloaded.manual_events()[0]["event_type"] == "manual_k_complex_trough_candidate"
