"""Regression coverage for bounded EDF reader concurrency and lifetimes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Condition, Event, Lock

import numpy as np
import pytest

from dreamcore.api.http import build_registry
from dreamcore.datasets.edf import (
    EdfSignalWindowRequest,
    read_edf_signal_window,
    read_edf_signal_windows,
)


class _ReaderState:
    def __init__(self) -> None:
        self.guard = Lock()
        self.condition = Condition(self.guard)
        self.active_paths: set[str] = set()
        self.constructor_attempts = 0
        self.open_count = 0
        self.close_count = 0
        self.active_reads = 0
        self.maximum_active_reads = 0
        self.first_read_started = Event()
        self.release_first_read = Event()
        self.hold_first_read = False
        self.raise_during_read = False


def _reader_factory(state: _ReaderState):
    class ThreadUnsafeReader:
        def __init__(self, path: str) -> None:
            self.path = path
            self.closed = False
            with state.condition:
                state.constructor_attempts += 1
                state.condition.notify_all()
                if path in state.active_paths:
                    raise OSError(f"{path}: file has already been opened")
                state.active_paths.add(path)
                state.open_count += 1

        def __enter__(self):
            return self

        def __exit__(self, _error_type, _error, _traceback) -> None:
            self.close()

        def close(self) -> None:
            if self.closed:
                return
            with state.guard:
                state.active_paths.remove(self.path)
                state.close_count += 1
            self.closed = True

        @staticmethod
        def getSignalLabels():  # noqa: N802 - mirrors pyedflib API
            return ["A", "B"]

        @staticmethod
        def getSampleFrequency(_channel_index: int) -> float:  # noqa: N802
            return 10.0

        def readSignal(self, channel_index: int, *, start: int, n: int):  # noqa: N802
            with state.guard:
                state.active_reads += 1
                state.maximum_active_reads = max(state.maximum_active_reads, state.active_reads)
                first_read = state.open_count == 1 and state.active_reads == 1
            if state.hold_first_read and first_read:
                state.first_read_started.set()
                if not state.release_first_read.wait(timeout=2):
                    raise TimeoutError("test did not release the first bounded read")
            try:
                if state.raise_during_read:
                    raise RuntimeError("synthetic bounded read failure")
                return np.arange(start, start + n, dtype=float) + channel_index
            finally:
                with state.guard:
                    state.active_reads -= 1

    return ThreadUnsafeReader


def _request(channel_name: str = "A") -> EdfSignalWindowRequest:
    return EdfSignalWindowRequest(
        channel_name=channel_name,
        expected_rate_hz=10.0,
        rate_tolerance_hz=0.0,
    )


def test_two_sequential_and_repeated_reads_close_each_reader(tmp_path, monkeypatch):
    state = _ReaderState()
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", _reader_factory(state))
    source = tmp_path / "SN001.edf"

    first = read_edf_signal_window(
        source,
        channel_name="A",
        start_seconds=1.0,
        duration_seconds=2.0,
        expected_rate_hz=10.0,
        rate_tolerance_hz=0.0,
    )
    second = read_edf_signal_window(
        source,
        channel_name="A",
        start_seconds=1.0,
        duration_seconds=2.0,
        expected_rate_hz=10.0,
        rate_tolerance_hz=0.0,
    )

    assert first == second
    assert len(first) == 20
    assert state.open_count == state.close_count == 2
    assert not state.active_paths


@pytest.mark.parametrize("channels", [("A", "B"), ("A", "A")])
def test_concurrent_reads_of_same_edf_are_serialized(tmp_path, monkeypatch, channels):
    state = _ReaderState()
    state.hold_first_read = True
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", _reader_factory(state))
    source = tmp_path / "SN001.edf"

    def read(channel_name: str):
        return read_edf_signal_window(
            source,
            channel_name=channel_name,
            start_seconds=6073.316,
            duration_seconds=10.0,
            expected_rate_hz=10.0,
            rate_tolerance_hz=0.0,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(read, channels[0])
        assert state.first_read_started.wait(timeout=1)
        second = executor.submit(read, channels[1])
        with state.condition:
            state.condition.wait_for(
                lambda: state.constructor_attempts >= 2,
                timeout=0.05,
            )
        state.release_first_read.set()
        assert len(first.result()) == len(second.result()) == 100

    assert state.maximum_active_reads == 1
    assert state.open_count == state.close_count == 2
    assert not state.active_paths


def test_multi_channel_window_uses_one_reader(tmp_path, monkeypatch):
    state = _ReaderState()
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", _reader_factory(state))

    windows = read_edf_signal_windows(
        tmp_path / "SN001.edf",
        requests=(_request("A"), _request("B")),
        start_seconds=3.0,
        duration_seconds=2.0,
    )

    assert [len(window) for window in windows] == [20, 20]
    assert windows[0][0] == 30.0
    assert windows[1][0] == 31.0
    assert state.open_count == state.close_count == 1


def test_separate_recordings_remain_independently_readable(tmp_path, monkeypatch):
    state = _ReaderState()
    barrier = __import__("threading").Barrier(2)
    reader_type = _reader_factory(state)
    original_read = reader_type.readSignal

    def concurrent_read(self, channel_index: int, *, start: int, n: int):
        barrier.wait(timeout=1)
        return original_read(self, channel_index, start=start, n=n)

    reader_type.readSignal = concurrent_read
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", reader_type)

    def read(source: Path):
        return read_edf_signal_windows(
            source,
            requests=(_request(),),
            start_seconds=0.0,
            duration_seconds=1.0,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                read,
                (tmp_path / "SN001.edf", tmp_path / "SN002.edf"),
            )
        )
    assert all(len(result[0]) == 10 for result in results)
    assert state.open_count == state.close_count == 2


def test_reader_closes_when_bounded_read_raises(tmp_path, monkeypatch):
    state = _ReaderState()
    state.raise_during_read = True
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", _reader_factory(state))

    with pytest.raises(RuntimeError, match="synthetic bounded read failure"):
        read_edf_signal_windows(
            tmp_path / "SN001.edf",
            requests=(_request(),),
            start_seconds=0.0,
            duration_seconds=1.0,
        )

    assert state.open_count == state.close_count == 1
    assert not state.active_paths


def test_rapid_seek_sequence_and_focused_validation_window(tmp_path, monkeypatch):
    state = _ReaderState()
    monkeypatch.setattr("dreamcore.datasets.edf.pyedflib.EdfReader", _reader_factory(state))
    source = tmp_path / "SN001.edf"

    def read(start_seconds: float, duration_seconds: float):
        return read_edf_signal_windows(
            source,
            requests=(_request("A"), _request("B")),
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
        )

    starts = tuple(float(value) for value in range(0, 120, 10))
    with ThreadPoolExecutor(max_workers=6) as executor:
        seek_results = tuple(executor.map(lambda start: read(start, 10.0), starts))
    focused = read(6078.316 - 5.0, 10.0)

    assert all(len(result[0]) == len(result[1]) == 100 for result in seek_results)
    assert len(focused[0]) == len(focused[1]) == 100
    assert state.open_count == state.close_count == len(starts) + 1
    assert not state.active_paths


@pytest.mark.skipif(
    not Path("data/datasets/raw/hmc_sleep_staging/1.1/recordings/SN001.edf").exists(),
    reason="local HMC validation recording unavailable",
)
def test_real_sn001_concurrent_bounded_reads_regression():
    registry = build_registry("data/session_packages")
    signal_ids = ("eeg-1", "eeg-2", "eeg-4", "eog-1", "eog-2")

    def read(signal_id: str):
        return registry.load_signal_window(
            "SN001",
            signal_id,
            6078.316 - 5.0,
            10.0,
        )

    with ThreadPoolExecutor(max_workers=len(signal_ids)) as executor:
        windows = tuple(executor.map(read, signal_ids))
    assert [window.signal.id for window in windows] == list(signal_ids)
    assert all(window.samples for window in windows)

    batched = registry.load_signal_windows(
        "SN001",
        signal_ids,
        6078.316 - 5.0,
        10.0,
    )
    assert [window.signal.id for window in batched] == list(signal_ids)
