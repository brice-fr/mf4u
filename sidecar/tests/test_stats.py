"""
Tests for sidecar/stats.py — per-channel statistics.
"""
from __future__ import annotations

import math

import pytest


def _open(path: str):
    from asammdf import MDF  # type: ignore[import-untyped]
    return MDF(path, memory="low")


class TestChannelStats:
    """Uses minimal.mf4: group 0 has Ch1=sin(t), Ch2=cos(t), Ch3=t*2, 100 samples, t∈[0,1]."""

    def test_returns_sample_count(self, minimal_mf4):
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch1")
        finally:
            mdf.close()
        assert result["samples"] == 100

    def test_numeric_stats_present(self, minimal_mf4):
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch1")
        finally:
            mdf.close()
        assert "min" in result
        assert "max" in result
        assert "mean" in result

    def test_sin_channel_range(self, minimal_mf4):
        """Ch1 = sin(t) for t in [0,1] — range roughly [-1, 1], mean ≈ 0.46."""
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch1")
        finally:
            mdf.close()
        assert result["min"] >= -1.0 - 1e-6
        assert result["max"] <= 1.0 + 1e-6
        assert result["max"] > 0.8   # sin reaches ~0.84 at t=1

    def test_linear_channel_range(self, minimal_mf4):
        """Ch3 = t*2 for t in [0,1] — range [0, 2], mean = 1."""
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch3")
        finally:
            mdf.close()
        assert result["min"] == pytest.approx(0.0, abs=0.01)
        assert result["max"] == pytest.approx(2.0, abs=0.01)
        assert result["mean"] == pytest.approx(1.0, abs=0.02)

    def test_timestamps_present(self, minimal_mf4):
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch1")
        finally:
            mdf.close()
        assert "first_t" in result
        assert "last_t" in result
        assert result["first_t"] == pytest.approx(0.0, abs=1e-9)
        assert result["last_t"] == pytest.approx(1.0, abs=0.01)

    def test_last_t_greater_than_first_t(self, minimal_mf4):
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch2")
        finally:
            mdf.close()
        assert result["last_t"] > result["first_t"]

    def test_all_values_finite(self, minimal_mf4):
        import stats as st
        mdf = _open(minimal_mf4)
        try:
            result = st.channel_stats(mdf, 0, "Ch1")
        finally:
            mdf.close()
        for key in ("min", "max", "mean"):
            assert math.isfinite(result[key]), f"{key} should be finite"

    def test_multi_group_indexing(self, multi_group_mf4):
        """Verify we can retrieve stats from groups other than group 0."""
        import stats as st
        mdf = _open(multi_group_mf4)
        try:
            # Group 1 has VehicleSpeed and SteeringAngle
            result = st.channel_stats(mdf, 1, "VehicleSpeed")
        finally:
            mdf.close()
        assert result["samples"] == 100
        assert "min" in result
