"""Contract tests for the real-metadata Alpha V1 Session Package."""

import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from dreamcore.datasets.models import (
    CapabilityName,
    CapabilityState,
    ProvenanceClass,
)
from dreamcore.datasets.registry import DatasetRegistry
from dreamcore.datasets.repository import SessionPackageRepository

PACKAGE_ROOT = Path("data/session_packages")
MANIFEST_PATH = PACKAGE_ROOT / "sleep-edf" / "sc4001-alpha-v1" / "manifest.json"


def _contains_samples(value) -> bool:
    if isinstance(value, dict):
        return "samples" in value or any(_contains_samples(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_samples(item) for item in value)
    return False


def test_real_alpha_manifest_is_discoverable_without_signal_payloads():
    raw_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    repository = SessionPackageRepository(PACKAGE_ROOT)
    manifests = repository.discover()

    manifest = next(item for item in manifests if item.session.session_id == "sc4001-alpha-v1")
    assert manifest.schema_version == "dreamcore.session.v1"
    assert manifest.session.session_id == "sc4001-alpha-v1"
    assert manifest.provenance.classification is ProvenanceClass.IMPORTED
    assert manifest.has_n3
    assert "REAL PUBLIC EEG DATA" in manifest.provenance.notes
    assert "SIMULATED STIMULATION EVENTS" in manifest.provenance.notes
    assert not _contains_samples(raw_manifest)
    replay = raw_manifest["derived"]["alpha_power"]["metadata"]["viewer"]["replay"]
    viewer = raw_manifest["derived"]["alpha_power"]["metadata"]["viewer"]
    analysis = raw_manifest["derived"]["alpha_power"]["metadata"]["analysis"]
    assert viewer["feature_timestamp_semantics"] == "window_end"
    assert viewer["default_start_s"] <= viewer["default_time_s"]
    assert viewer["stage_jump_time_s"] is not None
    assert replay["enabled"] is True
    assert replay["tick_interval_ms"] > 0
    assert replay["default_speed"] in replay["speed_options"]
    assert 0.5 in replay["speed_options"]
    assert replay["cache_max_windows"] > 0
    assert 0 < replay["prefetch_threshold_fraction"] < 1
    assert 0 <= replay["seek_cursor_fraction"] < 1
    assert replay["provenance_notice"] == ("SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED")
    assert analysis["time_reference"] == "recording_relative"
    assert analysis["timestamp_field"] == "window_end_s"
    assert analysis["timestamp_unit"] == "seconds"
    assert analysis["first_feature_time_s"] == (
        analysis["evaluation_start_s"] + analysis["analysis_window_s"]
    )
    assert analysis["feature_row_count"] == (
        analysis["accepted_windows"] * len(analysis["channels"])
    )
    assert analysis["channels"] == ["EEG Fpz-Cz", "EEG Pz-Oz"]
    assert analysis["rejection_reasons"] == {
        "stage_transition:N1+N2": 2,
        "stage_transition:N1+W": 2,
    }


def test_alpha_capabilities_preserve_raw_derived_and_simulated_provenance():
    manifest = next(
        item
        for item in SessionPackageRepository(PACKAGE_ROOT).discover()
        if item.session.session_id == "sc4001-alpha-v1"
    )

    assert manifest.capability(CapabilityName.EEG).source is ProvenanceClass.RAW
    assert manifest.capability(CapabilityName.ALPHA_POWER).source is ProvenanceClass.DERIVED
    assert manifest.capability(CapabilityName.EOG).source is ProvenanceClass.RAW
    assert (
        manifest.capability(CapabilityName.EYE_MOVEMENT_ACTIVITY).source is ProvenanceClass.DERIVED
    )
    assert manifest.capability(CapabilityName.SONIFICATION_CONTROLS).status is (
        CapabilityState.AVAILABLE
    )
    assert (
        manifest.capability(CapabilityName.STIMULATION_DEMAND).source is ProvenanceClass.SIMULATED
    )
    assert manifest.capability(CapabilityName.READY_TO_REMOVE).status is CapabilityState.AVAILABLE


def test_registry_discovers_alpha_session_and_adapter_reads_only_window():
    repository = SessionPackageRepository(PACKAGE_ROOT)
    adapter = next(
        adapter
        for adapter in repository.adapters()
        if any(
            summary.session.session_id == "sc4001-alpha-v1" for summary in adapter.list_sessions()
        )
    )
    registry = DatasetRegistry()
    registry.register(adapter)
    assert any(
        summary.session.session_id == "sc4001-alpha-v1" for summary in registry.list_sessions()
    )

    sfreq = 100.0
    times = np.arange(int(5 * sfreq)) / sfreq
    data = np.vstack(
        (
            20e-6 * np.sin(2 * np.pi * 10 * times),
            10e-6 * np.sin(2 * np.pi * 10 * times),
        )
    )
    info = mne.create_info(["EEG Fpz-Cz", "EEG Pz-Oz"], sfreq, ch_types=["eeg", "eeg"])
    raw = mne.io.RawArray(data, info, verbose=False)

    with patch("dreamcore.datasets.repository.mne.io.read_raw_edf", return_value=raw):
        window = adapter.load_signal_window(
            "sc4001-alpha-v1", "eeg-1", start_seconds=1.0, duration_seconds=2.0
        )

    assert len(window.samples) == 200
    assert window.duration_seconds == 2.0
    assert 19.0 < max(window.samples) < 20.1
