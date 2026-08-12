"""End-to-end tests for the offline Hilbert phase audit script."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import mne
import numpy as np

from scripts.estimate_hilbert_phase import LANDMARK_FIELDS, run_phase_estimation


def _test_config(sfreq: float) -> dict:
    return {
        "dataset": {
            "name": "synthetic",
            "subject_id": "S01",
            "recording_id": "R01",
        },
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
            "active_profile": "strict_test",
            "amplitude_scale_to_uv": 1e6,
            "profiles": {
                "strict_test": {
                    "detection_band": {
                        "low_hz": 0.5,
                        "high_hz": 2.0,
                        "method": "fir",
                    },
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
        },
        "hilbert_phase": {
            "active_profile": "offline_test",
            "amplitude_scale_to_uv": 1e6,
            "profiles": {
                "offline_test": {
                    "phase_band": {
                        "low_hz": 0.5,
                        "high_hz": 2.0,
                        "method": "fir",
                        "phase": "zero",
                    },
                    "project_phase_offset_rad": -float(np.pi),
                    "boundary_invalid_s": 1.0,
                    "min_signal_duration_s": 5.0,
                    "constant_std_tolerance": 0.0,
                    "amplitude_envelope": {
                        "strategy": "none",
                        "fixed_min_uv": None,
                        "quantile": 0.1,
                    },
                    "instantaneous_frequency": {
                        "enabled": True,
                        "min_hz": 0.2,
                        "max_hz": 3.0,
                    },
                    "invalid_time_masks": [],
                    "expected_landmark_phases_rad": {
                        "downward_zero_crossing": -float(np.pi / 2),
                        "trough": 0.0,
                        "upward_zero_crossing": float(np.pi / 2),
                        "positive_peak": float(np.pi),
                    },
                    "event_validation": {
                        "reverse_step_tolerance_rad": 0.05,
                        "max_reverse_step_fraction": 0.05,
                        "min_forward_advance_rad": float(np.pi),
                        "min_event_valid_fraction": 0.9,
                    },
                }
            },
            "cross_channel": {
                "accepted_only": True,
                "min_overlap_s": 0.0,
                "comparison_time": "overlap_midpoint",
            },
            "landmarks_csv": "unused.csv",
            "summary_json": "unused.json",
            "json_indent": 2,
            "qa": {
                "segment_id": "SC0001E0-PSG_n3_0001",
                "preprocessing_profile": "input",
                "detector_profile": "strict_test",
                "phase_profile": "offline_test",
                "offset_s": 5.0,
                "duration_s": 5.0,
                "output_path": "unused.png",
                "figure_width_inches": 10.0,
                "figure_height_inches": 7.0,
                "dpi": 72,
                "amplitude_unit": "µV",
                "signal_color": "#1D4ED8",
                "phase_color": "#7C3AED",
                "envelope_color": "#059669",
                "accepted_color": "#2563EB",
                "invalid_color": "#D97706",
                "grid_alpha": 0.18,
            },
        },
    }


def test_phase_pipeline_writes_landmarks_summary_and_qa_figure(tmp_path):
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
    landmarks_path = tmp_path / "landmarks.csv"
    summary_path = tmp_path / "summary.json"
    qa_path = tmp_path / "qa.png"

    with patch("scripts.estimate_hilbert_phase.load_edf", return_value=(raw, annotations)):
        summary = run_phase_estimation(
            Path("SC0001E0-PSG.edf"),
            Path("SC0001EC-Hypnogram.edf"),
            _test_config(sfreq),
            landmarks_csv_path=landmarks_path,
            summary_json_path=summary_path,
            qa_output_path=qa_path,
        )

    accepted = summary["detector"]["accepted_event_count"]
    assert accepted > 0
    assert set(summary["per_channel"]) == {"EEG A", "EEG B"}
    assert all(
        channel_summary["valid_phase_ratio"] > 0
        for channel_summary in summary["per_channel"].values()
    )
    assert summary["cross_channel_phase_difference"][0]["valid_pair_count"] > 0
    assert summary["qa_figure"]["duration_s"] == 5.0
    assert qa_path.stat().st_size > 0
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary

    with landmarks_path.open(encoding="utf-8", newline="") as landmarks_file:
        rows = list(csv.DictReader(landmarks_file))
    assert len(rows) == accepted * 4
    assert list(rows[0]) == LANDMARK_FIELDS
    assert rows[0]["preprocessing_profile"] == "input"
    assert rows[0]["detector_profile"] == "strict_test"
    assert rows[0]["phase_profile"] == "offline_test"
