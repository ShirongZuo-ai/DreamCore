"""Tests for the reusable N3 EEG visualization pipeline."""

import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from scripts.visualize_n3_eeg import run_visualization


def test_visualization_writes_two_figures_and_structured_summary(tmp_path):
    sfreq = 10.0
    times = np.arange(100) / sfreq
    info = mne.create_info(["EEG A", "EEG B"], sfreq, ch_types=["eeg", "eeg"])
    raw = mne.io.RawArray(
        np.vstack((np.sin(2 * np.pi * times), np.cos(2 * np.pi * times))),
        info,
        verbose=False,
    )
    annotations = np.array(
        [(0.0, 5.0, "Sleep stage 3"), (5.0, 5.0, "Sleep stage 4")],
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    long_path = tmp_path / "long.png"
    short_path = tmp_path / "short.png"
    summary_path = tmp_path / "summary.json"
    config = {
        "dataset": {"name": "synthetic", "subject_id": "S01", "recording_id": "R01"},
        "eeg": {"sampling_rate_hz": sfreq},
        "data": {"preload_edf": False, "sampling_rate_tolerance_hz": 0.01},
        "sleep_staging": {
            "stage_labels": {"N3": ["Sleep stage 3", "Sleep stage 4"]},
            "unknown_label_policy": "raise",
            "unknown_label": "UNKNOWN",
            "merge_tolerance_s": 0.0,
        },
        "n3_extraction": {
            "target_label": "N3",
            "min_segment_duration_s": 1.0,
            "eeg_channels": ["EEG A", "EEG B"],
        },
        "preprocessing": {
            "active_profile": "raw_eeg",
            "eeg_channels": ["EEG A", "EEG B"],
            "profiles": {
                "raw_eeg": {
                    "reference": {"mode": "none", "channels": []},
                    "notch_freqs_hz": [],
                    "notch_method": "fir",
                    "bandpass": {"low_hz": None, "high_hz": None, "method": "fir"},
                    "detrend": "none",
                    "target_sampling_rate_hz": None,
                    "resample_method": "fft",
                    "boundary_discard_s": 0.0,
                }
            },
        },
        "n3_visualization": {
            "segment_id": "SC0001E0-PSG_n3_0001",
            "preprocessing_profile": "raw_eeg",
            "amplitude_scale": 1.0,
            "amplitude_unit": "V",
            "figure_width_inches": 6.0,
            "figure_height_per_channel_inches": 2.0,
            "dpi": 72,
            "raw_color": "#6B7280",
            "processed_color": "#2563EB",
            "raw_line_width": 0.7,
            "processed_line_width": 1.0,
            "raw_line_style": ":",
            "processed_line_style": "-",
            "grid_alpha": 0.18,
            "windows": {
                "long": {"offset_s": 1.0, "duration_s": 2.0, "output_path": "unused"},
                "short": {"offset_s": 3.0, "duration_s": 1.0, "output_path": "unused"},
            },
            "summary_json": "unused",
            "json_indent": 2,
        },
    }

    with patch("scripts.visualize_n3_eeg.load_edf", return_value=(raw, annotations)):
        summary = run_visualization(
            Path("SC0001E0-PSG.edf"),
            Path("SC0001EC-Hypnogram.edf"),
            config,
            output_paths={"long": long_path, "short": short_path},
            summary_path=summary_path,
        )

    assert summary["segment"]["segment_id"] == "SC0001E0-PSG_n3_0001"
    assert summary["channels"] == ["EEG A", "EEG B"]
    assert summary["sampling_rates_hz"] == {"original": sfreq, "output": sfreq}
    assert [figure["duration_s"] for figure in summary["figures"]] == [2.0, 1.0]
    assert long_path.stat().st_size > 0
    assert short_path.stat().st_size > 0
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary
