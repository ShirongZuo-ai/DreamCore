"""Checkpoint integrity and frozen-loading utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path


class CBraModCheckpointError(RuntimeError):
    """Raised when the official checkpoint is missing or invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_checkpoint(path: Path, expected_sha256: str) -> dict[str, object]:
    source = Path(path)
    if not source.is_file():
        raise CBraModCheckpointError(f"CBraMod checkpoint is missing: {source}")
    actual = sha256_file(source)
    if actual != expected_sha256:
        raise CBraModCheckpointError(
            f"CBraMod checkpoint checksum mismatch: expected {expected_sha256}, got {actual}"
        )
    return {"path": str(source), "size_bytes": source.stat().st_size, "sha256": actual}


def load_frozen_model(path: Path, config, *, device: str):
    import torch

    from dreamcore.foundation_models.cbramod.model import build_cbramod

    validate_checkpoint(path, str(config["checkpoint_sha256"]))
    model = build_cbramod(config["architecture"])
    state = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(state, strict=True)
    model.proj_out = torch.nn.Identity()
    model.requires_grad_(False)
    model.eval().to(device)
    return model
