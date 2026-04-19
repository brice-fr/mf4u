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

def start(mdf: Any, fmt: str, output_path: str) -> str:
    """Start an export job in a background thread; return its job_id."""
    job_id = str(uuid.uuid4())
    job    = _Job(total=len(mdf.groups))
    _JOBS[job_id] = job

    def _run() -> None:
        try:
            if fmt == "mat":
                _do_mat(mdf, output_path, job)
            elif fmt == "tdms":
                _do_tdms(mdf, output_path, job)
            elif fmt == "parquet":
                _do_parquet(mdf, output_path, job)
            elif fmt == "csv":
                _do_csv(mdf, output_path, job, delimiter=",")
            elif fmt == "tsv":
                _do_csv(mdf, output_path, job, delimiter="\t")
            elif fmt == "xlsx":
                _do_xlsx(mdf, output_path, job)
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

def _do_mat(mdf: Any, output_path: str, job: _Job) -> None:
    try:
        import scipy.io as sio  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(f"scipy is required for .mat export: {exc}") from exc

    import numpy as np

    mat_data: dict[str, Any] = {}
    seen:     dict[str, int] = {}       # uniqueness counter for var names

    for i, group in enumerate(mdf.groups):
        if job.cancel_requested:
            return

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
                mat_data[_mat_var(name, seen)] = samples
            except Exception:  # noqa: BLE001
                pass

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
