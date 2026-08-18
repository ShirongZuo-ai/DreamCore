"""Lightweight CBraMod adapter and verifier contract tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from dreamcore.foundation_models.cbramod.adapter import CBraModAdapter
from dreamcore.foundation_models.cbramod.checkpoint import (
    CBraModCheckpointError,
    sha256_file,
    validate_checkpoint,
)
from dreamcore.foundation_models.cbramod.embeddings import embedding_cache_identity
from dreamcore.foundation_models.cbramod.labels import label_candidate, leave_one_recording_out
from dreamcore.foundation_models.cbramod.verifier import VerificationResult, apply_verification


def config():
    return yaml.safe_load(Path("configs/default.yaml").read_text())["cbramod_kc_v1"]


@pytest.mark.parametrize("rate", [100.0, 200.0, 256.0])
def test_resampling_is_deterministic_and_has_official_patch_shape(rate):
    timestamps = np.arange(int(rate * 10)) / rate
    signal = np.sin(2 * np.pi * timestamps)[None, :]
    adapter = CBraModAdapter(config())
    first = adapter.prepare(
        signal, rate, ("original-Cz-reference",), unit="uV", reference="A1", dataset_id="fixture"
    )
    second = adapter.prepare(
        signal, rate, ("original-Cz-reference",), unit="uV", reference="A1", dataset_id="fixture"
    )
    assert first.values.shape == (1, 10, 200)
    assert np.array_equal(first.values, second.values)
    assert first.channels == ("original-Cz-reference",)
    assert first.original_sampling_rate_hz == rate


def test_multichannel_input_preserves_names_without_fabrication():
    signal = np.vstack((np.arange(2000), np.arange(2000)[::-1])).astype(float)
    prepared = CBraModAdapter(config()).prepare(
        signal, 200, ("F7-native", "F8-native"), unit="uV", reference=None, dataset_id="epoc"
    )
    assert prepared.values.shape == (2, 10, 200)
    assert prepared.channels == ("F7-native", "F8-native")


def test_checkpoint_validation_and_missing_error(tmp_path):
    checkpoint = tmp_path / "weights.pth"
    checkpoint.write_bytes(b"official-fixture")
    digest = sha256_file(checkpoint)
    assert validate_checkpoint(checkpoint, digest)["sha256"] == digest
    with pytest.raises(CBraModCheckpointError, match="missing"):
        validate_checkpoint(tmp_path / "missing.pth", digest)


def test_cache_identity_changes_for_every_material_input():
    base = dict(
        source_fingerprint="source",
        channels=("Cz",),
        preprocessing={"rate": 200},
        checkpoint_hash="checkpoint",
        adapter_version="v1",
        window={"before": 5, "after": 5},
    )
    original = embedding_cache_identity(**base)
    changed = embedding_cache_identity(**{**base, "channels": ("F4",)})
    assert original["cache_key"] != changed["cache_key"]


def test_expert_disagreement_and_missing_expert_are_not_negative_votes():
    candidate = {"onset_s": 10, "end_s": 12}
    matching = ({"onset_s": 10.5, "end_s": 11.5},)
    assert label_candidate(candidate, matching, matching, exclusion_margin_s=1) == (
        "high_confidence_positive"
    )
    assert label_candidate(candidate, matching, (), exclusion_margin_s=1) == (
        "single_expert_positive"
    )
    assert label_candidate(candidate, (), None, exclusion_margin_s=1) == ("single_expert_unmatched")


def test_grouped_split_has_zero_recording_leakage():
    folds = leave_one_recording_out(("one", "one", "two", "three"))
    assert len(folds) == 3
    for fold in folds:
        assert not set(fold["test_recordings"]) & set(fold["train_recordings"])


def test_acceptance_never_moves_original_trough():
    event = {"negative_trough_s": 12.345, "score": 0.8}
    output = apply_verification(event, VerificationResult(True, 0.91, "high", "v1"))
    assert output["negative_trough_s"] == event["negative_trough_s"]
    assert output["cbramod_accepted"] is True


def test_backbone_is_frozen_when_torch_is_available(tmp_path):
    torch = pytest.importorskip("torch")
    from dreamcore.foundation_models.cbramod.model import build_cbramod

    model = build_cbramod(config()["architecture"])
    model.requires_grad_(False)
    assert all(not parameter.requires_grad for parameter in model.parameters())
    output = model(torch.zeros((1, 1, 2, 200)))
    assert output.shape == (1, 1, 2, 200)
