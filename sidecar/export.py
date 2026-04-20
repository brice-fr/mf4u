"""
Export jobs: MDF → .mat / .tdms / .parquet / .csv / .tsv / .xlsx.

Jobs run in background daemon threads.  Callers poll progress via
get_progress() and may request cancellation via cancel().
"""
from __future__ import annotations

import os
import re
import threading
import uuid
from typing import Any


# --------------------------------------------------------------------------- #
# Job state
# --------------------------------------------------------------------------- #

class _Job:
    __slots__ = ("total", "done", "status", "error", "_cancel", "_cleanup")

    def __init__(self, total: int) -> None:
        self.total    = total
        self.done     = 0
        self.status   = "running"         # running | done | error | cancelled
        self.error: str | None = None
        self._cancel  = threading.Event()
        self._cleanup: list[str] = []     # files to remove on cancel / error

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def request_cancel(self) -> None:
        self._cancel.set()


_JOBS: dict[str, _Job] = {}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def start(
    mdf: Any,
    fmt: str,
    output_path: str,
    db_assignments: "list[dict] | None" = None,
    flatten: bool = False,
    mat_link_groups: bool = False,
) -> str:
    """Start an export job in a background thread; return its job_id.

    If *db_assignments* is provided (a list of ``{"group_index": int, "db_path": str}``
    dicts in priority order), ``extract_bus_logging`` is applied before writing.

    If *flatten* is ``True`` and the format supports it (MAT / Parquet / CSV / TSV /
    XLSX), all channel groups are merged into a single timestamp-union table with
    NaN-filling for channels absent at a given timestamp.  TDMS and MF4 do not
    support flatten and will be exported normally.
    """
    # flatten only applies to tabular formats; MF4 always uses a single save() step
    do_flatten    = flatten and fmt not in ("tdms", "mf4")
    initial_total = 1 if fmt == "mf4" else len(mdf.groups)

    job_id = str(uuid.uuid4())
    job    = _Job(total=initial_total)
    _JOBS[job_id] = job

    def _run() -> None:
        try:
            active_mdf   = mdf
            original_mdf: Any = None

            if db_assignments:
                original_mdf = mdf
                active_mdf   = _build_decoded_mdf(mdf, db_assignments)
                if fmt != "mf4":
                    job.total = len(active_mdf.groups)

            if fmt == "mf4":
                _do_mf4(active_mdf, output_path, job, original_mdf=original_mdf)
            elif do_flatten:
                # Phase C — collect all groups into a flat table, then write once
                ts, cols = _build_flat_table(active_mdf, job)
                if not job.cancel_requested and cols:
                    if fmt == "mat":
                        _write_flat_mat(output_path, ts, cols)
                    elif fmt == "parquet":
                        job._cleanup.append(output_path)
                        _write_flat_parquet(output_path, ts, cols)
                    elif fmt in ("csv", "tsv"):
                        job._cleanup.append(output_path)
                        _write_flat_csv(output_path, ts, cols,
                                        delimiter="," if fmt == "csv" else "\t")
                    elif fmt == "xlsx":
                        job._cleanup.append(output_path)
                        _write_flat_xlsx(output_path, ts, cols)
            elif fmt == "mat":
                _do_mat(active_mdf, output_path, job,
                        mat_link_groups=mat_link_groups)
            elif fmt == "tdms":
                _do_tdms(active_mdf, output_path, job)
            elif fmt == "parquet":
                _do_parquet(active_mdf, output_path, job)
            elif fmt == "csv":
                _do_csv(active_mdf, output_path, job, delimiter=",")
            elif fmt == "tsv":
                _do_csv(active_mdf, output_path, job, delimiter="\t")
            elif fmt == "xlsx":
                _do_xlsx(active_mdf, output_path, job)
            else:
                job.error  = f"unsupported format: {fmt!r}"
                job.status = "error"
                return

            # Determine which files to remove on cancel / error
            to_delete = job._cleanup if job._cleanup else [output_path]
            if job.cancel_requested:
                for p in to_delete:
                    _delete(p)
                # status was already set to "cancelled" in cancel()
            else:
                job.status = "done"
        except Exception as exc:   # noqa: BLE001
            job.error  = str(exc)
            job.status = "error"
            for p in (job._cleanup if job._cleanup else [output_path]):
                _delete(p)

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def preview_bus_decoding(mdf: Any, db_assignments: list[dict]) -> list[dict]:
    """Lightweight DB-preview scan (no full decode).

    For each ``{"group_index": int, "db_path": str}`` entry, count how many
    messages in the DB have IDs that appear in the group's raw CAN frames.
    When the group has no ``CAN_DataFrame.ID`` channel the full DB is reported.

    Returns a list of result dicts in the same order as the input.
    """
    db_cache:  dict[str, Any]       = {}   # db_path → canmatrix CanMatrix
    id_cache:  dict[int, "set[int] | None"] = {}   # group_index → CAN ID set
    results:   list[dict]           = []

    for assignment in db_assignments:
        group_index = int(assignment["group_index"])
        db_path     = str(assignment["db_path"])
        res: dict = {
            "group_index":      group_index,
            "db_path":          db_path,
            "matched_messages": 0,
            "signal_count":     0,
            "error":            None,
        }

        try:
            if db_path not in db_cache:
                db_cache[db_path] = _load_db_matrix(db_path)
            db = db_cache[db_path]

            db_msg_map = _db_message_map(db)  # {arb_id: signal_count}

            if group_index not in id_cache:
                id_cache[group_index] = _get_group_can_ids(mdf, group_index)
            group_ids = id_cache[group_index]

            if group_ids is None:
                # Can't read IDs from this group — report all DB entries as matched.
                matched = db_msg_map
            else:
                matched = {aid: sc for aid, sc in db_msg_map.items()
                           if aid in group_ids}

            res["matched_messages"] = len(matched)
            res["signal_count"]     = sum(matched.values())

        except Exception as exc:  # noqa: BLE001
            res["error"] = str(exc)

        results.append(res)

    return results


