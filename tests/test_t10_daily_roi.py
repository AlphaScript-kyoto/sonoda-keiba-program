from src.predictor.t10_daily_roi import (
    T10DailyRoiReport,
    T10RaceRoi,
    format_s_plus_buy_line_message,
    format_t10_daily_roi_message,
    is_tier_s_plus,
)


def test_is_tier_s_plus():
    assert is_tier_s_plus("SS")
    assert is_tier_s_plus("S")
    assert not is_tier_s_plus("A")
    assert not is_tier_s_plus("C")


def test_format_empty_report():
    msg = format_t10_daily_roi_message(T10DailyRoiReport(date="20260618"))
    assert "\u3010\u5712\u7530 6\u670818\u65e5 \u8cb7\u3044\u76ee\u306e\u6210\u7e3e\u3011" in msg
    assert "\u30ec\u30fc\u30b910\u5206\u524d" in msg
    assert "\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f35\u70b9" in msg
    assert "\u5358\u52dd" not in msg
    assert "\u8907\u52dd" not in msg
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
                sanren_points=5,
                investment=500,
                return_yen=1200,
                sanren_hit=True,
                sanren_display="11-12,3-12,3,4,5(計5点)",
            )
        ],
    )
    msg = format_t10_daily_roi_message(report)
    assert "3R" in msg
    assert "期待値S" in msg
    assert "三連複　11-12,3-12,3,4,5(計5点)" in msg
    assert "単勝" not in msg
    assert "複勝" not in msg
    assert "投500円" in msg
    assert "回収240%" in msg
    assert "【当日合計】" in msg
    assert "回収率 240%" in msg
    assert "対象 1R" in msg
    assert "（三連複1）" in msg


def test_format_s_plus_buy_line_message():
    import pandas as pd

    from src.predictor.bets import RaceBetPlan

    plan = RaceBetPlan(
        race_id="r1",
        race_no=4,
        race_name="テスト",
        confidence="高",
        exotic_confidence="高",
        win_profile="堅",
        exotic_profile="堅",
        race_profile="堅",
        fav_odds=1.3,
        win_prob_top=0.9,
        prob_gap=0.2,
        marks=[],
        post_time="12:10",
        expectation_tier="SS",
        expectation_score=95,
    )
    top5 = pd.DataFrame(
        {
            "umaban": ["1", "2", "3", "4", "5"],
            "horse_name": ["A", "B", "C", "D", "E"],
            "mark": ["◎", "○", "▲", "△", "☆"],
        }
    )
    msg = format_s_plus_buy_line_message(
        plan, top5, header_line="4R\u300012:10\u767a\u8d70\u3000\u30c6\u30b9\u30c8"
    )
    assert msg is not None
    assert "【買い目】期待値SS" in msg
    assert "三連複フォーメーション5点" in msg
    assert "1-2,3" in msg
    assert "計5点" in msg
