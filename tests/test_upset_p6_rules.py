"""Tests for P6 upset-high buy rules."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import build_race_bet_plan
from src.predictor.race_day_notify import build_upset_high_admin_line_message
from src.predictor.upset_high_bet_gate import (
    UpsetHighBetState,
    record_signaled_bet,
    should_send_upset_high_buy,
)
from src.predictor.upset_p6_rules import is_p6_eligible_plan


def _upset_race():
    rows = []
    for i, p in enumerate([0.82, 0.10, 0.04, 0.02, 0.01, 0.01], start=1):
        rows.append(
            {
                "race_id": "r1",
                "race_no": 5,
                "race_name": "C3",
                "umaban": str(i),
                "horse_name": f"h{i}",
                "rank_pred": i,
                "win_prob": p,
                "odds": float(i * 2),
            }
        )
    race = pd.DataFrame(rows)
    race["head_count"] = 12
    race["odds"] = [4.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    return race


def test_p6_eligible_upset_volatile():
    plan = build_race_bet_plan(_upset_race())
    assert plan.exotic_profile == "\u8352"
    assert plan.is_volatile
    assert plan.axis_odds >= 2.0
    assert is_p6_eligible_plan(plan)


def test_p6_ineligible_low_axis_odds():
    race = _upset_race()
    race["odds"] = [1.4, 5.0, 10.0, 15.0, 20.0, 30.0]
    plan = build_race_bet_plan(race)
    assert not is_p6_eligible_plan(plan)


def test_p6_admin_message_only_when_eligible():
    plan = build_race_bet_plan(_upset_race())
    assert build_upset_high_admin_line_message("20260618", 5, plan) is not None
    race = _upset_race()
    race["odds"] = [1.4, 5.0, 10.0, 15.0, 20.0, 30.0]
    plan2 = build_race_bet_plan(race)
    assert build_upset_high_admin_line_message("20260618", 5, plan2) is None


def test_p6_daily_cap_two():
    plan = build_race_bet_plan(_upset_race())
    st = UpsetHighBetState()
    assert should_send_upset_high_buy(st, "20260618", plan=plan)[0]
    record_signaled_bet(st, "20260618", 1, 500)
    record_signaled_bet(st, "20260618", 2, 500)
    ok, reason = should_send_upset_high_buy(st, "20260618", plan=plan)
    assert not ok
    assert "2R" in reason