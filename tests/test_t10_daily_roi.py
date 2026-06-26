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
    assert "\u3010\u5712\u7530 6\u670818\u65e5 \u8cb7\u3044\u76ee\u306e\u6210\u7e3e\u3011" in msg
    assert "\u30ec\u30fc\u30b910\u5206\u524d" in msg
    assert "1.5\u500d\u4ee5\u4e0a" in msg
    assert "\u5bfe\u8c61\u30ec\u30fc\u30b9\u306a\u3057" in msg


def test_format_race_line():
    report = T10DailyRoiReport(
        date="20260618",
        races=[
            T10RaceRoi(
                race_id="x",
                race_no=3,
                race_name="テストレース",
                race_class="C3三",
                expectation_tier="S",
                expectation_score=80,
                win_points=1,
                place_points=2,
                sanren_points=5,
                investment=800,
                return_yen=1200,
                win_hit=True,
                place_hits=1,
                win_bought=True,
                win_umaban="11",
                place_umabans=["11", "12"],
                sanren_display="11-12,3-12,3,4,5(計5点)",
            )
        ],
    )
    msg = format_t10_daily_roi_message(report)
    assert "3R" in msg
    assert "期待値S" in msg
    assert "単勝　11" in msg
    assert "複勝　11,12" in msg
    assert "三連複　11-12,3-12,3,4,5(計5点)" in msg
    assert "投800円" in msg
    assert "回収150%" in msg
    assert "【当日合計】" in msg
    assert "回収率 150%" in msg
    assert "対象 1R" in msg
