"""
Per-channel statistics computed from asammdf Signal objects.
"""
from __future__ import annotations

from typing import Any


def channel_stats(mdf: Any, group_index: int, channel_name: str) -> dict[str, Any]:
    """
    Load one channel's samples and return summary statistics.
    Numeric channels: min, max, mean.
    All channels: sample count, first/last timestamp.
    """
    import numpy as np  # imported here to avoid top-level cost if asammdf absent

    signal = mdf.get(
        channel_name,
        group=group_index,
        raw=False,
        ignore_invalidation_bits=True,
    )
    samples = signal.samples
    n = int(len(samples))
    result: dict[str, Any] = {"samples": n}

    if n > 0 and np.issubdtype(samples.dtype, np.number):
        finite = samples[np.isfinite(samples.astype(np.float64, copy=False))]
        if len(finite) > 0:
            result["min"]  = float(np.min(finite))
            result["max"]  = float(np.max(finite))
            result["mean"] = float(np.mean(finite))

    ts = signal.timestamps
    if ts is not None and len(ts) > 0:
        result["first_t"] = float(ts[0])
        result["last_t"]  = float(ts[-1])

    return result
