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
        "start_time":       start_iso,
        "end_time":         end_iso,
        "duration_s":       duration_s,
        "num_channel_groups":         num_cg,
        "num_nonempty_channel_groups": num_cg_nonempty,
        "num_channels":               num_ch,
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
