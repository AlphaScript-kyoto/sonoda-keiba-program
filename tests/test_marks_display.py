"""印表示順のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.marks_display import build_marks_display_frame, sort_marks


def test_sort_marks_fixed_order():
    raw = [("△", "3", "c"), ("◎", "1", "a"), ("☆", "7", "e"), ("○", "8", "b"), ("▲", "2", "d")]
    ordered = sort_marks(raw)
    assert [m[0] for m in ordered] == ["◎", "○", "▲", "△", "☆"]


def test_build_marks_display_frame_order():
    plan = RaceBetPlan(
        race_id="r1",
        race_no=1,
        race_name="テスト",
        confidence="高",
        win_prob_top=0.9,
        prob_gap=0.7,
        marks=[("◎", "1", "A"), ("○", "2", "B"), ("▲", "3", "C"), ("△", "4", "D"), ("☆", "5", "E")],
    )
    ex = pd.DataFrame(
        [
            {"race_no": 1, "umaban": "1", "horse_name": "A", "score": 10.0, "win_prob": 0.3, "odds": "2.0", "popularity": "1", "rank_pred": 1},
            {"race_no": 1, "umaban": "2", "horse_name": "B", "score": 8.0, "win_prob": 0.2, "odds": "5.0", "popularity": "2", "rank_pred": 2},
            {"race_no": 1, "umaban": "3", "horse_name": "C", "score": 7.0, "win_prob": 0.15, "odds": "8.0", "popularity": "3", "rank_pred": 3},
            {"race_no": 1, "umaban": "4", "horse_name": "D", "score": 6.0, "win_prob": 0.1, "odds": "10.0", "popularity": "4", "rank_pred": 4},
            {"race_no": 1, "umaban": "5", "horse_name": "E", "score": 5.0, "win_prob": 0.08, "odds": "12.0", "popularity": "5", "rank_pred": 5},
        ]
    )
    win = pd.DataFrame(
        [
            {"race_no": 1, "umaban": "4", "horse_name": "D", "win_prob": 0.5, "odds": "1.5", "popularity": "1", "rank_pred": 1},
        ]
    )
    df = build_marks_display_frame(plan, win, ex)
    assert list(df["mark"]) == ["◎", "○", "▲", "△", "☆"]
    assert df.iloc[0]["odds"] == "2.0"
    assert df.iloc[0]["win_prob"] is not None
    assert float(df.iloc[0]["win_prob"]) > 0
