"""Task-appropriate cross-feature contamination checks on synthetic signals."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np

from dreamcore.alpha import extract_alpha_features
from dreamcore.eye_movement import extract_eye_movement_track
from dreamcore.k_complex import N2Bout, detect_k_complexes
from dreamcore.validation.synthetic import cross_talk_cases


def run_synthetic_crosstalk(
    full_config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validation = full_config["signal_validation_v1"]
    config = validation["synthetic_crosstalk"]
    rate = float(config["sampling_rate_hz"])
    duration = float(config["duration_s"])
    alpha_product = full_config["automatic_analysis"]["alpha"]
    window_samples = int(round(float(alpha_product["analysis_window_s"]) * rate))
    step_samples = int(round(float(alpha_product["step_s"]) * rate))
    kc_config = full_config["k_complex_v0"]
    alpha_scale_to_uv = float(full_config["alpha"]["input_scale_to_uv"])
    alpha_profile = str(full_config["alpha"]["active_profile"])
    display_min_confidence = float(
        full_config["alpha"]["profiles"][alpha_profile]["iaf"]["product_display_min_confidence"]
    )
    kc_hash = hashlib.sha256(
        json.dumps(kc_config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    bout = N2Bout("synthetic-N2-0001", "N2", 0.0, duration, ("synthetic",), ("ground_truth",))
    rows = []
    for case in cross_talk_cases(config):
        alpha_features = []
        for start in range(0, case.eeg_posterior_uv.size - window_samples + 1, step_samples):
            alpha_features.append(
                extract_alpha_features(
                    case.eeg_posterior_uv[start : start + window_samples] / alpha_scale_to_uv,
                    rate,
                    str(config["eeg_posterior_channel"]),
                    start / rate,
                    (start + window_samples) / rate,
                    "N2",
                    full_config,
                )
            )
        alpha_power = [
            float(item.absolute_alpha_power)
            for item in alpha_features
            if item.absolute_alpha_power is not None
        ]
        reliable_peaks = [
            item
            for item in alpha_features
            if item.iaf_available and item.iaf_confidence >= display_min_confidence
        ]
        kc_events = detect_k_complexes(
            case.eeg_frontal_uv,
            rate,
            str(config["eeg_frontal_channel"]),
            (bout,),
            kc_config,
            dataset_id="synthetic-crosstalk",
            subject_id=str(case.seed),
            recording_id=case.case_id,
            detector_version=str(kc_config["detector_version"]),
            config_hash=kc_hash,
            source_fingerprint=hashlib.sha256(case.eeg_frontal_uv.tobytes()).hexdigest(),
        )
        eye_track = extract_eye_movement_track(
            case.eog_uv,
            rate,
            str(config["eog_channel"]),
            case.case_id,
            None,
            full_config,
        )
        rows.append(
            {
                "case_id": case.case_id,
                "family": case.family,
                "seed": case.seed,
                "level": case.level,
                "true_alpha": case.true_alpha,
                "true_k_complex": case.true_k_complex,
                "true_eog": case.true_eog,
                "median_absolute_alpha_power": float(np.median(alpha_power))
                if alpha_power
                else None,
                "reliable_alpha_peak_rate": len(reliable_peaks) / len(alpha_features)
                if alpha_features
                else None,
                "k_complex_detection_count": len(kc_events),
                "eye_movement_candidate_count": len(eye_track.events),
                "false_k_complex_per_hour": (
                    len(kc_events) * 3600.0 / duration if not case.true_k_complex else None
                ),
                "false_eye_candidates_per_hour": (
                    len(eye_track.events) * 3600.0 / duration if not case.true_eog else None
                ),
            }
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["family"])].append(row)
    matrix = {}
    for family, selected in grouped.items():
        matrix[family] = {
            "case_count": len(selected),
            "true_alpha": bool(selected[0]["true_alpha"]),
            "true_k_complex": bool(selected[0]["true_k_complex"]),
            "true_eog": bool(selected[0]["true_eog"]),
            "median_absolute_alpha_power": float(
                np.median([row["median_absolute_alpha_power"] for row in selected])
            ),
            "mean_reliable_alpha_peak_rate": float(
                np.mean([row["reliable_alpha_peak_rate"] for row in selected])
            ),
            "k_complex_detected_case_rate": sum(
                int(row["k_complex_detection_count"]) > 0 for row in selected
            )
            / len(selected),
            "eog_candidate_detected_case_rate": sum(
                int(row["eye_movement_candidate_count"]) > 0 for row in selected
            )
            / len(selected),
            "mean_false_k_complex_per_hour": float(
                np.mean(
                    [
                        row["false_k_complex_per_hour"]
                        for row in selected
                        if row["false_k_complex_per_hour"] is not None
                    ]
                    or [0.0]
                )
            ),
            "mean_false_eye_candidates_per_hour": float(
                np.mean(
                    [
                        row["false_eye_candidates_per_hour"]
                        for row in selected
                        if row["false_eye_candidates_per_hour"] is not None
                    ]
                    or [0.0]
                )
            ),
        }
    return rows, {
        "case_count": len(rows),
        "contamination_matrix": matrix,
        "scope": "deterministic algorithm cross-talk stress tests; not clinical physiology",
    }
