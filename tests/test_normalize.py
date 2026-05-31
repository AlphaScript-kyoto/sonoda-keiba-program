"""正規化のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.normalize import normalize_race_features


def test_normalize_inverts_lower_is_better():
    df = pd.DataFrame({"last3_avg_last3f": [41.0, 42.0, 43.0]})
    out = normalize_race_features(df, ["last3_avg_last3f"])
    z = out["_z_last3_avg_last3f"]
    assert z.iloc[0] > z.iloc[2]


def test_normalize_higher_is_better():
    df = pd.DataFrame({"horse_win_rate": [0.1, 0.2, 0.3]})
    out = normalize_race_features(df, ["horse_win_rate"])
    z = out["_z_horse_win_rate"]
    assert z.iloc[0] < z.iloc[2]
