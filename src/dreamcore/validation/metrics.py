"""Small numerical summaries with explicit missing-value semantics."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def finite_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {"count": 0, "mean": None, "median": None, "mae": None, "p90": None, "p95": None}
    absolute = np.abs(array)
    return {
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "mae": float(np.mean(absolute)),
        "p90": float(np.quantile(absolute, 0.90)),
        "p95": float(np.quantile(absolute, 0.95)),
    }


def safe_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if np.sum(valid) < 2 or np.std(x[valid]) == 0 or np.std(y[valid]) == 0:
        return None
    return float(np.corrcoef(x[valid], y[valid])[0, 1])
