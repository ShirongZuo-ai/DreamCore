"""Reproducible, non-clinical signal validation for frozen DreamCore features."""

from dreamcore.validation.matching import (
    Match,
    detection_metrics,
    match_intervals,
    match_points_to_intervals,
)
from dreamcore.validation.models import BenchmarkInterval

__all__ = [
    "BenchmarkInterval",
    "Match",
    "detection_metrics",
    "match_intervals",
    "match_points_to_intervals",
]
