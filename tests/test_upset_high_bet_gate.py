"""Tests for upset-high bet pause gate."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.upset_high_bet_gate import (
    MAX_CONSECUTIVE_MISSES,
    ROLLING_MIN_ROI_PCT,
    ROLLING_WINDOW,
    UpsetHighBetRecord,
    UpsetHighBetState,
    build_pause_skip_message,
    enter_pause,
    on_race_day_open,
    pause_check_reason,
    record_signaled_bet,
    rolling_roi_pct,
    should_send_upset_high_buy,
)


def _master_dates() -> pd.DataFrame:
    return pd.DataFrame({"date": ["20260618", "20260624", "20260701"]})


def test_four_misses_triggers_pause():
    st = UpsetHighBetState(consecutive_misses=MAX_CONSECUTIVE_MISSES)
    assert pause_check_reason(st) == f"{MAX_CONSECUTIVE_MISSES}\u9023\u6557"


def test_rolling_roi_triggers_pause():
    bets = [
        UpsetHighBetRecord("20260101", i, 500, 0, False) for i in range(1, ROLLING_WINDOW + 1)
    ]
    st = UpsetHighBetState(recent_bets=bets)
    reason = pause_check_reason(st)
    assert reason is not None
    assert str(int(ROLLING_MIN_ROI_PCT)) in reason


def test_resume_on_next_race_day():
    st = UpsetHighBetState(paused=True, resume_on_date="20260624")
    st = on_race_day_open("20260624", st, master=_master_dates())
    assert not st.paused


def test_should_not_send_when_paused():
    st = UpsetHighBetState(paused=True, pause_reason="4\u9023\u6557", resume_on_date="20260624")
    ok, reason = should_send_upset_high_buy(st, "20260618", master=_master_dates())
    assert not ok
    assert "\u9023\u6557" in reason or "\u4f11\u6b62" in reason


def test_enter_pause_sets_resume_date():
    st = UpsetHighBetState()
    enter_pause(st, "test", "20260618", _master_dates())
    assert st.paused
    assert st.resume_on_date == "20260624"


def test_record_signaled_bet_dedupes():
    st = UpsetHighBetState()
    record_signaled_bet(st, "20260618", 1, 500)
    record_signaled_bet(st, "20260618", 1, 500)
    assert len(st.pending_signals) == 1


def test_build_pause_skip_message_contains_resume():
    st = UpsetHighBetState(
        paused=True,
        consecutive_misses=4,
        resume_on_date="20260624",
    )
    msg = build_pause_skip_message("20260618", 5, "4\u9023\u6557", st)
    assert "20260624" in msg
    assert "\u4f11\u6b62" in msg


def test_rolling_roi_calc():
    bets = [UpsetHighBetRecord("d", 1, 100, 50, False)] * 10
    assert rolling_roi_pct(bets) == 50.0
