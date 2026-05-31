"""特徴量構築用の共通ユーティリティ。"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

_DISTANCE_M_RE = re.compile(r"(\d+)")


def jockey_trainer_pair_key(
    jockey: pd.Series, trainer: pd.Series
) -> pd.Series:
    return (
        jockey.fillna("").astype(str)
        + "||"
        + trainer.fillna("").astype(str)
    )


def parse_distance_m(text: object) -> float:
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan
    m = _DISTANCE_M_RE.search(str(text))
    if not m:
        return np.nan
    return float(m.group(1))
