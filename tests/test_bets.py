"""馬券フォーメーション生成のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import (
    BetStrategyConfig,
    ConfidenceThresholds,
    DEFAULT_STRATEGY,
    assign_marks,
    build_race_bet_plan,
    collect_race_signals,
    detect_exotic_profile,
    detect_win_profile,
    assign_marks,
    build_sanrenpuku_box,
    build_sanrenpuku_formation_firm,
    build_sanrenpuku_nagashi,
    build_sanrentan_formation,
    build_wide_formation,
    check_sanrenpuku_box_hit,
    check_sanrenpuku_formation_firm_hit,
    check_sanrenpuku_hit,
    check_sanrentan_hit,
    check_wide_hits,
    is_high_confidence,
    matches_threshold,
)

OLD_THRESHOLDS = ConfidenceThresholds(
    win_prob=0.30, win_prob_alt=0.22, prob_gap=0.12, mode="or"
)


def _sample_race(probs: list[float]) -> pd.DataFrame:
    rows = []
    for i, p in enumerate(probs, start=1):
        rows.append(
            {
                "race_id": "r1",
                "race_no": 1,
                "race_name": "テスト",
                "umaban": str(i),
                "horse_name": f"馬{i}",
                "rank_pred": i,
                "win_prob": p,
            }
        )
    return pd.DataFrame(rows)


def test_high_confidence_by_win_prob():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08, 0.07])
    high, p1, gap = is_high_confidence(race, OLD_THRESHOLDS)
    assert high is True
    assert p1 == 0.35
    assert abs(gap - 0.15) < 1e-9


def test_high_confidence_by_gap():
    race = _sample_race([0.24, 0.10, 0.10, 0.10, 0.08, 0.07])
    high, _, gap = is_high_confidence(race, OLD_THRESHOLDS)
    assert high is True
    assert abs(gap - 0.14) < 1e-9


def test_not_high_confidence():
    race = _sample_race([0.18, 0.16, 0.15, 0.14, 0.13, 0.12])
    high, _, _ = is_high_confidence(race)
    assert high is False


def test_sanrenpuku_nagashi_points():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = race.sort_values("rank_pred").head(5)
    nagashi = build_sanrenpuku_nagashi(top5)
    assert nagashi is not None
    assert nagashi.axis_umaban == "1"
    assert nagashi.partner_umaban == ["2", "3", "4", "5"]
    assert nagashi.points == 6


def test_sanrenpuku_formation_firm_points():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = assign_marks(race.sort_values("rank_pred").head(5))
    formation = build_sanrenpuku_formation_firm(top5)
    assert formation is not None
    assert formation.points == 5
    assert formation.key_partner_umaban == ["2", "3"]
    assert check_sanrenpuku_formation_firm_hit(formation, ["1", "2", "4"])
    assert check_sanrenpuku_formation_firm_hit(formation, ["1", "3", "5"])
    assert not check_sanrenpuku_formation_firm_hit(formation, ["1", "4", "5"])


def test_sanrentan_formation_tickets():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = race.sort_values("rank_pred").head(5)
    formation = build_sanrentan_formation(top5)
    assert formation is not None
    assert formation.points == 4
    assert ("1", "2", "4") in formation.tickets
    assert ("1", "2", "5") in formation.tickets
    assert ("1", "3", "4") in formation.tickets
    assert ("1", "3", "5") in formation.tickets


def test_bet_plan_includes_bets_when_high():
    race = _sample_race([0.90, 0.10, 0.05, 0.03, 0.02, 0.01])
    race["odds"] = [1.5, 3.0, 5.0, 8.0, 12.0, 20.0]
    race["head_count"] = 10
    plan = build_race_bet_plan(race)
    assert plan.confidence == "高"
    assert plan.exotic_confidence == "高"
    assert plan.win_profile == "堅"
    assert plan.exotic_profile == "堅"
    assert plan.sanrenpuku is not None
    assert plan.sanrentan is not None
    assert plan.wide is not None
    assert plan.wide.points == 2
    assert plan.marks[0][0] == "◎"


def test_win_confidence_with_old_thresholds():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08, 0.07])
    race["odds"] = [2.0, 4.0, 6.0, 10.0, 15.0, 20.0]
    plan = build_race_bet_plan(race, OLD_THRESHOLDS)
    assert plan.confidence == "高"


def test_upset_profile_uses_formation():
    race = _sample_race([0.82, 0.10, 0.04, 0.02, 0.01, 0.01])
    race["odds"] = [4.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    race["head_count"] = 12
    plan = build_race_bet_plan(race)
    assert plan.win_profile == "荒"
    assert plan.exotic_profile == "荒"
    assert plan.sanrenpuku is None
    assert plan.sanrenpuku_box is None
    assert plan.sanrenpuku_formation is not None
    assert plan.sanrenpuku_formation.points == 5
    assert plan.sanrentan is None
    assert plan.wide is not None
    assert plan.wide.points == 3


def test_split_win_firm_exotic_upset():
    """混戦(score3)・1番人気2.8倍: 単勝は買う、三連系は5点フォーメーション。"""
    race = _sample_race([0.87, 0.23, 0.10, 0.08, 0.06, 0.05])
    race["odds"] = [2.8, 4.0, 6.0, 10.0, 15.0, 20.0]
    race["head_count"] = 12
    plan = build_race_bet_plan(race)
    assert plan.win_profile == "堅"
    assert plan.exotic_profile == "荒"
    assert plan.confidence == "高"
    assert plan.sanrenpuku is None
    assert plan.sanrenpuku_formation is not None


def test_volatile_firm_uses_wide_upset():
    """12頭・堅い三連系でもワイドは拡張。"""
    probs = [0.90, 0.05, 0.02, 0.01, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005]
    rows = []
    for i, p in enumerate(probs, start=1):
        rows.append(
            {
                "race_id": "r1",
                "race_no": 1,
                "race_name": "テスト",
                "umaban": str(i),
                "horse_name": f"馬{i}",
                "rank_pred": i,
                "win_prob": p,
                "odds": 1.8 if i == 1 else float(i * 3),
            }
        )
    race = pd.DataFrame(rows)
    race["head_count"] = 12
    plan = build_race_bet_plan(race)
    assert plan.win_profile == "堅"
    assert plan.exotic_profile == "堅"
    assert plan.sanrenpuku is not None
    assert plan.wide is not None
    assert plan.wide.points == 3


def test_sanrenpuku_box_hit():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = race.sort_values("rank_pred").head(5)
    box = build_sanrenpuku_box(top5, race)
    assert check_sanrenpuku_box_hit(box, ["1", "2", "3"])
    assert not check_sanrenpuku_box_hit(box, ["2", "3", "6"])


def test_class_upset_profile():
    """下位クラス + upset_score>=2 → 荒。"""
    race = _sample_race([0.85, 0.08, 0.04, 0.02, 0.005, 0.005])
    race["odds"] = [2.0, 5.0, 8.0, 12.0, 20.0, 30.0]
    race["head_count"] = 12
    race["race_class"] = "C2"
    race["distance"] = "1400m"
    signals = collect_race_signals(race, 0.85, 0.77)
    assert signals.upset_score >= 2
    assert detect_exotic_profile(signals) == "荒"


def test_distance_upset_profile():
    """1700m+ + upset_score>=2 → 荒。"""
    race = _sample_race([0.85, 0.06, 0.04, 0.02, 0.015, 0.015])
    race["odds"] = [2.0, 5.0, 8.0, 12.0, 20.0, 30.0]
    race["head_count"] = 12
    race["race_class"] = "B1"
    race["distance"] = "1870m"
    signals = collect_race_signals(race, 0.85, 0.79)
    assert signals.upset_score >= 2
    assert detect_exotic_profile(signals) == "荒"


def test_hit_checks():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = race.sort_values("rank_pred").head(5)
    nagashi = build_sanrenpuku_nagashi(top5)
    formation = build_sanrentan_formation(top5)
    wide = build_wide_formation(top5)
    assert check_sanrenpuku_hit(nagashi, ["1", "2", "3"])
    assert not check_sanrenpuku_hit(nagashi, ["2", "3", "4"])
    assert check_sanrentan_hit(formation, ["1", "2", "4"])
    assert not check_sanrentan_hit(formation, ["1", "4", "2"])
    assert check_wide_hits(wide, ["1", "2", "5"]) == [("1", "2")]
    assert check_wide_hits(wide, ["2", "3", "4"]) == []
