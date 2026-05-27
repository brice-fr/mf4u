"""
Tests for BLF file import (blf.open_blf) and end-to-end integration
with the existing metadata / stats / export / sidecar pipeline.

Fixture: can_bus.blf — 10 CAN frames on channel 1
  IDs 100 (EngineStatus) and 200 (VehicleStatus), same payloads as bus_raw.mf4
  so the can_bus.dbc decode tests can be shared across both formats.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

SIDECAR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SIDECAR_ROOT not in sys.path:
    sys.path.insert(0, SIDECAR_ROOT)

import blf as blf_mod
import metadata as meta
import stats as st
import export as exp


# --------------------------------------------------------------------------- #
# open_blf — core structure
# --------------------------------------------------------------------------- #

class TestOpenBlf:
    def test_returns_mdf_object(self, can_bus_blf):
        from asammdf import MDF
        mdf = blf_mod.open_blf(can_bus_blf)
        assert isinstance(mdf, MDF)
        mdf.close()

    def test_has_one_channel_group(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        # Fixture has only channel 1, no FD → exactly one group
        assert len(mdf.groups) == 1
        mdf.close()

    def test_group_has_ten_frames(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        grp = mdf.groups[0]
        # cycles_nr reflects how many records were appended
        cg = grp.channel_group
        assert int(getattr(cg, "cycles_nr", 0)) == 10
        mdf.close()

    def test_has_can_dataframe_channels(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        names = {ch.name for ch in mdf.groups[0].channels}
        for required in (
            "CAN_DataFrame",
            "CAN_DataFrame.ID",
            "CAN_DataFrame.BusChannel",
            "CAN_DataFrame.IDE",
            "CAN_DataFrame.DataBytes",
        ):
            assert required in names, f"missing channel: {required}"
        mdf.close()

    def test_bus_event_flag_set(self, can_bus_blf):
        import asammdf.blocks.v4_constants as v4c
        mdf = blf_mod.open_blf(can_bus_blf)
        cg = mdf.groups[0].channel_group
        assert int(cg.flags) & v4c.FLAG_CG_BUS_EVENT, "FLAG_CG_BUS_EVENT not set"
        mdf.close()

    def test_acq_source_bus_type_can(self, can_bus_blf):
        import asammdf.blocks.v4_constants as v4c
        mdf = blf_mod.open_blf(can_bus_blf)
        src = getattr(mdf.groups[0].channel_group, "acq_source", None)
        assert src is not None, "no acq_source on channel group"
        assert int(src.bus_type) == v4c.BUS_TYPE_CAN
        mdf.close()

    def test_start_time_set(self, can_bus_blf):
        from datetime import datetime, timezone
        mdf = blf_mod.open_blf(can_bus_blf)
        assert mdf.start_time is not None
        # Fixture was written with base time 2024-01-15T10:00:00Z
        assert mdf.start_time.year == 2024
        mdf.close()

    def test_can_ids_correct(self, can_bus_blf):
        import numpy as np
        mdf = blf_mod.open_blf(can_bus_blf)
        sig = mdf.get("CAN_DataFrame.ID", group=0, raw=True,
                      ignore_invalidation_bits=True)
        ids = set(sig.samples.tolist())
        assert 100 in ids
        assert 200 in ids
        mdf.close()

    def test_data_bytes_shape(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        sig = mdf.get("CAN_DataFrame.DataBytes", group=0, raw=True,
                      ignore_invalidation_bits=True)
        assert sig.samples.ndim == 2
        assert sig.samples.shape[1] == 8   # classic CAN, 8-byte rows
        mdf.close()

    def test_timestamps_are_relative(self, can_bus_blf):
        """The first timestamp must be 0.0 (or very close to it)."""
        mdf = blf_mod.open_blf(can_bus_blf)
        master = mdf.get_master(0)
        assert abs(float(master[0])) < 1e-6
        mdf.close()

    def test_empty_blf_returns_empty_mdf(self, tmp_path):
        import can
        empty_blf = str(tmp_path / "empty.blf")
        with can.BLFWriter(empty_blf):
            pass  # write nothing
        mdf = blf_mod.open_blf(empty_blf)
        assert len(mdf.groups) == 0
        mdf.close()

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="Failed to read BLF"):
            blf_mod.open_blf(str(tmp_path / "nonexistent.blf"))

    def test_multi_channel_creates_multiple_groups(self, tmp_path):
        import can
        blf_path = str(tmp_path / "multi_ch.blf")
        import time as _time
        t_base = _time.time()
        with can.BLFWriter(blf_path) as writer:
            writer(can.Message(arbitration_id=1, data=b"\x01", channel=1,
                               timestamp=t_base + 0.0))
            writer(can.Message(arbitration_id=2, data=b"\x02", channel=2,
                               timestamp=t_base + 0.01))
        mdf = blf_mod.open_blf(blf_path)
        assert len(mdf.groups) == 2
        mdf.close()

    def test_canfd_group_has_brs_edl(self, tmp_path):
        import can
        blf_path = str(tmp_path / "fd.blf")
        import time as _time
        t_base = _time.time()
        with can.BLFWriter(blf_path) as writer:
            writer(can.Message(arbitration_id=0x100,
                               data=bytes(range(12)),
                               is_fd=True,
                               bitrate_switch=True,
                               channel=1,
                               timestamp=t_base))
        mdf = blf_mod.open_blf(blf_path)
        assert len(mdf.groups) == 1
        names = {ch.name for ch in mdf.groups[0].channels}
        assert "CAN_DataFrame.BRS" in names
        assert "CAN_DataFrame.EDL" in names
        # FD DataBytes should be 64 columns wide
        sig = mdf.get("CAN_DataFrame.DataBytes", group=0, raw=True,
                      ignore_invalidation_bits=True)
        assert sig.samples.shape[1] == 64
        mdf.close()


# --------------------------------------------------------------------------- #
# metadata.extract — BLF-specific fields
# --------------------------------------------------------------------------- #

class TestBlfMetadata:
    def test_is_finalized_is_none(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["is_finalized"] is None
        mdf.close()

    def test_is_sorted_is_none(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["is_sorted"] is None
        mdf.close()

    def test_program_id_empty_for_blf(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        # BLF files do not have an MDF program_identification field
        assert md["program_id"] == ""
        mdf.close()

    def test_has_bus_frames_true(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["has_bus_frames"] is True
        assert "CAN" in md["bus_types"]
        mdf.close()

    def test_version_is_410(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["version"] == "4.10"
        mdf.close()

    def test_start_time_present(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["start_time"] is not None
        assert "2024" in md["start_time"]
        mdf.close()

    def test_num_channels_nonzero(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["num_channels"] > 0
        assert md["num_channel_groups"] == 1
        mdf.close()

    def test_file_name_and_size(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        md = meta.extract(mdf, can_bus_blf)
        assert md["file_name"].endswith(".blf")
        assert md["file_size"] > 0
        mdf.close()


# --------------------------------------------------------------------------- #
# signal stats
# --------------------------------------------------------------------------- #

class TestBlfStats:
    def test_id_stats(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        result = st.channel_stats(mdf, 0, "CAN_DataFrame.ID")
        assert result["samples"] == 10
        assert result["min"] == 100
        assert result["max"] == 200
        mdf.close()

    def test_bus_channel_stats(self, can_bus_blf):
        mdf = blf_mod.open_blf(can_bus_blf)
        result = st.channel_stats(mdf, 0, "CAN_DataFrame.BusChannel")
        assert result["samples"] == 10
        assert result["min"] == 1
        assert result["max"] == 1
        mdf.close()


# --------------------------------------------------------------------------- #
# DBC decoding (export.get_exportable_signals + extract_bus_logging)
# --------------------------------------------------------------------------- #

class TestBlfDecoding:
    def test_preview_bus_decoding_matches(self, can_bus_blf, can_bus_dbc):
        mdf = blf_mod.open_blf(can_bus_blf)
        previews = exp.preview_bus_decoding(
            mdf, [{"group_index": 0, "db_path": can_bus_dbc}]
        )
        assert len(previews) == 1
        p = previews[0]
        assert p["error"] is None
        assert p["matched_messages"] == 2   # EngineStatus + VehicleStatus
        assert p["signal_count"] >= 4       # ≥ 2 signals per message
        mdf.close()

    def test_get_exportable_signals_has_decoded_groups(self, can_bus_blf, can_bus_dbc):
        mdf = blf_mod.open_blf(can_bus_blf)
        result = exp.get_exportable_signals(
            mdf, [{"group_index": 0, "db_path": can_bus_dbc}]
        )
        sources = [g["source"] for g in result["groups"]]
        assert "decoded" in sources
        mdf.close()

    def test_decoded_signals_include_engine_speed(self, can_bus_blf, can_bus_dbc):
        mdf = blf_mod.open_blf(can_bus_blf)
        result = exp.get_exportable_signals(
            mdf, [{"group_index": 0, "db_path": can_bus_dbc}]
        )
        all_names = {
            ch["name"]
            for g in result["groups"]
            for ch in g["channels"]
        }
        assert "EngineSpeed"  in all_names
        assert "VehicleSpeed" in all_names
        mdf.close()


# --------------------------------------------------------------------------- #
# Export to various formats
# --------------------------------------------------------------------------- #

class TestBlfExport:
    def _wait(self, job_id: str, timeout: float = 10.0) -> dict:
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            p = exp.get_progress(job_id)
            if p["status"] in ("done", "error", "cancelled"):
                return p
            time.sleep(0.05)
        raise TimeoutError(f"export job {job_id} did not finish in {timeout}s")

    def test_export_csv(self, can_bus_blf, can_bus_dbc, tmp_path):
        mdf = blf_mod.open_blf(can_bus_blf)
        out = str(tmp_path / "out.csv")
        job_id = exp.start(
            mdf, "csv", out,
            db_assignments=[{"group_index": 0, "db_path": can_bus_dbc}],
        )
        result = self._wait(job_id)
        assert result["status"] == "done", result.get("error")
        # At least one CSV file should exist
        csvs = [f for f in os.listdir(tmp_path) if f.endswith(".csv")]
        assert csvs, "no CSV output files found"
        mdf.close()

    def test_export_mf4(self, can_bus_blf, can_bus_dbc, tmp_path):
        mdf = blf_mod.open_blf(can_bus_blf)
        out = str(tmp_path / "decoded.mf4")
        job_id = exp.start(
            mdf, "mf4", out,
            db_assignments=[{"group_index": 0, "db_path": can_bus_dbc}],
        )
        result = self._wait(job_id)
        assert result["status"] == "done", result.get("error")
        assert os.path.isfile(out)
        # Verify the re-exported MF4 opens and has decoded groups
        from asammdf import MDF
        with MDF(out) as decoded:
            names = {ch.name for g in decoded.groups for ch in g.channels}
            assert "EngineSpeed" in names
        mdf.close()

    def test_export_csv_no_dbc(self, can_bus_blf, tmp_path):
        """Raw bus groups should be skippable — export just returns nothing (no phy channels)."""
        mdf = blf_mod.open_blf(can_bus_blf)
        out = str(tmp_path / "raw.csv")
        job_id = exp.start(mdf, "csv", out)
        result = self._wait(job_id)
        # Status is done; output may be empty since all groups are bus-raw
        assert result["status"] == "done"
        mdf.close()


# --------------------------------------------------------------------------- #
# _normalize_channel helper
# --------------------------------------------------------------------------- #

class TestNormalizeChannel:
    def test_none_returns_1(self):
        assert blf_mod._normalize_channel(None) == 1

    def test_int_passthrough(self):
        assert blf_mod._normalize_channel(3) == 3

    def test_int_clamped_to_1(self):
        assert blf_mod._normalize_channel(0) == 1
        assert blf_mod._normalize_channel(-5) == 1

    def test_str_with_number(self):
        assert blf_mod._normalize_channel("CAN1") == 1
        assert blf_mod._normalize_channel("Channel_2") == 2
        assert blf_mod._normalize_channel("3") == 3

    def test_str_no_digits(self):
        assert blf_mod._normalize_channel("CAN") == 1

    def test_str_multiple_numbers_uses_all_digits(self):
        # "CAN12" → digits "12" → 12
        assert blf_mod._normalize_channel("CAN12") == 12
