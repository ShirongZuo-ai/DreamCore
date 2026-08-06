"""Tests for the real-data inspection script using synthetic data."""

import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from scripts.inspect_sleep_edf import build_summary, inspect_sleep_edf


def _config(output_path: Path) -> dict:
    return {
        "dataset": {"name": "synthetic Sleep-EDF"},
        "eeg": {"sampling_rate_hz": 2.0},
        "data": {
            "preload_edf": False,
            "sampling_rate_tolerance_hz": 0.01,
            "quality": {
                "flatline_threshold_s": 2.0,
                "max_nan_ratio": 0.0,
                "std_ddof": 0,
            },
        },
        "inspection": {
            "output_path": str(output_path),
            "json_indent": 2,
            "required_stage_descriptions": ["Sleep stage 2", "Sleep stage 3"],
        },
    }


def _annotations(onsets: list[float]) -> np.ndarray:
    annotations = np.empty(
        len(onsets),
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    annotations["onset"] = onsets
    annotations["duration"] = [2.0, 2.0]
    annotations["description"] = ["Sleep stage 2", "Sleep stage 3"]
    return annotations


def test_inspection_reuses_reader_and_writes_summary(tmp_path):
    output_path = tmp_path / "summary.json"
    config = _config(output_path)
    info = mne.create_info(["EEG", "EOG"], sfreq=2.0, ch_types=["eeg", "eog"])
    raw = mne.io.RawArray(np.arange(16.0).reshape(2, 8), info, verbose=False)
    annotations = _annotations([0.0, 2.0])
    quality_report = {"passed": True, "channels": {}}

    with (
        patch("scripts.inspect_sleep_edf.load_edf", return_value=(raw, annotations)) as loader,
        patch("scripts.inspect_sleep_edf.check_quality", return_value=quality_report) as quality,
    ):
        summary = inspect_sleep_edf(
            Path("SC0001E0-PSG.edf"),
            Path("SC0001EC-Hypnogram.edf"),
            output_path,
            config,
        )

    loader.assert_called_once()
    quality.assert_called_once_with(raw, config)
    assert summary["recording"]["sampling_rate_hz"] == 2.0
    assert summary["recording"]["duration_s"] == 4.0
    assert summary["annotations"]["stage_durations_s"] == {
        "Sleep stage 2": 2.0,
        "Sleep stage 3": 2.0,
    }
    assert summary["annotations"]["all_required_stages_present"] is True
    assert summary["alignment"]["overlap_duration_s"] == 4.0
    assert summary["alignment"]["has_valid_overlap"] is True
    assert json.loads(output_path.read_text(encoding="utf-8")) == summary


def test_build_summary_reports_invalid_time_overlap(tmp_path):
    config = _config(tmp_path / "summary.json")
    info = mne.create_info(["EEG"], sfreq=2.0, ch_types="eeg")
    raw = mne.io.RawArray(np.arange(8.0).reshape(1, 8), info, verbose=False)

    summary = build_summary(
        raw,
        _annotations([10.0, 12.0]),
        {"passed": True},
        config,
        Path("PSG.edf"),
        Path("Hypnogram.edf"),
    )

    assert summary["alignment"]["overlap_duration_s"] == 0.0
    assert summary["alignment"]["has_valid_overlap"] is False
