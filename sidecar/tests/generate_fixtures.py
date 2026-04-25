#!/usr/bin/env python3
"""
Generate test fixture .mf4 files into tests/fixtures/.

Run once before running pytest:
    cd sidecar
    source .venv/bin/activate
    python tests/generate_fixtures.py

The three generated files are small (< 100 KB each) and should be
committed to the repository so CI can run pytest without this script.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import numpy as np

# Ensure the sidecar root is importable when run as a script from any cwd.
SIDECAR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SIDECAR_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(FIXTURES_DIR, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


# --------------------------------------------------------------------------- #
# 1. minimal.mf4
#    One channel group, three float channels, 100 samples.
#    Header comment is XML so we can test author/project extraction.
# --------------------------------------------------------------------------- #

def make_minimal() -> None:
    from asammdf import MDF, Signal  # type: ignore[import-untyped]

    mdf = MDF(version="4.10")
    mdf.start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    t = np.linspace(0.0, 1.0, 100, dtype=np.float64)
    mdf.append(
        [
            Signal(samples=np.sin(t),     timestamps=t, name="Ch1", unit="V",
                   comment="Sine voltage"),
            Signal(samples=np.cos(t),     timestamps=t, name="Ch2", unit="A",
                   comment="Cosine current"),
            Signal(samples=t * 2.0,       timestamps=t, name="Ch3", unit="rpm"),
        ],
        acq_name="main",
    )

    # Set a structured XML comment so _parse_hd_comment is exercised end-to-end.
    mdf.header.comment = (
        "<HDcomment>"
        "<TX>Unit test measurement</TX>"
        "<author>Test Author</author>"
        "<department>Test Department</department>"
        "<project>Test Project</project>"
        "<subject>Test Subject</subject>"
        "</HDcomment>"
    )

    dst = _path("minimal.mf4")
    mdf.save(dst, overwrite=True)
    mdf.close()
    print(f"  wrote {dst}  ({os.path.getsize(dst):,} bytes)")


# --------------------------------------------------------------------------- #
# 2. bus_raw.mf4
#    One channel group with a proper CAN bus-logging structure so that
#    asammdf's extract_bus_logging can decode it against can_bus.dbc.
#
#    Channel group flags: FLAG_CG_BUS_EVENT (0x02)
#    Acquisition source:  bus_type=BUS_TYPE_CAN (2)
#    Sub-channels:
#      CAN_DataFrame           — placeholder uint8 (required by detection logic)
#      CAN_DataFrame.ID        — uint32, alternates 100 / 200 (matches DBC)
#      CAN_DataFrame.BusChannel — uint8, all 1 (bus channel 1)
#      CAN_DataFrame.IDE       — uint8, all 0 (standard addressing)
#      CAN_DataFrame.DataBytes — uint8[N,8] with properly encoded signal values
#
#    Message 100 (EngineStatus, 8 B): EngineSpeed=1000 rpm, ThrottlePos=25 %
#      EngineSpeed  raw = 10000 (= 1000/0.1), LE uint16 → [0x10, 0x27]
#      ThrottlePos  raw = 65   (= (25+1)/0.4), uint8   → [0x41]
#      bytes: [0x10, 0x27, 0x41, 0x00, 0x00, 0x00, 0x00, 0x00]
#
#    Message 200 (VehicleStatus, 4 B): VehicleSpeed=80 km/h, Gear=3
#      VehicleSpeed raw = 1600 (= 80/0.05), LE uint16 → [0x40, 0x06]
#      Gear         raw = 3, uint8              → [0x03]
#      bytes: [0x40, 0x06, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00]
# --------------------------------------------------------------------------- #

def make_bus_raw() -> None:
    from asammdf import MDF, Signal  # type: ignore[import-untyped]
    from asammdf.blocks.source_utils import Source  # type: ignore[import-untyped]
    import asammdf.blocks.v4_constants as v4c  # type: ignore[import-untyped]

    mdf = MDF(version="4.10")
    mdf.start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    n = 10
    t = np.linspace(0.0, 0.09, n, dtype=np.float64)

    can_ids     = np.array([100, 200, 100, 200, 100, 200, 100, 200, 100, 200], dtype=np.uint32)
    bus_chans   = np.ones(n, dtype=np.uint8)
    ide_flags   = np.zeros(n, dtype=np.uint8)

    data_bytes = np.zeros((n, 8), dtype=np.uint8)
    data_bytes[0::2] = [0x10, 0x27, 0x41, 0x00, 0x00, 0x00, 0x00, 0x00]  # EngineStatus
    data_bytes[1::2] = [0x40, 0x06, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00]  # VehicleStatus

    acq_source = Source(
        name="CAN1", path="CAN1", comment="",
        source_type=v4c.SOURCE_BUS, bus_type=v4c.BUS_TYPE_CAN,
    )

    cg_nr = mdf.append(
        [
            Signal(samples=np.zeros(n, dtype=np.uint8), timestamps=t,
                   name="CAN_DataFrame",             unit=""),
            Signal(samples=can_ids,                   timestamps=t,
                   name="CAN_DataFrame.ID",           unit=""),
            Signal(samples=bus_chans,                 timestamps=t,
                   name="CAN_DataFrame.BusChannel",   unit=""),
            Signal(samples=ide_flags,                 timestamps=t,
                   name="CAN_DataFrame.IDE",          unit=""),
            Signal(samples=data_bytes,                timestamps=t,
                   name="CAN_DataFrame.DataBytes",    unit=""),
        ],
        acq_name="CAN_bus",
        acq_source=acq_source,
        comment="Synthetic CAN bus-logging fixture",
    )
    # Mark the channel group as a bus-event group so asammdf's
    # extract_bus_logging picks it up for decoding.
    mdf._mdf.groups[cg_nr].channel_group.flags |= v4c.FLAG_CG_BUS_EVENT

    mdf.header.comment = "Synthetic CAN bus-logging fixture"

    dst = _path("bus_raw.mf4")
    mdf.save(dst, overwrite=True)
    mdf.close()
    print(f"  wrote {dst}  ({os.path.getsize(dst):,} bytes)")


# --------------------------------------------------------------------------- #
# 3. multi_group.mf4
#    Four data groups with different signals and timestamps so each
#    group is stored as its own CG block.
#    Saved with compression=1 (deflate/zipped) to exercise the DZ
#    block detection path.
# --------------------------------------------------------------------------- #

def make_multi_group() -> None:
    from asammdf import MDF, Signal  # type: ignore[import-untyped]

    mdf = MDF(version="4.10")
    mdf.start_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    configs = [
        ("EngineSignals",  50,  1.0, [("EngineSpeed",  "rpm"), ("ThrottlePos", "%")]),
        ("VehicleSignals", 100, 2.0, [("VehicleSpeed", "km/h"), ("SteeringAngle", "deg")]),
        ("ThermalData",    25,  0.5, [("CoolantTemp",  "°C"), ("OilTemp", "°C")]),
        ("PowerSignals",   75,  3.0, [("BattVoltage",  "V"), ("BattCurrent", "A")]),
    ]

    for acq_name, n, duration, channels in configs:
        t = np.linspace(0.0, duration, n, dtype=np.float64)
        signals = [
            Signal(
                samples=np.random.default_rng(seed=i).standard_normal(n).astype(np.float32),
                timestamps=t,
                name=ch_name,
                unit=unit,
            )
            for i, (ch_name, unit) in enumerate(channels)
        ]
        mdf.append(signals, acq_name=acq_name)

    mdf.header.comment = "Synthetic multi-group fixture with 4 channel groups"

    dst = _path("multi_group.mf4")
    # compression=1 → deflate (##DZ blocks, zip_type=0 → "zipped")
    mdf.save(dst, overwrite=True, compression=1)
    mdf.close()
    print(f"  wrote {dst}  ({os.path.getsize(dst):,} bytes)")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("Generating MF4 test fixtures …")
    make_minimal()
    make_bus_raw()
    make_multi_group()
    print("Done.")
