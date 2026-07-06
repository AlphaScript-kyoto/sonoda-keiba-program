"""Upset x High / P6 daily ROI message tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.upset_high_daily_roi import (
    UpsetHighDailyBet,
    UpsetHighDailyRoiReport,
    format_p6_daily_roi_message,
    format_upset_high_daily_roi_message,
)


def test_format_empty_no_qualifying():
    msg = format_p6_daily_roi_message(UpsetHighDailyRoiReport(date="20260619"))
    assert "P6\u5b9f\u7e3e" in msg
    assert "\u672c\u65e5\u306e\u8cb7\u3044\u76ee\u306a\u3057" in msg
    assert "\u4f11\u6b62\u306a\u3057\u3067\u5168\u8cfc\u5165" not in msg


def test_format_empty_with_qualifying_paused():
    msg = format_p6_daily_roi_message(
        UpsetHighDailyRoiReport(
            date="20260619",
            qualifying_count=2,
            paused=True,
            continuous_bets=[
                UpsetHighDailyBet(3, "C3", 500, 0, False),
                UpsetHighDailyBet(8, "B2", 500, 1200, True),
            ],
        )
    )
    assert "\u4f11\u6b62\u4e2d\u306e\u305f\u3081\u898b\u9001\u308a" in msg
    assert "R3" not in msg
    assert "\u203b\u4f11\u6b62\u4e2d" in msg


def test_format_with_bets():
    report = UpsetHighDailyRoiReport(
        date="20260619",
        bets=[UpsetHighDailyBet(3, "C3", 500, 1200, True)],
        consecutive_misses=1,
        rolling_roi_pct=85.0,
    )
    msg = format_p6_daily_roi_message(report)
    assert "R3" in msg
    assert "\u6295500" in msg
    assert "\u56de\u53ce240%" in msg
    assert "\u5408\u8a08 1R" in msg
    assert "\u76f4\u8fd110R ROI" not in msg


def test_alias_format_upset_high_daily_roi_message():
    report = UpsetHighDailyRoiReport(
        date="20260619",
        bets=[UpsetHighDailyBet(3, "C3", 500, 0, False)],
    )
    assert format_upset_high_daily_roi_message(report) == format_p6_daily_roi_message(report)
