"""
Export jobs: MDF → .mat (scipy) or .tdms (nptdms).

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
    __slots__ = ("total", "done", "status", "error", "_cancel")

    def __init__(self, total: int) -> None:
        self.total   = total
        self.done    = 0
        self.status  = "running"          # running | done | error | cancelled
        self.error: str | None = None
        self._cancel = threading.Event()

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
            else:
                job.error  = f"unsupported format: {fmt!r}"
                job.status = "error"
                return
            if job.cancel_requested:
                _delete(output_path)
                # status was already set to "cancelled" in cancel()
            else:
                job.status = "done"
        except Exception as exc:   # noqa: BLE001
            job.error  = str(exc)
            job.status = "error"
            _delete(output_path)

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
