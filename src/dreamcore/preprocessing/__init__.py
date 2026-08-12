"""Preprocessing — filtering, artifact removal, re-referencing."""

from dreamcore.preprocessing.eeg import (
    PreprocessedEEG,
    get_preprocessing_profile,
    preprocess_n3_segment,
    signal_statistics,
)

__all__ = [
    "PreprocessedEEG",
    "get_preprocessing_profile",
    "preprocess_n3_segment",
    "signal_statistics",
]
