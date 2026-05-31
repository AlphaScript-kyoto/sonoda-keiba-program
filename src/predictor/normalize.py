"""レース内 z-score 正規化。"""

from __future__ import annotations

from typing import AbstractSet, Dict, Iterable

import numpy as np
import pandas as pd

# 値が小さいほど良い特徴量（正規化前に符号反転）
LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "last3_avg_finish",
        "last5_avg_finish",
        "days_since_last",
        "last3_avg_last3f",
        "horse_best_last3f",
        "last3_avg_popularity",
        "last_body_weight_delta",
        "entry_carried_weight",
        "entry_body_weight_delta",
        "body_weight_vs_avg",
        "last_avg_body_weight",
        "last3_avg_margin",
        "last3_avg_time_index",
        "horse_best_time_index",
        "corner_pos_avg_last",
        "entry_head_count",
    }
)


def normalize_race_features(
    df: pd.DataFrame,
    feature_cols: Iterable[str],
    *,
    lower_is_better: AbstractSet[str] = LOWER_IS_BETTER,
    prefix: str = "_z_",
) -> pd.DataFrame:
    """レース内 z-score。低いほど良い列は反転して「高いほど良い」に統一。"""
    out = df.copy()
    for feat in feature_cols:
        col = f"{prefix}{feat}"
        if feat in out.columns:
            raw = pd.to_numeric(out[feat], errors="coerce")
        else:
            raw = pd.Series(np.nan, index=out.index, dtype=float)
        if feat in lower_is_better:
            raw = -raw
        mean = raw.mean()
        std = raw.std()
        if std is None or std == 0 or np.isnan(std):
            out[col] = raw.fillna(0.0) * 0.0
        else:
            out[col] = ((raw - mean) / std).fillna(0.0)
    return out


def z_column(feat: str, prefix: str = "_z_") -> str:
    return f"{prefix}{feat}"