def get_progress(job_id: str) -> dict[str, Any]:
    job = _JOBS.get(job_id)
    if job is None:
        return {"status": "not_found", "done": 0, "total": 0, "error": None}
    return {
        "status": job.status,
        "done":   job.done,
        "total":  job.total,
        "error":  job.error,
    }


def cancel(job_id: str) -> None:
    job = _JOBS.get(job_id)
    if job and job.status == "running":
        job.request_cancel()
        job.status = "cancelled"


# --------------------------------------------------------------------------- #
# .mat export
# --------------------------------------------------------------------------- #

def _do_mat(
    mdf: Any,
    output_path: str,
    job: _Job,
    mat_link_groups: bool = False,
) -> None:
    """Write a ``.mat`` v5 file.

    Each non-empty channel group produces a timestamp vector named ``t1``,
    ``t2``, … in the output file.  Channel variables are named with the
    standard ``_mat_var`` sanitiser.

    When *mat_link_groups* is ``True`` the data-vector name for every channel
    in group *i* is suffixed with the matching time-vector label (e.g.
    ``EngineSpeed_t1``), making the channel-to-time-axis association explicit
    when the file is loaded in MATLAB.
    """
    try:
        import scipy.io as sio  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"scipy is required for .mat export: {exc}") from exc

    import numpy as np

    mat_data: dict[str, Any] = {}
    seen:     dict[str, int] = {}   # uniqueness counter for _mat_var

    # ── Phase 1: pre-register time-vector labels ─────────────────────────────
    # Assign t1, t2, … to every group that has channel entries and reserve
    # these names in `seen` so no channel variable can accidentally steal them.
    group_time_label: dict[int, str] = {}  # group_index → actual MATLAB var name
    t_counter = 1
    for i, group in enumerate(mdf.groups):
        if group.channels:
            group_time_label[i] = _mat_var(f"t{t_counter}", seen)
            t_counter += 1

    # ── Phase 2: iterate groups, collect data and timestamps ─────────────────
    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return

        time_label    = group_time_label.get(i)   # e.g. "t1", "t2", …
        timestamps_arr: "Any | None" = None
        found_numeric = False

        for ch in group.channels:
            name = str(ch.name or "")
            if not name:
                continue
            try:
                sig     = mdf.get(name, group=i, raw=False,
                                  ignore_invalidation_bits=True)
                samples = sig.samples
                if not (hasattr(samples, "dtype")
                        and np.issubdtype(samples.dtype, np.number)):
                    continue
                if timestamps_arr is None and sig.timestamps is not None:
                    timestamps_arr = sig.timestamps

                if mat_link_groups and time_label:
                    var_name = _mat_var(f"{name}_{time_label}", seen)
                else:
                    var_name = _mat_var(name, seen)
                mat_data[var_name] = samples
                found_numeric = True
            except Exception:  # noqa: BLE001
                pass

        # Export the timestamp vector only when there is numeric data for it
        if found_numeric and timestamps_arr is not None and time_label:
            mat_data[time_label] = timestamps_arr

        job.done = i + 1

    sio.savemat(output_path, mat_data, do_compression=True)


