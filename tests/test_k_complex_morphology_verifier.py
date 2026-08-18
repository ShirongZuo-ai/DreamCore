"""Frozen morphology B1 artifact, inference, product, and benchmark regressions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from dreamcore.analysis.manager import FEATURE_K_COMPLEX, AutomaticAnalysisManager
from dreamcore.api.http import build_registry
from dreamcore.k_complex import (
    MORPHOLOGY_B1_FEATURE_NAMES,
    MorphologyB1Verifier,
    detect_k_complexes,
    load_morphology_b1_verifier,
    morphology_b1_features,
    verify_k_complex_candidate,
)
from dreamcore.k_complex.verifier import artifact_checksum
from dreamcore.validation.dreams import (
    excerpt_index,
    load_k_complex_signal,
    load_n2_bouts,
    recording_paths,
)


def _full_config() -> dict:
    return yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))


def _verifier() -> MorphologyB1Verifier:
    config = _full_config()["automatic_analysis"]["k_complex"]["verifier"]
    return load_morphology_b1_verifier(
        Path(config["artifact_path"]),
        expected_version=str(config["version"]),
        expected_checksum=str(config["artifact_checksum"]),
        expected_threshold=float(config["decision_threshold"]),
    )


def _candidate(**overrides) -> dict:
    return {
        "event_id": "kc-fixture",
        "score": 0.9,
        "duration_s": 1.2,
        "negative_trough_amplitude": -120.0,
        "negative_trough_s": 10.0,
        "positive_peak_s": 10.5,
        "onset_s": 9.5,
        "end_s": 10.7,
        **overrides,
    }


def test_exact_frozen_b1_feature_order_and_deterministic_extraction() -> None:
    assert MORPHOLOGY_B1_FEATURE_NAMES == (
        "score",
        "duration_s",
        "negative_trough_amplitude",
        "positive_peak_delay_s",
    )
    candidate = _candidate()
    expected = (0.9, 1.2, -120.0, 0.5)
    assert morphology_b1_features(candidate) == expected
    assert morphology_b1_features(candidate) == morphology_b1_features(candidate)
    assert morphology_b1_features(_candidate(positive_peak_s=None))[-1] == 0.0


def test_final_artifact_loads_and_probability_matches_frozen_coefficients() -> None:
    verifier = _verifier()
    result = verify_k_complex_candidate(
        _candidate(), morphology_b1_features(_candidate()), verifier
    )
    assert verifier.feature_names == MORPHOLOGY_B1_FEATURE_NAMES
    assert result.probability == pytest.approx(0.5532194888284978, abs=1e-15)
    assert result.accepted is True
    assert result.verification_status == "accepted"
    assert result.verification_method == "morphology_b1"


def test_threshold_is_inclusive_and_status_is_not_ground_truth() -> None:
    accepted = MorphologyB1Verifier(
        version="fixture",
        feature_names=MORPHOLOGY_B1_FEATURE_NAMES,
        scaler_mean=(0.0, 0.0, 0.0, 0.0),
        scaler_scale=(1.0, 1.0, 1.0, 1.0),
        coefficients=(0.0, 0.0, 0.0, 0.0),
        intercept=0.0,
        threshold=0.5,
        checksum="fixture",
    ).verify(_candidate(), (0.0, 0.0, 0.0, 0.0))
    rejected = MorphologyB1Verifier(
        version="fixture",
        feature_names=MORPHOLOGY_B1_FEATURE_NAMES,
        scaler_mean=(0.0, 0.0, 0.0, 0.0),
        scaler_scale=(1.0, 1.0, 1.0, 1.0),
        coefficients=(0.0, 0.0, 0.0, 0.0),
        intercept=0.0,
        threshold=0.5000001,
        checksum="fixture",
    ).verify(_candidate(), (0.0, 0.0, 0.0, 0.0))
    assert accepted.probability == 0.5 and accepted.accepted
    assert rejected.probability == 0.5 and not rejected.accepted
    assert {accepted.verification_status, rejected.verification_status} == {"accepted", "rejected"}


def test_verification_enriches_a_copy_and_never_changes_landmarks() -> None:
    candidate = _candidate()
    original = dict(candidate)
    verified = _verifier().apply(candidate)
    assert candidate == original
    assert verified["trough_s"] == original["negative_trough_s"]
    for key in ("onset_s", "negative_trough_s", "positive_peak_s", "end_s", "duration_s"):
        assert verified[key] == original[key]
    assert verified["original_candidate_id"] == original["event_id"]
    assert verified["original_morphology_score"] == original["score"]


def test_artifact_checksum_rejects_any_material_change(tmp_path: Path) -> None:
    config = _full_config()["automatic_analysis"]["k_complex"]["verifier"]
    payload = json.loads(Path(config["artifact_path"]).read_text(encoding="utf-8"))
    assert artifact_checksum(payload) == config["artifact_checksum"]
    payload["classifier"]["intercept"] += 0.01
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_morphology_b1_verifier(
            tampered,
            expected_version=str(config["version"]),
            expected_checksum=str(config["artifact_checksum"]),
            expected_threshold=float(config["decision_threshold"]),
        )


def test_default_config_is_b1_and_cbramod_is_optional() -> None:
    config = _full_config()
    product = config["automatic_analysis"]["k_complex"]
    assert product["algorithm_version"] == "k-complex-morphology-b1-v1"
    assert product["verifier"]["method"] == "morphology_b1"
    assert product["verifier"]["default_enabled"] is True
    assert config["cbramod_kc_v1"]["status"] == "research_comparison_only"
    assert config["cbramod_kc_v1"]["default_enabled"] is False


def test_product_cache_identity_invalidates_on_verifier_version_or_checksum(tmp_path: Path) -> None:
    full = _full_config()
    full["automatic_analysis"]["cache_root"] = str(tmp_path / "first")
    registry = build_registry(Path(full["session_transport"]["session_package_root"]))
    manager = AutomaticAnalysisManager(Path.cwd(), registry, full)
    try:
        manifest = registry.get_session_by_id("SN001")
        sources = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        original = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
    finally:
        manager.shutdown()
    changed = _full_config()
    changed["automatic_analysis"]["cache_root"] = str(tmp_path / "second")
    changed["automatic_analysis"]["k_complex"]["verifier"]["version"] += "-changed"
    changed["automatic_analysis"]["k_complex"]["verifier"]["artifact_checksum"] = "changed"
    manager = AutomaticAnalysisManager(Path.cwd(), registry, changed)
    try:
        updated = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
    finally:
        manager.shutdown()
    assert updated["configuration_hash"] != original["configuration_hash"]
    assert updated["cache_key"] != original["cache_key"]


def test_hmc_single_channel_product_path_needs_no_cbramod_checkpoint(tmp_path: Path) -> None:
    full = _full_config()
    raw = Path("data/datasets/raw/hmc_sleep_staging/1.1/recordings/SN001.edf")
    if not raw.is_file():
        pytest.skip("ignored HMC sanity source is not installed")
    full["automatic_analysis"]["cache_root"] = str(tmp_path / "cache")
    full["cbramod_kc_v1"]["checkpoint_path"] = str(tmp_path / "missing-cbramod.pth")
    registry = build_registry(Path(full["session_transport"]["session_package_root"]))
    manager = AutomaticAnalysisManager(Path.cwd(), registry, full)
    try:
        manifest = registry.get_session_by_id("SN001")
        sources = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        assert len(sources) == 1
        identity = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
        output = manager._run_k_complex(manifest, sources, identity)
        assert output["analysis"]["candidate_count"] == 226
        assert output["analysis"]["verified_count"] == 22
        assert output["analysis"]["rejected_count"] == 204
        metadata = manager._finalize_output(
            manifest, FEATURE_K_COMPLEX, identity, output, duration_ms=0
        )
        metadata_path = manager._metadata_path("SN001", FEATURE_K_COMPLEX)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        payload = manager.k_complex_payload("SN001")
        assert payload["verification_method"] == "morphology_b1"
        assert payload["candidate_count"] == 226
        assert payload["verified_count"] == 22
        assert payload["rejected_count"] == 204
        assert all(row["trough_s"] == row["negative_trough_s"] for row in payload["events"])
    finally:
        manager.shutdown()


def test_frozen_b1_grouped_benchmark_reproduces_when_dreams_is_available() -> None:
    sklearn = pytest.importorskip("sklearn")
    del sklearn
    from scripts.run_cbramod_kc_v1 import grouped_predictions, intervals, metrics

    full = _full_config()
    config = full["cbramod_kc_v1"]
    validation = full["signal_validation_v1"]
    dreams = validation["dreams"]
    dreams_kc = dreams["k_complex"]
    detector = full["k_complex_v0"]
    root = Path(dreams_kc["extracted_root"])
    if not root.is_dir():
        pytest.skip("ignored DREAMS benchmark source is not installed")
    features = []
    labels = []
    groups = []
    for edf_path in recording_paths(root, dreams_kc["recording_glob"]):
        index = excerpt_index(edf_path)
        recording_id = f"dreams-kc-excerpt{index}"
        signal_path = root / dreams_kc["signal_text_template"].format(index=index)
        channel, signal = load_k_complex_signal(
            signal_path, expected_rate_hz=float(dreams_kc["sampling_rate_hz"])
        )
        bouts = load_n2_bouts(
            root / dreams_kc["hypnogram_template"].format(index=index), dreams, detector
        )
        events = detect_k_complexes(
            signal,
            float(dreams_kc["sampling_rate_hz"]),
            channel,
            bouts,
            detector,
            dataset_id="dreams-k-complexes",
            subject_id=f"excerpt{index}",
            recording_id=recording_id,
            detector_version=detector["detector_version"],
            config_hash="benchmark-regression",
            source_fingerprint="local-ignored-source",
        )
        expert_1 = intervals(
            root / dreams_kc["expert_1_template"].format(index=index),
            recording_id,
            "expert_1",
        )
        expert_2 = intervals(
            root / dreams_kc["expert_2_template"].format(index=index),
            recording_id,
            "expert_2",
        )
        from dreamcore.foundation_models.cbramod.labels import label_candidate

        for event in events:
            label = label_candidate(
                event.to_dict(),
                expert_1 or (),
                expert_2,
                exclusion_margin_s=float(config["exclusion_margin_s"]),
            )
            if label not in {"high_confidence_positive", "high_confidence_negative"}:
                continue
            features.append(morphology_b1_features(event))
            labels.append(label == "high_confidence_positive")
            groups.append(recording_id)
    matrix = np.asarray(features, dtype=float)
    truth = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups)
    result = metrics(
        truth,
        grouped_predictions(matrix, truth, group_array, config),
        float(config["classifier"]["decision_threshold"]),
    )
    assert truth.size == 108
    assert result["precision"] == pytest.approx(0.575)
    assert result["recall"] == pytest.approx(0.8214285714285714)
    assert result["f1"] == pytest.approx(0.6764705882352942)
    assert result["auroc"] == pytest.approx(0.9044642857142857)
    assert result["auprc"] == pytest.approx(0.83225600915748)
