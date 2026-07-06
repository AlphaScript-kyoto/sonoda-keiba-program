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
    update_schedule_race_meta,
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


def test_due_line_notify_jobs_t10(tmp_path, monkeypatch):
    import src.predictor.race_day_notify as notify_mod
    import src.scraper.race_snapshots as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_ROOT", tmp_path)
    monkeypatch.setattr(notify_mod, "snapshots_dir", mod.snapshots_dir)

    from datetime import datetime

    from src.predictor.race_day_notify import (
        due_line_notify_jobs,
        load_notified_race_ids,
        mark_race_notified,
    )

    sched = _schedule()
    now = datetime(2026, 6, 12, 11, 51)
    due = due_line_notify_jobs("20260612", sched, notify_offset=10, now=now)
    assert len(due) == 1
    assert due[0].race_id == "202650061201"

    mark_race_notified("20260612", "202650061201")
    due2 = due_line_notify_jobs("20260612", sched, notify_offset=10, now=now)
    assert len(due2) == 0
    assert "202650061201" in load_notified_race_ids("20260612")


def test_update_schedule_race_meta(tmp_path, monkeypatch):
    import src.scraper.race_snapshots as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_ROOT", tmp_path)
    sched = _schedule()
    mod.save_schedule(sched)

    changed = mod.update_schedule_race_meta(
        "20260612",
        "202650061201",
        post_time="12:10",
    )
    assert changed == ("12:00", "12:10")

    updated = mod.load_schedule("20260612")
    assert updated["races"][0]["post_time"] == "12:10"

    unchanged = mod.update_schedule_race_meta(
        "20260612",
        "202650061201",
        post_time="12:10",
    )
    assert unchanged is None


def test_due_line_notify_uses_updated_post_time(tmp_path, monkeypatch):
    import src.predictor.race_day_notify as notify_mod
    import src.scraper.race_snapshots as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_ROOT", tmp_path)
    monkeypatch.setattr(notify_mod, "snapshots_dir", mod.snapshots_dir)

    from src.predictor.race_day_notify import due_line_notify_jobs

    sched = _schedule()
    mod.save_schedule(sched)
    mod.update_schedule_race_meta(
        "20260612",
        "202650061201",
        post_time="12:10",
    )
    sched = mod.load_schedule("20260612")

    too_early = datetime(2026, 6, 12, 11, 59)
    assert due_line_notify_jobs("20260612", sched, notify_offset=10, now=too_early) == []

    on_time = datetime(2026, 6, 12, 12, 0)
    due = due_line_notify_jobs("20260612", sched, notify_offset=10, now=on_time)
    assert len(due) == 1
    assert due[0].post_time == "12:10"


def test_chunk_text_for_line():
    from tools.line_bot import chunk_text_for_line

    body = "A\n" + ("x" * 5000)
    parts = chunk_text_for_line(body, max_len=100)
    assert len(parts) >= 2
    assert all(len(p) <= 100 for p in parts)