# --------------------------------------------------------------------------- #
# .tdms export
# --------------------------------------------------------------------------- #

def _do_tdms(mdf: Any, output_path: str, job: _Job) -> None:
    try:
        from nptdms import TdmsWriter, ChannelObject  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"nptdms is required for .tdms export: {exc}") from exc

    import numpy as np

    with TdmsWriter(output_path) as writer:
        for i, group in enumerate(mdf.groups):
            if job.cancel_requested:
                return

            cg       = group.channel_group
            grp_name = (str(getattr(cg, "acq_name", "") or "").strip()
                        or f"Group_{i}")

            channels: list[Any] = []
            for ch in group.channels:
                name = str(ch.name or "")
                if not name:
                    continue
                try:
                    sig     = mdf.get(name, group=i, raw=False,
                                      ignore_invalidation_bits=True)
                    samples = sig.samples
                    if not (hasattr(samples, "dtype")
                            and np.issubdtype(samples.dtype, np.number)):
                        continue
                    channels.append(ChannelObject(grp_name, name, samples))
                except Exception:  # noqa: BLE001
                    pass

            if channels:
                writer.write_segment(channels)

            job.done = i + 1


# --------------------------------------------------------------------------- #
# .parquet export
# --------------------------------------------------------------------------- #

def _do_parquet(mdf: Any, output_path: str, job: _Job) -> None:
    """
    Write one Parquet file per non-empty channel group.

    • Single non-empty group  → written to *output_path* exactly.
    • Multiple non-empty groups → written to
        ``{stem}_g{i:02d}_{safe_acq_name}.parquet``
      where *stem* is *output_path* with the ``.parquet`` suffix stripped.

    Each file contains a ``timestamps`` column (float64 seconds) followed by
    one column per channel.  Columns that cannot be converted to an Arrow
    array are silently skipped.  All arrays are truncated to the shortest
    length in the group to guarantee a rectangular table.
    """
    try:
        import pyarrow as pa            # type: ignore[import-untyped]
        import pyarrow.parquet as pq    # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            f"pyarrow is required for Parquet export: {exc}"
        ) from exc

    from pathlib import Path

    base = Path(output_path)
    stem = base.with_suffix("")   # strip .parquet for multi-file naming

    non_empty_count = sum(1 for g in mdf.groups if g.channels)
    single_file     = non_empty_count <= 1

    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return

        if not group.channels:
            job.done = i + 1
            continue

        cg       = group.channel_group
        grp_name = (str(getattr(cg, "acq_name", "") or "").strip()
                    or f"group_{i}")

        # ── collect raw numpy arrays ────────────────────────────────────────
        timestamps_arr = None
        columns: dict[str, Any] = {}

        for ch in group.channels:
            ch_name = str(ch.name or "")
            if not ch_name:
                continue
            try:
                sig = mdf.get(ch_name, group=i, raw=False,
                              ignore_invalidation_bits=True)
                if timestamps_arr is None and sig.timestamps is not None:
                    timestamps_arr = sig.timestamps
                columns[ch_name] = sig.samples
            except Exception:  # noqa: BLE001
                pass

        if not columns:
            job.done = i + 1
            continue

        # ── align lengths ───────────────────────────────────────────────────
        all_arrs = list(columns.values())
        if timestamps_arr is not None:
            all_arrs.append(timestamps_arr)
        min_len = min(len(a) for a in all_arrs)

        # ── build Arrow table ───────────────────────────────────────────────
        arrow_cols: dict[str, Any] = {}
        if timestamps_arr is not None:
            arrow_cols["timestamps"] = pa.array(
                timestamps_arr[:min_len], type=pa.float64()
            )
        for col_name, arr in columns.items():
            try:
                arrow_cols[col_name] = pa.array(arr[:min_len])
            except Exception:  # noqa: BLE001
                pass  # skip unconvertible columns (e.g. structured dtypes)

        if not arrow_cols:
            job.done = i + 1
            continue

        table = pa.table(arrow_cols)

        # ── resolve output path ─────────────────────────────────────────────
        if single_file:
            out_file = str(base)
        else:
            safe = re.sub(r"[^\w\-]", "_", grp_name)[:40].strip("_") or f"g{i}"
            out_file = str(Path(f"{stem}_g{i:02d}_{safe}.parquet"))

        job._cleanup.append(out_file)
        pq.write_table(table, out_file, compression="snappy")

        job.done = i + 1


