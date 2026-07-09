"""Off-day notice throttle (Option B) tests."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.predictor.automation_log import ALERT_STATE_PATH
from src.predictor.off_day_notify import (
    OFF_DAY_STATE_KEY,
    record_off_day_notice_sent,
    should_send_off_day_notice,
)


@pytest.fixture
def alert_state(tmp_path, monkeypatch):
    path = tmp_path / "alert_state.json"
    monkeypatch.setattr("src.predictor.automation_log.ALERT_STATE_PATH", path)
    return path


def _dt(y, m, d, h=10):
    return datetime(y, m, d, h, 0, 0)


def test_first_off_day_sends(alert_state):
    ok, reason = should_send_off_day_notice(
        "20260615", "20260617", now=_dt(2026, 6, 15)
    )
    assert ok
    assert reason == "first"


def test_same_next_within_7_days_skips(alert_state):
    record_off_day_notice_sent("20260615", "20260617", now=_dt(2026, 6, 15))
    ok, reason = should_send_off_day_notice(
        "20260616", "20260617", now=_dt(2026, 6, 16)
    )
    assert not ok
    assert "skip" in reason


def test_next_date_change_sends(alert_state):
    record_off_day_notice_sent("20260615", "20260617", now=_dt(2026, 6, 15))
    ok, reason = should_send_off_day_notice(
        "20260620", "20260624", now=_dt(2026, 6, 20)
    )
    assert ok
    assert reason.startswith("next_date_changed")


def test_cooldown_7_days_sends(alert_state):
    record_off_day_notice_sent("20260615", "20260617", now=_dt(2026, 6, 15))
    ok, reason = should_send_off_day_notice(
        "20260622", "20260617", now=_dt(2026, 6, 22)
    )
    assert ok
    assert reason == "cooldown_7d"


def test_june_15_29_scenario(alert_state):
    """Simulate 2026/06/15-06/29 off-day sends (race days excluded)."""
    race_days = {
        "20260617",
        "20260618",
        "20260619",
        "20260624",
        "20260625",
        "20260626",
    }
    sends = []
    d = _dt(2026, 6, 15)
    end = _dt(2026, 6, 29)
    next_by_day = {
        "20260615": "20260617",
        "20260616": "20260617",
        "20260620": "20260624",
        "20260621": "20260624",
        "20260622": "20260624",
        "20260623": "20260624",
        "20260627": "20260701",
        "20260628": "20260701",
        "20260629": "20260701",
    }
    while d <= end:
        ymd = d.strftime("%Y%m%d")
        if ymd not in race_days:
            nxt = next_by_day.get(ymd)
            ok, _reason = should_send_off_day_notice(ymd, nxt, now=d)
            if ok:
                sends.append(ymd)
                record_off_day_notice_sent(ymd, nxt, now=d)
        d = datetime(d.year, d.month, d.day + 1, 10, 0, 0)
    assert sends == ["20260615", "20260620", "20260627"]


def test_shared_state_persists(alert_state):
    record_off_day_notice_sent("20260615", "20260617", now=_dt(2026, 6, 15))
    data = json.loads(alert_state.read_text(encoding="utf-8"))
    rec = data[OFF_DAY_STATE_KEY]
    assert rec["last_off_date"] == "20260615"
    assert rec["last_next_date"] == "20260617"