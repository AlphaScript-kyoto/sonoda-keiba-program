"""特徴量生成の簡易テスト。"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.features.build_features import build_features


def test_no_leakage():
    df = pd.DataFrame(
        {
            "horse_id": ["h1", "h1", "h1"],
            "date": ["20260101", "20260108", "20260115"],
            "race_no": [1, 1, 1],
            "finish": [3, 1, 2],
            "distance": ["1400m", "1400m", "1400m"],
            "track": ["良", "良", "重"],
            "jockey": ["A", "A", "A"],
            "trainer": ["T1", "T1", "T2"],
        }
    )
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = build_features(df)

    assert pd.isna(out.loc[0, "horse_win_rate"])
    assert out.loc[1, "horse_win_rate"] == 0.0
    assert out.loc[2, "horse_win_rate"] == 0.5
    assert out.loc[1, "days_since_last"] == 7
    assert pd.isna(out.loc[0, "jockey_trainer_win_rate"])
    assert out.loc[1, "jockey_trainer_win_rate"] == 0.0
    assert pd.isna(out.loc[2, "jockey_trainer_win_rate"])


def test_jockey_trainer_pair_win_rate():
    df = pd.DataFrame(
        {
            "horse_id": ["h1", "h2", "h3", "h4"],
            "date": ["20260101", "20260108", "20260115", "20260122"],
            "race_no": [1, 1, 1, 1],
            "finish": [1, 2, 1, 3],
            "distance": ["1400m"] * 4,
            "track": ["良"] * 4,
            "jockey": ["A", "A", "A", "B"],
            "trainer": ["T1", "T1", "T1", "T1"],
        }
    )
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = build_features(df)
    row3 = out[out["date"] == "20260115"].iloc[0]
    row4 = out[out["date"] == "20260122"].iloc[0]
    assert row3["jockey_trainer_win_rate"] == 0.5
    assert pd.isna(row4["jockey_trainer_win_rate"])


def test_parse_body_weight():
    from src.features.build_features import parse_body_weight

    assert parse_body_weight("456(+2)") == (456.0, 2.0)
    assert parse_body_weight("480(-4)") == (480.0, -4.0)
    assert parse_body_weight("456") == (456.0, np.nan)


def test_parse_margin_and_race_time():
    from src.features.build_features import (
        parse_distance_m,
        parse_margin,
        parse_race_time,
        race_time_index,
    )

    assert parse_margin("") == 0.0
    assert parse_margin("0.1") == 0.1
    assert parse_margin("3/4") == 0.75
    assert parse_margin("1.3/4") == 1.75
    assert parse_margin("1.1/2") == 1.5
    assert parse_margin("クビ") == 0.2
    assert parse_race_time("1:34.8") == 94.8
    assert parse_distance_m("1400m") == 1400.0
    idx = race_time_index(94.8, 1400.0)
    assert abs(idx - 67.7142857143) < 0.01


def test_phase_c_features_no_leakage():
    from src.features.build_features import build_features, race_time_index

    df = pd.DataFrame(
        {
            "horse_id": ["h1", "h1", "h1"],
            "date": ["20260101", "20260108", "20260115"],
            "race_no": [1, 1, 1],
            "finish": [2, 1, 3],
            "distance": ["1400m", "1400m", "1400m"],
            "track": ["良", "良", "重"],
            "jockey": ["A", "A", "A"],
            "trainer": ["T1", "T1", "T1"],
            "margin": ["1", "", "2"],
            "race_time": ["1:36.0", "1:34.8", "1:37.0"],
        }
    )
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = build_features(df)

    assert pd.isna(out.loc[0, "last3_avg_margin"])
    assert out.loc[1, "last3_avg_margin"] == 1.0
    assert out.loc[2, "last3_avg_margin"] == 0.5
    assert pd.isna(out.loc[0, "horse_best_time_index"])
    assert out.loc[1, "horse_best_time_index"] == race_time_index(96.0, 1400.0)
    assert out.loc[2, "horse_best_time_index"] == race_time_index(94.8, 1400.0)


def test_new_features_no_leakage():
    df = pd.DataFrame(
        {
            "horse_id": ["h1", "h1", "h1"],
            "date": ["20260101", "20260108", "20260115"],
            "race_no": [1, 1, 1],
            "finish": [3, 1, 2],
            "distance": ["1400m", "1400m", "1400m"],
            "track": ["良", "良", "重"],
            "jockey": ["A", "A", "A"],
            "trainer": ["T1", "T1", "T1"],
            "last_3f": ["42.0", "41.0", "40.5"],
            "popularity": ["5", "2", "1"],
            "body_weight": ["450(+2)", "452(0)", "454(+2)"],
        }
    )
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = build_features(df)

    assert pd.isna(out.loc[0, "last3_avg_last3f"])
    assert out.loc[1, "last3_avg_last3f"] == 42.0
    assert out.loc[2, "last3_avg_last3f"] == (42.0 + 41.0) / 2
    assert out.loc[1, "horse_best_last3f"] == 42.0
    assert out.loc[2, "horse_best_last3f"] == 41.0
    assert pd.isna(out.loc[0, "trainer_win_rate"])
    assert out.loc[1, "trainer_win_rate"] == 0.0
    assert out.loc[2, "trainer_win_rate"] == 0.5
    assert pd.isna(out.loc[0, "last_body_weight_delta"])
    assert out.loc[1, "last_body_weight_delta"] == 2.0


if __name__ == "__main__":
    test_no_leakage()
    test_jockey_trainer_pair_win_rate()
    print("ok")
