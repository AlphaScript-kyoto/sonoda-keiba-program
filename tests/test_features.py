"""特徴量生成の簡易テスト。"""

import sys
from pathlib import Path

import pandas as pd

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
        }
    )
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = build_features(df)

    assert pd.isna(out.loc[0, "horse_win_rate"])
    assert out.loc[1, "horse_win_rate"] == 0.0
    assert out.loc[2, "horse_win_rate"] == 0.5
    assert out.loc[1, "days_since_last"] == 7


if __name__ == "__main__":
    test_no_leakage()
    print("ok")
