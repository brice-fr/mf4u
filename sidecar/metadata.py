"""
MDF file metadata extraction via asammdf.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Any


# --------------------------------------------------------------------------- #
# Bus-frame channel names per bus type (MDF 4.x bus logging convention)
# --------------------------------------------------------------------------- #
_BUS_CHANNEL_MAP: dict[str, set[str]] = {
    "CAN":      {"CAN_DataFrame", "CAN_RemoteFrame", "CAN_ErrorFrame",
                 "CAN_DataFrame_Raw"},
    # CAN FD shares CAN_DataFrame with plain CAN.  The FD-specific sub-signals
    # CAN_DataFrame.BRS (Bit Rate Switch) and CAN_DataFrame.EDL (Extended Data
    # Length) are only present in CAN FD groups — asammdf uses these names in
    # its own bus-analysis code (mdf.py lines 6483-6486).
    "CAN FD":   {"CAN_DataFrame.BRS", "CAN_DataFrame.EDL"},
    "LIN":      {"LIN_Frame", "LIN_SyncError", "LIN_ReceiveError",
                 "LIN_WakeUp", "LIN_Checksum_Error"},
    "FlexRay":  {"FlexRay_Frame", "FlexRay_RxError", "FlexRay_TxError",
                 "FlexRay_PDU"},
    "Ethernet": {"Ethernet_Frame", "Ethernet_RxError", "Ethernet_TxError"},
    "MOST":     {"MOST_Frame"},
}

# acq_source.bus_type integer → label
# Values from asammdf v4_constants.py (BUS_TYPE_* constants).
# NOTE: asammdf uses BUS_TYPE_CAN (2) for *both* CAN and CAN FD; there is no
# separate constant for CAN FD.  CAN FD is detected via channel names above.
_SRC_BUS_TYPE: dict[int, str] = {
    2: "CAN",       # BUS_TYPE_CAN     (also covers CAN FD — see detection below)
    3: "LIN",       # BUS_TYPE_LIN
    4: "MOST",      # BUS_TYPE_MOST
    5: "FlexRay",   # BUS_TYPE_FLEXRAY
    6: "K-Line",    # BUS_TYPE_K_LINE
    7: "Ethernet",  # BUS_TYPE_ETHERNET
    8: "USB",       # BUS_TYPE_USB
}


def extract(mdf_obj: Any, file_path: str) -> dict[str, Any]:
    """Return a flat metadata dict for *mdf_obj* (an open asammdf.MDF instance)."""
    groups = mdf_obj.groups

    # ── finalization state ────────────────────────────────────────────────── #
    # Read the raw identification block from the ORIGINAL file on disk.
    # asammdf never modifies the original file; unfinalized files are copied to
    # a temp location before in-memory finalization, so this read is always safe
    # and reflects the true on-disk state.
    is_finalized, unfinalized_flags = _read_finalization(file_path)

    # ── timing ──────────────────────────────────────────────────────────── #
    start_dt = mdf_obj.start_time          # datetime | None
    start_iso = start_dt.isoformat() if start_dt else None
    duration_s, end_iso = _duration(mdf_obj, start_dt)

    # ── structure ────────────────────────────────────────────────────────── #
    num_cg          = len(groups)
    num_cg_nonempty = sum(1 for g in groups if len(g.channels) > 0)
    num_ch          = sum(len(g.channels) for g in groups)

    # ── bus frames ───────────────────────────────────────────────────────── #
    has_bus, bus_types, bus_frame_counts = _detect_bus_frames(groups)

    # ── header comment + HD text fields ─────────────────────────────────── #
    raw_comment = ""
    if mdf_obj.header and mdf_obj.header.comment:
        raw_comment = str(mdf_obj.header.comment).strip()
    hd = _parse_hd_comment(raw_comment)

    # ── sort state ───────────────────────────────────────────────────────── #
    # record_id_len == 0 means sorted (one CG per DG, records contiguous).
    # Non-zero (1, 2, 4, 8 bytes) means unsorted / interleaved.
    # asammdf's _sort() reads this field but never resets it, so it always
    # reflects the true on-disk value even after the in-memory sort runs.
    is_sorted = all(
        getattr(getattr(g, "data_group", None), "record_id_len", 0) == 0
        for g in groups
    )

    # ── per-DG compression state ─────────────────────────────────────────── #
    dg_compression = [_group_compression_state(mdf_obj, g) for g in groups]

    # ── attachments ──────────────────────────────────────────────────────── #
    attachments: list[str] = []
    try:
        for at in mdf_obj.attachments:
            name = (
                getattr(at, "file_name", None)
                or getattr(at, "name", None)
                or ""
            )
            if name:
                attachments.append(str(name))
    except Exception:  # noqa: BLE001
        pass

    return {
        "file_name":        os.path.basename(file_path),
        "file_size":        os.path.getsize(file_path),
        "version":          mdf_obj.version,
        "is_finalized":     is_finalized,
        "unfinalized_flags": unfinalized_flags,
        "start_time":       start_iso,
        "end_time":         end_iso,
        "duration_s":       duration_s,
        "num_channel_groups":         num_cg,
        "num_nonempty_channel_groups": num_cg_nonempty,
        "num_channels":               num_ch,
        "is_sorted":          is_sorted,
        "has_bus_frames":     has_bus,
        "bus_types":          bus_types,
        "bus_frame_counts":   bus_frame_counts,  # {type: group_count}
        "comment":          hd["comment"],
        "author":           hd["author"],
        "department":       hd["department"],
        "project":          hd["project"],
        "subject":          hd["subject"],
        "dg_compression":   dg_compression,
        "attachments":      attachments,
    }


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _read_finalization(file_path: str) -> tuple[bool, int]:
    """Read the MDF identification block directly from *file_path* and return
    ``(is_finalized, unfinalized_standard_flags)``.

    The identification block is the first 64 bytes of every MDF file (same
    layout for MDF 2, 3 and 4):

      • bytes  0– 7: ``file_identification``
                       Finalized  → bytes that .strip() to b"MDF"
                       Unfinalized → bytes that .strip() to b"UnFinMF"
                     Real-world tools use various trailing-pad characters (spaces,
                     nulls, tabs), so we always compare the stripped form.
      • bytes  8–15: ``version_str`` (e.g. b"4.10    " or b"3.30    ")
      • bytes 60–61: ``unfinalized_standard_flags`` (uint16 LE)
                     Only meaningful for MDF 4.x — in MDF 2/3 these bytes
                     may hold unrelated data and must be ignored.

    Rule:
      A file is *unfinalized* when at least one of the following holds:
        1. ``file_identification.strip() == b"UnFinMF"``   (explicit marker)
        2. The file is MDF 4.x AND ``unfinalized_standard_flags != 0``

    asammdf **never** modifies the original file; when it opens an unfinalized
    MDF 4.10+ file it copies it to a temp directory and finalises only the copy.
    Reading from *file_path* therefore always reflects the true on-disk state.

    On any read error or truncated file returns ``(True, 0)`` — treat unknown
    as finalized so the UI stays clean.
    """
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read(64)
        if len(raw) < 64:
            return True, 0

        file_id     = raw[:8]
        version_str = raw[8:16]
        unfin_flags = int.from_bytes(raw[60:62], "little")

        # Strip trailing whitespace chars (space, tab, CR, LF …) to normalise
        # across the many padding styles used by different logger tools.
        # Note: bytes.strip() does NOT remove null bytes, so tools that use
        # null-padding are handled correctly as long as asammdf accepts them
        # (asammdf applies the same strip() check and rejects null-padded files).
        file_id_stripped = file_id.strip()

        # Rule 1: explicitly marked unfinalized
        if file_id_stripped == b"UnFinMF":
            return False, unfin_flags

        # Rule 2: MDF 4.x with pending work items
        is_mdf4 = version_str.startswith(b"4")
        if is_mdf4 and unfin_flags != 0:
            return False, unfin_flags

        return True, 0

    except OSError:
        return True, 0


def _parse_hd_comment(raw: str) -> dict[str, str]:
    """
    Parse an MDF4 HD block comment that may be plain text or XML.

    Plain-text comments (MDF3-style TX blocks or simple strings) are returned
    as-is in the "comment" key.  XML HD comments (HDcomment MD block) are split
    into their constituent fields:
      <TX>         → comment
      <author>     → author
      <department> → department
      <project>    → project
      <subject>    → subject
    """
    out: dict[str, str] = {
        "comment": "", "author": "", "department": "", "project": "", "subject": "",
    }
    if not raw:
        return out

    stripped = raw.strip()
    if not stripped.startswith("<"):
        # Plain text — no XML to parse.
        out["comment"] = stripped
        return out

    try:
        root = ET.fromstring(stripped)

        # Comment text: prefer <TX> (MDF4 spec), fall back to root text, then
        # any child element text — so real-world files that omit <TX> still work.
        tx = root.find("TX")
        if tx is None:
            tx = root.find(".//TX")
        if tx is not None and (tx.text or "").strip():
            out["comment"] = tx.text.strip()
        elif (root.text or "").strip():
            out["comment"] = root.text.strip()
        else:
            # Last resort: concatenate all direct child text nodes
            parts = [
                (el.text or "").strip()
                for el in root
                if el.tag not in ("author", "department", "project", "subject")
                and (el.text or "").strip()
            ]
            out["comment"] = " ".join(parts)

        for tag in ("author", "department", "project", "subject"):
            # Format 1: direct child element  <author>value</author>
            el = root.find(tag)
            if el is None:
                el = root.find(f".//{tag}")
            if el is not None and (el.text or "").strip():
                out[tag] = el.text.strip()
                continue
            # Format 2: ETAS INCA / MDF4 common_properties
            #   <common_properties><e name="author">value</e></common_properties>
            for e in root.findall(".//e"):
                if e.get("name") == tag and (e.text or "").strip():
                    out[tag] = e.text.strip()
                    break
    except ET.ParseError:
        # If we can't parse it as XML, treat the whole string as the comment.
        out["comment"] = stripped

    return out


def _group_compression_state(mdf_obj: Any, group: Any) -> str:
    """
    Determine the compression state of a data group.

    Reads the ``block_type`` field from the first ``DataBlockInfo`` entry on
    ``group.data_blocks`` — an asammdf-internal list that is always populated
    after the file is opened, regardless of the ``memory`` mode.

    asammdf block_type values (from ``v4_constants``):
      DT_BLOCK            = 0  → "uncompressed"
      DZ_BLOCK_DEFLATE    = 1  → "zipped"
      DZ_BLOCK_TRANSPOSED = 2  → "transposed-zipped"
      DZ_BLOCK_LZ         = 3  → "zipped"
      DZ_BLOCK_LZ_TRANSPOSED = 4  → "transposed-zipped"
      DZ_BLOCK_ZSTD       = 5  → "zipped"
      DZ_BLOCK_ZSTD_TRANSPOSED = 6  → "transposed-zipped"
    """
    try:
        blocks = getattr(group, "data_blocks", None)
        if not blocks:
            return "uncompressed"   # no data blocks → effectively empty/uncompressed
        block_type = getattr(blocks[0], "block_type", 0)
        if block_type == 0:
            return "uncompressed"
        if block_type in (2, 4, 6):
            return "transposed-zipped"
        if block_type in (1, 3, 5):
            return "zipped"
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _duration(
    mdf_obj: Any, start_dt: Any
) -> tuple[float | None, str | None]:
    """Scan master (time) channels to find the recording end time."""
    max_t: float | None = None
    for i in range(len(mdf_obj.groups)):
        try:
            master = mdf_obj.get_master(i)
            if master is not None and len(master) > 0:
                t = float(master[-1])
                if max_t is None or t > max_t:
                    max_t = t
        except Exception:  # noqa: BLE001
            continue

    if max_t is None:
        return None, None

    end_iso = None
    if start_dt is not None:
        end_iso = (start_dt + timedelta(seconds=max_t)).isoformat()

    return max_t, end_iso


def group_bus_type(group: Any) -> str | None:
    """
    Return the bus type label for a single channel group, or None.

    Combines two methods (same logic as the file-level _detect_bus_frames):
    - Method 1 (channel names): CAN FD detected via CAN_DataFrame.BRS/EDL.
    - Method 2 (acq_source.bus_type): authoritative for non-CAN types.
    """
    detected: set[str] = set()

    cg_names = {ch.name for ch in group.channels}
    for bus_label, bus_ch_names in _BUS_CHANNEL_MAP.items():
        if cg_names & bus_ch_names:
            detected.add(bus_label)

    cg = group.channel_group
    if hasattr(cg, "flags") and (cg.flags & 0x02):
        src = getattr(cg, "acq_source", None)
        if src is not None:
            bt    = getattr(src, "bus_type", 0)
            label = _SRC_BUS_TYPE.get(bt)
            if label:
                if label == "CAN":
                    if "CAN FD" not in detected:
                        detected.add("CAN")
                else:
                    detected.discard("CAN")
                    detected.discard("CAN FD")
                    detected.add(label)

    if "CAN FD" in detected:
        detected.discard("CAN")

    if not detected:
        return None
    return sorted(detected)[0]  # stable: return first label alphabetically


def _detect_bus_frames(
    groups: list[Any],
) -> tuple[bool, list[str], dict[str, int]]:
    """Return (has_bus_frames, sorted_type_list, {bus_type: group_count})."""
    counts: dict[str, int] = {}
    for grp in groups:
        bt = group_bus_type(grp)
        if bt is not None:
            counts[bt] = counts.get(bt, 0) + 1
    return bool(counts), sorted(counts), counts
