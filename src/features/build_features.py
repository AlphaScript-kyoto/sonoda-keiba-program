"""
過去レース CSV から特徴量を生成し、マスタ CSV に統合する。

各レース行について「そのレースより前」の成績のみを使い、リークを防ぐ。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    HORSES_FEATURES_PATH,
    HORSES_MASTER_PATH,
)
from src.storage.csv_store import read_horses_csv

from src.features.constants import STYLE_FEATURE_COLUMNS
from src.features.utils import jockey_trainer_pair_key, parse_distance_m
from src.scraper.bloodline import load_bloodline_cache
from src.scraper.odds import load_odds_cache
from src.scraper.race_lap import load_lap_cache
from src.scraper.running_style import load_style_cache, style_to_score

FEATURE_COLUMNS = [
    "days_since_last",
    "last3_avg_finish",
    "last5_avg_finish",
    "horse_win_rate",
    "horse_win_rate_distance",
    "horse_win_rate_track",
    "jockey_win_rate",
    "jockey_trainer_win_rate",
    "trainer_win_rate",
    "last3_avg_last3f",
    "horse_best_last3f",
    "last3_avg_popularity",
    "last_avg_body_weight",
    "last_body_weight_delta",
    "last3_avg_margin",
    "last3_avg_time_index",
    "horse_best_time_index",
    *STYLE_FEATURE_COLUMNS,
]

RAW_STYLE_COLUMNS = [
    "running_style",
    "corner_pos_avg",
    "race_pace",
    "race_first3f",
    "sire",
    "dam_sire",
]

_BODY_WEIGHT_RE = re.compile(r"^(\d+)(?:\(([+-]?\d+)\))?$")
_MARGIN_FRAC_RE = re.compile(r"^(\d+)\.(\d+)/(\d+)$")
_MARGIN_SIMPLE_FRAC_RE = re.compile(r"^(\d+)/(\d+)$")

_MARGIN_TEXT: dict[str, float] = {
    "クビ": 0.2,
    "ハナ": 0.1,
    "アタマ": 0.1,
    "同": 0.0,
    "大": 10.0,
    "大差": 10.0,
}


def parse_body_weight(text: object) -> Tuple[float, float]:
    """馬体重文字列を (体重, 増減) に分解。例: 456(+2) → (456, 2)"""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan, np.nan
    s = str(text).strip()
    if not s:
        return np.nan, np.nan
    m = _BODY_WEIGHT_RE.match(s)
    if not m:
        return np.nan, np.nan
    weight = float(m.group(1))
    delta = float(m.group(2)) if m.group(2) is not None else np.nan
    return weight, delta


def parse_margin(text: object) -> float:
    """着差文字列を馬身相当の数値に変換。1着（空欄）は 0。"""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return 0.0
    s = str(text).strip()
    if not s:
        return 0.0
    if s in _MARGIN_TEXT:
        return _MARGIN_TEXT[s]

    m = _MARGIN_FRAC_RE.match(s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))

    m = _MARGIN_SIMPLE_FRAC_RE.match(s)
    if m:
        return int(m.group(1)) / int(m.group(2))

    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_race_time(text: object) -> float:
    """走破タイムを秒に変換。例: 1:34.8 → 94.8"""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan
    s = str(text).strip()
    if not s:
        return np.nan
    if ":" in s:
        parts = s.split(":", 1)
        try:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60.0 + seconds
        except ValueError:
            return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def race_time_index(race_time_sec: float, distance_m: float) -> float:
    """1000m あたりの走破秒（小さいほど速い）。"""
    if (
        race_time_sec is None
        or distance_m is None
        or np.isnan(race_time_sec)
        or np.isnan(distance_m)
        or distance_m <= 0
    ):
        return np.nan
    return race_time_sec / (distance_m / 1000.0)


def load_raw_horses(raw_dir: Optional[Path] = None) -> pd.DataFrame:
    """data/raw/horses_*.csv を結合。"""
    raw_dir = raw_dir or DATA_RAW_DIR
    paths = sorted(raw_dir.glob("horses_*.csv"))
    if not paths:
        raise FileNotFoundError(f"{raw_dir} に horses_*.csv がありません")
    frames = [read_horses_csv(p) for p in paths]
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


def _attach_race_meta_from_caches(df: pd.DataFrame) -> pd.DataFrame:
    """style/lap/bloodline キャッシュから raw 列を付与。"""
    out = df.copy()
    style_cache = load_style_cache()
    lap_cache = load_lap_cache()
    blood_cache = load_bloodline_cache()
    odds_cache = load_odds_cache()

    running_styles: list = []
    corner_avgs: list = []
    corner_1: list = []
    corner_2: list = []
    corner_3: list = []
    corner_4: list = []
    race_paces: list = []
    race_first3fs: list = []
    place_odds: list = []
    sires: list = []
    dam_sires: list = []

    for _, row in out.iterrows():
        rid = str(row.get("race_id", ""))
        u = str(row.get("umaban", ""))
        hid = str(row.get("horse_id", ""))

        style_entry = style_cache.get(rid, {}).get("horses", {}).get(u, {})
        running_styles.append(style_entry.get("running_style", ""))
        corner_avgs.append(style_entry.get("corner_pos_avg", np.nan))
        corner_1.append(style_entry.get("corner_pos_1", np.nan))
        corner_2.append(style_entry.get("corner_pos_2", np.nan))
        corner_3.append(style_entry.get("corner_pos_3", np.nan))
        corner_4.append(style_entry.get("corner_pos_4", np.nan))

        lap = lap_cache.get(rid, {})
        race_paces.append(lap.get("pace", ""))
        race_first3fs.append(lap.get("first3f_sec", np.nan))

        odds_entry = odds_cache.get(rid, {})
        place_odds.append(odds_entry.get("place", {}).get(u, ""))

        bl = blood_cache.get(hid, {})
        sires.append(bl.get("sire", ""))
        dam_sires.append(bl.get("dam_sire", ""))

    out["running_style"] = running_styles
    out["corner_pos_avg"] = corner_avgs
    out["corner_pos_1"] = corner_1
    out["corner_pos_2"] = corner_2
    out["corner_pos_3"] = corner_3
    out["corner_pos_4"] = corner_4
    out["race_pace"] = race_paces
    out["race_first3f"] = race_first3fs
    out["place_odds"] = place_odds
    out["sire"] = sires
    out["dam_sire"] = dam_sires
    return out


def build_features(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    特徴量付き DataFrame を返す。

    追加列: FEATURE_COLUMNS
    """
    if df is None:
        df = load_raw_horses()

    df = _attach_race_meta_from_caches(df)
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

    sort_cols = ["date_dt", "race_no"]
    if "umaban" in out.columns:
        sort_cols.append("umaban")
    chron = out.sort_values(sort_cols, na_position="last")
    pair_key = jockey_trainer_pair_key(chron["jockey"], chron["trainer"])
    out.loc[chron.index, "jockey_trainer_win_rate"] = _past_win_rate(chron, pair_key)

    trainer = out["trainer"].fillna("").astype(str)
    out["trainer_win_rate"] = _past_win_rate(out, trainer)

    out["_last3f"] = pd.to_numeric(out.get("last_3f", pd.Series(dtype=str)), errors="coerce")
    out["_popularity"] = pd.to_numeric(out.get("popularity", pd.Series(dtype=str)), errors="coerce")
    parsed = out.get("body_weight", pd.Series(dtype=str)).apply(parse_body_weight)
    out["_body_weight"] = parsed.apply(lambda t: t[0])
    out["_body_weight_delta"] = parsed.apply(lambda t: t[1])

    out["last3_avg_last3f"] = g["_last3f"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["horse_best_last3f"] = g["_last3f"].transform(
        lambda s: s.shift(1).expanding(min_periods=1).min()
    )
    out["last3_avg_popularity"] = g["_popularity"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["last_avg_body_weight"] = g["_body_weight"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["last_body_weight_delta"] = g["_body_weight_delta"].shift(1)

    out["_margin"] = out.get("margin", pd.Series(dtype=str)).apply(parse_margin)
    out["_race_time_sec"] = out.get("race_time", pd.Series(dtype=str)).apply(parse_race_time)
    out["_distance_m"] = out.get("distance", pd.Series(dtype=str)).apply(parse_distance_m)
    out["_time_index"] = out.apply(
        lambda row: race_time_index(row["_race_time_sec"], row["_distance_m"]),
        axis=1,
    )

    out["last3_avg_margin"] = g["_margin"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["last3_avg_time_index"] = g["_time_index"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    out["horse_best_time_index"] = g["_time_index"].transform(
        lambda s: s.shift(1).expanding(min_periods=1).min()
    )

    out["_style_score"] = out.get("running_style", pd.Series(dtype=str)).map(style_to_score)
    out["horse_style_score"] = g["_style_score"].shift(1)
    out["last3_avg_style_score"] = g["_style_score"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    front = out["_style_score"] >= 2.0
    out["_is_front"] = front.astype(float)
    out["style_front_ratio"] = g["_is_front"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()
    )
    out["corner_pos_avg_last"] = g["corner_pos_avg"].shift(1)

    out = out.drop(
        columns=[
            "_last3f",
            "_popularity",
            "_body_weight",
            "_body_weight_delta",
            "_margin",
            "_race_time_sec",
            "_distance_m",
            "_time_index",
            "_style_score",
            "_is_front",
        ],
        errors="ignore",
    )

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
    for col in (
        "last3_avg_finish",
        "last5_avg_finish",
        "horse_win_rate",
        "horse_win_rate_distance",
        "horse_win_rate_track",
        "jockey_win_rate",
        "jockey_trainer_win_rate",
        "trainer_win_rate",
        "last3_avg_last3f",
        "horse_best_last3f",
        "last3_avg_popularity",
        "last_avg_body_weight",
        "last_body_weight_delta",
        "last3_avg_margin",
        "last3_avg_time_index",
        "horse_best_time_index",
        "horse_style_score",
        "last3_avg_style_score",
        "style_front_ratio",
        "corner_pos_avg_last",
    ):
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
