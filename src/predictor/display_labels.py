"""UI 表示用の日本語ラベル。"""

from __future__ import annotations

import pandas as pd

RACE_TABLE_COLUMNS: dict[str, str] = {
    "mark": "印",
    "rank_pred": "三連予想順",
    "umaban": "馬番",
    "horse_name": "馬名",
    "win_prob": "モデル確率",
    "horse_win_rate": "勝率",
    "horse_place_rate": "連対率",
    "odds": "オッズ",
    "popularity": "人気",
    "score": "スコア",
    "jockey_trainer_win_rate": "騎調教勝率",
    "last3_avg_finish": "近3走平均着",
}


def format_race_table_for_display(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """表示用に列を選び、ヘッダを日本語化。"""
    cols = [c for c in columns if c in df.columns]
    out = df[cols].copy()
    if "win_prob" in out.columns and out["win_prob"].dtype != object:
        out["win_prob"] = out["win_prob"].map(lambda x: f"{float(x):.1%}" if pd.notna(x) else "")
    if "horse_win_rate" in out.columns and out["horse_win_rate"].dtype != object:
        out["horse_win_rate"] = out["horse_win_rate"].map(
            lambda x: f"{float(x):.1%}" if pd.notna(x) else ""
        )
    if "horse_place_rate" in out.columns and out["horse_place_rate"].dtype != object:
        out["horse_place_rate"] = out["horse_place_rate"].map(
            lambda x: f"{float(x):.1%}" if pd.notna(x) else ""
        )
    rename = {k: v for k, v in RACE_TABLE_COLUMNS.items() if k in out.columns}
    return out.rename(columns=rename)
