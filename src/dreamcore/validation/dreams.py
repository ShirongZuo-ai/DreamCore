"""Adapters for the official, locally extracted DREAMS benchmark archives."""

from __future__ import annotations

import hashlib
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dreamcore.k_complex import N2Bout, segment_stage_bouts
from dreamcore.validation.models import BenchmarkInterval


@dataclass(frozen=True)
class DreamsRecording:
    recording_id: str
    edf_path: Path
    duration_s: float
    sampling_rate_hz: float
    channel_names: tuple[str, ...]
    channel_units: tuple[str, ...]


def excerpt_index(path: Path) -> int:
    match = re.search(r"excerpt(\d+)", path.name, re.IGNORECASE)
    if match is None:
        raise ValueError(f"DREAMS filename has no excerpt index: {path.name}")
    return int(match.group(1))


def validate_archive(path: Path, *, size_bytes: int, published_checksum: str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Official DREAMS archive is missing: {source}")
    if source.stat().st_size != size_bytes:
        raise ValueError(f"DREAMS archive size mismatch: {source.name}")
    kind, expected = published_checksum.split(":", 1)
    if kind != "md5":
        raise ValueError(f"Unsupported published checksum: {kind}")
    digest = hashlib.md5(source.read_bytes(), usedforsecurity=False).hexdigest()
    if digest != expected:
        raise ValueError(f"DREAMS archive checksum mismatch: {source.name}")
    return {"path": str(source), "size_bytes": size_bytes, "checksum": f"md5:{digest}"}


def parse_interval_annotations(
    path: Path,
    *,
    recording_id: str,
    scorer: str,
) -> tuple[BenchmarkInterval, ...]:
    """Parse DREAMS onset/duration rows and retain invalid native rows."""

    lines = Path(path).read_text(encoding="ascii").splitlines()
    if not lines or not lines[0].startswith("[") or "/" not in lines[0]:
        raise ValueError(f"DREAMS annotation header is invalid: {path}")
    header = lines[0].strip()[1:-1]
    label, channel = header.split("/", 1)
    events = []
    for line_number, raw in enumerate(lines[1:], start=2):
        stripped = raw.strip()
        if not stripped:
            continue
        fields = stripped.split()
        if len(fields) != 2:
            raise ValueError(
                f"DREAMS annotation row must have onset and duration: {path}:{line_number}"
            )
        onset, duration = map(float, fields)
        events.append(
            BenchmarkInterval(
                event_id=f"{recording_id}:{scorer}:{len(events) + 1:04d}",
                recording_id=recording_id,
                scorer=scorer,
                label=label,
                channel=channel,
                onset_s=onset,
                duration_s=duration,
                source_file=str(path),
                source_line=line_number,
                raw_text=stripped,
            )
        )
    return tuple(events)


def load_hypnogram(path: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    lines = Path(path).read_text(encoding="ascii").splitlines()
    if not lines or lines[0].strip().casefold() != "[hypnogram]":
        raise ValueError(f"DREAMS hypnogram header is invalid: {path}")
    epoch_s = float(config["hypnogram_epoch_s"])
    stage_map = {int(key): str(value) for key, value in config["stage_code_map"].items()}
    output = []
    for index, raw in enumerate(lines[1:]):
        if not raw.strip():
            continue
        code = int(raw)
        output.append(
            {
                "start_seconds": index * epoch_s,
                "duration_seconds": epoch_s,
                "label": stage_map.get(code, "UNKNOWN"),
                "normalized_label": stage_map.get(code, "UNKNOWN"),
                "raw_label": str(code),
                "scorer": "DREAMS hypnogram expert",
                "annotation_source": str(path),
            }
        )
    return tuple(output)


def load_n2_bouts(
    path: Path, dreams_config: Mapping[str, Any], detector_config: Mapping[str, Any]
) -> tuple[N2Bout, ...]:
    return segment_stage_bouts(load_hypnogram(path, dreams_config), detector_config)


def load_k_complex_signal(path: Path, *, expected_rate_hz: float) -> tuple[str, np.ndarray]:
    """Use the official central-EEG microvolt text export declared by DREAMS."""

    lines = Path(path).read_text(encoding="ascii").splitlines()
    if not lines or not lines[0].startswith("[") or not lines[0].endswith("]"):
        raise ValueError(f"DREAMS central EEG header is invalid: {path}")
    channel = lines[0].strip()[1:-1]
    if not channel or "/" in channel:
        raise ValueError(f"DREAMS central EEG channel header is invalid: {path}")
    values = np.asarray([float(value) for value in lines[1:] if value.strip()], dtype=float)
    expected = int(round(1800.0 * expected_rate_hz))
    if values.size != expected:
        raise ValueError(f"DREAMS central EEG has {values.size} samples; expected {expected}")
    return channel, values


def inspect_edf_compatibly(path: Path) -> DreamsRecording:
    """Read native metadata from legacy DREAMS EDF using MNE's tolerant reader."""

    import mne

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        raw = mne.io.read_raw_edf(path, preload=False, verbose="error")
    units = tuple(str(raw._orig_units.get(name, "n/a")) for name in raw.ch_names)
    return DreamsRecording(
        recording_id=Path(path).stem,
        edf_path=Path(path),
        duration_s=float(raw.n_times / raw.info["sfreq"]),
        sampling_rate_hz=float(raw.info["sfreq"]),
        channel_names=tuple(raw.ch_names),
        channel_units=units,
    )


def select_eog_channels(
    channel_names: Sequence[str], config: Mapping[str, Any]
) -> tuple[str, tuple[str, ...]]:
    compatible_patterns = tuple(
        re.compile(str(value)) for value in config["compatible_eog_patterns"]
    )
    primary_patterns = tuple(re.compile(str(value)) for value in config["primary_eog_patterns"])
    compatible = tuple(
        name
        for name in channel_names
        if any(pattern.search(name) for pattern in compatible_patterns)
    )
    primary = next(
        (name for name in compatible if any(pattern.search(name) for pattern in primary_patterns)),
        None,
    )
    if primary is None:
        raise LookupError(f"No configured DREAMS primary EOG channel in {list(channel_names)}")
    return primary, compatible


def load_edf_channel_uv(path: Path, channel: str) -> tuple[float, np.ndarray, str]:
    import mne

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        raw = mne.io.read_raw_edf(path, preload=False, verbose="error")
    if channel not in raw.ch_names:
        raise LookupError(f"DREAMS EDF channel not found: {channel}")
    unit = str(raw._orig_units.get(channel, "n/a"))
    normalized_unit = unit.replace("μ", "u").replace("µ", "u").casefold()
    values = np.asarray(raw.get_data(picks=[channel])[0], dtype=float)
    if normalized_unit == "uv":
        # DREAMS' legacy EDF calibration exposes native microvolt magnitudes
        # directly (for example, EOG values near +/-200), despite MNE's
        # internal FIFF unit metadata. Preserve the archive's declared unit.
        return float(raw.info["sfreq"]), values, "uV"
    if normalized_unit == "v":
        return float(raw.info["sfreq"]), values * 1.0e6, "uV"
    raise ValueError(f"Unsupported DREAMS EOG unit {unit!r} for {channel}")


def recording_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    return tuple(sorted(Path(root).glob(pattern), key=excerpt_index))
