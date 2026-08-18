"""Deterministic coverage for Signal Validation V1 primitives."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dreamcore.config import load_config
from dreamcore.validation.alpha import run_alpha_synthetic
from dreamcore.validation.dreams import (
    load_edf_channel_uv,
    load_k_complex_signal,
    parse_interval_annotations,
    select_eog_channels,
)
from dreamcore.validation.matching import (
    detection_metrics,
    match_intervals,
    match_points_to_intervals,
)
from dreamcore.validation.models import BenchmarkInterval, ValidationPoint
from dreamcore.validation.synthetic import alpha_cases, cross_talk_cases


@pytest.fixture(scope="module")
def config() -> dict:
    return load_config(Path("configs/default.yaml"))


@pytest.fixture(scope="module")
def alpha_validation(config: dict) -> tuple[list[dict], dict]:
    return run_alpha_synthetic(config)


def _interval(event_id: str, onset: float, duration: float) -> BenchmarkInterval:
    return BenchmarkInterval(
        event_id=event_id,
        recording_id="excerpt1",
        scorer="expert",
        label="Kcomplex",
        channel="CZ-A1",
        onset_s=onset,
        duration_s=duration,
        source_file="fixture.txt",
        source_line=2,
        raw_text=f"{onset} {duration}",
    )


def test_alpha_generator_is_seed_deterministic(config: dict) -> None:
    settings = config["signal_validation_v1"]["alpha_synthetic"]
    first = alpha_cases(settings)
    second = alpha_cases(settings)
    assert [case.case_id for case in first] == [case.case_id for case in second]
    assert all(
        np.array_equal(left.samples_uv, right.samples_uv)
        for left, right in zip(first, second, strict=True)
    )


def test_alpha_known_frequency_and_no_alpha_rejection(
    alpha_validation: tuple[list[dict], dict],
) -> None:
    rows, summary = alpha_validation
    stationary = [row for row in rows if row["family"] == "stationary_alpha"]
    assert stationary
    assert max(abs(float(row["frequency_error_hz"])) for row in stationary) <= 0.25
    assert summary["negative_false_reliable_peak_rate"] == 0.0


def test_alpha_known_amplitude_ordering(alpha_validation: tuple[list[dict], dict]) -> None:
    _, summary = alpha_validation
    assert all(summary["monotonic_power_recovery_by_seed"].values())
    assert summary["absolute_power_spearman_r"] > 0.9
    assert summary["absolute_power_relative_error"]["count"] > 0
    assert summary["absolute_power_absolute_relative_error"]["mae"] >= 0


def test_dreams_parser_preserves_independent_experts_and_invalid_rows(tmp_path: Path) -> None:
    expert_1 = tmp_path / "expert1.txt"
    expert_2 = tmp_path / "expert2.txt"
    expert_1.write_text("[Kcomplex/CZ-A1]\n10 1.2\n20 -0.5\n", encoding="ascii")
    expert_2.write_text("[Kcomplex/CZ-A1]\n10.1 0.9\n", encoding="ascii")

    first = parse_interval_annotations(expert_1, recording_id="r1", scorer="expert_1")
    second = parse_interval_annotations(expert_2, recording_id="r1", scorer="expert_2")

    assert first[0].scorer == "expert_1"
    assert second[0].scorer == "expert_2"
    assert first[1].valid is False
    assert first[1].raw_text == "20 -0.5"
    assert not hasattr(first[0], "trough_s")


def test_dreams_eog_selection_uses_native_labels(config: dict) -> None:
    settings = config["signal_validation_v1"]["dreams"]["rem"]
    primary, compatible = select_eog_channels(("CZ-A1", "EOG2", "EOG1"), settings)
    assert primary == "EOG1"
    assert compatible == ("EOG2", "EOG1")


def test_dreams_k_complex_signal_uses_channel_only_header(tmp_path: Path) -> None:
    signal_path = tmp_path / "excerpt1.txt"
    signal_path.write_text("[CZ-A1]\n-1\n2\n", encoding="ascii")
    channel, values = load_k_complex_signal(signal_path, expected_rate_hz=2 / 1800)
    assert channel == "CZ-A1"
    assert values.tolist() == [-1.0, 2.0]


def test_dreams_legacy_edf_eog_is_not_scaled_twice(config: dict) -> None:
    path = Path(config["signal_validation_v1"]["dreams"]["rem"]["extracted_root"]) / "excerpt1.edf"
    if not path.is_file():
        pytest.skip("Official ignored DREAMS archive is not installed")
    rate, values, unit = load_edf_channel_uv(path, "EOG1")
    assert rate == 200.0
    assert unit == "uV"
    assert 1.0 < float(np.std(values)) < 200.0


def test_point_matching_is_one_to_one_and_tolerance_sensitive() -> None:
    references = (_interval("r1", 10.0, 1.0), _interval("r2", 12.0, 1.0))
    detections = (
        ValidationPoint("d1", 10.5),
        ValidationPoint("d2", 10.7),
        ValidationPoint("d3", 13.2),
    )
    strict = match_points_to_intervals(references, detections, tolerance_s=0.0)
    padded = match_points_to_intervals(references, detections, tolerance_s=0.25)
    assert len(strict) == 1
    assert len(padded) == 2
    assert len({match.reference_id for match in padded}) == len(padded)
    assert len({match.detection_id for match in padded}) == len(padded)


def test_interval_matching_and_metrics_are_one_to_one() -> None:
    references = (_interval("e1", 5.0, 2.0), _interval("e2", 6.0, 2.0))
    detections = (ValidationPoint("d1", 6.0, 5.5, 7.5),)
    matches = match_intervals(references, detections, minimum_overlap_s=0.0)
    assert len(matches) == 1
    assert detection_metrics(2, 1, 1) == {
        "reference_events": 2,
        "detector_events": 1,
        "matched_events": 1,
        "unmatched_detector_events": 0,
        "missed_reference_events": 1,
        "precision": 1.0,
        "recall": 0.5,
        "f1": pytest.approx(2 / 3),
    }


def test_synthetic_cross_talk_cases_are_deterministic_and_isolated(config: dict) -> None:
    settings = config["signal_validation_v1"]["synthetic_crosstalk"]
    first = cross_talk_cases(settings)
    second = cross_talk_cases(settings)
    assert len(first) == len(settings["seeds"]) * len(settings["levels"]) * len(settings["cases"])
    assert all(
        np.array_equal(left.eog_uv, right.eog_uv) for left, right in zip(first, second, strict=True)
    )
    truth = {case.family: (case.true_alpha, case.true_k_complex, case.true_eog) for case in first}
    assert truth["alpha_only"] == (True, False, False)
    assert truth["k_complex_only"] == (False, True, False)
    assert truth["eog_only"] == (False, False, True)
    assert truth["noise_only"] == (False, False, False)
