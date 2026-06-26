"""期待値スコア・ティアのテスト。"""



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))



from src.predictor.bets import RaceBetPlan

from src.predictor.expectation import (

    ExpectationTierConfig,

    apply_expectation_to_plan,

    compute_expectation_score,

    is_s_eligible,

    is_ss_eligible,

    tier_from_score,

)

import pandas as pd

from src.predictor.post_format import format_note_race_rich, format_race_copy, format_x_race

MARK_ROW = {
    "race_no": 1,
    "distance": "1400m",
    "track": "良",
    "race_pace": "H",
    "running_style": "先",
    "horse_style_score": 2.0,
    "pace_style_fit": 0.1,
    "rank_pred": 1,
}





def _cfg() -> ExpectationTierConfig:

    return ExpectationTierConfig.from_dict(

        {

            "tier_min_scores": {"SS": 92, "S": 75, "A": 58, "B": 42, "C": 0},

            "note_tiers": ["SS", "S"],

            "x_tiers": ["A", "B", "C"],

            "venue_label": "園田",

        }

    )





def _plan(**kwargs) -> RaceBetPlan:

    defaults = dict(

        race_id="r1",

        race_no=3,

        race_name="テスト特別",

        confidence="高",

        win_prob_top=0.90,

        prob_gap=0.75,

        marks=[

            ("◎", "1", "サクラ"),

            ("○", "8", "ダノン"),

            ("▲", "2", "メイショウ"),

            ("△", "3", "ウマ"),

            ("☆", "7", "テスト"),

        ],

        exotic_confidence="高",

        exotic_profile="堅",

        win_profile="堅",

        fav_odds=2.5,

    )

    defaults.update(kwargs)

    return RaceBetPlan(**defaults)





def test_exotic_low_scores_zero():

    p = _plan(exotic_confidence="通常")

    assert compute_expectation_score(p) == 0

    apply_expectation_to_plan(p, _cfg())

    assert p.expectation_tier == "C"





def test_firm_high_becomes_s_not_ss_by_default():

    p = _plan(fav_odds=1.5)

    score = compute_expectation_score(p)

    assert 70 <= score < 92

    apply_expectation_to_plan(p, _cfg())

    assert p.expectation_tier == "S"

    assert is_ss_eligible(p)


def test_head_strength_bonus_spreads_s_band():
    base = dict(
        exotic_confidence="高",
        exotic_profile="堅",
        confidence="高",
        win_profile="堅",
        win_prob_top=1.0,
        prob_gap=1.0,
    )
    strong = _plan(fav_odds=1.1, **base)
    weak = _plan(fav_odds=2.6, **base)
    border = _plan(
        fav_odds=1.4,
        win_prob_top=0.91,
        prob_gap=0.82,
        **{k: v for k, v in base.items() if k not in ("win_prob_top", "prob_gap")},
    )
    assert compute_expectation_score(strong) >= 92
    assert 75 <= compute_expectation_score(weak) < 92
    assert compute_expectation_score(weak) < compute_expectation_score(strong)
    assert compute_expectation_score(border) < compute_expectation_score(weak)


def test_ss_requires_score_and_eligibility():

    cfg = _cfg()

    p = _plan(win_prob_top=0.90, prob_gap=0.75, fav_odds=1.3)

    p.expectation_score = 95

    assert is_ss_eligible(p)

    assert tier_from_score(95, cfg, p) == "SS"



    p2 = _plan(exotic_profile="荒", win_prob_top=0.90, prob_gap=0.75, fav_odds=1.3)

    assert not is_ss_eligible(p2)

    assert tier_from_score(95, cfg, p2) == "S"





def test_s_requires_fav_odds_cap():

    cfg = _cfg()

    p = _plan(fav_odds=2.2, win_prob_top=1.0, prob_gap=1.0)

    assert not is_s_eligible(p)

    assert compute_expectation_score(p) >= 75

    assert tier_from_score(compute_expectation_score(p), cfg, p) == "A"

    p_border = _plan(fav_odds=1.7, win_prob_top=1.0, prob_gap=1.0)

    assert not is_s_eligible(p_border)

    assert tier_from_score(compute_expectation_score(p_border), cfg, p_border) == "A"

    p_ok = _plan(fav_odds=1.6, win_prob_top=1.0, prob_gap=1.0)

    assert is_s_eligible(p_ok)

    assert tier_from_score(compute_expectation_score(p_ok), cfg, p_ok) in ("S", "SS")


def test_tier_from_score_boundaries():

    cfg = _cfg()

    assert tier_from_score(92, cfg) == "SS"

    assert tier_from_score(91, cfg) == "S"

    assert tier_from_score(75, cfg) == "S"

    assert tier_from_score(58, cfg) == "A"

    assert tier_from_score(39, cfg) == "C"





def test_format_x_marks_order():

    p = _plan(

        marks=[("△", "3", "ウマ"), ("◎", "1", "サクラ"), ("☆", "7", "テスト")]

    )

    apply_expectation_to_plan(p, _cfg())

    text = format_x_race(p, _cfg())

    body_lines = [ln for ln in text.split("\n") if ln and ln[0] in "◎○▲△☆"]
    assert [ln[0] for ln in body_lines] == ["◎", "△", "☆"]
    assert "◎：1" in text





def _marks_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                **MARK_ROW,
                "umaban": "1",
                "horse_name": "サクラ",
                "win_prob": 0.18,
                "odds": 2.1,
                "popularity": 1,
            }
        ]
    )


def test_format_note_includes_bets_label():
    p = _plan()
    apply_expectation_to_plan(p, _cfg())
    ex = _marks_df()
    text = format_note_race_rich(p, ex, ex)
    assert "期待値" in text
    assert "◎ 1. サクラ" in text
    assert "▼ 印と根拠" in text
    assert "▼ このレースの見方" not in text
    assert "買い目の目安" not in text


def test_format_race_copy_routes_by_tier():
    p = _plan()
    apply_expectation_to_plan(p, _cfg())
    p.expectation_tier = "C"
    ex = _marks_df()
    text = format_race_copy(p, ex, ex)
    assert "▼ このレースの見方" not in text
    assert "◎：1" in text