# --------------------------------------------------------------------------- #
# .csv / .tsv export
# --------------------------------------------------------------------------- #

def _do_csv(mdf: Any, output_path: str, job: _Job, delimiter: str = ",") -> None:
    """
    Write one delimited-text file per non-empty channel group.

    • Single non-empty group  → written to *output_path* exactly.
    • Multiple non-empty groups → written to
        ``{stem}_g{i:02d}_{safe_acq_name}{ext}``
      where *stem* is *output_path* with the extension stripped.

    Each file has a header row followed by one row per sample.
    Columns: ``timestamps`` (seconds, float) then one column per numeric channel.
    """
    import csv as _csv

    import numpy as np
    from pathlib import Path

    base = Path(output_path)
    ext  = base.suffix          # .csv or .tsv
    stem = base.with_suffix("")

    non_empty_count = sum(1 for g in mdf.groups if g.channels)
    single_file     = non_empty_count <= 1

    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return

        if not group.channels:
            job.done = i + 1
            continue

        cg       = group.channel_group
        grp_name = (str(getattr(cg, "acq_name", "") or "").strip()
                    or f"group_{i}")

        # ── collect numeric arrays ──────────────────────────────────────────
        timestamps_arr = None
        columns: dict[str, Any] = {}

        for ch in group.channels:
            ch_name = str(ch.name or "")
            if not ch_name:
                continue
            try:
                sig = mdf.get(ch_name, group=i, raw=False,
                              ignore_invalidation_bits=True)
                if not (hasattr(sig.samples, "dtype")
                        and np.issubdtype(sig.samples.dtype, np.number)):
                    continue
                if timestamps_arr is None and sig.timestamps is not None:
                    timestamps_arr = sig.timestamps
                columns[ch_name] = sig.samples
            except Exception:  # noqa: BLE001
                pass

        if not columns:
            job.done = i + 1
            continue

        # ── align lengths ───────────────────────────────────────────────────
        all_arrs = list(columns.values())
        if timestamps_arr is not None:
            all_arrs.append(timestamps_arr)
        min_len = min(len(a) for a in all_arrs)

        # ── resolve output path ─────────────────────────────────────────────
        if single_file:
            out_file = str(base)
        else:
            safe = re.sub(r"[^\w\-]", "_", grp_name)[:40].strip("_") or f"g{i}"
            out_file = str(Path(f"{stem}_g{i:02d}_{safe}{ext}"))

        job._cleanup.append(out_file)

        # ── write ───────────────────────────────────────────────────────────
        col_names = list(columns.keys())
        col_arrs  = [columns[n][:min_len] for n in col_names]
        ts_slice  = timestamps_arr[:min_len] if timestamps_arr is not None else None

        with open(out_file, "w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh, delimiter=delimiter)
            header = (["timestamps"] if ts_slice is not None else []) + col_names
            writer.writerow(header)
            for j in range(min_len):
                row = (([float(ts_slice[j])] if ts_slice is not None else [])
                       + [float(a[j]) for a in col_arrs])
                writer.writerow(row)

        job.done = i + 1


# --------------------------------------------------------------------------- #
# .xlsx export
# --------------------------------------------------------------------------- #

def _do_xlsx(mdf: Any, output_path: str, job: _Job) -> None:
    """
    Write a single Excel workbook with one worksheet per non-empty channel group.

    Sheet names are derived from the acquisition name (max 31 chars, special
    characters replaced with underscores — Excel's sheet-name rules).
    Each sheet has a header row followed by one row per sample.
    Columns: ``timestamps`` (seconds, float) then one column per numeric channel.
    """
    try:
        import openpyxl  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"openpyxl is required for .xlsx export: {exc}") from exc

    import numpy as np

    wb = openpyxl.Workbook(write_only=True)
    job._cleanup.append(output_path)

    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return

        if not group.channels:
            job.done = i + 1
            continue

        cg       = group.channel_group
        grp_name = (str(getattr(cg, "acq_name", "") or "").strip()
                    or f"Group_{i}")
        # Excel sheet name rules: ≤31 chars, no \ / * ? [ ] :
        sheet_name = re.sub(r'[\\/*?\[\]:]', "_", grp_name)[:31].strip() or f"Group_{i}"

        # ── collect numeric arrays ──────────────────────────────────────────
        timestamps_arr = None
        columns: dict[str, Any] = {}

        for ch in group.channels:
            ch_name = str(ch.name or "")
            if not ch_name:
                continue
            try:
                sig = mdf.get(ch_name, group=i, raw=False,
                              ignore_invalidation_bits=True)
                if not (hasattr(sig.samples, "dtype")
                        and np.issubdtype(sig.samples.dtype, np.number)):
                    continue
                if timestamps_arr is None and sig.timestamps is not None:
                    timestamps_arr = sig.timestamps
                columns[ch_name] = sig.samples
            except Exception:  # noqa: BLE001
                pass

        if not columns:
            job.done = i + 1
            continue

        # ── align lengths ───────────────────────────────────────────────────
        all_arrs = list(columns.values())
        if timestamps_arr is not None:
            all_arrs.append(timestamps_arr)
        min_len = min(len(a) for a in all_arrs)

        # ── write sheet ─────────────────────────────────────────────────────
        ws = wb.create_sheet(title=sheet_name)

        col_names = list(columns.keys())
        col_arrs  = [columns[n][:min_len] for n in col_names]
        ts_slice  = timestamps_arr[:min_len] if timestamps_arr is not None else None

        header = (["timestamps"] if ts_slice is not None else []) + col_names
        ws.append(header)

        for j in range(min_len):
            row = (([float(ts_slice[j])] if ts_slice is not None else [])
                   + [float(a[j]) for a in col_arrs])
            ws.append(row)

        job.done = i + 1

    wb.save(output_path)


