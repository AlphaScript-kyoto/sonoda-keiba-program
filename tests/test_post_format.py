"""投稿フォーマットのテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceBetPlan
from src.predictor.post_format import (
    copy_channel_label,
    format_note_race_rich,
    format_race_copy,
    format_x_race,
)


def _plan(tier: str = "S") -> RaceBetPlan:
    return RaceBetPlan(
        race_id="r1",
        race_no=5,
        race_name="テスト特別",
        confidence="高",
        win_prob_top=0.32,
        prob_gap=0.11,
        marks=[
            ("◎", "1", "マスクト"),
            ("○", "7", "セカンド"),
            ("▲", "6", "サード"),
            ("△", "5", "フォース"),
            ("☆", "9", "フィフス"),
        ],
        exotic_confidence="高",
        exotic_profile="堅",
        win_profile="堅",
        fav_odds=2.8,
        expectation_score=76,
        expectation_tier=tier,
    )


def _ex_df() -> pd.DataFrame:
    base = {
        "race_no": 5,
        "distance": "1400m",
        "track": "良",
        "weather": "晴",
        "race_pace": "H",
        "running_style": "先",
        "horse_style_score": 2.0,
        "pace_style_fit": 0.15,
        "horse_win_rate_distance": 0.22,
        "jockey_trainer_win_rate": 0.09,
        "jockey": "騎手",
        "trainer": "厩舎",
    }
    rows = [
            {"umaban": "1", "horse_name": "マスクト", "win_prob": 0.18, "odds": 2.1, "popularity": 1, "rank_pred": 1},
            {"umaban": "7", "horse_name": "セカンド", "win_prob": 0.14, "odds": 5.0, "popularity": 3, "rank_pred": 2},
            {"umaban": "6", "horse_name": "サード", "win_prob": 0.12, "odds": 6.0, "popularity": 4, "rank_pred": 3},
            {"umaban": "5", "horse_name": "フォース", "win_prob": 0.10, "odds": 8.0, "popularity": 5, "rank_pred": 4},
            {"umaban": "9", "horse_name": "フィフス", "win_prob": 0.08, "odds": 12.0, "popularity": 6, "rank_pred": 5},
    ]
    return pd.DataFrame([{**base, **r} for r in rows])


def test_format_note_race_rich_plain_language():
    text = format_note_race_rich(_plan("S"), _ex_df(), _ex_df())
    assert "▼ レースの展開" in text
    assert "▼ 印と根拠" in text
    assert "▼ このレースの見方" not in text
    assert "買い目の目安" not in text
    assert "三連スコア" not in text
    assert "自信度 高" not in text
    assert "AI1位" not in text
    assert "noteで" not in text


def test_format_note_ss_tier_line():
    text = format_note_race_rich(_plan("SS"), _ex_df(), _ex_df())
    assert "期待値SS" in text
    assert "いちばんおすすめ" not in text


def test_format_race_copy_tier_routing():
    ex = _ex_df()
    note_text = format_race_copy(_plan("S"), ex, ex)
    a_text = format_race_copy(_plan("A"), ex, ex)
    x_text = format_race_copy(_plan("C"), ex, ex)
    assert "▼ レースの展開" in note_text
    assert "▼ レースの展開" in a_text
    assert "▼ 印と根拠" in a_text
    assert "◎ 1. マスクト" in a_text
    assert "☆ 9. フィフス" in a_text
    assert a_text.count("  ・") == note_text.count("  ・")
    assert "▼ レースの展開" not in x_text
    assert "  ・" not in x_text
    assert "◎：1　マスクト" in x_text
    assert copy_channel_label("S") == "詳細（展開・根拠）"
    assert copy_channel_label("A") == "詳細（展開・根拠）"
    assert copy_channel_label("B") == "簡易（印のみ）"


def test_format_note_race_rich_a_tier():
    text = format_note_race_rich(_plan("A"), _ex_df(), _ex_df())
    assert "期待値A" in text
    assert "▼ レースの展開" in text
    assert "▼ 印と根拠" in text
    assert "△ 5. フォース" in text
    assert "☆ 9. フィフス" in text
    rationale = text.split("▼ 印と根拠", 1)[1]
    assert "  ・" in rationale


def test_format_x_race():
    text = format_x_race(_plan("A"))
    assert "期待値A" in text
    assert "◎：1　マスクト" in text
    assert "X用" not in text
    assert "※" not in text


def test_format_x_race_tier_c_intro():
    text = format_x_race(_plan("C"))
    assert "控えめ" not in text
    assert "◎：1　マスクト" in text
