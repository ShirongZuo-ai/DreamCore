"""Shared native-rate EDF metadata and bounded signal access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock

import numpy as np
import pyedflib

# pyedflib/EDFlib does not permit overlapping reader instances for one file in
# a process.  Session HTTP requests run on independent threads, so synchronize
# at the file boundary while allowing different recordings to proceed in
# parallel.  Readers themselves are deliberately short-lived and never cached.
_EDF_LOCKS_GUARD = Lock()
_EDF_LOCKS: dict[Path, Lock] = {}


@dataclass(frozen=True)
class EdfChannelHeader:
    index: int
    original_name: str
    sampling_rate_hz: float
    unit: str
    sample_count: int


@dataclass(frozen=True)
class EdfRecordingHeader:
    path: Path
    duration_seconds: float
    start_datetime: datetime
    channels: tuple[EdfChannelHeader, ...]


@dataclass(frozen=True)
class EdfSignalWindowRequest:
    """One channel request within a shared bounded EDF read."""

    channel_name: str
    expected_rate_hz: float
    rate_tolerance_hz: float
    scale_to_unit: float = 1.0


def _edf_file_lock(path: Path) -> Lock:
    """Return the process-wide lock for one canonical EDF path."""

    canonical_path = Path(path).resolve()
    with _EDF_LOCKS_GUARD:
        return _EDF_LOCKS.setdefault(canonical_path, Lock())


def inspect_edf(path: Path) -> EdfRecordingHeader:
    """Read only EDF headers and preserve every native channel descriptor."""

    source = Path(path).resolve()
    with _edf_file_lock(source), pyedflib.EdfReader(str(source)) as reader:
        labels = reader.getSignalLabels()
        rates = reader.getSampleFrequencies()
        signal_headers = reader.getSignalHeaders()
        sample_counts = reader.getNSamples()
        channels = tuple(
            EdfChannelHeader(
                index=index,
                original_name=str(label).strip(),
                sampling_rate_hz=float(rates[index]),
                unit=_canonical_unit(str(signal_headers[index]["dimension"]).strip()),
                sample_count=int(sample_counts[index]),
            )
            for index, label in enumerate(labels)
        )
        return EdfRecordingHeader(
            path=source,
            duration_seconds=float(reader.file_duration),
            start_datetime=reader.getStartdatetime(),
            channels=channels,
        )


def read_edf_signal_window(
    path: Path,
    *,
    channel_name: str,
    start_seconds: float,
    duration_seconds: float,
    expected_rate_hz: float,
    rate_tolerance_hz: float,
    scale_to_unit: float = 1.0,
) -> tuple[float, ...]:
    """Read one bounded native-rate channel window without whole-night preload."""

    return read_edf_signal_windows(
        path,
        requests=(
            EdfSignalWindowRequest(
                channel_name=channel_name,
                expected_rate_hz=expected_rate_hz,
                rate_tolerance_hz=rate_tolerance_hz,
                scale_to_unit=scale_to_unit,
            ),
        ),
        start_seconds=start_seconds,
        duration_seconds=duration_seconds,
    )[0]


def read_edf_signal_windows(
    path: Path,
    *,
    requests: tuple[EdfSignalWindowRequest, ...],
    start_seconds: float,
    duration_seconds: float,
) -> tuple[tuple[float, ...], ...]:
    """Read bounded native-rate channels with one synchronized EDF lifetime."""

    if not requests:
        return ()
    source = Path(path).resolve()
    with _edf_file_lock(source), pyedflib.EdfReader(str(source)) as reader:
        labels = tuple(str(label).strip() for label in reader.getSignalLabels())
        windows = []
        for request in requests:
            try:
                channel_index = labels.index(request.channel_name)
            except ValueError as error:
                raise LookupError(f"EDF channel {request.channel_name!r} not found") from error
            actual_rate = float(reader.getSampleFrequency(channel_index))
            if abs(actual_rate - request.expected_rate_hz) > request.rate_tolerance_hz:
                raise ValueError("Referenced EDF sampling rate differs from manifest")
            start_sample = int(round(start_seconds * actual_rate))
            sample_count = int(round(duration_seconds * actual_rate))
            values = np.asarray(
                reader.readSignal(channel_index, start=start_sample, n=sample_count),
                dtype=float,
            )
            if values.size != sample_count:
                raise OSError(f"EDF bounded read returned {values.size} of {sample_count} samples")
            windows.append(tuple((values * request.scale_to_unit).tolist()))
    return tuple(windows)


def _canonical_unit(unit: str) -> str:
    normalized = unit.replace("μ", "µ")
    if normalized.casefold() in {"uv", "µv"}:
        return "uV"
    return normalized or "unknown"
