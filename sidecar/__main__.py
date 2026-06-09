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
        if path.lower().endswith(".blf"):
            import blf as blf_mod  # noqa: PLC0415
            mdf = blf_mod.open_blf(path)
        else:
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
            "index":       i,
            "acq_name":    acq_name,
            "is_bus_raw":  is_bus_raw,
            "bus_type":    bus_type,
            "has_phy":     has_phy,
            "compression": _meta._group_compression_state(mdf, group),
            "cycles_nr":   int(getattr(cg, "cycles_nr", 0) or 0),
            "channels":    channels_out,
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


def handle_preview_bus_decoding(req: dict) -> dict:
    """Return per-(group, db) match counts without running a full decode."""
    session, err = _session(req)
    if err:
        return err

    params         = req.get("params", {})
    db_assignments = params.get("db_assignments", [])

    if not isinstance(db_assignments, list):
        return _err(req, 1001, "params.db_assignments must be a list")

    try:
        import export as exp
        previews = exp.preview_bus_decoding(session["mdf"], db_assignments)
        return _ok(req, {"previews": previews})
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1003, f"preview error: {exc}")


def handle_get_exportable_signals(req: dict) -> dict:
    """Return all exportable channels (physical + optionally decoded) for a session."""
    session, err = _session(req)
    if err:
        return err

    params         = req.get("params", {})
    db_assignments = params.get("db_assignments") or None

    try:
        import export as exp
        result = exp.get_exportable_signals(session["mdf"], db_assignments)
        return _ok(req, result)
    except Exception as exc:  # noqa: BLE001
        return _err(req, 1003, f"get_exportable_signals error: {exc}")


def handle_start_export(req: dict) -> dict:
    session, err = _session(req)
    if err:
        return err

    params               = req.get("params", {})
    fmt                  = params.get("format", "")
    output_path          = params.get("output_path", "")
    db_assignments       = params.get("db_assignments") or None  # None if absent/null/[]
    flatten              = bool(params.get("flatten") or False)
    mat_link_groups      = bool(params.get("mat_link_groups") or False)
    signal_filter        = params.get("signal_filter") or None   # None if absent/null/[]
    split_mode           = str(params.get("split_mode") or "none").strip()
    split_size_mb        = float(params.get("split_size_mb") or 100.0)
    split_period_s       = float(params.get("split_period_s") or 60.0)
    split_first_offset_s = float(params.get("split_first_offset_s") or 0.0)

    if fmt not in ("mat", "tdms", "parquet", "csv", "tsv", "xlsx", "mf4"):
        return _err(req, 1001,
                    "params.format must be 'mat', 'tdms', 'parquet', 'csv', 'tsv', 'xlsx', or 'mf4'")
    if not output_path:
        return _err(req, 1001, "params.output_path is required")

    try:
        import export as exp
        job_id = exp.start(
            session["mdf"], fmt, output_path,
            db_assignments=db_assignments, flatten=flatten,
            mat_link_groups=mat_link_groups, signal_filter=signal_filter,
            split_mode=split_mode, split_size_mb=split_size_mb,
            split_period_s=split_period_s, split_first_offset_s=split_first_offset_s,
            source_path=session.get("path", ""),
        )
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


def _to_relative(abs_path: str, base_dir: str) -> str:
    """Return *abs_path* as a path relative to *base_dir*.

    Falls back to the original path when ``os.path.relpath`` raises
    ``ValueError`` (e.g. paths on different Windows drives).
    Forward slashes are used as the separator so the result is readable on
    all platforms when embedded in a JSON file.
    """
    try:
        rel = os.path.relpath(abs_path, base_dir)
        return rel.replace("\\", "/")
    except ValueError:
        return abs_path.replace("\\", "/")


def _to_absolute(rel_or_abs: str, base_dir: str) -> str:
    """Return the absolute form of *rel_or_abs* resolved against *base_dir*.

    Absolute paths are returned unchanged (after normalisation).
    """
    if os.path.isabs(rel_or_abs):
        return os.path.normpath(rel_or_abs)
    return os.path.normpath(os.path.join(base_dir, rel_or_abs))


