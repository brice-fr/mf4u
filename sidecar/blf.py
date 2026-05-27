"""
BLF (Binary Logging Format) → in-memory MDF4 converter.

Uses python-can's BLFReader to read the file frame by frame, then builds
a proper asammdf MDF4 object with bus-raw channel groups — one per
(bus-channel, frame-type) pair.  The returned object has the same structure
as a native CAN bus logging .mf4 file, so all downstream operations
(get_structure, get_signal_stats, extract_bus_logging, export) work without
modification.

Supported object types
----------------------
- CAN classic frames          → CAN_DataFrame group(s)
- CAN FD frames               → CAN_DataFrame group(s) with BRS / EDL sub-channels
- Remote frames               → included (Dir flag = 2 = Tx-Request by convention)
- Error frames                → silently skipped (no payload to decode)
- Non-CAN objects (LIN, …)   → silently skipped (future extension)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Maximum payload widths stored in DataBytes per frame type.
_CAN_BYTES   = 8   # classic CAN: max 8 data bytes
_CANFD_BYTES = 64  # CAN FD:      max 64 data bytes

# Dir field values (same convention as asammdf uses for native MF4 logging)
_DIR_RX = 0
_DIR_TX = 1


def open_blf(path: str) -> Any:
    """
    Open a BLF file and return an asammdf MDF4 object with bus-raw groups.

    Each (bus-channel, frame-type) pair in the file becomes one MDF4 channel
    group.  Every group is structured as a proper bus-event group:

      CAN_DataFrame             uint8     placeholder — required for group detection
      CAN_DataFrame.ID          uint32    29-bit CAN arbitration ID
      CAN_DataFrame.BusChannel  uint8     bus channel number
      CAN_DataFrame.IDE         uint8     1 = extended (29-bit) ID, 0 = standard
      CAN_DataFrame.Dir         uint8     0 = Rx, 1 = Tx, 2 = Tx-Request (remote)
      CAN_DataFrame.DLC         uint8     data length code (byte count in python-can)
      CAN_DataFrame.DataBytes   uint8[N, 8|64]  payload, zero-padded to column width

    CAN FD groups additionally carry:

      CAN_DataFrame.BRS         uint8     1 = bit-rate switch active
      CAN_DataFrame.EDL         uint8     1 = extended data length (always 1 for FD)

    Parameters
    ----------
    path:
        Absolute path to the .blf file.

    Returns
    -------
    asammdf.MDF
        In-memory MDF4 object ready for get_structure / extract_bus_logging /
        export, etc.

    Raises
    ------
    ImportError
        If python-can is not installed.
    RuntimeError
        On read or conversion errors.
    """
    try:
        from can.io import BLFReader  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "python-can is required to open BLF files. "
            "Install it with:  pip install python-can"
        ) from exc

    from asammdf import MDF, Signal  # type: ignore[import-untyped]
    from asammdf.blocks.source_utils import Source  # type: ignore[import-untyped]
    import asammdf.blocks.v4_constants as v4c  # type: ignore[import-untyped]
    import numpy as np

    # ── pass 1: read all frames grouped by (channel_int, is_fd) ─────────────
    # Each group is a list of python-can Message objects.
    frame_groups: dict[tuple[int, bool], list[Any]] = {}
    blf_start: float | None = None

    try:
        with BLFReader(path) as reader:
            blf_start = getattr(reader, "start_timestamp", None)
            for msg in reader:
                if msg.is_error_frame:
                    continue  # no usable payload — skip
                ch  = _normalize_channel(msg.channel)
                key = (ch, bool(msg.is_fd))
                if key not in frame_groups:
                    frame_groups[key] = []
                frame_groups[key].append(msg)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to read BLF file {path!r}: {exc}") from exc

    # ── determine recording start time and relative-t0 ───────────────────────
    all_msgs = [m for msgs in frame_groups.values() for m in msgs]
    t0 = min((m.timestamp for m in all_msgs), default=0.0)

    if blf_start is not None:
        start_dt = datetime.fromtimestamp(blf_start, tz=timezone.utc)
    elif all_msgs:
        start_dt = datetime.fromtimestamp(t0, tz=timezone.utc)
    else:
        start_dt = datetime.now(tz=timezone.utc)

    # ── build in-memory MDF4 ─────────────────────────────────────────────────
    mdf = MDF(version="4.10")
    mdf.start_time = start_dt

    if not frame_groups:
        return mdf  # empty file

    for (ch_num, is_fd), msgs in sorted(frame_groups.items()):
        n         = len(msgs)
        max_bytes = _CANFD_BYTES if is_fd else _CAN_BYTES

        timestamps   = np.array([m.timestamp - t0 for m in msgs], dtype=np.float64)
        ids          = np.array([m.arbitration_id  for m in msgs], dtype=np.uint32)
        bus_channels = np.full(n, ch_num, dtype=np.uint8)
        ide_flags    = np.array([int(m.is_extended_id)   for m in msgs], dtype=np.uint8)
        dir_flags    = np.array([_dir_flag(m)            for m in msgs], dtype=np.uint8)
        dlc_arr      = np.array([m.dlc                   for m in msgs], dtype=np.uint8)

        # DataBytes: copy each frame's payload into its row, zero-pad the rest.
        data_bytes = np.zeros((n, max_bytes), dtype=np.uint8)
        for i, msg in enumerate(msgs):
            raw = bytes(msg.data)
            data_bytes[i, : len(raw)] = list(raw)

        acq_source = Source(
            name    = f"CAN{ch_num}",
            path    = f"CAN{ch_num}",
            comment = "",
            source_type = v4c.SOURCE_BUS,
            bus_type    = v4c.BUS_TYPE_CAN,
        )
        acq_name = f"CAN{ch_num}{'_FD' if is_fd else ''}"

        signals: list[Any] = [
            Signal(samples=np.zeros(n, dtype=np.uint8), timestamps=timestamps,
                   name="CAN_DataFrame",           unit=""),
            Signal(samples=ids,                     timestamps=timestamps,
                   name="CAN_DataFrame.ID",         unit=""),
            Signal(samples=bus_channels,            timestamps=timestamps,
                   name="CAN_DataFrame.BusChannel", unit=""),
            Signal(samples=ide_flags,               timestamps=timestamps,
                   name="CAN_DataFrame.IDE",        unit=""),
            Signal(samples=dir_flags,               timestamps=timestamps,
                   name="CAN_DataFrame.Dir",        unit=""),
            Signal(samples=dlc_arr,                 timestamps=timestamps,
                   name="CAN_DataFrame.DLC",        unit=""),
            Signal(samples=data_bytes,              timestamps=timestamps,
                   name="CAN_DataFrame.DataBytes",  unit=""),
        ]

        if is_fd:
            brs_arr = np.array(
                [int(getattr(m, "bitrate_switch", False)) for m in msgs],
                dtype=np.uint8,
            )
            edl_arr = np.ones(n, dtype=np.uint8)  # all FD frames have EDL set
            signals += [
                Signal(samples=brs_arr, timestamps=timestamps,
                       name="CAN_DataFrame.BRS", unit=""),
                Signal(samples=edl_arr, timestamps=timestamps,
                       name="CAN_DataFrame.EDL", unit=""),
            ]

        cg_nr = mdf.append(
            signals,
            acq_name   = acq_name,
            acq_source = acq_source,
            comment    = f"BLF import — {'CAN FD' if is_fd else 'CAN'} bus channel {ch_num}",
        )
        # Mark the group as a bus-event group so asammdf's extract_bus_logging
        # picks it up for DBC decoding.
        mdf._mdf.groups[cg_nr].channel_group.flags |= v4c.FLAG_CG_BUS_EVENT

    return mdf


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _normalize_channel(raw: Any) -> int:
    """Convert a python-can channel value to a positive integer (≥ 1).

    python-can tools produce various channel representations:
      int   → use directly (clamp to ≥ 1)
      None  → default to 1
      str   → extract trailing digits ("CAN1" → 1, "Channel_2" → 2, "1" → 1)
              if no digits found, default to 1
    """
    if raw is None:
        return 1
    if isinstance(raw, int):
        return max(1, raw)
    s      = str(raw).strip()
    digits = "".join(c for c in s if c.isdigit())
    return int(digits) if digits else 1


def _dir_flag(msg: Any) -> int:
    """Return the MDF4 Dir flag for a python-can Message."""
    if getattr(msg, "is_remote_frame", False):
        return 2   # Tx-Request
    if getattr(msg, "is_rx", None) is False:
        return _DIR_TX
    return _DIR_RX   # BLF Rx frames (most common; BLF doesn't always set is_rx)
