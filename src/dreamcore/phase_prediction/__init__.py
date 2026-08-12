"""Phase prediction — Hilbert, fixed-threshold, and state-space methods."""

from dreamcore.phase_prediction.hilbert import (
    EventPhaseValidation,
    HilbertChannelPhase,
    HilbertPhaseResult,
    PhaseLandmark,
    PhaseProvenance,
    circular_error,
    compare_overlapping_channel_phases,
    estimate_channel_hilbert,
    estimate_hilbert_phase,
    get_phase_profile,
    validate_event_landmarks,
    wrap_phase,
)

__all__ = [
    "EventPhaseValidation",
    "HilbertChannelPhase",
    "HilbertPhaseResult",
    "PhaseLandmark",
    "PhaseProvenance",
    "circular_error",
    "compare_overlapping_channel_phases",
    "estimate_channel_hilbert",
    "estimate_hilbert_phase",
    "get_phase_profile",
    "validate_event_landmarks",
    "wrap_phase",
]