def _copy_dbc_to_dir(dbc_abs: str, dest_dir: str) -> str:
    """Copy *dbc_abs* into *dest_dir* and return the resulting filename.

    If the source file is already inside *dest_dir* no copy is made and the
    bare filename is returned.  Name collisions are resolved by appending
    ``_1``, ``_2``, … before the extension.  When the source file does not
    exist the function falls back to a plain relative path without copying.
    """
    import shutil

    if not os.path.isfile(dbc_abs):
        # Cannot copy a non-existent file — store a relative path instead.
        return _to_relative(dbc_abs, dest_dir)

    filename = os.path.basename(dbc_abs)
    dest     = os.path.join(dest_dir, filename)

    # Already the same file?
    try:
        if os.path.exists(dest) and os.path.samefile(dbc_abs, dest):
            return filename
    except (OSError, ValueError):
        pass

    # Resolve filename collision.
    if os.path.exists(dest):
        stem, ext = os.path.splitext(filename)
        i = 1
        while os.path.exists(os.path.join(dest_dir, f"{stem}_{i}{ext}")):
            i += 1
        filename = f"{stem}_{i}{ext}"
        dest = os.path.join(dest_dir, filename)

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(dbc_abs, dest)
    return filename


def handle_save_config(req: dict) -> dict:
    """Write an application config dict as formatted JSON to *params.path*.

    ``params.dbc_path_mode`` controls how DBC / ARXML paths are stored:

    ``"relative"`` (default)
        Paths relative to the config file's directory.  Portable when the
        config and DBC files are moved together.

    ``"absolute"``
        Full absolute paths.  Works only on the current machine with files
        in their present locations.

    ``"copy"``
        Each DBC file is copied into the same directory as the config file
        and referenced by its bare filename (a relative path).  The config
        folder becomes fully self-contained.  If the source file does not
        exist the path falls back to a relative reference without copying.

    The ``output_folder`` is always stored as a relative path (or absolute
    when on a different Windows drive than the config file).
    """
    import copy

    params        = req.get("params", {})
    file_path     = str(params.get("path", "")).strip()
    config        = params.get("config")
    dbc_path_mode = str(params.get("dbc_path_mode", "relative")).strip()
    if not file_path:
        return _err(req, 1010, "params.path is required")
    if dbc_path_mode not in ("absolute", "relative", "copy"):
        dbc_path_mode = "relative"

    config_dir = os.path.dirname(os.path.abspath(file_path))

    # Work on a deep copy so we never mutate the caller's object.
    cfg = copy.deepcopy(config) if config else {}

    # Apply the chosen DBC path strategy.
    for entry in cfg.get("decoding", []):
        raw = str(entry.get("db_path") or "").strip()
        if not raw:
            continue
        if dbc_path_mode == "absolute":
            entry["db_path"] = os.path.normpath(raw).replace("\\", "/")
        elif dbc_path_mode == "copy":
            entry["db_path"] = _copy_dbc_to_dir(raw, config_dir)
        else:  # "relative"
            entry["db_path"] = _to_relative(raw, config_dir)

    # output_folder is always relativised (portable by default).
    raw_folder = str(cfg.get("output_folder") or "").strip()
    if raw_folder:
        cfg["output_folder"] = _to_relative(raw_folder, config_dir)

    try:
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
        return _ok(req, {})
    except OSError as exc:
        return _err(req, 1011, f"Failed to write config: {exc}")


def handle_load_config(req: dict) -> dict:
    """Read a JSON config file from *params.path* and return its contents.

    Relative ``decoding[].db_path`` values and ``output_folder`` are resolved
    to absolute paths against the config file's directory before returning,
    so the rest of the application always works with absolute paths.
    """
    params    = req.get("params", {})
    file_path = str(params.get("path", "")).strip()
    if not file_path:
        return _err(req, 1010, "params.path is required")

    config_dir = os.path.dirname(os.path.abspath(file_path))

    try:
        with open(file_path, encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return _err(req, 1011, f"Failed to read config: {exc}")

    # Resolve relative DBC / ARXML paths back to absolute.
    for entry in config.get("decoding", []):
        raw = str(entry.get("db_path") or "").strip()
        if raw:
            entry["db_path"] = _to_absolute(raw, config_dir)

    # Resolve relative output folder back to absolute.
    raw_folder = str(config.get("output_folder") or "").strip()
    if raw_folder:
        config["output_folder"] = _to_absolute(raw_folder, config_dir)

    return _ok(req, {"config": config})


HANDLERS: dict[str, Any] = {
    "ping":                      handle_ping,
    "open_file":                 handle_open_file,
    "get_structure":             handle_get_structure,
    "get_signal_stats":          handle_get_signal_stats,
    "close_session":             handle_close_session,
    "start_export":              handle_start_export,
    "get_export_progress":       handle_get_export_progress,
    "cancel_export":             handle_cancel_export,
    "preview_bus_decoding":      handle_preview_bus_decoding,
    "get_exportable_signals":    handle_get_exportable_signals,
    "debug_bus_detection":       handle_debug_bus_detection,
    "save_config":               handle_save_config,
    "load_config":               handle_load_config,
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