# --------------------------------------------------------------------------- #
# .mf4 re-export (Phase D)
# --------------------------------------------------------------------------- #

def _do_mf4(
    mdf: Any,
    output_path: str,
    job: _Job,
    original_mdf: Any = None,
) -> None:
    """Re-export *mdf* to an MF4 file using ``MDF.save()``.

    Progress: total = 1; done = 1 after ``save()`` returns.

    When *original_mdf* is provided (i.e., *mdf* came from
    ``extract_bus_logging``), the original HD metadata fields are copied
    onto the decoded MDF header before saving so provenance is preserved.
    """
    job.total = 1
    job.done  = 0

    if original_mdf is not None:
        try:
            src_hdr = original_mdf.header
            dst_hdr = mdf.header
            for attr in ("author", "department", "project", "subject", "comment"):
                val = getattr(src_hdr, attr, None)
                if val is not None:
                    try:
                        setattr(dst_hdr, attr, val)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

    job._cleanup.append(output_path)
    mdf.save(output_path, overwrite=True)
    job.done = 1


# --------------------------------------------------------------------------- #
# Flatten helpers (Phase C)
# --------------------------------------------------------------------------- #

def _build_flat_table(
    mdf: Any,
    job: _Job,
) -> "tuple[Any, dict[str, Any]]":
    """Collect all numeric channels across all groups into a flat timestamp-union table.

    Returns ``(timestamps, columns)`` where *timestamps* is a sorted float64
    array of every unique sample time across all groups and *columns* is an
    ``{name: float64_array}`` dict with ``nan`` at timestamps where a channel
    has no sample.

    Progress: ``job.done`` is incremented to ``i + 1`` after each group.
    """
    import numpy as np

    seen_names: set[str]  = set()
    group_data: list[Any] = []   # [(float64_ts, {col_name: float64_arr})]

    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return np.array([]), {}

        ts_arr:  "Any | None"    = None
        columns: dict[str, Any]  = {}

        for ch in group.channels:
            ch_name = str(ch.name or "")
            if not ch_name:
                continue
            try:
                sig = mdf.get(ch_name, group=i, raw=False,
                              ignore_invalidation_bits=True)
                if not (hasattr(sig.samples, "dtype")
                        and np.issubdtype(sig.samples.dtype, np.number)):
                    continue
                if ts_arr is None and sig.timestamps is not None:
                    ts_arr = sig.timestamps.astype(np.float64)
                columns[ch_name] = sig.samples
            except Exception:  # noqa: BLE001
                pass

        if ts_arr is None or not columns:
            job.done = i + 1
            continue

        # Align all arrays in this group to the shortest length
        min_len = min(len(ts_arr), min(len(a) for a in columns.values()))

        # Deduplicate column names across groups by appending _g{i}
        aligned: dict[str, Any] = {}
        for ch_name, arr in columns.items():
            key = ch_name
            if key in seen_names:
                key = f"{ch_name}_g{i}"
                cnt = 2
                while key in seen_names:
                    key = f"{ch_name}_g{i}_{cnt}"
                    cnt += 1
            seen_names.add(key)
            aligned[key] = arr[:min_len].astype(np.float64)

        group_data.append((ts_arr[:min_len], aligned))
        job.done = i + 1

    if not group_data:
        return np.array([]), {}

    # Build sorted union of all group timestamps
    all_ts = np.unique(np.concatenate([ts for ts, _ in group_data]))

    # NaN-fill each group's channels at missing union timestamps
    merged: dict[str, Any] = {}
    for g_ts, g_cols in group_data:
        indices = np.searchsorted(all_ts, g_ts)
        for col_name, arr in g_cols.items():
            col = np.full(len(all_ts), np.nan, dtype=np.float64)
            col[indices] = arr
            merged[col_name] = col

    return all_ts, merged


