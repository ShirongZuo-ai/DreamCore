"""Frozen official CBraMod integration."""

from dreamcore.foundation_models.cbramod.adapter import CBraModAdapter, PreparedEEG
from dreamcore.foundation_models.cbramod.verifier import VerificationResult, apply_verification

__all__ = ["CBraModAdapter", "PreparedEEG", "VerificationResult", "apply_verification"]
