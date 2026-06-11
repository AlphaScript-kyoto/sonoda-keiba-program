"""Tests for race snapshot scheduling."""

from datetime import datetime

from src.scraper.race_snapshots import (
    CaptureJob,
    all_captures_done,
    due_capture_jobs,
    label_for_offset,
    next_wake_datetime,
    parse_capture_offsets,
    trigger_datetime,
)


def _schedule():
    return {
        "date": "20260612",
        "races": [
            {"race_id": "202650061201", "race_no": 1, "post_time": "12:00", "race_name": "A"},
            {"race_id": "202650061202", "race_no": 2, "post_time": "12:30", "race_name": "B"},
        ],
    }


def test_label_for_offset():
    assert label_for_offset(30) == "t_minus_30"
    assert label_for_offset(10) == "t_minus_10"


def test_parse_capture_offsets():
    assert parse_capture_offsets("30,20,10") == (30, 20, 10)
    assert parse_capture_offsets("10") == (10,)


def test_trigger_datetime():
    dt = trigger_datetime("20260612", "12:00", 30)
    assert dt == datetime(2026, 6, 12, 11, 30)


def test_due_and_next_wake(tmp_path, monkeypatch):
    import src.scraper.race_snapshots as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_ROOT", tmp_path)
    sched = _schedule()
    now = datetime(2026, 6, 12, 11, 31)
    due = due_capture_jobs("20260612", sched, offsets=(30, 20, 10), now=now)
    assert len(due) == 1
    assert due[0].race_id == "202650061201"
    assert due[0].minutes_before == 30

    wake = next_wake_datetime("20260612", sched, offsets=(30, 20, 10), now=now)
    assert wake == datetime(2026, 6, 12, 11, 40)

    assert not all_captures_done("20260612", sched, offsets=(30, 20, 10), now=now)
