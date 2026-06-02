"""通算1着率（career_win_stats）のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.marks_display import career_win_stats


def test_career_win_stats_matches_manual():
    master = pd.DataFrame(
        [
            {"horse_id": "h1", "date": "20260101", "finish": "3"},
            {"horse_id": "h1", "date": "20260201", "finish": "1"},
            {"horse_id": "h1", "date": "20260301", "finish": "2"},
            {"horse_id": "h1", "date": "20260529", "finish": "1"},
        ]
    )
    wins, runs, rate = career_win_stats(master, "h1", "20260529")
    assert wins == 1
    assert runs == 3
    assert abs(rate - 1 / 3) < 1e-6