def _write_flat_mat(
    output_path: str,
    timestamps: Any,
    columns: dict[str, Any],
) -> None:
    try:
        import scipy.io as sio  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"scipy is required for .mat export: {exc}") from exc

    seen: dict[str, int] = {}
    mat_data: dict[str, Any] = {}
    if len(timestamps):
        mat_data[_mat_var("timestamps", seen)] = timestamps
    for col_name, arr in columns.items():
        mat_data[_mat_var(col_name, seen)] = arr
    sio.savemat(output_path, mat_data, do_compression=True)


def _write_flat_parquet(
    output_path: str,
    timestamps: Any,
    columns: dict[str, Any],
) -> None:
    try:
        import pyarrow as pa            # type: ignore[import-untyped]
        import pyarrow.parquet as pq    # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            f"pyarrow is required for Parquet export: {exc}"
        ) from exc

    arrow_cols: dict[str, Any] = {}
    if len(timestamps):
        arrow_cols["timestamps"] = pa.array(timestamps, type=pa.float64())
    for col_name, arr in columns.items():
        try:
            arrow_cols[col_name] = pa.array(arr)
        except Exception:  # noqa: BLE001
            pass
    if arrow_cols:
        pq.write_table(pa.table(arrow_cols), output_path, compression="snappy")


def _write_flat_csv(
    output_path: str,
    timestamps: Any,
    columns: dict[str, Any],
    delimiter: str = ",",
) -> None:
    import csv as _csv

    col_names = list(columns.keys())
    has_ts    = len(timestamps) > 0
    n         = len(timestamps) if has_ts else (
        max((len(a) for a in columns.values()), default=0)
    )

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = _csv.writer(fh, delimiter=delimiter)
        header = (["timestamps"] if has_ts else []) + col_names
        writer.writerow(header)
        col_arrs = [columns[name] for name in col_names]
        for j in range(n):
            row = (
                [float(timestamps[j])] if has_ts else []
            ) + [float(a[j]) for a in col_arrs]
            writer.writerow(row)


def _write_flat_xlsx(
    output_path: str,
    timestamps: Any,
    columns: dict[str, Any],
) -> None:
    try:
        import openpyxl  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"openpyxl is required for .xlsx export: {exc}") from exc

    import math

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Flattened")

    col_names = list(columns.keys())
    has_ts    = len(timestamps) > 0
    header    = (["timestamps"] if has_ts else []) + col_names
    ws.append(header)

    n        = len(timestamps) if has_ts else (
        max((len(a) for a in columns.values()), default=0)
    )
    col_arrs = [columns[name] for name in col_names]

    for j in range(n):
        row = (
            [float(timestamps[j])] if has_ts else []
        ) + [
            None if math.isnan(a[j]) else float(a[j])
            for a in col_arrs
        ]
        ws.append(row)

    wb.save(output_path)


