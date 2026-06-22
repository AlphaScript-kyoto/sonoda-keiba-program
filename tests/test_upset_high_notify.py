"""Upset-high admin LINE message tests."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import (
    build_race_bet_plan,
    build_sanrenpuku_formation_firm,
    format_sanrenpuku_formation_umaban_line,
)
from src.predictor.race_day_notify import build_upset_high_admin_line_message


def _upset_race():
    rows = []
    for i, p in enumerate([0.82, 0.10, 0.04, 0.02, 0.01, 0.01], start=1):
        rows.append(
            {
                "race_id": "r1",
                "race_no": 5,
                "race_name": "C3二",
                "umaban": str(i),
                "horse_name": f"馬{i}",
                "rank_pred": i,
                "win_prob": p,
                "odds": float(i * 2),
            }
        )
    race = pd.DataFrame(rows)
    race["head_count"] = 12
    race["odds"] = [4.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    return race


def test_formation_umaban_line_format():
    top5 = _upset_race().sort_values("rank_pred").head(5)
    formation = build_sanrenpuku_formation_firm(top5)
    assert formation is not None
    assert format_sanrenpuku_formation_umaban_line(formation) == "1-2,3,-2,3,4,5"


def test_upset_high_admin_line_message():
    plan = build_race_bet_plan(_upset_race())
    plan.race_name = "C3二"
    msg = build_upset_high_admin_line_message("20260618", 5, plan)
    assert msg is not None
    assert "荒Highレースです" in msg
    assert "三連複フォーメーション" in msg
    assert "1-2,3,-2,3,4,5" in msg
    assert "です" in msg


def test_firm_race_no_upset_high_message():
    race = _upset_race()
    race["odds"] = [1.5, 3.0, 5.0, 8.0, 12.0, 20.0]
    plan = build_race_bet_plan(race)
    assert build_upset_high_admin_line_message("20260618", 5, plan) is None
