"""Simulated abstract stimulation-demand dynamics for research visualization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from dreamcore.alpha.state import ResearchState
from dreamcore.alpha.trend import AlphaTrendPoint

SIMULATED_DEMAND_PROVENANCE = "SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE"


@dataclass(frozen=True)
class ControlObservation:
    """Derived evidence supplied to the simulated demand controller."""

    timestamp_s: float
    state: ResearchState
    trend: AlphaTrendPoint
    alpha_power: float | None
    relative_alpha_power: float | None
    signal_quality_valid: bool


@dataclass(frozen=True)
class DemandPoint:
    """One simulated demand state aligned to an observation timestamp."""

    timestamp: float
    stimulation_demand: float
    demand_available: bool
    controller_state: str
    ready_to_remove: bool
    provenance: str = SIMULATED_DEMAND_PROVENANCE


@dataclass(frozen=True)
class SimulationEvent:
    """Hardware-neutral simulated event for future frontend display."""

    timestamp: float
    demand_before: float
    demand_after: float
    state: str
    alpha_power: float | None
    relative_alpha_power: float | None
    alpha_trend: str
    confidence: float
    event_type: str
    provenance: str = "simulated"
    provenance_notice: str = SIMULATED_DEMAND_PROVENANCE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _simulation_config(config: Mapping) -> Mapping:
    simulation = config.get("alpha", {}).get("simulated_demand")
    if not isinstance(simulation, Mapping):
        raise TypeError("Config section 'alpha.simulated_demand' must be a mapping")
    return simulation


def _limited_smoothed_value(
    previous: float,
    target: float,
    elapsed_s: float,
    simulation: Mapping,
) -> float:
    time_constant_s = float(simulation["smoothing_time_constant_s"])
    if time_constant_s <= 0:
        raise ValueError("Demand smoothing time constant must be positive")
    smoothing = 1.0 - np.exp(-elapsed_s / time_constant_s)
    desired = previous + smoothing * (target - previous)
    if desired >= previous:
        max_delta = float(simulation["max_rise_per_minute"]) * elapsed_s / 60.0
        output = min(desired, previous + max_delta)
    else:
        max_delta = float(simulation["max_fall_per_minute"]) * elapsed_s / 60.0
        output = max(desired, previous - max_delta)
    return float(np.clip(output, 0.0, 1.0))


def simulate_stimulation_demand(
    observations: Sequence[ControlObservation],
    config: Mapping,
) -> tuple[list[DemandPoint], list[SimulationEvent]]:
    """Generate bounded, smoothed simulated demand without altering EEG."""
    if not observations:
        return [], []
    simulation = _simulation_config(config)
    times = np.asarray([item.timestamp_s for item in observations], dtype=float)
    if np.any(np.diff(times) <= 0):
        raise ValueError("Demand observation timestamps must be strictly increasing")
    initial_elapsed_s = float(simulation["initial_observation_step_s"])
    min_valid_duration_s = float(simulation["minimum_valid_observation_s"])
    min_confidence = float(simulation["minimum_state_confidence"])
    ready_duration_s = float(simulation["ready_sustain_s"])
    ready_entry = float(simulation["ready_drowsiness_entry"])
    ready_exit = float(simulation["ready_drowsiness_exit"])
    if ready_exit >= ready_entry:
        raise ValueError("Ready hysteresis exit must be below entry")

    previous = float(simulation["initial_demand"])
    valid_duration_s = 0.0
    ready_evidence_s = 0.0
    ready_latched = False
    points: list[DemandPoint] = []
    events: list[SimulationEvent] = []
    for index, observation in enumerate(observations):
        elapsed_s = initial_elapsed_s if index == 0 else times[index] - times[index - 1]
        confidence = observation.state.state_confidence
        valid = bool(
            observation.signal_quality_valid
            and observation.state.available
            and confidence >= min_confidence
        )
        before = previous
        if not valid:
            valid_duration_s = 0.0
            ready_evidence_s = 0.0
            available = False
            controller_state = "hold_quality_or_confidence"
            event_type = "stimulation_held"
        else:
            valid_duration_s += elapsed_s
            drowsiness = float(observation.state.drowsiness_score)
            change = observation.trend.alpha_change_from_baseline
            ready_evidence = bool(
                drowsiness >= ready_entry
                and change is not None
                and change <= float(simulation["ready_alpha_change_max"])
                and observation.trend.alpha_trend in tuple(simulation["ready_allowed_trends"])
            )
            ready_evidence_s = ready_evidence_s + elapsed_s if ready_evidence else 0.0
            if ready_latched and drowsiness < ready_exit:
                ready_latched = False
            if ready_evidence_s >= ready_duration_s:
                ready_latched = True

            if valid_duration_s < min_valid_duration_s:
                available = False
                controller_state = "observing"
                event_type = "stimulation_held"
            else:
                available = True
                awake = float(observation.state.awake_score)
                target = float(simulation["minimum_active_demand"]) + awake * (
                    float(simulation["maximum_demand"]) - float(simulation["minimum_active_demand"])
                )
                target *= 1.0 - float(simulation["drowsiness_reduction_weight"]) * drowsiness
                if observation.trend.alpha_trend == "falling":
                    target *= float(simulation["falling_trend_multiplier"])
                if ready_latched:
                    target = 0.0
                if abs(target - previous) < float(simulation["demand_hysteresis_deadband"]):
                    target = previous
                previous = _limited_smoothed_value(previous, target, elapsed_s, simulation)
                if ready_latched and previous <= float(simulation["ready_demand_max"]):
                    previous = 0.0
                    controller_state = "ready_to_remove"
                    event_type = "ready_to_remove"
                elif before <= float(simulation["stopped_demand_threshold"]) < previous:
                    controller_state = "active_simulation"
                    event_type = "stimulation_requested"
                elif previous <= float(simulation["stopped_demand_threshold"]) < before:
                    controller_state = "stopped_simulation"
                    event_type = "stimulation_stopped"
                elif previous < before - float(simulation["event_change_threshold"]):
                    controller_state = "reducing_simulation"
                    event_type = "stimulation_reduced"
                else:
                    controller_state = "holding_simulation"
                    event_type = "stimulation_held"

        ready_to_remove = bool(ready_latched and previous <= float(simulation["ready_demand_max"]))
        point = DemandPoint(
            timestamp=observation.timestamp_s,
            stimulation_demand=float(np.clip(previous, 0.0, 1.0)),
            demand_available=available,
            controller_state=controller_state,
            ready_to_remove=ready_to_remove,
        )
        points.append(point)
        state_label = (
            "unavailable"
            if not observation.state.available
            else (
                "drowsy"
                if float(observation.state.drowsiness_score)
                >= float(simulation["event_drowsiness_label_threshold"])
                else "awake"
            )
        )
        events.append(
            SimulationEvent(
                timestamp=observation.timestamp_s,
                demand_before=before,
                demand_after=point.stimulation_demand,
                state=state_label,
                alpha_power=observation.alpha_power,
                relative_alpha_power=observation.relative_alpha_power,
                alpha_trend=observation.trend.alpha_trend,
                confidence=confidence,
                event_type=event_type,
            )
        )
    return points, events