# --------------------------------------------------------------------------- #
# Bus-decoding helpers (Phase A)
# --------------------------------------------------------------------------- #

def _load_db_matrix(db_path: str) -> Any:
    """Load a ``.dbc`` or ``.arxml`` file.  Returns a canmatrix ``CanMatrix``."""
    try:
        import canmatrix.formats  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            f"canmatrix is required for bus decoding: {exc}"
        ) from exc
    db_dict = canmatrix.formats.loadp(db_path)
    if not db_dict:
        raise RuntimeError(f"No network found in database file: {db_path!r}")
    return next(iter(db_dict.values()))


def _db_message_map(db: Any) -> dict[int, int]:
    """Return ``{normalised_arb_id: signal_count}`` for all frames in *db*.

    canmatrix uses ``CanMatrix.frames`` (a list of ``Frame`` objects).
    The ``arbitration_id`` field is a ``canmatrix.ArbitrationId`` object
    (with a ``.id`` int attribute) in recent versions; older versions store
    a plain int with bit 31 set for extended frames.
    """
    result: dict[int, int] = {}
    frames = getattr(db, "frames", None) or getattr(db, "messages", [])
    for frame in frames:
        arb = frame.arbitration_id
        msg_id = int(getattr(arb, "id", arb)) & 0x1FFF_FFFF
        result[msg_id] = len(list(frame.signals))
    return result


def _get_group_can_ids(mdf: Any, group_index: int) -> "set[int] | None":
    """Read unique 29-bit CAN IDs from a raw group.  Returns *None* on failure."""
    try:
        sig = mdf.get(
            "CAN_DataFrame.ID",
            group=group_index,
            raw=True,
            ignore_invalidation_bits=True,
        )
        return {int(x) & 0x1FFF_FFFF for x in sig.samples.tolist()}
    except Exception:  # noqa: BLE001
        return None


# asammdf extract_bus_logging key per our metadata bus-type label
_BUS_TYPE_TO_EBL_KEY: dict[str, str] = {
    "CAN":      "CAN",
    "CAN FD":   "CAN",   # CAN FD frames are decoded with CAN databases
    "LIN":      "LIN",
    "FlexRay":  "FLEXRAY",
    "MOST":     "MOST",
    "Ethernet": "Ethernet",
    "K-Line":   "K_LINE",
}


def _build_decoded_mdf(mdf: Any, db_assignments: list[dict]) -> Any:
    """Apply ``MDF.extract_bus_logging()`` using the given ordered DB assignments.

    Builds the ``database_files`` dict by mapping each assigned group's bus type
    to the correct key expected by asammdf.  DB paths for the same bus type are
    deduplicated (first occurrence wins, preserving priority order).

    Returns the decoded MDF object (a new instance; the original is unmodified).
    """
    import metadata as _meta  # sidecar root is on sys.path at runtime

    # ebl_key → ordered list of unique db_paths
    ebl_dbs: dict[str, list[str]] = {}
    seen:    dict[str, set[str]]  = {}

    for assignment in db_assignments:
        group_index = int(assignment["group_index"])
        db_path     = str(assignment["db_path"])

        if group_index >= len(mdf.groups):
            continue

        group    = mdf.groups[group_index]
        bus_type = _meta.group_bus_type(group) or ""
        ebl_key  = _BUS_TYPE_TO_EBL_KEY.get(bus_type)
        if not ebl_key:
            continue

        if ebl_key not in ebl_dbs:
            ebl_dbs[ebl_key] = []
            seen[ebl_key]    = set()

        if db_path not in seen[ebl_key]:
            ebl_dbs[ebl_key].append(db_path)
            seen[ebl_key].add(db_path)

    if not ebl_dbs:
        return mdf

    # asammdf expects {"CAN": [(path, bus_channel), ...], ...}
    database_files = {
        key: [(path, 0) for path in paths]
        for key, paths in ebl_dbs.items()
    }

    return mdf.extract_bus_logging(database_files=database_files)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _mat_var(name: str, seen: dict[str, int]) -> str:
    """Unique MATLAB-safe variable name (≤ 63 chars)."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not safe or not safe[0].isalpha():
        safe = "ch_" + safe
    safe = safe[:60]
    n = seen.get(safe, 0)
    seen[safe] = n + 1
    return safe if n == 0 else f"{safe}_{n}"


def _delete(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
