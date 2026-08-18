"""Embedding cache identity without duplicated raw EEG."""

from __future__ import annotations

import hashlib
import json


def embedding_cache_identity(
    *, source_fingerprint, channels, preprocessing, checkpoint_hash, adapter_version, window
):
    payload = {
        "source_fingerprint": source_fingerprint,
        "channels": list(channels),
        "preprocessing": preprocessing,
        "checkpoint_hash": checkpoint_hash,
        "adapter_version": adapter_version,
        "window": window,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {**payload, "cache_key": hashlib.sha256(canonical.encode()).hexdigest()}
