"""
園田競馬場のドメイン知識を特徴量に落とし込む。

ユーザーの主観・コース分析を数値化:
- 先行・逃げ有利（園田全体）
- 1400m 外枠先行有利 / 内枠先行不利
- 馬場状態 × 脚質
- 距離帯 × 枠番
- 騎手×厩舎 ROI
- 季節 × 馬体重増減
- ラップペース × 脚質適性
- 父・母父血統（ダート70% / 小回り30%）
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.features.constants import (
    DOMAIN_COMPUTED_FEATURES,
    DOMAIN_FEATURE_COLUMNS,
    DOMAIN_LOOKUP_FEATURES,
    STYLE_FEATURE_COLUMNS,
)
from src.features.utils import jockey_trainer_pair_key, parse_distance_m
from src.scraper.running_style import style_to_score

DISTANCE_BUCKETS = {
    "1230": (0, 1230),
    "1400": (1231, 1400),
    "1700+": (1701, 9999),
}


def distance_bucket(distance_m: float) -> str:
    if distance_m is None or (isinstance(distance_m, float) and np.isnan(distance_m)):
        return ""
    d = float(distance_m)
    if d <= 1230:
        return "1230"
    if d <= 1400:
        return "1400"
    return "1700+"


def month_from_date(date_yyyymmdd: str) -> int:
    s = str(date_yyyymmdd)
    if len(s) >= 6:
        return int(s[4:6])
    return 0


def season_weight_score(month: int, body_weight_delta: float) -> float:
    """
    季節 × 馬体重増減の適合スコア。
    夏(6-9): 絞り気味(+/-小) / 冬(11-2): ややプラス許容
    """
    if month == 0 or body_weight_delta != body_weight_delta:
        return 0.0
    delta = float(body_weight_delta)
    if 6 <= month <= 9:
        return -abs(delta) * 0.02
    if month in (11, 12, 1, 2):
        if -10 <= delta <= 15:
            return 0.15
        return -abs(delta - 5) * 0.01
    return 0.0


def sonoda_waku_style_fit(
    waku: float,
    style_score: float,
    distance_m: float,
) -> float:
    """
    枠番 × 脚質 × 距離の適合度。
    1400m: 外枠(6+)×先行/逃げボーナス、内枠(1-3)×先行ペナルティ
    """
    if waku != waku or style_score != style_score:
        return 0.0
    w = float(waku)
    s = float(style_score)
    bucket = distance_bucket(distance_m)
    score = 0.0
    if bucket == "1400" and s >= 2.0:
        if w >= 6:
            score += 0.35
        elif w <= 3:
            score -= 0.25
    if s >= 2.0:
        score += 0.15
    elif s <= 0.5:
        score -= 0.10
    return score


def pace_style_fit(pace: str, style_score: float) -> float:
    """Hペース=先行有利、Sペース=差し・追込に微加点。"""
    if style_score != style_score:
        return 0.0
    s = float(style_score)
    p = str(pace).upper()
    if p == "H":
        return 0.2 if s >= 2.0 else -0.05
    if p == "S":
        return 0.15 if s <= 1.0 else -0.05
    return 0.0


def lookup_waku_distance_win_rate(
    master: pd.DataFrame,
    before_date: str,
) -> Dict[str, float]:
    hist = master[master["date"].astype(str) < before_date].copy()
    if hist.empty:
        return {}
    waku = pd.to_numeric(hist.get("waku"), errors="coerce")
    dist = hist.get("distance", pd.Series(dtype=str)).apply(parse_distance_m)
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    valid = waku.notna() & dist.notna()
    if not valid.any():
        return {}
    keys = (
        waku.loc[valid].astype(int).astype(str)
        + "||"
        + dist.loc[valid].apply(distance_bucket)
    )
    stats = pd.DataFrame({"key": keys, "win": finish.loc[valid] == 1})
    grouped = stats.groupby("key", sort=False)
    return (grouped["win"].sum() / grouped.size()).astype(float).to_dict()


def lookup_style_track_win_rate(
    master: pd.DataFrame,
    before_date: str,
) -> Dict[str, float]:
    hist = master[master["date"].astype(str) < before_date].copy()
    if hist.empty or "running_style" not in hist.columns:
        return {}
    style = hist["running_style"].fillna("").astype(str)
    track = hist.get("track", pd.Series(dtype=str)).fillna("").astype(str)
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    valid = style.str.len().gt(0) & track.str.len().gt(0)
    if not valid.any():
        return {}
    keys = style.loc[valid] + "||" + track.loc[valid]
    stats = pd.DataFrame({"key": keys, "win": finish.loc[valid] == 1})
    grouped = stats.groupby("key", sort=False)
    return (grouped["win"].sum() / grouped.size()).astype(float).to_dict()


def lookup_jockey_trainer_roi(
    master: pd.DataFrame,
    before_date: str,
) -> Dict[str, float]:
    """騎手×厩舎の単勝回収率（100円投資あたり払戻/投資）。"""
    hist = master[master["date"].astype(str) < before_date].copy()
    if hist.empty:
        return {}
    pair = jockey_trainer_pair_key(hist["jockey"], hist["trainer"])
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    odds = pd.to_numeric(hist.get("odds"), errors="coerce")
    valid = pair.str.len().gt(0) & odds.notna() & (odds > 0)
    if not valid.any():
        return {}
    payout = np.where(finish.loc[valid] == 1, odds.loc[valid] * 100.0, 0.0)
    stats = pd.DataFrame({"pair": pair.loc[valid], "payout": payout})
    grouped = stats.groupby("pair", sort=False)
    return (grouped["payout"].sum() / (grouped.size() * 100.0)).astype(float).to_dict()


def lookup_sire_win_rate(
    master: pd.DataFrame,
    before_date: str,
) -> Dict[str, float]:
    if "sire" not in master.columns:
        return {}
    hist = master[master["date"].astype(str) < before_date].copy()
    sire = hist["sire"].fillna("").astype(str).str.strip()
    valid = sire.str.len().gt(0)
    if not valid.any():
        return {}
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    stats = pd.DataFrame({"sire": sire.loc[valid], "win": finish.loc[valid] == 1})
    grouped = stats.groupby("sire", sort=False)
    return (grouped["win"].sum() / grouped.size()).astype(float).to_dict()


def lookup_dam_sire_win_rate(
    master: pd.DataFrame,
    before_date: str,
) -> Dict[str, float]:
    if "dam_sire" not in master.columns:
        return {}
    hist = master[master["date"].astype(str) < before_date].copy()
    ds = hist["dam_sire"].fillna("").astype(str).str.strip()
    valid = ds.str.len().gt(0)
    if not valid.any():
        return {}
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    stats = pd.DataFrame({"dam_sire": ds.loc[valid], "win": finish.loc[valid] == 1})
    grouped = stats.groupby("dam_sire", sort=False)
    return (grouped["win"].sum() / grouped.size()).astype(float).to_dict()


def apply_domain_lookups(
    df: pd.DataFrame,
    master: pd.DataFrame,
    before_date: str,
    lap_pace: str = "",
) -> pd.DataFrame:
    out = df.copy()
    waku_dist = lookup_waku_distance_win_rate(master, before_date)
    style_track = lookup_style_track_win_rate(master, before_date)
    jt_roi = lookup_jockey_trainer_roi(master, before_date)
    sire_rates = lookup_sire_win_rate(master, before_date)
    dam_sire_rates = lookup_dam_sire_win_rate(master, before_date)

    waku = pd.to_numeric(out.get("waku"), errors="coerce")
    dist_m = out.get("distance", pd.Series(dtype=str)).apply(parse_distance_m)
    bucket = dist_m.apply(distance_bucket)
    waku_keys = pd.Series("", index=out.index, dtype=str)
    for idx in out.index:
        w = waku.loc[idx]
        b = bucket.loc[idx]
        if pd.notna(w) and b:
            waku_keys.loc[idx] = f"{int(w)}||{b}"
    out["waku_distance_win_rate"] = waku_keys.map(waku_dist)

    style = out.get("entry_running_style", out.get("running_style", pd.Series(dtype=str)))
    track = out.get("track", pd.Series(dtype=str)).fillna("").astype(str)
    st_keys = style.fillna("").astype(str) + "||" + track
    out["style_track_win_rate"] = st_keys.map(style_track)

    pair = jockey_trainer_pair_key(out["jockey"], out["trainer"])
    out["jockey_trainer_roi"] = pair.map(jt_roi)

    if "sire" in out.columns:
        out["sire_win_rate"] = out["sire"].fillna("").astype(str).str.strip().map(sire_rates)
    else:
        out["sire_win_rate"] = np.nan
    if "dam_sire" in out.columns:
        out["dam_sire_win_rate"] = (
            out["dam_sire"].fillna("").astype(str).str.strip().map(dam_sire_rates)
        )
    else:
        out["dam_sire_win_rate"] = np.nan

    style_score = pd.to_numeric(out.get("horse_style_score", pd.Series(index=out.index, dtype=float)), errors="coerce")
    if "entry_running_style" in out.columns:
        style_score = style_score.fillna(out["entry_running_style"].map(style_to_score))
    months = out["date"].astype(str).map(month_from_date)
    bw_delta = pd.to_numeric(out.get("entry_body_weight_delta", pd.Series(index=out.index, dtype=float)), errors="coerce")
    out["season_weight_score"] = [
        season_weight_score(m, d) for m, d in zip(months, bw_delta)
    ]

    dist_vals = dist_m
    out["sonoda_waku_style_fit"] = pd.Series(
        [sonoda_waku_style_fit(w, s, d) for w, s, d in zip(waku, style_score, dist_vals)],
        index=out.index,
    )
    out["pace_style_fit"] = pd.Series(
        [pace_style_fit(lap_pace, s) for s in style_score],
        index=out.index,
    )
    out["sonoda_front_bonus"] = style_score.fillna(0) * 0.1 + out["sonoda_waku_style_fit"]
    return out
