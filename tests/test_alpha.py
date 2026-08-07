"""Synthetic coverage for the Alpha V1 research and simulated-demand pipeline."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from dreamcore.alpha.features import assess_signal_quality, extract_alpha_features
from dreamcore.alpha.iaf import IAFResult, estimate_iaf
from dreamcore.alpha.simulation import (
    SIMULATED_DEMAND_PROVENANCE,
    ControlObservation,
    simulate_stimulation_demand,
)
from dreamcore.alpha.spectral import (
    SpectralEstimate,
    estimate_welch_psd,
    integrate_band_power,
)
from dreamcore.alpha.state import ResearchState
from dreamcore.alpha.trend import AlphaTrendPoint, estimate_alpha_trend
from dreamcore.config import load_config
from dreamcore.datasets.models import (
    CapabilityName,
    ProvenanceClass,
    parse_session_manifest,
)


@pytest.fixture
def config() -> dict:
    return load_config(Path("configs/default.yaml"))


def _signal(
    frequency_hz: float = 10.0,
    amplitude_uv: float = 20.0,
    duration_s: float = 30.0,
    sfreq: float = 100.0,
) -> np.ndarray:
    times = np.arange(int(duration_s * sfreq)) / sfreq
    return amplitude_uv * 1e-6 * np.sin(2 * np.pi * frequency_hz * times)


def _trend(
    timestamp_s: float,
    trend: str = "stable",
    change: float = 0.0,
) -> AlphaTrendPoint:
    return AlphaTrendPoint(
        timestamp_s=timestamp_s,
        short_alpha=0.2 * (1 + change),
        baseline_alpha=0.2,
        alpha_trend=trend,
        alpha_trend_slope=0.0,
        alpha_change_from_baseline=change,
        confidence=1.0,
    )


def _observation(
    timestamp_s: float,
    *,
    drowsiness: float = 0.0,
    trend: str = "stable",
    change: float = 0.0,
    valid: bool = True,
    confidence: float = 1.0,
) -> ControlObservation:
    state = ResearchState(
        awake_score=1.0 - drowsiness if valid else None,
        drowsiness_score=drowsiness if valid else None,
        state_confidence=confidence,
        available=valid,
        reason=None if valid else "test_invalid",
    )
    return ControlObservation(
        timestamp_s=timestamp_s,
        state=state,
        trend=_trend(timestamp_s, trend, change),
        alpha_power=20.0,
        relative_alpha_power=0.2,
        signal_quality_valid=valid,
    )


def test_known_ten_hz_signal_has_alpha_power_and_iaf(config):
    signal = _signal()
    estimate = estimate_welch_psd(signal, 100.0, config, "fixed_alpha")
    iaf = estimate_iaf(estimate, config, "fixed_alpha")
    features = extract_alpha_features(
        signal,
        100.0,
        "EEG TEST",
        0.0,
        30.0,
        "W",
        config,
        "fixed_alpha",
        iaf,
    )

    assert iaf.available
    assert iaf.individual_alpha_frequency_hz == pytest.approx(10.0, abs=0.26)
    assert iaf.iaf_confidence > 0
    assert features.absolute_alpha_power > 0
    assert features.relative_alpha_power > 0.9
    assert features.alpha_envelope == pytest.approx(20.0, rel=0.08)


def test_flat_search_spectrum_returns_unavailable_iaf(config):
    estimate = SpectralEstimate(
        frequencies_hz=np.linspace(0.5, 30.0, 200),
        psd_uv2_per_hz=np.ones(200),
        parameters={},
    )

    result = estimate_iaf(estimate, config, "fixed_alpha")

    assert not result.available
    assert result.individual_alpha_frequency_hz is None
    assert result.iaf_confidence == 0.0
    assert result.reason == "no_reliable_alpha_peak"


def test_fixed_and_individualized_bands_are_distinct(config):
    signal = _signal()
    iaf = IAFResult(10.0, 1.0, True, None, 10.0, 7.0, 14.0)
    fixed = extract_alpha_features(signal, 100.0, "EEG", 0.0, 30.0, "W", config, "fixed_alpha", iaf)
    individualized = extract_alpha_features(
        signal,
        100.0,
        "EEG",
        0.0,
        30.0,
        "W",
        config,
        "individualized_alpha",
        iaf,
    )

    assert (fixed.alpha_band_low_hz, fixed.alpha_band_high_hz) == (8.0, 13.0)
    assert (
        individualized.alpha_band_low_hz,
        individualized.alpha_band_high_hz,
    ) == (8.0, 12.0)


def test_absolute_and_relative_power_use_configured_bands(config):
    signal = _signal(amplitude_uv=20.0) + _signal(frequency_hz=3.0, amplitude_uv=20.0)
    estimate = estimate_welch_psd(signal, 100.0, config, "fixed_alpha")
    alpha_power = integrate_band_power(estimate, 8.0, 13.0)
    total_power = integrate_band_power(estimate, 0.5, 30.0)

    assert alpha_power > 0
    assert alpha_power / total_power == pytest.approx(0.5, abs=0.03)


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        (np.linspace(0.2, 0.4, 31), "rising"),
        (np.full(31, 0.2), "stable"),
        (np.linspace(0.2, 0.08, 31), "falling"),
    ],
)
def test_history_distinguishes_rising_stable_and_falling(config, tail, expected):
    times = np.arange(61) * 10.0
    values = np.concatenate((np.full(30, 0.2), tail))

    result = estimate_alpha_trend(times, values, np.ones(61, dtype=bool), config)

    assert result[-1].alpha_trend == expected


def test_signal_quality_gates_flat_signal(config):
    signal = np.zeros(3000)
    original = signal.copy()

    quality = assess_signal_quality(signal, config)
    features = extract_alpha_features(signal, 100.0, "EEG", 0.0, 30.0, "W", config, "fixed_alpha")

    assert not quality.valid
    assert features.absolute_alpha_power is None
    assert features.relative_alpha_power is None
    np.testing.assert_array_equal(signal, original)


def test_valid_alpha_feature_extraction_does_not_modify_raw_eeg(config):
    signal = _signal()
    original = signal.copy()

    extract_alpha_features(signal, 100.0, "EEG", 0.0, 30.0, "W", config, "fixed_alpha")

    np.testing.assert_array_equal(signal, original)


def test_demand_is_bounded_smoothed_and_rate_limited(config):
    observations = [_observation(index * 10.0) for index in range(30)]

    points, events = simulate_stimulation_demand(observations, config)

    demand = np.asarray([point.stimulation_demand for point in points])
    assert np.all((demand >= 0.0) & (demand <= 1.0))
    assert demand[-1] < config["alpha"]["simulated_demand"]["maximum_demand"]
    max_rise = config["alpha"]["simulated_demand"]["max_rise_per_minute"] / 6.0
    assert np.max(np.diff(demand)) <= max_rise + 1e-12
    assert all(event.provenance == "simulated" for event in events)
    assert all(point.provenance == SIMULATED_DEMAND_PROVENANCE for point in points)


def test_quality_and_confidence_gate_hold_demand(config):
    observations = [_observation(index * 10.0, valid=False, confidence=0.0) for index in range(20)]

    points, events = simulate_stimulation_demand(observations, config)

    assert not any(point.demand_available for point in points)
    assert all(point.stimulation_demand == 0.0 for point in points)
    assert {event.event_type for event in events} == {"stimulation_held"}


def test_demand_hysteresis_holds_small_target_change(config):
    modified = deepcopy(config)
    demand = modified["alpha"]["simulated_demand"]
    demand["initial_demand"] = 0.5
    demand["minimum_valid_observation_s"] = 0.0
    demand["demand_hysteresis_deadband"] = 1.0

    points, _ = simulate_stimulation_demand([_observation(10.0), _observation(20.0)], modified)

    assert [point.stimulation_demand for point in points] == [0.5, 0.5]


def test_sustained_drowsiness_reaches_ready_to_remove(config):
    modified = deepcopy(config)
    demand = modified["alpha"]["simulated_demand"]
    demand["smoothing_time_constant_s"] = 1.0
    demand["max_fall_per_minute"] = 1.0
    observations = [
        _observation(
            index * 10.0,
            drowsiness=1.0,
            trend="falling",
            change=-0.5,
        )
        for index in range(40)
    ]

    points, events = simulate_stimulation_demand(observations, modified)

    assert any(point.ready_to_remove for point in points)
    assert points[-1].stimulation_demand == 0.0
    assert any(event.event_type == "ready_to_remove" for event in events)


def test_session_v1_serializes_alpha_provenance_without_schema_upgrade():
    capabilities = {
        name.value: {
            "status": "AVAILABLE",
            "source": "derived" if name is not CapabilityName.STIMULATION_DEMAND else "simulated",
        }
        for name in (
            CapabilityName.ALPHA_POWER,
            CapabilityName.RELATIVE_ALPHA_POWER,
            CapabilityName.INDIVIDUAL_ALPHA_FREQUENCY,
            CapabilityName.ALPHA_TREND,
            CapabilityName.DROWSINESS_SCORE,
            CapabilityName.STIMULATION_DEMAND,
            CapabilityName.READY_TO_REMOVE,
        )
    }
    manifest = parse_session_manifest(
        {
            "schema_version": "dreamcore.session.v1",
            "dataset": {"id": "public-test", "display_name": "Public Test"},
            "session": {"session_id": "alpha-test", "subject_id": "S01"},
            "recording": {"duration_seconds": 30.0},
            "signals": [
                {
                    "id": "eeg-1",
                    "modality": "eeg",
                    "channel_name": "EEG",
                    "unit": "uV",
                    "sampling_rate_hz": 100.0,
                    "source": "raw",
                    "available": True,
                }
            ],
            "annotations": {},
            "derived": {
                "alpha_power": {"available": True, "source": "derived"},
                "stimulation_demand": {"available": True, "source": "simulated"},
            },
            "capabilities": capabilities,
            "provenance": {
                "classification": "imported",
                "notes": "REAL PUBLIC EEG; DERIVED ALPHA; SIMULATED DEMAND",
            },
        }
    )

    assert manifest.schema_version == "dreamcore.session.v1"
    assert manifest.signals[0].source is ProvenanceClass.RAW
    assert manifest.derived["alpha_power"].source is ProvenanceClass.DERIVED
    assert manifest.derived["stimulation_demand"].source is ProvenanceClass.SIMULATED
