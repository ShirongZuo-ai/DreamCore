"""Synthetic ground-truth validation for the frozen Alpha V1 estimator."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from dreamcore.alpha import extract_alpha_features
from dreamcore.validation.metrics import finite_summary, safe_correlation
from dreamcore.validation.synthetic import alpha_cases


def run_alpha_synthetic(
    full_config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = full_config["signal_validation_v1"]["alpha_synthetic"]
    product = full_config["automatic_analysis"]["alpha"]
    rate = float(config["sampling_rate_hz"])
    window_s = float(config["window_s"])
    step_s = float(config["step_s"])
    if window_s != float(product["analysis_window_s"]) or step_s != float(product["step_s"]):
        raise ValueError("Synthetic Alpha cadence must match the frozen product cadence")
    window_samples = int(round(window_s * rate))
    step_samples = int(round(step_s * rate))
    input_scale_to_uv = float(full_config["alpha"]["input_scale_to_uv"])
    profile_name = str(full_config["alpha"]["active_profile"])
    display_min_confidence = float(
        full_config["alpha"]["profiles"][profile_name]["iaf"]["product_display_min_confidence"]
    )
    case_rows: list[dict[str, Any]] = []
    for case in alpha_cases(config):
        window_rows = []
        for start in range(0, case.samples_uv.size - window_samples + 1, step_samples):
            feature = extract_alpha_features(
                case.samples_uv[start : start + window_samples] / input_scale_to_uv,
                rate,
                "synthetic-posterior",
                start / rate,
                (start + window_samples) / rate,
                "W",
                full_config,
            )
            window_rows.append(feature)
        reliable = [
            row
            for row in window_rows
            if row.iaf_available
            and row.individual_alpha_frequency_hz is not None
            and row.iaf_confidence >= display_min_confidence
        ]
        reliable_fraction = len(reliable) / len(window_rows) if window_rows else 0.0
        estimated_frequency = (
            float(np.median([row.individual_alpha_frequency_hz for row in reliable]))
            if reliable
            else None
        )
        absolute = [
            float(row.absolute_alpha_power)
            for row in window_rows
            if row.absolute_alpha_power is not None
        ]
        relative = [
            float(row.relative_alpha_power)
            for row in window_rows
            if row.relative_alpha_power is not None
        ]
        frequencies = [
            float(row.individual_alpha_frequency_hz)
            for row in reliable
            if row.individual_alpha_frequency_hz is not None
        ]
        expected_power = (
            case.injected_amplitude_uv**2 / 2.0 if case.injected_frequency_hz is not None else 0.0
        )
        median_absolute_power = float(np.median(absolute)) if absolute else None
        case_rows.append(
            {
                "case_id": case.case_id,
                "family": case.family,
                "seed": case.seed,
                "snr_db": case.snr_db,
                "injected_frequency_hz": case.injected_frequency_hz,
                "injected_amplitude_uv": case.injected_amplitude_uv,
                "injected_power_proxy_uv2": case.injected_amplitude_uv**2,
                "expected_sinusoid_power_uv2": expected_power,
                "window_count": len(window_rows),
                "reliable_window_count": len(reliable),
                "reliable_window_fraction": reliable_fraction,
                "reliable_peak_detected": reliable_fraction
                >= float(config["reliable_window_fraction"]),
                "estimated_peak_hz": estimated_frequency,
                "frequency_error_hz": (
                    estimated_frequency - case.injected_frequency_hz
                    if estimated_frequency is not None and case.injected_frequency_hz is not None
                    else None
                ),
                "median_absolute_alpha_power": median_absolute_power,
                "absolute_power_relative_error": (
                    (median_absolute_power - expected_power) / expected_power
                    if median_absolute_power is not None and expected_power > 0
                    else None
                ),
                "median_relative_alpha_power": float(np.median(relative)) if relative else None,
                "absolute_alpha_power_sd": float(np.std(absolute)) if absolute else None,
                "relative_alpha_power_sd": float(np.std(relative)) if relative else None,
                "peak_frequency_sd_hz": float(np.std(frequencies)) if frequencies else None,
            }
        )
    positive = [row for row in case_rows if row["injected_frequency_hz"] is not None]
    negative = [row for row in case_rows if row["family"] == "no_alpha"]
    errors = [
        float(row["frequency_error_hz"])
        for row in positive
        if row["frequency_error_hz"] is not None
    ]
    power_rows = [row for row in case_rows if row["family"] == "amplitude_ordering"]
    injected_power = [float(row["expected_sinusoid_power_uv2"]) for row in power_rows]
    estimated_power = [float(row["median_absolute_alpha_power"]) for row in power_rows]
    relative_power_errors = [
        float(row["absolute_power_relative_error"])
        for row in power_rows
        if row["absolute_power_relative_error"] is not None
    ]
    monotonic_by_seed = {}
    for seed in config["seeds"]:
        selected = sorted(
            (row for row in power_rows if row["seed"] == int(seed)),
            key=lambda row: float(row["injected_amplitude_uv"]),
        )
        monotonic_by_seed[str(seed)] = bool(
            all(
                float(right["median_absolute_alpha_power"])
                > float(left["median_absolute_alpha_power"])
                for left, right in zip(selected, selected[1:], strict=False)
            )
        )
    by_snr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in positive:
        if row["snr_db"] is not None:
            by_snr[str(row["snr_db"])].append(row)
    summary = {
        "case_count": len(case_rows),
        "product_reliable_peak_min_confidence": display_min_confidence,
        "positive_case_count": len(positive),
        "negative_control_count": len(negative),
        "frequency_error": finite_summary(errors),
        "positive_reliable_peak_detection_rate": (
            sum(bool(row["reliable_peak_detected"]) for row in positive) / len(positive)
            if positive
            else None
        ),
        "negative_false_reliable_peak_rate": (
            sum(bool(row["reliable_peak_detected"]) for row in negative) / len(negative)
            if negative
            else None
        ),
        "absolute_power_pearson_r": safe_correlation(injected_power, estimated_power),
        "absolute_power_spearman_r": (
            float(spearmanr(injected_power, estimated_power).statistic) if power_rows else None
        ),
        "absolute_power_relative_error": finite_summary(relative_power_errors),
        "absolute_power_absolute_relative_error": finite_summary(
            [abs(value) for value in relative_power_errors]
        ),
        "monotonic_power_recovery_by_seed": monotonic_by_seed,
        "stationary_stability": {
            "peak_frequency_sd_hz": finite_summary(
                [
                    float(row["peak_frequency_sd_hz"])
                    for row in case_rows
                    if row["family"] == "stationary_alpha"
                    and row["peak_frequency_sd_hz"] is not None
                ]
            ),
            "relative_power_sd": finite_summary(
                [
                    float(row["relative_alpha_power_sd"])
                    for row in case_rows
                    if row["family"] == "stationary_alpha"
                    and row["relative_alpha_power_sd"] is not None
                ]
            ),
        },
        "by_snr": {
            snr: {
                "case_count": len(rows),
                "detection_rate": sum(bool(row["reliable_peak_detected"]) for row in rows)
                / len(rows),
                "frequency_error": finite_summary(
                    [
                        float(row["frequency_error_hz"])
                        for row in rows
                        if row["frequency_error_hz"] is not None
                    ]
                ),
            }
            for snr, rows in sorted(by_snr.items(), key=lambda item: float(item[0]))
        },
        "interpretation_scope": (
            "algorithm behavior on deterministic synthetic signals; not biological accuracy"
        ),
    }
    return case_rows, summary
