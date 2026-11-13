import fcntl

import pytest

from chess_backend.limits import BusyError, job_slot


def test_one_job_slot_blocks_second_process_style_lock(tmp_path):
    with job_slot(tmp_path, max_jobs=1, queue_timeout=0):
        with pytest.raises(BusyError, match="busy"):
            with job_slot(tmp_path, max_jobs=1, queue_timeout=0):
                pass
    with job_slot(tmp_path, max_jobs=1, queue_timeout=0):
        pass


def test_second_slot_can_run_when_limit_is_two(tmp_path):
    with job_slot(tmp_path, max_jobs=2, queue_timeout=0) as first:
        with job_slot(tmp_path, max_jobs=2, queue_timeout=0) as second:
            assert first != second
