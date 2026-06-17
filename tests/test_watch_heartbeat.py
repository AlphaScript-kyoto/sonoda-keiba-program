"""Tests for watch heartbeat health check."""

from datetime import datetime, timedelta

from src.predictor.automation_log import write_heartbeat
from src.predictor.watch_heartbeat import (
    evaluate_heartbeat,
    is_in_watch_window,
    race_day_window,
)


def _schedule():
    return {
        "date": "20260612",
        "races": [
            {"race_id": "202650061201", "race_no": 1, "post_time": "12:00", "race_name": "A"},
            {"race_id": "202650061202", "race_no": 2, "post_time": "12:30", "race_name": "B"},
        ],
    }


def test_race_day_window():
    sched = _schedule()
    start, end = race_day_window(sched, now=datetime(2026, 6, 12, 11, 0))
    assert start == datetime(2026, 6, 12, 11, 25)
    assert end == datetime(2026, 6, 12, 12, 45)


def test_is_in_watch_window():
    sched = _schedule()
    inside = datetime(2026, 6, 12, 11, 30)
    outside = datetime(2026, 6, 12, 10, 0)
    assert is_in_watch_window(sched, now=inside)
    assert not is_in_watch_window(sched, now=outside)


def test_evaluate_heartbeat_outside_window():
    sched = _schedule()
    ok, reason = evaluate_heartbeat(
        "20260612",
        schedule=sched,
        now=datetime(2026, 6, 12, 8, 0),
    )
    assert ok
    assert reason == "outside_window"


def test_evaluate_heartbeat_sleeping(tmp_path, monkeypatch):
    import src.predictor.automation_log as log_mod

    monkeypatch.setattr(log_mod, "LOGS_DIR", tmp_path)
    sched = _schedule()
    now = datetime(2026, 6, 12, 11, 30)
    wake = datetime(2026, 6, 12, 11, 40)
    write_heartbeat("20260612", status="sleeping", next_wake_at=wake)
    ok, reason = evaluate_heartbeat("20260612", schedule=sched, now=now)
    assert ok
    assert reason == "sleeping_until_wake"


def test_evaluate_heartbeat_stale(tmp_path, monkeypatch):
    import json

    import src.predictor.automation_log as log_mod

    monkeypatch.setattr(log_mod, "LOGS_DIR", tmp_path)
    sched = _schedule()
    now = datetime(2026, 6, 12, 11, 30)
    old = now - timedelta(minutes=30)
    payload = {
        "date": "20260612",
        "status": "running",
        "updated_at": old.isoformat(timespec="seconds"),
    }
    hb_path = tmp_path / "watch_heartbeat_20260612.json"
    hb_path.write_text(json.dumps(payload), encoding="utf-8")

    ok, reason = evaluate_heartbeat("20260612", schedule=sched, now=now)
    assert not ok
    assert reason.startswith("stale_")


def test_evaluate_heartbeat_missing(tmp_path, monkeypatch):
    import src.predictor.automation_log as log_mod

    monkeypatch.setattr(log_mod, "LOGS_DIR", tmp_path)
    sched = _schedule()
    now = datetime(2026, 6, 12, 11, 30)
    ok, reason = evaluate_heartbeat("20260612", schedule=sched, now=now)
    assert not ok
    assert reason == "heartbeat_missing"
