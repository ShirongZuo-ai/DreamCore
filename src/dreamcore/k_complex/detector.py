"""Transparent retrospective K-complex morphology detector.

The detector intentionally uses the complete candidate waveform. It is not a
causal trough predictor and exposes no lead-time quantity.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.signal import butter, find_peaks, peak_prominences, sosfiltfilt


@dataclass(frozen=True)
class N2Bout:
    bout_id: str
    stage: str
    start_s: float
    end_s: float
    raw_labels: tuple[str, ...]
    scorers: tuple[str, ...]

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "duration_s": self.duration_s}


@dataclass(frozen=True)
class KComplexEvent:
    event_id: str
    dataset_id: str
    subject_id: str
    recording_id: str
    channel: str
    stage: str
    n2_bout_id: str
    ordinal_in_n2_bout: int
    onset_s: float
    negative_trough_s: float
    negative_trough_amplitude: float
    positive_peak_s: float | None
    end_s: float
    duration_s: float
    score: float
    confidence: str
    detector_version: str
    config_hash: str
    source_fingerprint: str
    amplitude_unit: str = "uV"
    provenance: str = "derived"
    event_type: str = "k_complex_candidate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def segment_stage_bouts(
    annotations: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[N2Bout, ...]:
    """Merge contiguous configured-stage annotations into auditable bouts."""

    stage_config = config["stage_gating"]
    target = str(stage_config["primary_stage"])
    tolerance = float(stage_config["bout_merge_tolerance_s"])
    intervals = []
    for annotation in annotations:
        stage = str(annotation.get("normalized_label", annotation.get("label", "UNKNOWN")))
        if bool(stage_config["enabled"]) and stage != target:
            continue
        start = float(annotation["start_seconds"])
        end = start + float(annotation["duration_seconds"])
        if end <= start:
            continue
        intervals.append(
            (
                start,
                end,
                stage,
                str(annotation.get("raw_label", annotation.get("label", stage))),
                str(annotation.get("scorer", "unknown")),
            )
        )
    intervals.sort(key=lambda item: (item[0], item[1]))
    merged: list[dict[str, Any]] = []
    for start, end, stage, raw_label, scorer in intervals:
        if merged and stage == merged[-1]["stage"] and start <= merged[-1]["end"] + tolerance:
            merged[-1]["end"] = max(merged[-1]["end"], end)
            merged[-1]["raw_labels"].add(raw_label)
            merged[-1]["scorers"].add(scorer)
        else:
            merged.append(
                {
                    "start": start,
                    "end": end,
                    "stage": stage,
                    "raw_labels": {raw_label},
                    "scorers": {scorer},
                }
            )
    return tuple(
        N2Bout(
            bout_id=f"{target}-{index:04d}",
            stage=str(item["stage"]),
            start_s=float(item["start"]),
            end_s=float(item["end"]),
            raw_labels=tuple(sorted(item["raw_labels"])),
            scorers=tuple(sorted(item["scorers"])),
        )
        for index, item in enumerate(merged, start=1)
    )


def _interpolate_nonfinite(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(values)
    if finite.all():
        return values.copy(), finite
    if not finite.any():
        return np.zeros_like(values), finite
    indices = np.arange(values.size)
    return np.interp(indices, indices[finite], values[finite]), finite


def _crossing_before(values: np.ndarray, trough: int, limit: int) -> int | None:
    start = max(0, trough - limit)
    crossing = np.flatnonzero((values[start:trough] >= 0) & (values[start + 1 : trough + 1] < 0))
    return start + int(crossing[-1]) + 1 if crossing.size else None


def _upward_crossing_after(values: np.ndarray, start: int, limit: int) -> int | None:
    end = min(values.size - 1, start + limit)
    crossing = np.flatnonzero((values[start:end] <= 0) & (values[start + 1 : end + 1] > 0))
    return start + int(crossing[0]) + 1 if crossing.size else None


def _downward_crossing_after(values: np.ndarray, start: int, limit: int) -> int | None:
    end = min(values.size - 1, start + limit)
    crossing = np.flatnonzero((values[start:end] >= 0) & (values[start + 1 : end + 1] < 0))
    return start + int(crossing[0]) + 1 if crossing.size else None


def _confidence(score: float, config: Mapping[str, Any]) -> str:
    score_config = config["score"]
    if score >= float(score_config["high_confidence_min"]):
        return "high"
    if score >= float(score_config["medium_confidence_min"]):
        return "medium"
    return "low"


def suppress_refractory(
    events: Sequence[dict[str, Any]], refractory_s: float
) -> list[dict[str, Any]]:
    """Keep the stronger of candidates whose troughs violate refractory time."""

    kept: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: float(item["negative_trough_s"])):
        if (
            not kept
            or float(event["negative_trough_s"]) - float(kept[-1]["negative_trough_s"])
            >= refractory_s
        ):
            kept.append(event)
        elif float(event["score"]) > float(kept[-1]["score"]):
            kept[-1] = event
    return kept


def detect_k_complexes(
    samples_uv: Sequence[float],
    sampling_rate_hz: float,
    channel: str,
    bouts: Sequence[N2Bout],
    config: Mapping[str, Any],
    *,
    dataset_id: str,
    subject_id: str,
    recording_id: str,
    detector_version: str,
    config_hash: str,
    source_fingerprint: str,
) -> tuple[KComplexEvent, ...]:
    """Detect retrospective negative-positive candidates inside configured bouts."""

    rate = float(sampling_rate_hz)
    values = np.asarray(samples_uv, dtype=float)
    if values.ndim != 1 or values.size < 3 or rate <= 0:
        return ()
    interpolated, finite_mask = _interpolate_nonfinite(values)
    filtering = config["filtering"]
    nyquist = rate / 2.0
    low = float(filtering["low_hz"])
    high = float(filtering["high_hz"])
    if not 0 < low < high < nyquist:
        raise ValueError("K-complex filter band must be below the native Nyquist frequency")
    if str(filtering["method"]) != "butterworth" or str(filtering["phase"]) != "zero":
        raise ValueError("K-complex V0 supports configured zero-phase Butterworth filtering")
    sos = butter(
        int(filtering["order"]),
        [low / nyquist, high / nyquist],
        btype="band",
        output="sos",
    )
    filtered = sosfiltfilt(sos, interpolated)
    morphology = config["morphology"]
    baseline_config = config["baseline"]
    candidate_config = config["candidate"]
    artifact = config["artifact_rejection"]
    score_config = config["score"]
    raw_events: list[dict[str, Any]] = []
    for bout in bouts:
        first = max(0, int(round(bout.start_s * rate)))
        last = min(values.size, int(round(bout.end_s * rate)))
        if last - first < 3:
            continue
        segment = filtered[first:last]
        baseline = float(np.median(segment))
        scale = max(
            float(baseline_config["minimum_scale_uv"]),
            float(baseline_config["robust_scale_factor"])
            * float(np.median(np.abs(segment - baseline))),
        )
        centered = segment - baseline
        peaks, _ = find_peaks(
            -centered,
            height=float(candidate_config["negative_depth_robust_z"]) * scale,
            prominence=float(candidate_config["prominence_robust_z"]) * scale,
        )
        prominences = peak_prominences(-centered, peaks)[0] if peaks.size else np.array([])
        for relative_trough, prominence in zip(peaks, prominences, strict=True):
            trough = first + int(relative_trough)
            local_radius = int(round(float(baseline_config["local_window_s"]) * rate / 2.0))
            local_start = max(first, trough - local_radius)
            local_end = min(last, trough + local_radius + 1)
            local = filtered[local_start:local_end]
            local_baseline = float(np.median(local))
            local_scale = max(
                float(baseline_config["minimum_scale_uv"]),
                float(baseline_config["robust_scale_factor"])
                * float(np.median(np.abs(local - local_baseline))),
            )
            centered_full = filtered - local_baseline
            onset = _crossing_before(
                centered_full,
                trough,
                int(round(float(morphology["onset_search_s"]) * rate)),
            )
            if onset is None:
                continue
            negative_duration = (trough - onset) / rate
            if (
                not float(morphology["negative_halfwave_min_s"])
                <= negative_duration
                <= float(morphology["negative_halfwave_max_s"])
            ):
                continue
            positive_start = trough + int(
                round(float(morphology["positive_peak_min_delay_s"]) * rate)
            )
            positive_end = min(
                last,
                trough + int(round(float(morphology["positive_peak_max_delay_s"]) * rate)) + 1,
            )
            positive_peak: int | None = None
            if positive_start < positive_end:
                proposed = positive_start + int(
                    np.argmax(centered_full[positive_start:positive_end])
                )
                if (
                    centered_full[proposed]
                    >= float(morphology["positive_peak_min_robust_z"]) * local_scale
                ):
                    positive_peak = proposed
            if positive_peak is None and bool(morphology["require_positive_peak"]):
                continue
            if positive_peak is None:
                end = _upward_crossing_after(
                    centered_full,
                    trough,
                    int(round(float(morphology["event_duration_max_s"]) * rate)),
                )
            else:
                end = _downward_crossing_after(
                    centered_full,
                    positive_peak,
                    int(round(float(morphology["end_search_after_peak_s"]) * rate)),
                )
            if end is None:
                continue
            duration = (end - onset) / rate
            if (
                not float(morphology["event_duration_min_s"])
                <= duration
                <= float(morphology["event_duration_max_s"])
            ):
                continue
            finite_ratio = float(np.mean(finite_mask[onset : end + 1]))
            raw_window = values[onset : end + 1]
            if finite_ratio < float(artifact["minimum_finite_ratio"]):
                continue
            finite_raw = raw_window[np.isfinite(raw_window)]
            if not finite_raw.size:
                continue
            if np.max(np.abs(finite_raw)) > float(artifact["maximum_absolute_amplitude_uv"]):
                continue
            if np.ptp(finite_raw) > float(artifact["maximum_peak_to_peak_uv"]):
                continue
            depth_z = max(0.0, -centered_full[trough] / local_scale)
            prominence_z = max(0.0, float(prominence) / local_scale)
            saturation = float(candidate_config["confidence_saturation_z"])
            positive_score = (
                min(1.0, max(0.0, centered_full[positive_peak] / saturation / local_scale))
                if positive_peak is not None
                else 0.0
            )
            score = min(
                1.0,
                float(score_config["negative_depth_weight"]) * min(1.0, depth_z / saturation)
                + float(score_config["prominence_weight"]) * min(1.0, prominence_z / saturation)
                + float(score_config["positive_component_weight"]) * positive_score,
            )
            raw_events.append(
                {
                    "bout": bout,
                    "onset_s": onset / rate,
                    "negative_trough_s": trough / rate,
                    "negative_trough_amplitude": float(centered_full[trough]),
                    "positive_peak_s": positive_peak / rate if positive_peak is not None else None,
                    "end_s": end / rate,
                    "duration_s": duration,
                    "score": score,
                }
            )
    kept = suppress_refractory(raw_events, float(config["refractory_interval_s"]))
    ordinals: dict[str, int] = {}
    output = []
    for candidate in kept:
        bout = candidate.pop("bout")
        ordinals[bout.bout_id] = ordinals.get(bout.bout_id, 0) + 1
        trough_s = float(candidate["negative_trough_s"])
        digest = hashlib.sha256(
            f"{recording_id}|{channel}|{trough_s:.9f}|{detector_version}|{config_hash}".encode()
        ).hexdigest()[:20]
        score = float(candidate["score"])
        output.append(
            KComplexEvent(
                event_id=f"kc-{digest}",
                dataset_id=dataset_id,
                subject_id=subject_id,
                recording_id=recording_id,
                channel=channel,
                stage=bout.stage,
                n2_bout_id=bout.bout_id,
                ordinal_in_n2_bout=ordinals[bout.bout_id],
                onset_s=float(candidate["onset_s"]),
                negative_trough_s=trough_s,
                negative_trough_amplitude=float(candidate["negative_trough_amplitude"]),
                positive_peak_s=candidate["positive_peak_s"],
                end_s=float(candidate["end_s"]),
                duration_s=float(candidate["duration_s"]),
                score=score,
                confidence=_confidence(score, config),
                detector_version=detector_version,
                config_hash=config_hash,
                source_fingerprint=source_fingerprint,
            )
        )
    return tuple(output)
