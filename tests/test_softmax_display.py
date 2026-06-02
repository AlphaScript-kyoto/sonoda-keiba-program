"""表示用モデル確率（温度付き softmax）のテスト。"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import DISPLAY_SOFTMAX_TEMPERATURE, race_display_model_probs, tempered_probabilities


def test_tempered_prob_not_extreme():
    scores = pd.Series([20.0, 8.0, 7.0, 6.0, 5.0])
    raw = tempered_probabilities(scores, temperature=1.0)
    disp = tempered_probabilities(scores, temperature=DISPLAY_SOFTMAX_TEMPERATURE)
    assert float(raw.max()) > 0.99
    assert float(disp.max()) < 0.85
    assert abs(float(disp.sum()) - 1.0) < 1e-6


def test_race_display_model_probs():
    df = pd.DataFrame({"score": [10.0, 8.0, 7.0]})
    top, gap = race_display_model_probs(df)
    assert 0.3 < top < 0.75
    assert gap >= 0
