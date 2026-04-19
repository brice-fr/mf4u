"""
Tests for sidecar/export.py — MAT, TDMS, and Parquet export jobs.
"""
from __future__ import annotations

import os
import time

import pytest


def _open(path: str):
    from asammdf import MDF  # type: ignore[import-untyped]
    return MDF(path, memory="low")


def _wait_for_job(job_id: str, timeout: float = 30.0) -> dict:
    """Poll get_progress until the job leaves the 'running' state."""
    import export as exp
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        progress = exp.get_progress(job_id)
        if progress["status"] != "running":
            return progress
        time.sleep(0.05)
    raise TimeoutError(f"export job {job_id!r} did not finish within {timeout}s")


# --------------------------------------------------------------------------- #
# MAT export
# --------------------------------------------------------------------------- #

class TestMatExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_progress_done_equals_total(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["done"] == progress["total"]

    def test_output_readable_by_scipy(self, minimal_mf4, tmp_path):
        import export as exp
        import scipy.io as sio  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        mat = sio.loadmat(out)
        # At least one channel should be present
        data_keys = [k for k in mat if not k.startswith("_")]
        assert len(data_keys) >= 1

    def test_mat_contains_signal_arrays(self, minimal_mf4, tmp_path):
        import export as exp
        import scipy.io as sio  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        mat = sio.loadmat(out)
        # Ch1, Ch2, Ch3 are numeric → should be exported
        assert any("Ch" in k for k in mat), f"Expected Ch* keys, got {list(mat)}"


# --------------------------------------------------------------------------- #
# TDMS export
# --------------------------------------------------------------------------- #

class TestTdmsExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.tdms")
        try:
            job_id = exp.start(mdf, "tdms", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_output_readable_by_nptdms(self, minimal_mf4, tmp_path):
        import export as exp
        from nptdms import TdmsFile  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.tdms")
        try:
            job_id = exp.start(mdf, "tdms", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        tdms = TdmsFile.read(out)
        groups = tdms.groups()
        assert len(groups) >= 1

    def test_tdms_contains_channels(self, minimal_mf4, tmp_path):
        import export as exp
        from nptdms import TdmsFile  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.tdms")
        try:
            job_id = exp.start(mdf, "tdms", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        tdms = TdmsFile.read(out)
        all_channels = [ch for g in tdms.groups() for ch in g.channels()]
        assert len(all_channels) >= 3   # Ch1, Ch2, Ch3


# --------------------------------------------------------------------------- #
# Parquet export
# --------------------------------------------------------------------------- #

class TestParquetExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.parquet")
        try:
            job_id = exp.start(mdf, "parquet", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        # Single-group file → written to the exact output path
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_output_readable_by_pyarrow(self, minimal_mf4, tmp_path):
        import export as exp
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.parquet")
        try:
            job_id = exp.start(mdf, "parquet", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        table = pq.read_table(out)
        assert table.num_rows > 0

    def test_multi_group_creates_multiple_files(self, multi_group_mf4, tmp_path):
        import export as exp
        mdf = _open(multi_group_mf4)
        out = str(tmp_path / "multi.parquet")
        try:
            job_id = exp.start(mdf, "parquet", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        parquet_files = [f for f in os.listdir(tmp_path) if f.endswith(".parquet")]
        assert len(parquet_files) == 4


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #

class TestCancellation:
    def test_cancel_sets_status(self, multi_group_mf4, tmp_path):
        """Start an export and immediately cancel — status should become 'cancelled'."""
        import export as exp
        mdf = _open(multi_group_mf4)
        out = str(tmp_path / "cancelled.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            exp.cancel(job_id)
            # Wait for the thread to settle
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] in ("cancelled", "done"), (
            f"Unexpected status: {progress['status']}"
        )

    def test_cancel_cleans_up_partial_file(self, multi_group_mf4, tmp_path):
        """Cancelled export should not leave a partial output file behind."""
        import export as exp
        mdf = _open(multi_group_mf4)
        out = str(tmp_path / "partial.mat")
        try:
            job_id = exp.start(mdf, "mat", out)
            exp.cancel(job_id)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        if progress["status"] == "cancelled":
            assert not os.path.isfile(out), "Partial file should have been cleaned up"

    def test_not_found_status_for_unknown_job(self):
        import export as exp
        progress = exp.get_progress("no-such-job-id")
        assert progress["status"] == "not_found"
