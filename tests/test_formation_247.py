"""formation_247 tests."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import RaceSignals, check_sanrenpuku_box_hit
from src.predictor.formation_247 import (
    build_sanrenpuku_247_box,
    is_247_target_race,
    parse_place_odds_low,
    select_247_horses,
)


def test_parse_place_odds_low():
    assert parse_place_odds_low("1.5-2.8") == 1.5
    assert parse_place_odds_low("3.2") == 3.2


def _sample_master():
    rows = []
    for i in range(1, 13):
        for d in ("20260101", "20260201", "20260301"):
            rows.append(
                {
                    "horse_id": f"h{i:02d}",
                    "date": d,
                    "finish": "1" if i <= 3 else "5",
                }
            )
    return pd.DataFrame(rows)


def _sample_race():
    rows = []
    for i in range(1, 13):
        rows.append(
            {
                "race_id": "r1",
                "date": "20260610",
                "race_no": 1,
                "horse_id": f"h{i:02d}",
                "horse_name": f"H{i}",
                "umaban": str(i),
                "popularity": str(i),
                "odds": str(2 + i * 1.5),
                "place_odds": "1.2-1.5" if i <= 2 else "3.0-5.0",
                "race_class": "C3",
                "distance": "1200m",
            }
        )
    return pd.DataFrame(rows)


def test_select_247_horses_six():
    race = _sample_race()
    master = _sample_master()
    horses = select_247_horses(race, master, "20260610")
    assert horses is not None
    assert len(horses) == 6


def test_build_box_points():
    race = _sample_race()
    master = _sample_master()
    box = build_sanrenpuku_247_box(race, master, "20260610")
    assert box is not None
    assert box.points == 20


def test_is_247_target_upset():
    race = _sample_race()
    sig = RaceSignals(
        fav_odds=4.0,
        head_count=12,
        odds_std=90.0,
        win_prob_top=0.5,
        prob_gap=0.1,
        upset_score=4,
        race_class="C3",
        distance_m=1200.0,
    )
    assert is_247_target_race(race, sig, exotic_profile="\u8352")
