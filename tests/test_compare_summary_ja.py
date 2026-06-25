"""Japanese odds compare summary tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.snapshot_compare import RaceTimingCompare, format_compare_summary_ja


def _row(**kwargs):
    base = dict(
        race_id="x",
        race_no=1,
        race_name="A",
        snapshot_label="t_minus_10",
        captured_at="2026-06-24T10:00:00",
        fav_odds_live=2.0,
        fav_odds_final=2.5,
        odds_std_live=50.0,
        odds_std_final=55.0,
        upset_live=1,
        upset_final=2,
        win_profile_live="\u5805",
        win_profile_final="\u5805",
        exotic_profile_live="\u5805",
        exotic_profile_final="\u8352",
        confidence_live="\u9ad8",
        confidence_final="\u9ad8",
        exotic_confidence_live="\u9ad8",
        exotic_confidence_final="\u901a\u5e38",
        mark_live="\u25ce",
        mark_final="\u25ce",
        umaban_live="4",
        umaban_final="5",
        win_prob_live=0.3,
        win_prob_final=0.28,
        winner_umaban="4",
        winner_in_live_top3=True,
        winner_in_final_top3=True,
        profile_match=True,
        exotic_profile_match=False,
        mark_match=False,
        confidence_match=True,
        exotic_confidence_match=False,
    )
    base.update(kwargs)
    return RaceTimingCompare(**base)


def test_format_compare_summary_ja():
    msg = format_compare_summary_ja([_row()], date_yyyymmdd="20260624")
    assert "\u30aa\u30c3\u30ba\u5909\u52d5\u30c1\u30a7\u30c3\u30af" in msg
    assert "T-10" in msg
    assert "\u5358\u52dd\u30d7\u30ed\u30d5\u30a3\u30fc\u30eb\u4e00\u81f4: 1/1" in msg
    assert "\u4e09\u9023\u30d7\u30ed\u30d5\u30a3\u30fc\u30eb\u4e00\u81f4: 0/1" in msg
    assert "\u6210\u7e3e\u3067\u306f\u3042\u308a\u307e\u305b\u3093" in msg


def test_format_compare_summary_ja_empty():
    assert format_compare_summary_ja([], date_yyyymmdd="20260624") == ""
