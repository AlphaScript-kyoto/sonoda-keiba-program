"""根拠文生成のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.rationale import build_race_flow_lines, build_mark_rationale_lines
from src.predictor.post_format import format_note_race_rich


def _race_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "race_no": 5,
                "umaban": "1",
                "horse_name": "逃げ馬",
                "running_style": "逃",
                "horse_style_score": 3.0,
                "pace_style_fit": 0.2,
                "race_pace": "H",
                "distance": "1400m",
                "track": "稍",
                "weather": "晴",
                "entry_waku": 8,
                "sonoda_waku_style_fit": 0.35,
                "horse_win_rate_distance": 0.28,
                "jockey_trainer_win_rate": 0.12,
                "jockey": "騎手A",
                "trainer": "厩舎B",
                "sire": "サンデー系",
                "sire_win_rate": 0.15,
                "rank_pred": 1,
                "odds": 4.5,
                "popularity": 2,
            },
            {
                "race_no": 5,
                "umaban": "3",
                "horse_name": "先行馬",
                "running_style": "先",
                "horse_style_score": 2.0,
                "pace_style_fit": 0.15,
                "race_pace": "H",
                "distance": "1400m",
                "track": "稍",
                "weather": "晴",
                "entry_waku": 3,
                "rank_pred": 3,
                "odds": 8.0,
                "popularity": 4,
            },
        ]
    )


def test_race_flow_front_runners():
    lines = build_race_flow_lines(_race_df())
    assert any("逃げ・先行" in ln for ln in lines)
    assert any("1番逃げ馬" in ln for ln in lines)


def test_mark_rationale_uses_features_not_odds_only():
    row = _race_df().iloc[0]
    lines = build_mark_rationale_lines(
        "◎", "1", "逃げ馬", row, _race_df(), plan=_plan(), fav_u="2"
    )
    body = "\n".join(lines)
    assert "1400m" in body or "園田" in body or "脚質" in body or "距離" in body
    assert "市場の1番人気と同じ" not in body


def _plan() -> RaceBetPlan:
    return RaceBetPlan(
        race_id="r1",
        race_no=5,
        race_name="テスト",
        confidence="高",
        win_prob_top=0.3,
        prob_gap=0.1,
        marks=[("◎", "1", "逃げ馬"), ("○", "3", "先行馬")],
        exotic_confidence="高",
        exotic_profile="堅",
        win_profile="堅",
        fav_odds=2.5,
        expectation_score=80,
        expectation_tier="S",
    )


def test_format_note_includes_rationale_sections():
    df = _race_df()
    text = format_note_race_rich(_plan(), df, df)
    assert "▼ レースの展開" in text
    assert "▼ 印と根拠" in text
    assert "▼ 印の意味" not in text
