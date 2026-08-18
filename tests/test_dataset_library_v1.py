"""Multi-dataset catalog, adapter, and native-window contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml
from pyedflib import highlevel

from dreamcore.datasets.edf import inspect_edf
from dreamcore.datasets.indexing import HmcSleepStagingIndexer, IsrucCohortIIIIndexer
from dreamcore.datasets.models import CanonicalSignalRole, CapabilityName, CapabilityState
from dreamcore.datasets.repository import SessionPackageRepository


def _write_psg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    signals = [
        np.linspace(-50, 50, 1500, dtype=float),
        np.linspace(-25, 25, 3000, dtype=float),
        np.linspace(-10, 10, 750, dtype=float),
    ]
    headers = [
        highlevel.make_signal_header(
            "EEG F3-M2",
            dimension="uV",
            sample_frequency=10,
            physical_min=-100,
            physical_max=100,
        ),
        highlevel.make_signal_header(
            "E1-M2",
            dimension="uV",
            sample_frequency=20,
            physical_min=-100,
            physical_max=100,
        ),
        highlevel.make_signal_header(
            "ECG",
            dimension="mV",
            sample_frequency=5,
            physical_min=-20,
            physical_max=20,
        ),
    ]
    highlevel.write_edf(
        str(path.with_suffix(".edf")), signals, headers, highlevel.make_header(), digital=False
    )
    if path.suffix == ".rec":
        path.with_suffix(".edf").replace(path)


def _library_config() -> dict:
    return yaml.safe_load(Path("configs/dataset_library_v1.yaml").read_text())


def _indexer_kwargs(tmp_path: Path, config: dict) -> dict:
    return {
        "project_root": tmp_path,
        "raw_root": tmp_path / "raw",
        "package_root": tmp_path / "packages",
        "role_rules": tuple(config["signal_role_rules"]),
        "viewer_config": config["viewer"],
        "download_audit": {},
    }


def test_native_edf_header_and_bounded_window_preserve_per_channel_rates(
    tmp_path: Path, monkeypatch
):
    config = _library_config()
    dataset = dict(config["datasets"]["hmc"])
    dataset["raw_subdirectory"] = "hmc"
    dataset["recordings"] = {
        "SNTEST": {
            "subject_id": "SNTEST",
            "psg": {"name": "SNTEST.edf"},
            "annotations": {"name": "SNTEST_sleepscoring.edf"},
            "annotation_audit": {"name": "SNTEST_sleepscoring.txt"},
        }
    }
    raw = tmp_path / "raw" / "hmc"
    _write_psg(raw / "SNTEST.edf")
    (raw / "SNTEST_sleepscoring.edf").touch()
    (raw / "SNTEST_sleepscoring.txt").write_text("W\n", encoding="utf-8")
    monkeypatch.setattr(
        HmcSleepStagingIndexer,
        "_edf_stage_descriptor",
        lambda self, path: {
            "available": True,
            "source": "imported",
            "metadata": {"contains_stages": ["W"], "primary_for_viewer": True},
        },
    )

    header = inspect_edf(raw / "SNTEST.edf")
    assert [channel.sampling_rate_hz for channel in header.channels] == [10.0, 20.0, 5.0]
    [indexed] = HmcSleepStagingIndexer(dataset, **_indexer_kwargs(tmp_path, config)).index()
    repository = SessionPackageRepository(tmp_path / "packages")
    [manifest] = repository.discover()
    assert indexed.recording_id == "SNTEST"
    assert [signal.original_channel_name for signal in manifest.signals] == [
        "EEG F3-M2",
        "E1-M2",
        "ECG",
    ]
    assert [signal.canonical_role for signal in manifest.signals] == [
        CanonicalSignalRole.EEG_FRONTAL,
        CanonicalSignalRole.EOG_LEFT,
        CanonicalSignalRole.ECG,
    ]
    adapter = repository.adapters()[0]
    window = adapter.load_signal_window("SNTEST", "eog-1", 1.0, 2.0)
    assert len(window.samples) == 40
    assert window.signal.sampling_rate_hz == 20.0
    assert manifest.capability(CapabilityName.EYE_MOVEMENT_ACTIVITY).status is (
        CapabilityState.PLANNED
    )
    assert "not computed" in manifest.derived["eye_movement_activity_v1"].reason


def test_isruc_preserves_both_scorers_and_raw_stage_labels(tmp_path: Path):
    config = _library_config()
    dataset = dict(config["datasets"]["isruc"])
    dataset["raw_subdirectory"] = "isruc"
    dataset["expected_subjects"] = ["1"]
    subject = tmp_path / "raw" / "isruc" / "1"
    _write_psg(subject / "1.rec")
    (subject / "1_1.txt").write_text("0\n1\n2\n3\n5\n", encoding="utf-8")
    (subject / "1_2.txt").write_text("0\n1\n2\n4\n5\n", encoding="utf-8")

    [indexed] = IsrucCohortIIIIndexer(dataset, **_indexer_kwargs(tmp_path, config)).index()
    repository = SessionPackageRepository(tmp_path / "packages")
    [manifest] = repository.discover()
    assert indexed.recording_id == "isruc-c3-01"
    assert set(manifest.annotations) == {
        "sleep_stages",
        "sleep_stages_scorer_1",
        "sleep_stages_scorer_2",
    }
    adapter = repository.adapters()[0]
    scorer_one = adapter.load_annotations("isruc-c3-01", "sleep_stages_scorer_1")
    scorer_two = adapter.load_annotations("isruc-c3-01", "sleep_stages_scorer_2")
    assert [item["raw_label"] for item in scorer_one[:4]] == ["0", "1", "2", "3"]
    assert [item["normalized_label"] for item in scorer_one[:4]] == ["W", "N1", "N2", "N3"]
    assert scorer_two[3]["raw_label"] == "4"
    assert scorer_two[3]["normalized_label"] == "N3"
    assert scorer_one[0]["scorer"] == "1"
    assert scorer_two[0]["scorer"] == "2"
    raw_manifest = json.loads(indexed.manifest_path.read_text(encoding="utf-8"))
    assert raw_manifest["annotations"]["sleep_stages"]["metadata"]["primary_for_viewer"] is True
    assert (
        raw_manifest["annotations"]["sleep_stages_scorer_2"]["metadata"]["primary_for_viewer"]
        is False
    )
