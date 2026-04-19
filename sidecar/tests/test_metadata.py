"""
Tests for sidecar/metadata.py — extraction of file-level metadata.
"""
from __future__ import annotations

import os

import pytest


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _open(path: str):
    from asammdf import MDF  # type: ignore[import-untyped]
    return MDF(path, memory="low")


def _extract(path: str) -> dict:
    import metadata as meta
    mdf = _open(path)
    try:
        return meta.extract(mdf, path)
    finally:
        mdf.close()


# --------------------------------------------------------------------------- #
# Unit tests for _parse_hd_comment — no fixture file required
# --------------------------------------------------------------------------- #

class TestParseHdComment:
    def test_plain_text(self):
        import metadata as meta
        result = meta._parse_hd_comment("Hello world")
        assert result["comment"] == "Hello world"
        assert result["author"] == ""
        assert result["project"] == ""

    def test_empty_string(self):
        import metadata as meta
        result = meta._parse_hd_comment("")
        assert all(v == "" for v in result.values())

    def test_xml_tx_only(self):
        import metadata as meta
        xml = "<HDcomment><TX>My comment</TX></HDcomment>"
        result = meta._parse_hd_comment(xml)
        assert result["comment"] == "My comment"
        assert result["author"] == ""

    def test_xml_all_fields(self):
        import metadata as meta
        xml = (
            "<HDcomment>"
            "<TX>Test measurement</TX>"
            "<author>Jane Doe</author>"
            "<department>Engineering</department>"
            "<project>Vehicle X</project>"
            "<subject>Cold start</subject>"
            "</HDcomment>"
        )
        result = meta._parse_hd_comment(xml)
        assert result["comment"] == "Test measurement"
        assert result["author"] == "Jane Doe"
        assert result["department"] == "Engineering"
        assert result["project"] == "Vehicle X"
        assert result["subject"] == "Cold start"

    def test_xml_partial_fields(self):
        import metadata as meta
        xml = "<HDcomment><TX>Notes</TX><author>Bob</author></HDcomment>"
        result = meta._parse_hd_comment(xml)
        assert result["comment"] == "Notes"
        assert result["author"] == "Bob"
        assert result["project"] == ""

    def test_malformed_xml_falls_back_to_raw(self):
        import metadata as meta
        bad = "<HDcomment><TX>Unclosed"
        result = meta._parse_hd_comment(bad)
        # Should not raise; raw string used as comment fallback
        assert result["comment"] == bad

    def test_common_properties_format(self):
        """ETAS INCA stores fields as <common_properties><e name="author">…</e>."""
        import metadata as meta
        xml = (
            "<HDcomment>"
            "<TX>Measurement comment</TX>"
            "<common_properties>"
            '<e name="subject">TestVehicle</e>'
            '<e name="project">ProjectX</e>'
            '<e name="department">Engineering</e>'
            '<e name="author">Alice</e>'
            "</common_properties>"
            "</HDcomment>"
        )
        result = meta._parse_hd_comment(xml)
        assert result["comment"] == "Measurement comment"
        assert result["author"] == "Alice"
        assert result["department"] == "Engineering"
        assert result["project"] == "ProjectX"
        assert result["subject"] == "TestVehicle"

    def test_root_text_fallback(self):
        """Files that omit <TX> but put text directly in the root element."""
        import metadata as meta
        xml = "<SomeToolComment>direct root text</SomeToolComment>"
        result = meta._parse_hd_comment(xml)
        assert result["comment"] == "direct root text"


# --------------------------------------------------------------------------- #
# Integration tests against fixture files
# --------------------------------------------------------------------------- #

class TestMinimalMf4:
    def test_file_fields(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["file_name"] == "minimal.mf4"
        assert md["file_size"] == os.path.getsize(minimal_mf4)
        assert md["version"].startswith("4.")

    def test_timing(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["start_time"] is not None
        assert md["duration_s"] is not None
        assert md["duration_s"] == pytest.approx(1.0, abs=0.1)

    def test_structure(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["num_channel_groups"] >= 1
        assert md["num_nonempty_channel_groups"] >= 1
        # 3 signals + t master channel per group
        assert md["num_channels"] >= 3

    def test_no_bus_frames(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["has_bus_frames"] is False
        assert md["bus_types"] == []

    def test_comment_extracted(self, minimal_mf4):
        md = _extract(minimal_mf4)
        # generate_fixtures sets an XML comment with <TX>Unit test measurement</TX>
        assert "Unit test measurement" in md["comment"]

    def test_hd_text_fields(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["author"] == "Test Author"
        assert md["department"] == "Test Department"
        assert md["project"] == "Test Project"
        assert md["subject"] == "Test Subject"

    def test_dg_compression_list_length(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert isinstance(md["dg_compression"], list)
        assert len(md["dg_compression"]) == md["num_channel_groups"]

    def test_dg_compression_values_valid(self, minimal_mf4):
        md = _extract(minimal_mf4)
        valid = {"uncompressed", "zipped", "transposed-zipped", "unknown"}
        for state in md["dg_compression"]:
            assert state in valid

    def test_no_attachments(self, minimal_mf4):
        md = _extract(minimal_mf4)
        assert md["attachments"] == []


class TestBusRawMf4:
    def test_bus_detection(self, bus_raw_mf4):
        md = _extract(bus_raw_mf4)
        assert md["has_bus_frames"] is True
        assert "CAN" in md["bus_types"] or "CAN FD" in md["bus_types"]

    def test_bus_frame_counts_positive(self, bus_raw_mf4):
        md = _extract(bus_raw_mf4)
        assert sum(md["bus_frame_counts"].values()) >= 1


class TestMultiGroupMf4:
    def test_four_groups(self, multi_group_mf4):
        md = _extract(multi_group_mf4)
        assert md["num_channel_groups"] == 4

    def test_dg_compression_all_zipped(self, multi_group_mf4):
        md = _extract(multi_group_mf4)
        # Saved with compression=1 → all groups should be "zipped" or "unknown"
        # (asammdf may skip compression for very small groups)
        for state in md["dg_compression"]:
            assert state in ("zipped", "transposed-zipped", "uncompressed", "unknown")
        # At least one group should be identified as compressed
        compressed = [s for s in md["dg_compression"] if s in ("zipped", "transposed-zipped")]
        assert len(compressed) > 0, (
            f"Expected at least one compressed group; got {md['dg_compression']}"
        )

    def test_structure_counts(self, multi_group_mf4):
        md = _extract(multi_group_mf4)
        # 4 groups × 2 channels each (+ master channels)
        assert md["num_channels"] >= 8
