"""
過去レース CSV から特徴量を生成し、マスタ CSV に統合する。

各レース行について「そのレースより前」の成績のみを使い、リークを防ぐ。
"""

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    HORSES_FEATURES_PATH,
    HORSES_MASTER_PATH,
)

FEATURE_COLUMNS = [
    "days_since_last",
    "last3_avg_finish",
    "last5_avg_finish",
    "horse_win_rate",
    "horse_win_rate_distance",
    "horse_win_rate_track",
    "jockey_win_rate",
]


def load_raw_horses(raw_dir: Optional[Path] = None) -> pd.DataFrame:
    """data/raw/horses_*.csv を結合。"""
    raw_dir = raw_dir or DATA_RAW_DIR
    paths = sorted(raw_dir.glob("horses_*.csv"))
    if not paths:
        raise FileNotFoundError(f"{raw_dir} に horses_*.csv がありません")
    frames = [pd.read_csv(p, dtype=str) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df["finish"] = pd.to_numeric(df["finish"], errors="coerce")
    df["date_dt"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df["race_no"] = pd.to_numeric(df["race_no"], errors="coerce")
    df = df.dropna(subset=["horse_id", "date_dt"])
    df = df.sort_values(["date_dt", "race_no", "umaban"], na_position="last")
    df = df.drop_duplicates(subset=["race_id", "horse_id"], keep="last")
    df = df.sort_values(["horse_id", "date_dt", "race_no"]).reset_index(drop=True)
    return df


def _past_win_rate(df: pd.DataFrame, group_key: pd.Series) -> pd.Series:
    """グループ内の過去走のみで1着率（当行は含めない）。"""
    finish_prev = df.groupby(group_key)["finish"].shift(1)
    wins = (finish_prev == 1).astype(float)
    cum_wins = wins.groupby(group_key).cumsum()
    cum_runs = df.groupby(group_key).cumcount()
    return cum_wins / cum_runs.replace(0, np.nan)


def build_features(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    特徴量付き DataFrame を返す。

    追加列: FEATURE_COLUMNS
    """
    if df is None:
        df = load_raw_horses()

    out = df.copy()
    g = out.groupby("horse_id", sort=False)

    out["days_since_last"] = g["date_dt"].diff().dt.days

    out["last3_avg_finish"] = g["finish"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["last5_avg_finish"] = g["finish"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )

    out["horse_win_rate"] = _past_win_rate(out, out["horse_id"])

    dist_key = out["horse_id"].astype(str) + "||" + out["distance"].fillna("").astype(str)
    out["horse_win_rate_distance"] = _past_win_rate(out, dist_key)

    track_key = out["horse_id"].astype(str) + "||" + out["track"].fillna("").astype(str)
    out["horse_win_rate_track"] = _past_win_rate(out, track_key)

    jockey = out["jockey"].fillna("").astype(str)
    out["jockey_win_rate"] = _past_win_rate(out, jockey)

    return out


def _format_master(df: pd.DataFrame) -> pd.DataFrame:
    """マスタ保存用に列順・型を整える。"""
    out = df.copy()
    if "date_dt" in out.columns:
        out["date_sort"] = out["date_dt"]
    else:
        out["date_sort"] = pd.to_datetime(out["date"], format="%Y%m%d", errors="coerce")

    out = out.sort_values(["date_sort", "race_no", "umaban"], na_position="last")
    out = out.drop(columns=["date_dt", "date_sort"], errors="ignore")

    # 数値列は CSV 上で見やすくする程度に丸める
    for col in ("last3_avg_finish", "last5_avg_finish", "horse_win_rate", "horse_win_rate_distance", "horse_win_rate_track", "jockey_win_rate"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(4)

    return out.reset_index(drop=True)


def save_master(df: Optional[pd.DataFrame] = None, path: Optional[Path] = None) -> Path:
    """全列入りマスタ CSV を保存。"""
    path = path or HORSES_MASTER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if df is None:
        df = build_features()
    master = _format_master(df)
    master.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def save_features(df: Optional[pd.DataFrame] = None, path: Optional[Path] = None) -> Path:
    """特徴量付き CSV（features / master 同一内容）を保存。"""
    path = path or HORSES_FEATURES_PATH
    if df is None:
        df = build_features()
    formatted = _format_master(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    formatted.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def build_and_save_all(raw_dir: Optional[Path] = None) -> tuple[Path, Path]:
    """raw 読込 → 特徴量 → features + master の2ファイル保存。"""
    raw = load_raw_horses(raw_dir)
    featured = build_features(raw)
    features_path = save_features(featured)
    master_path = save_master(featured, HORSES_MASTER_PATH)
    return features_path, master_path
