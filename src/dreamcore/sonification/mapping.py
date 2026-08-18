"""Map derived features to musical controls without physiological claims."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from dreamcore.eye_movement.features import EyeMovementEvent, EyeMovementFeature


@dataclass(frozen=True)
class SonificationControlFrame:
    session_id: str
    source: str
    source_feature: str
    window_start_s: float
    window_end_s: float
    available: bool
    tempo_bpm: float | None
    density: float | None
    intensity: float | None
    brightness_hz: float | None
    trigger: bool
    event_id: str | None
    note_midi: int | None
    note_velocity: float | None
    mapping_version: str
    control_version: str
    seed: int
    provenance: str = "sonification_control"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Config section {key!r} must be a mapping")
    return value


def _linear(value: float, bounds: Mapping[str, Any]) -> float:
    return float(bounds["minimum"]) + value * (float(bounds["maximum"]) - float(bounds["minimum"]))


class SonificationMapper:
    """A deterministic feature-to-music mapping suitable for later adapters."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._config = _section(config, "sonification")
        self.mapping_version = str(self._config["mapping_version"])
        self.control_version = str(self._config["control_version"])
        self.seed = int(self._config["seed"])

    def eye_movement_frames(
        self,
        session_id: str,
        features: Sequence[EyeMovementFeature],
        events: Sequence[EyeMovementEvent],
    ) -> tuple[SonificationControlFrame, ...]:
        mapping = _section(self._config, "eye_movement")
        tempo = _section(mapping, "tempo_bpm")
        velocity = _section(mapping, "velocity")
        scale = tuple(int(note) for note in mapping["midi_scale"])
        if not scale:
            raise ValueError("Eye-movement sonification scale cannot be empty")
        rotation = random.Random(f"{self.seed}:{session_id}:eye_movement").randrange(len(scale))
        event_order = {event.event_id: index for index, event in enumerate(events)}
        sorted_events = sorted(events, key=lambda event: event.timestamp)
        event_index = 0
        previous_end = float("-inf")
        frames = []
        for feature in features:
            reached = []
            while (
                event_index < len(sorted_events)
                and sorted_events[event_index].timestamp <= feature.window_end_s
            ):
                event = sorted_events[event_index]
                if event.timestamp > previous_end:
                    reached.append(event)
                event_index += 1
            event = reached[-1] if reached else None
            available = feature.signal_quality == "valid" and all(
                value is not None
                for value in (
                    feature.activity_score,
                    feature.amplitude_score,
                    feature.event_rate_per_min,
                )
            )
            if available:
                activity = float(feature.activity_score)
                amplitude = float(feature.amplitude_score)
                event_rate = min(
                    1.0,
                    float(feature.event_rate_per_min) / float(tempo["event_rate_max_per_min"]),
                )
                event_note = (
                    scale[(rotation + event_order[event.event_id]) % len(scale)]
                    if event is not None
                    else None
                )
                event_velocity = (
                    _linear(float(event.confidence), velocity) if event is not None else None
                )
            else:
                activity = amplitude = event_rate = 0.0
                event_note = None
                event_velocity = None
            frames.append(
                SonificationControlFrame(
                    session_id=session_id,
                    source="eye_movement",
                    source_feature="eye_movement_activity_v1",
                    window_start_s=feature.window_start_s,
                    window_end_s=feature.window_end_s,
                    available=available,
                    tempo_bpm=_linear(event_rate, tempo) if available else None,
                    density=_linear(activity, _section(mapping, "density")) if available else None,
                    intensity=(
                        _linear(amplitude, _section(mapping, "intensity")) if available else None
                    ),
                    brightness_hz=(
                        _linear(activity, _section(mapping, "brightness_hz")) if available else None
                    ),
                    trigger=event is not None and available,
                    event_id=event.event_id if event is not None and available else None,
                    note_midi=event_note,
                    note_velocity=event_velocity,
                    mapping_version=self.mapping_version,
                    control_version=self.control_version,
                    seed=self.seed,
                )
            )
            previous_end = feature.window_end_s
        return tuple(frames)

    def alpha_comparison_frames(
        self,
        session_id: str,
        alpha_rows: Sequence[Mapping[str, Any]],
    ) -> tuple[SonificationControlFrame, ...]:
        mapping = _section(self._config, "alpha_comparison")
        channel = mapping.get("source_channel")
        selected = [
            row for row in alpha_rows if channel is None or str(row.get("channel")) == str(channel)
        ]
        values = np.asarray([float(row["relative_alpha_power"]) for row in selected], dtype=float)
        finite = np.isfinite(values)
        scores = np.full(values.shape, np.nan)
        if np.any(finite):
            low = float(np.quantile(values[finite], float(mapping["low_quantile"])))
            high = float(np.quantile(values[finite], float(mapping["high_quantile"])))
            if high > low:
                scores[finite] = np.clip((values[finite] - low) / (high - low), 0.0, 1.0)
        scale = tuple(int(note) for note in mapping["midi_scale"])
        rotation = random.Random(f"{self.seed}:{session_id}:alpha").randrange(len(scale))
        frames = []
        for index, (row, score) in enumerate(zip(selected, scores, strict=True)):
            available = bool(np.isfinite(score))
            value = float(score) if available else 0.0
            frames.append(
                SonificationControlFrame(
                    session_id=session_id,
                    source="alpha",
                    source_feature="relative_alpha_power",
                    window_start_s=float(row["window_start_s"]),
                    window_end_s=float(row["window_end_s"]),
                    available=available,
                    tempo_bpm=_linear(value, _section(mapping, "tempo_bpm")) if available else None,
                    density=_linear(value, _section(mapping, "density")) if available else None,
                    intensity=_linear(value, _section(mapping, "intensity")) if available else None,
                    brightness_hz=(
                        _linear(value, _section(mapping, "brightness_hz")) if available else None
                    ),
                    trigger=available,
                    event_id=None,
                    note_midi=scale[(rotation + index) % len(scale)] if available else None,
                    note_velocity=(
                        _linear(value, _section(mapping, "intensity")) if available else None
                    ),
                    mapping_version=self.mapping_version,
                    control_version=self.control_version,
                    seed=self.seed,
                )
            )
        return tuple(frames)

    def metadata(self) -> dict[str, Any]:
        """Return the exact inspectable mappings persisted with the artifact."""

        return {
            "mapping_version": self.mapping_version,
            "control_version": self.control_version,
            "seed": self.seed,
            "eye_movement": dict(_section(self._config, "eye_movement")),
            "alpha_comparison": dict(_section(self._config, "alpha_comparison")),
            "baseline": dict(_section(self._config, "baseline")),
            "audio": dict(_section(self._config, "audio")),
            "scientific_boundary": (
                "Musical mappings are deterministic exploratory controls, not physiological "
                "interpretations or therapeutic parameters."
            ),
        }
