from src.predictor.t10_daily_roi import (
    T10DailyRoiReport,
    T10RaceRoi,
    _should_buy_place,
    format_t10_daily_roi_message,
    is_tier_s_plus,
)


def test_is_tier_s_plus():
    assert is_tier_s_plus("SS")
    assert is_tier_s_plus("S")
    assert not is_tier_s_plus("A")
    assert not is_tier_s_plus("C")


def test_should_buy_place_min_odds():
    snap = {"odds": {"place": {"1": "1.6 - 2.5", "2": "1.2 - 1.4"}}}
    assert _should_buy_place(snap, "1")
    assert not _should_buy_place(snap, "2")
    assert not _should_buy_place(snap, "9")


def test_format_empty_report():
    msg = format_t10_daily_roi_message(T10DailyRoiReport(date="20260618"))
    assert "1.5倍以上" in msg
    assert "対象レースなし" in msg


def test_format_race_line():
    report = T10DailyRoiReport(
        date="20260618",
        races=[
            T10RaceRoi(
                race_id="x",
                race_no=3,
                race_name="テストレース",
                expectation_tier="S",
                expectation_score=80,
                win_points=1,
                place_points=2,
                sanren_points=5,
                investment=800,
                return_yen=1200,
                win_hit=True,
                place_hits=1,
            )
        ],
    )
    msg = format_t10_daily_roi_message(report)
    assert "R3" in msg
    assert "回収150%" in msg
    assert "合計 1R" in msg
