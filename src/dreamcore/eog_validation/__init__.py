"""Cross-dataset Eye Movement V1 validation primitives."""

from dreamcore.eog_validation.core import (
    assign_event_stage,
    build_control_sample,
    deterministic_stratified_sample,
    match_events,
    stage_exposure,
)

__all__ = [
    "assign_event_stage",
    "build_control_sample",
    "deterministic_stratified_sample",
    "match_events",
    "stage_exposure",
]
