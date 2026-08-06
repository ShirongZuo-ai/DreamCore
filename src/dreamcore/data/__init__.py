"""Data I/O — read public sleep EEG datasets, quality checks, metadata handling."""

from dreamcore.data.reader import check_quality, load_edf

__all__ = ["check_quality", "load_edf"]
