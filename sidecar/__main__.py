"""
mf4u Python sidecar — JSON-RPC 2.0 over stdio.

Each request  : single JSON line on stdin.
Each response : single JSON line on stdout  (flush=True).
Progress notif: JSON line with no "id" field (future use).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

# Ensure sibling modules (metadata.py, stats.py, …) are importable when run
# as a plain script: python3 sidecar/__main__.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERSION = "0.1.0"

# Active MDF sessions  {session_id: {"mdf": MDF, "path": str}}
SESSIONS: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------- #
# JSON-RPC helpers
# --------------------------------------------------------------------------- #

def _ok(req: dict, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req["id"], "result": result}


def _err(req: dict, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": code, "message": message}}


def _session(req: dict) -> tuple[dict | None, dict | None]:
    """Return (session_dict, error_response). One of them is always None."""
    sid: str = req.get("params", {}).get("session_id", "")
    session = SESSIONS.get(sid)
    if session is None:
        return None, _err(req, 1002, f"session not found: {sid!r}")
    return session, None


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #

def handle_ping(req: dict) -> dict:
    return _ok(req, {"version": VERSION})


def handle_open_file(req: dict) -> dict:
    path: str = req.get("params", {}).get("path", "")
    if not path:
        return _err(req, 1001, "params.path is required")
    if not os.path.isfile(path):
        return _err(req, 1001, f"file not found: {path!r}")

    try:
        from asammdf import MDF  # type: ignore[import-untyped]
        import metadata as meta
    except ImportError as exc:
        return _err(req, 1001, f"import error — is asammdf installed? {exc}")

    try:
        mdf = MDF(path, memory="low")
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {"mdf": mdf, "path": path}
        md = meta.extract(mdf, path)
        return _ok(req, {"session_id": session_id, "metadata": md})
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1001, f"failed to open file: {exc}")


def _is_phy(ch: Any) -> bool:
    """
    Return True if *ch* carries a physical (calibrated) value, i.e. it has
    a non-empty unit string OR a non-trivial conversion rule.

    Trivial conversions:
      - None                              (raw = physical, identity)
      - CONVERSION_TYPE_NON  (0)          (explicit 1:1)
      - CONVERSION_TYPE_LIN  (1) a=1,b=0  (linear identity)
    Everything else counts as physical.
    """
    if str(getattr(ch, "unit", "") or "").strip():
        return True

    conv = getattr(ch, "conversion", None)
    if conv is None:
        return False

    ct = getattr(conv, "conversion_type", 0)
    if ct == 0:          # CONVERSION_TYPE_NON
        return False
    if ct == 1:          # CONVERSION_TYPE_LIN — identity only if a≈1, b≈0
        try:
            a = float(getattr(conv, "a", 1.0))
            b = float(getattr(conv, "b", 0.0))
            return not (abs(a - 1.0) < 1e-9 and abs(b) < 1e-9)
        except (TypeError, ValueError):
            return True  # can't parse coefficients — assume non-trivial
    return True  # RAT, ALG, TABI, TAB, RTAB, TABX, RTABX, TTAB, TRANS, BITFIELD …


def handle_get_structure(req: dict) -> dict:
    """Return the group→channel hierarchy (names + units, no samples loaded)."""
    session, err = _session(req)
    if err:
        return err

    try:
        from asammdf import MDF  # noqa: F401 (ensures asammdf is available)
    except ImportError as exc:
        return _err(req, 1001, f"asammdf not available: {exc}")

    mdf = session["mdf"]
    groups_out = []

    import metadata as _meta

    for i, group in enumerate(mdf.groups):
        cg = group.channel_group
        acq_name: str = str(getattr(cg, "acq_name", "") or "").strip() or f"Group {i}"

        bus_type   = _meta.group_bus_type(group)   # "CAN FD", "LIN", … or None
        is_bus_raw = bus_type is not None

        channels_out = []
        has_phy = False
        for ch in group.channels:
            name    = str(ch.name or "")
            unit    = str(ch.unit or "").strip()
            comment = str(ch.comment or "").strip() if ch.comment else ""
            phy     = (not is_bus_raw) and _is_phy(ch)
            if phy:
                has_phy = True
            channels_out.append({
                "name":    name,
                "unit":    unit,
                "comment": comment,
                "is_phy":  phy,
            })

        groups_out.append({
            "index":      i,
            "acq_name":   acq_name,
            "is_bus_raw": is_bus_raw,
            "bus_type":   bus_type,
            "has_phy":    has_phy,
            "channels":   channels_out,
        })

    return _ok(req, {"groups": groups_out})


def handle_get_signal_stats(req: dict) -> dict:
    """Compute min/max/mean/count for one channel (loads samples into memory)."""
    session, err = _session(req)
    if err:
        return err

    params      = req.get("params", {})
    group_index = params.get("group_index")
    channel_name = params.get("channel_name", "")

    if group_index is None or not channel_name:
        return _err(req, 1001, "params.group_index and params.channel_name are required")

    try:
        import stats as st
        result = st.channel_stats(session["mdf"], int(group_index), channel_name)
        return _ok(req, result)
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1003, f"stats error for {channel_name!r}: {exc}")


def handle_close_session(req: dict) -> dict:
    session_id: str = req.get("params", {}).get("session_id", "")
    session = SESSIONS.pop(session_id, None)
    if session:
        try:
            session["mdf"].close()
        except Exception:  # noqa: BLE001
            pass
    return _ok(req, {})


def handle_debug_bus_detection(req: dict) -> dict:
    """
    Return per-group raw detection data for troubleshooting bus frame detection.
    Call via the browser console: invoke('debug_bus_detection', {sessionId: id})
    """
    session, err = _session(req)
    if err:
        return err

    from asammdf.blocks import v4_constants as v4c  # type: ignore[import-untyped]

    mdf = session["mdf"]
    rows = []
    for i, group in enumerate(mdf.groups):
        cg       = group.channel_group
        ch_names = [str(ch.name or "") for ch in group.channels]

        flags    = int(getattr(cg, "flags", 0))
        src      = getattr(cg, "acq_source", None)
        bus_type = int(getattr(src, "bus_type", -1)) if src is not None else -1
        bus_str  = v4c.BUS_TYPE_TO_STRING.get(bus_type, f"?{bus_type}") if bus_type >= 0 else "no_src"

        rows.append({
            "group":    i,
            "flags":    hex(flags),
            "bus_event": bool(flags & 0x02),
            "bus_type": bus_type,
            "bus_str":  bus_str,
            "channels": ch_names,
        })

    return _ok(req, {"groups": rows})


def handle_start_export(req: dict) -> dict:
    session, err = _session(req)
    if err:
        return err

    params      = req.get("params", {})
    fmt         = params.get("format", "")
    output_path = params.get("output_path", "")

    if fmt not in ("mat", "tdms", "parquet"):
        return _err(req, 1001, "params.format must be 'mat', 'tdms', or 'parquet'")
    if not output_path:
        return _err(req, 1001, "params.output_path is required")

    try:
        import export as exp
        job_id = exp.start(session["mdf"], fmt, output_path)
        return _ok(req, {"job_id": job_id})
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1001, f"failed to start export: {exc}")


def handle_get_export_progress(req: dict) -> dict:
    job_id: str = req.get("params", {}).get("job_id", "")
    if not job_id:
        return _err(req, 1001, "params.job_id is required")
    try:
        import export as exp
        return _ok(req, exp.get_progress(job_id))
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1001, str(exc))


def handle_cancel_export(req: dict) -> dict:
    job_id: str = req.get("params", {}).get("job_id", "")
    if not job_id:
        return _err(req, 1001, "params.job_id is required")
    try:
        import export as exp
        exp.cancel(job_id)
        return _ok(req, {})
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1001, str(exc))


HANDLERS: dict[str, Any] = {
    "ping":                   handle_ping,
    "open_file":              handle_open_file,
    "get_structure":          handle_get_structure,
    "get_signal_stats":       handle_get_signal_stats,
    "close_session":          handle_close_session,
    "start_export":           handle_start_export,
    "get_export_progress":    handle_get_export_progress,
    "cancel_export":          handle_cancel_export,
    "debug_bus_detection":    handle_debug_bus_detection,
}


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        req: dict = {}
        try:
            req = json.loads(line)
            method = req.get("method", "")
            handler = HANDLERS.get(method)
            if handler is None:
                response = _err(req, -32601, f"method not found: {method!r}")
            else:
                response = handler(req)
        except json.JSONDecodeError as exc:
            response = _err(req, -32700, f"parse error: {exc}")
        except Exception as exc:  # noqa: BLE001
            response = _err(req, -32000, str(exc))
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
