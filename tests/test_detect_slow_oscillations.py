"""Tests for the end-to-end slow-oscillation candidate audit script."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from scripts.detect_slow_oscillations import run_detection


def test_detection_pipeline_writes_events_summary_and_qa_figure(tmp_path):
    sfreq = 50.0
    times = np.arange(int(20 * sfreq)) / sfreq
    data = np.vstack(
        (
            -20e-6 * np.sin(2 * np.pi * times),
            -30e-6 * np.sin(2 * np.pi * times + 0.1),
        )
    )
    info = mne.create_info(["EEG A", "EEG B"], sfreq, ch_types=["eeg", "eeg"])
    raw = mne.io.RawArray(data, info, verbose=False)
    annotations = np.array(
        [(0.0, 20.0, "Sleep stage 3")],
        dtype=[("onset", np.float64), ("duration", np.float64), ("description", object)],
    )
    events_path = tmp_path / "events.csv"
    summary_path = tmp_path / "summary.json"
    qa_path = tmp_path / "qa.png"
    config = {
        "dataset": {"name": "synthetic", "subject_id": "S01", "recording_id": "R01"},
        "eeg": {"sampling_rate_hz": sfreq},
        "data": {"preload_edf": False, "sampling_rate_tolerance_hz": 0.01},
        "sleep_staging": {
            "stage_labels": {"N3": ["Sleep stage 3"]},
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
            "active_profile": "input",
            "eeg_channels": ["EEG A", "EEG B"],
            "profiles": {
                "input": {
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
        "slow_oscillation": {
            "active_profile": "test",
            "amplitude_scale_to_uv": 1e6,
            "profiles": {
                "test": {
                    "detection_band": {"low_hz": 0.5, "high_hz": 2.0, "method": "fir"},
                    "duration": {
                        "negative_halfwave_min_s": 0.3,
                        "negative_halfwave_max_s": 0.7,
                        "full_cycle_min_s": 0.8,
                        "full_cycle_max_s": 1.2,
                    },
                    "amplitude": {
                        "strategy": "none",
                        "metric": "peak_to_peak_amplitude_uv",
                        "fixed_min_uv": None,
                        "quantile": 0.75,
                    },
                    "artifact_rejection": {
                        "boundary_exclusion_s": 1.0,
                        "max_peak_to_peak_uv": 500.0,
                        "invalid_time_masks": [],
                    },
                }
            },
            "overlap": {"accepted_only": True, "min_overlap_s": 0.0},
            "output_csv": "unused.csv",
            "summary_json": "unused.json",
            "json_indent": 2,
            "qa": {
                "segment_id": "SC0001E0-PSG_n3_0001",
                "preprocessing_profile": "input",
                "offset_s": 5.0,
                "duration_s": 5.0,
                "output_path": "unused.png",
                "figure_width_inches": 8.0,
                "figure_height_per_channel_inches": 2.5,
                "dpi": 72,
                "amplitude_scale": 1e6,
                "amplitude_unit": "µV",
                "raw_color": "#6B7280",
                "detection_color": "#1D4ED8",
                "accepted_color": "#2563EB",
                "rejected_color": "#D97706",
                "grid_alpha": 0.18,
            },
        },
    }

    with patch("scripts.detect_slow_oscillations.load_edf", return_value=(raw, annotations)):
        summary = run_detection(
            Path("SC0001E0-PSG.edf"),
            Path("SC0001EC-Hypnogram.edf"),
            config,
            events_csv_path=events_path,
            summary_json_path=summary_path,
            qa_output_path=qa_path,
        )

    assert summary["total_candidate_event_count"] > 0
    assert summary["total_accepted_event_count"] > 0
    assert set(summary["per_channel"]) == {"EEG A", "EEG B"}
    assert summary["overlap"][0]["overlapping_event_pair_count"] > 0
    assert qa_path.stat().st_size > 0
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary
    with events_path.open(encoding="utf-8", newline="") as events_file:
        rows = list(csv.DictReader(events_file))
    assert len(rows) == summary["total_candidate_event_count"]
    assert rows[0]["detector_profile"] == "test"
    assert "downward_zero_crossing_s" in rows[0]
    assert "rejection_reasons" in rows[0]
