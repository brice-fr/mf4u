"""
Tests for sidecar/export.py — MAT, TDMS, Parquet, CSV, TSV, and XLSX export jobs.
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
# CSV export
# --------------------------------------------------------------------------- #

class TestCsvExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.csv")
        try:
            job_id = exp.start(mdf, "csv", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_has_header_and_data_rows(self, minimal_mf4, tmp_path):
        import csv
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.csv")
        try:
            job_id = exp.start(mdf, "csv", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        with open(out, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert len(rows) >= 2                         # header + at least one data row
        assert "timestamps" in rows[0]
        assert any("Ch" in col for col in rows[0])    # Ch1 / Ch2 / Ch3 in header

    def test_multi_group_creates_multiple_files(self, multi_group_mf4, tmp_path):
        import export as exp
        mdf = _open(multi_group_mf4)
        out = str(tmp_path / "multi.csv")
        try:
            job_id = exp.start(mdf, "csv", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        csv_files = [f for f in os.listdir(tmp_path) if f.endswith(".csv")]
        assert len(csv_files) == 4


# --------------------------------------------------------------------------- #
# TSV export
# --------------------------------------------------------------------------- #

class TestTsvExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.tsv")
        try:
            job_id = exp.start(mdf, "tsv", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_tab_delimited(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.tsv")
        try:
            job_id = exp.start(mdf, "tsv", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        with open(out, encoding="utf-8") as fh:
            header = fh.readline()
        assert "\t" in header
        assert "," not in header


# --------------------------------------------------------------------------- #
# XLSX export
# --------------------------------------------------------------------------- #

class TestXlsxExport:
    def test_creates_file(self, minimal_mf4, tmp_path):
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.xlsx")
        try:
            job_id = exp.start(mdf, "xlsx", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_output_readable_by_openpyxl(self, minimal_mf4, tmp_path):
        import export as exp
        import openpyxl  # type: ignore[import-untyped]
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.xlsx")
        try:
            job_id = exp.start(mdf, "xlsx", out)
            _wait_for_job(job_id)
        finally:
            mdf.close()
        wb = openpyxl.load_workbook(out, read_only=True)
        assert len(wb.sheetnames) >= 1
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        assert len(rows) >= 2    # header + at least one data row
        wb.close()

    def test_multi_group_creates_multiple_sheets(self, multi_group_mf4, tmp_path):
        import export as exp
        import openpyxl  # type: ignore[import-untyped]
        mdf = _open(multi_group_mf4)
        out = str(tmp_path / "multi.xlsx")
        try:
            job_id = exp.start(mdf, "xlsx", out)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        wb = openpyxl.load_workbook(out, read_only=True)
        assert len(wb.sheetnames) == 4
        wb.close()


# --------------------------------------------------------------------------- #
# Phase A — bus frame decoding
# --------------------------------------------------------------------------- #

class TestDbLoading:
    def test_load_dbc_returns_db_object(self, can_bus_dbc):
        """_load_db_matrix should parse the DBC without error."""
        import export as exp
        db = exp._load_db_matrix(can_bus_dbc)
        assert db is not None

    def test_dbc_message_map_correct_count(self, can_bus_dbc):
        """can_bus.dbc has exactly 2 messages (IDs 100 and 200)."""
        import export as exp
        db  = exp._load_db_matrix(can_bus_dbc)
        msg = exp._db_message_map(db)
        assert len(msg) == 2
        assert 100 in msg
        assert 200 in msg

    def test_dbc_signal_counts(self, can_bus_dbc):
        """Message 100 has 2 signals; message 200 has 2 signals → 4 total."""
        import export as exp
        db  = exp._load_db_matrix(can_bus_dbc)
        msg = exp._db_message_map(db)
        assert msg[100] == 2
        assert msg[200] == 2

    def test_load_nonexistent_raises(self, tmp_path):
        import export as exp
        with pytest.raises(Exception):
            exp._load_db_matrix(str(tmp_path / "ghost.dbc"))


class TestGetGroupCanIds:
    def test_reads_ids_from_bus_raw(self, bus_raw_mf4):
        """bus_raw.mf4 has CAN_DataFrame.ID with values 100 and 200."""
        import export as exp
        mdf = _open(bus_raw_mf4)
        try:
            ids = exp._get_group_can_ids(mdf, 0)
        finally:
            mdf.close()
        assert ids is not None
        assert 100 in ids
        assert 200 in ids

    def test_returns_none_for_missing_channel(self, minimal_mf4):
        """minimal.mf4 has no CAN_DataFrame.ID channel → should return None."""
        import export as exp
        mdf = _open(minimal_mf4)
        try:
            ids = exp._get_group_can_ids(mdf, 0)
        finally:
            mdf.close()
        assert ids is None


class TestPreviewBusDecoding:
    def test_preview_returns_one_entry_per_assignment(self, bus_raw_mf4, can_bus_dbc):
        import export as exp
        mdf = _open(bus_raw_mf4)
        assignments = [
            {"group_index": 0, "db_path": can_bus_dbc},
        ]
        try:
            results = exp.preview_bus_decoding(mdf, assignments)
        finally:
            mdf.close()
        assert len(results) == 1
        assert results[0]["group_index"] == 0
        assert results[0]["db_path"] == can_bus_dbc
        assert results[0]["error"] is None

    def test_preview_correct_match_count(self, bus_raw_mf4, can_bus_dbc):
        """Both DB messages (100, 200) appear in bus_raw.mf4 → matched_messages=2."""
        import export as exp
        mdf = _open(bus_raw_mf4)
        assignments = [{"group_index": 0, "db_path": can_bus_dbc}]
        try:
            results = exp.preview_bus_decoding(mdf, assignments)
        finally:
            mdf.close()
        assert results[0]["matched_messages"] == 2
        assert results[0]["signal_count"] == 4   # 2 signals per message

    def test_preview_empty_when_no_assignments(self, bus_raw_mf4):
        import export as exp
        mdf = _open(bus_raw_mf4)
        try:
            results = exp.preview_bus_decoding(mdf, [])
        finally:
            mdf.close()
        assert results == []

    def test_preview_error_for_bad_db_path(self, bus_raw_mf4, tmp_path):
        """Missing DB file should produce an error entry (not raise)."""
        import export as exp
        mdf = _open(bus_raw_mf4)
        assignments = [{"group_index": 0, "db_path": str(tmp_path / "missing.dbc")}]
        try:
            results = exp.preview_bus_decoding(mdf, assignments)
        finally:
            mdf.close()
        assert results[0]["error"] is not None

    def test_preview_fallback_when_no_can_id_channel(self, minimal_mf4, can_bus_dbc):
        """When group has no CAN_DataFrame.ID, all DB messages count as matched."""
        import export as exp
        mdf = _open(minimal_mf4)
        # minimal.mf4 has no CAN frames — _get_group_can_ids returns None
        assignments = [{"group_index": 0, "db_path": can_bus_dbc}]
        try:
            results = exp.preview_bus_decoding(mdf, assignments)
        finally:
            mdf.close()
        # Fallback: report all DB messages since we can't cross-reference IDs
        assert results[0]["matched_messages"] == 2
        assert results[0]["signal_count"] == 4


class TestExportWithDecoding:
    def test_export_with_empty_db_assignments_unchanged(self, minimal_mf4, tmp_path):
        """db_assignments=[] should behave identically to no decoding."""
        import export as exp
        mdf = _open(minimal_mf4)
        out = str(tmp_path / "out.csv")
        try:
            job_id   = exp.start(mdf, "csv", out, db_assignments=[])
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        assert progress["status"] == "done", progress.get("error")
        assert os.path.isfile(out)

    def test_export_with_decoding_completes_or_errors_cleanly(
        self, bus_raw_mf4, can_bus_dbc, tmp_path
    ):
        """
        Export with db_assignments should start and either complete or fail cleanly
        (no crash / hung thread) regardless of whether extract_bus_logging succeeds.
        """
        import export as exp
        mdf = _open(bus_raw_mf4)
        out = str(tmp_path / "decoded.csv")
        assignments = [{"group_index": 0, "db_path": can_bus_dbc}]
        try:
            job_id   = exp.start(mdf, "csv", out, db_assignments=assignments)
            progress = _wait_for_job(job_id)
        finally:
            mdf.close()
        # The job must reach a terminal state — not hang
        assert progress["status"] in ("done", "error"), (
            f"unexpected status: {progress['status']}"
        )
        # If it errored, the error must carry a meaningful message
        if progress["status"] == "error":
            assert progress["error"]


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
