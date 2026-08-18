"""Verifier output changes acceptance only and preserves V0 landmarks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    probability: float
    confidence: str
    verifier_version: str


def apply_verification(event, result: VerificationResult):
    row = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    row.update(
        cbramod_accepted=result.accepted,
        cbramod_probability=result.probability,
        cbramod_confidence=result.confidence,
        cbramod_verifier_version=result.verifier_version,
    )
    return row
