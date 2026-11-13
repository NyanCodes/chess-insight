"""Cross-process Stockfish job slots for one host (POSIX flock)."""
from __future__ import annotations

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path


class BusyError(RuntimeError):
    """The configured engine capacity is currently occupied."""


@contextmanager
def job_slot(directory: Path, *, max_jobs: int = 1, queue_timeout: float = 10.0):
    if not 1 <= max_jobs <= 2 or not 0 <= queue_timeout <= 60:
        raise ValueError("max_jobs must be 1..2 and queue_timeout 0..60")
    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + queue_timeout
    while True:
        for index in range(max_jobs):
            # A fixed per-user directory is used; all CLI invocations share these slots.
            fd = (directory / f"stockfish-job-{index}.lock").open("a+b")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fd.close()
                continue
            try:
                yield index
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
            return
        if time.monotonic() >= deadline:
            raise BusyError("Stockfish busy: no available analysis job slot")
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
