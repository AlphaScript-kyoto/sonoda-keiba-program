"""過去 CSV からの簡易勝率集計（骨格）。"""

from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import DATA_RAW_DIR
from src.storage.csv_store import read_horses_csv


def load_all_horse_csvs(raw_dir: Optional[Path] = None) -> pd.DataFrame:
    """data/raw/ 内の horses_*.csv を結合して返す。"""
    raw_dir = raw_dir or DATA_RAW_DIR
    paths = sorted(raw_dir.glob("horses_*.csv"))
    if not paths:
        raise FileNotFoundError(
            f"{raw_dir} に horses_*.csv がありません。"
            "先に fetch_races.py でデータを取得してください。"
        )
    frames = [read_horses_csv(p) for p in paths]
    return pd.concat(frames, ignore_index=True)


def calc_horse_win_rates(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    馬ごとの1着率を計算する（horse_id があれば ID で集計）。

    Returns:
        columns: horse_id, horse_name, runs, wins, win_rate
    """
    if df is None:
        df = load_all_horse_csvs()

    df = df.copy()
    df["finish"] = pd.to_numeric(df["finish"], errors="coerce")

    key = "horse_id" if "horse_id" in df.columns and df["horse_id"].notna().any() else "horse_name"
    df = df.dropna(subset=[key, "finish"])
    df = df[df[key].astype(str).str.len() > 0]

    if key == "horse_id":
        grouped = df.groupby("horse_id", as_index=False).agg(
            horse_name=("horse_name", "last"),
            runs=("finish", "count"),
            wins=("finish", lambda s: (s == 1).sum()),
        )
    else:
        grouped = df.groupby("horse_name", as_index=False).agg(
            runs=("finish", "count"),
            wins=("finish", lambda s: (s == 1).sum()),
        )
    grouped["win_rate"] = grouped["wins"] / grouped["runs"]
    return grouped.sort_values("win_rate", ascending=False).reset_index(drop=True)
