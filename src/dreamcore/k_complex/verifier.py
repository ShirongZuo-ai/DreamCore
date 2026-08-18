"""Frozen B1 morphology verification for retrospective K-complex candidates.

Inference is intentionally implemented with the Python standard library so the
default product path does not import scikit-learn, PyTorch, CUDA, or CBraMod.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MORPHOLOGY_B1_FEATURE_NAMES = (
    "score",
    "duration_s",
    "negative_trough_amplitude",
    "positive_peak_delay_s",
)
MORPHOLOGY_B1_METHOD = "morphology_b1"


def _value(candidate: Any, name: str) -> Any:
    if isinstance(candidate, Mapping):
        return candidate[name]
    return getattr(candidate, name)


def morphology_b1_features(candidate: Any) -> tuple[float, ...]:
    """Return the exact, ordered feature vector used by frozen benchmark B1."""

    trough_s = float(_value(candidate, "negative_trough_s"))
    positive_peak_s = _value(candidate, "positive_peak_s")
    return (
        float(_value(candidate, "score")),
        float(_value(candidate, "duration_s")),
        float(_value(candidate, "negative_trough_amplitude")),
        0.0 if positive_peak_s is None else float(positive_peak_s) - trough_s,
    )


def artifact_checksum(payload: Mapping[str, Any]) -> str:
    """Hash canonical artifact content, excluding the self-describing checksum."""

    unsigned = dict(payload)
    unsigned.pop("artifact_checksum", None)
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class KComplexVerificationResult:
    probability: float
    accepted: bool
    verification_status: str
    verification_method: str
    verifier_version: str
    threshold: float
    original_candidate_id: str
    original_trough_s: float
    original_morphology_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MorphologyB1Verifier:
    version: str
    feature_names: tuple[str, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    threshold: float
    checksum: str

    def probability(self, features: Sequence[float]) -> float:
        if len(features) != len(self.feature_names):
            raise ValueError(
                f"expected {len(self.feature_names)} morphology features, got {len(features)}"
            )
        standardized = tuple(
            (float(value) - mean) / scale
            for value, mean, scale in zip(
                features, self.scaler_mean, self.scaler_scale, strict=True
            )
        )
        logit = self.intercept + sum(
            coefficient * value
            for coefficient, value in zip(self.coefficients, standardized, strict=True)
        )
        if logit >= 0:
            return 1.0 / (1.0 + math.exp(-logit))
        exponent = math.exp(logit)
        return exponent / (1.0 + exponent)

    def verify(
        self,
        candidate: Any,
        morphology_features: Sequence[float] | None = None,
    ) -> KComplexVerificationResult:
        features = (
            morphology_b1_features(candidate)
            if morphology_features is None
            else tuple(float(value) for value in morphology_features)
        )
        probability = self.probability(features)
        accepted = probability >= self.threshold
        return KComplexVerificationResult(
            probability=probability,
            accepted=accepted,
            verification_status="accepted" if accepted else "rejected",
            verification_method=MORPHOLOGY_B1_METHOD,
            verifier_version=self.version,
            threshold=self.threshold,
            original_candidate_id=str(_value(candidate, "event_id")),
            original_trough_s=float(_value(candidate, "negative_trough_s")),
            original_morphology_score=float(_value(candidate, "score")),
        )

    def apply(self, candidate: Any) -> dict[str, Any]:
        """Return an enriched copy; never alter the V0 candidate or landmarks."""

        row = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        result = self.verify(candidate)
        row.update(
            verification_method=result.verification_method,
            verification_probability=result.probability,
            verification_status=result.verification_status,
            verification_accepted=result.accepted,
            verifier_version=result.verifier_version,
            verification_threshold=result.threshold,
            original_candidate_id=result.original_candidate_id,
            original_morphology_score=result.original_morphology_score,
            trough_s=result.original_trough_s,
        )
        if float(row["negative_trough_s"]) != result.original_trough_s:
            raise AssertionError("K-complex verification changed the original trough")
        return row


def load_morphology_b1_verifier(
    artifact_path: Path,
    *,
    expected_version: str,
    expected_checksum: str,
    expected_threshold: float,
) -> MorphologyB1Verifier:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    checksum = artifact_checksum(payload)
    recorded_checksum = str(payload.get("artifact_checksum", {}).get("value", ""))
    if checksum != recorded_checksum or checksum != expected_checksum:
        raise ValueError("K-complex morphology B1 artifact checksum mismatch")
    if payload.get("algorithm_version") != expected_version:
        raise ValueError("K-complex morphology B1 artifact version mismatch")
    feature_names = tuple(payload["feature_names"])
    if feature_names != MORPHOLOGY_B1_FEATURE_NAMES:
        raise ValueError("K-complex morphology B1 feature order mismatch")
    threshold = float(payload["decision_threshold"])
    if threshold != float(expected_threshold):
        raise ValueError("K-complex morphology B1 threshold mismatch")
    scaler = payload["preprocessing"]["standard_scaler"]
    classifier = payload["classifier"]
    mean = tuple(float(value) for value in scaler["mean"])
    scale = tuple(float(value) for value in scaler["scale"])
    coefficients = tuple(float(value) for value in classifier["coefficients"])
    expected_length = len(MORPHOLOGY_B1_FEATURE_NAMES)
    if not all(len(values) == expected_length for values in (mean, scale, coefficients)):
        raise ValueError("K-complex morphology B1 artifact shape mismatch")
    if any(value <= 0 or not math.isfinite(value) for value in scale):
        raise ValueError("K-complex morphology B1 scaler contains an invalid scale")
    return MorphologyB1Verifier(
        version=expected_version,
        feature_names=feature_names,
        scaler_mean=mean,
        scaler_scale=scale,
        coefficients=coefficients,
        intercept=float(classifier["intercept"]),
        threshold=threshold,
        checksum=checksum,
    )


def verify_k_complex_candidate(
    candidate: Any,
    morphology_features: Sequence[float] | None,
    verifier: MorphologyB1Verifier,
) -> KComplexVerificationResult:
    """Stable public interface for verification without candidate mutation."""

    return verifier.verify(candidate, morphology_features)
