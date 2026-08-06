"""Tests for N3 metadata generation using synthetic data."""

import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from scripts.extract_n3_segments import run_extraction


def test_run_extraction_writes_reproducible_csv_and_json(tmp_path):
    config = {
        "eeg": {"sampling_rate_hz": 10.0},
        "data": {"preload_edf": False, "sampling_rate_tolerance_hz": 0.01},
        "sleep_staging": {
            "stage_labels": {
                "N2": ["Sleep stage 2"],
                "N3": ["Sleep stage 3", "Sleep stage 4"],
                "UNKNOWN": ["Sleep stage ?"],
            },
            "unknown_label_policy": "map_to_unknown",
            "unknown_label": "UNKNOWN",
            "merge_tolerance_s": 0.0,
        },
        "n3_extraction": {
            "target_label": "N3",
            "min_segment_duration_s": 2.0,
            "eeg_channels": ["EEG"],
            "output_csv": str(tmp_path / "n3.csv"),
            "output_json": str(tmp_path / "n3.json"),
            "json_indent": 2,
        },
    }
    info = mne.create_info(["EEG", "Resp"], sfreq=10.0, ch_types=["eeg", "resp"])
    raw = mne.io.RawArray(np.arange(100.0).reshape(2, 50), info, verbose=False)
    annotations = np.array(
        [
            (0.0, 2.0, "Sleep stage 3"),
            (2.0, 2.0, "Sleep stage 4"),
            (5.0, 2.0, "Sleep stage ?"),
        ],
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    csv_path = tmp_path / "n3.csv"
    json_path = tmp_path / "n3.json"

    with patch("scripts.extract_n3_segments.load_edf", return_value=(raw, annotations)) as loader:
        summary = run_extraction(
            Path("SC0001E0-PSG.edf"),
            Path("SC0001EC-Hypnogram.edf"),
            csv_path,
            json_path,
            config,
        )

    loader.assert_called_once()
    assert summary["statistics"]["n3_interval_count_before_merge"] == 2
    assert summary["statistics"]["n3_interval_count_after_merge"] == 1
    assert summary["statistics"]["retained_segment_count"] == 1
    assert summary["segments"][0]["raw_label_sources"] == [
        "Sleep stage 3",
        "Sleep stage 4",
    ]
    assert summary["segments"][0]["n_samples"] == 40
    assert json.loads(json_path.read_text(encoding="utf-8")) == summary
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "SC0001E0-PSG_n3_0001" in csv_text
    assert "Sleep stage 3|Sleep stage 4" in csv_text
