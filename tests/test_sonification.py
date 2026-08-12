"""Deterministic, inspectable sonification mapping tests."""

from copy import deepcopy
from pathlib import Path

from dreamcore.config import load_config
from dreamcore.eye_movement import EyeMovementEvent, EyeMovementFeature
from dreamcore.sonification import SonificationMapper


def _config():
    return deepcopy(load_config(Path("configs/default.yaml")))


def _feature(start_s: float, activity: float, amplitude: float, rate: float):
    return EyeMovementFeature(
        session_id="fixture",
        source_channel="fixture-eog",
        window_start_s=start_s,
        window_end_s=start_s + 4.0,
        recording_start_time=None,
        absolute_window_start=None,
        absolute_window_end=None,
        eog_rms_uv=12.0,
        peak_to_peak_uv=40.0,
        mean_absolute_derivative_uv_per_s=20.0,
        robust_deviation_z=4.0,
        activity_score=activity,
        amplitude_score=amplitude,
        event_rate_per_min=rate,
        event_candidate=True,
        signal_quality="valid",
        signal_quality_reasons=(),
        feature_version="eye-movement-v1",
    )


def test_eye_movement_mapping_is_deterministic_bounded_and_event_driven():
    mapper = SonificationMapper(_config())
    features = (_feature(0.0, 0.2, 0.4, 2.0), _feature(4.0, 0.8, 0.9, 12.0))
    event = EyeMovementEvent(
        event_id="eye-1",
        session_id="fixture",
        timestamp=3.0,
        window_start_s=2.9,
        window_end_s=3.1,
        duration_s=0.2,
        amplitude_uv=-80.0,
        polarity="negative",
        confidence=0.7,
        robust_deviation_z=7.0,
        source_channel="fixture-eog",
        feature_version="eye-movement-v1",
    )

    first = mapper.eye_movement_frames("fixture", features, (event,))
    second = mapper.eye_movement_frames("fixture", features, (event,))

    assert first == second
    assert first[0].trigger is True
    assert first[0].event_id == "eye-1"
    assert first[1].trigger is False
    assert first[1].density > first[0].density
    assert first[1].intensity > first[0].intensity
    assert first[1].tempo_bpm > first[0].tempo_bpm
    assert first[0].provenance == "sonification_control"


def test_invalid_feature_maps_to_unavailable_not_zero():
    mapper = SonificationMapper(_config())
    invalid = _feature(0.0, 0.2, 0.4, 2.0)
    invalid = EyeMovementFeature(
        **{
            **invalid.__dict__,
            "signal_quality": "invalid",
            "activity_score": None,
            "amplitude_score": None,
            "event_rate_per_min": None,
        }
    )

    frame = mapper.eye_movement_frames("fixture", (invalid,), ())[0]

    assert frame.available is False
    assert frame.tempo_bpm is None
    assert frame.density is None
    assert frame.intensity is None
    assert frame.brightness_hz is None


def test_alpha_comparison_is_optional_and_uses_declared_source_channel():
    config = _config()
    config["sonification"]["alpha_comparison"]["source_channel"] = "posterior"
    mapper = SonificationMapper(config)
    rows = [
        {
            "channel": channel,
            "window_start_s": float(index),
            "window_end_s": float(index + 4),
            "relative_alpha_power": value,
        }
        for index, (channel, value) in enumerate(
            (("frontal", 0.8), ("posterior", 0.1), ("posterior", 0.5))
        )
    ]

    frames = mapper.alpha_comparison_frames("fixture", rows)

    assert len(frames) == 2
    assert all(frame.source == "alpha" for frame in frames)
    assert all(frame.source_feature == "relative_alpha_power" for frame in frames)
    assert frames[0].brightness_hz < frames[1].brightness_hz
