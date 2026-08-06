"""Slow oscillation detection — zero-crossing, amplitude/duration thresholding."""

from dreamcore.slow_oscillation.detector import (
    SlowOscillationDetection,
    SlowOscillationEvent,
    ZeroCrossing,
    detect_slow_oscillations,
    find_zero_crossings,
    get_detector_profile,
)

__all__ = [
    "SlowOscillationDetection",
    "SlowOscillationEvent",
    "ZeroCrossing",
    "detect_slow_oscillations",
    "find_zero_crossings",
    "get_detector_profile",
]
