"""馬券フォーメーション生成のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import (
    ConfidenceThresholds,
    build_race_bet_plan,
    build_sanrenpuku_box,
    build_sanrenpuku_nagashi,
    build_sanrentan_formation,
    build_wide_formation,
    check_sanrenpuku_box_hit,
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
    assert plan.race_profile == "堅"
    assert plan.sanrenpuku is not None
    assert plan.sanrentan is not None
    assert plan.wide is not None
    assert plan.wide.points == 2
    assert plan.marks[0][0] == "◎"


def test_win_confidence_with_old_thresholds():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08, 0.07])
    plan = build_race_bet_plan(race, OLD_THRESHOLDS)
    assert plan.confidence == "高"


def test_upset_profile_uses_box():
    race = _sample_race([0.82, 0.10, 0.04, 0.02, 0.01, 0.01])
    race["odds"] = [4.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    race["head_count"] = 12
    plan = build_race_bet_plan(race)
    assert plan.race_profile == "荒"
    assert plan.sanrenpuku is None
    assert plan.sanrenpuku_box is not None
    assert plan.sanrenpuku_box.points >= 10
    assert plan.sanrentan is None
    assert plan.wide is not None
    assert plan.wide.points == 3


def test_sanrenpuku_box_hit():
    race = _sample_race([0.35, 0.20, 0.15, 0.10, 0.08])
    top5 = race.sort_values("rank_pred").head(5)
    box = build_sanrenpuku_box(top5, race)
    assert check_sanrenpuku_box_hit(box, ["1", "2", "3"])
    assert not check_sanrenpuku_box_hit(box, ["2", "3", "4"])


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
