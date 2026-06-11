"""三連複 2-4-7型（2x2x2列）の馬選び・レース選定。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import comb
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.features.utils import parse_distance_m
from src.predictor.bets import RaceSignals, SanrenpukuBox, _parse_odds_value

_PLACE_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class Formation247Config:
    place_odds_max: float = 2.0
    col2_pop_max: int = 5
    col3_pop_min: int = 10
    min_head_count: int = 10
    min_odds_std: float = 70.0
    short_distance_max_m: float = 1400.0
    upset_classes: Tuple[str, ...] = ("C1", "C2", "C3", "B2", "B1")
    require_upset_profile: bool = True
    min_upset_score: int = 3
    horses_per_column: int = 2


DEFAULT_FORMATION_247 = Formation247Config()


def parse_place_odds_low(place_odds: str) -> float:
    s = str(place_odds or "").strip().replace(",", "")
    if not s:
        return float("nan")
    m = _PLACE_RANGE_RE.match(s)
    if m:
        return float(m.group(1))
    return _parse_odds_value(s)


def top3_rate_for_horse(master: pd.DataFrame, horse_id: str, before_date: str) -> float:
    hid = str(horse_id).strip()
    if not hid or master.empty:
        return 0.0
    hist = master[
        (master["horse_id"].astype(str) == hid)
        & (master["date"].astype(str) < str(before_date))
    ]
    finish = pd.to_numeric(hist["finish"], errors="coerce")
    valid = finish.notna()
    runs = int(valid.sum())
    if runs == 0:
        return 0.0
    return int((finish[valid] <= 3).sum()) / runs


def _race_df_enriched(race_df: pd.DataFrame, master: pd.DataFrame, before_date: str) -> pd.DataFrame:
    out = race_df.copy()
    out["pop_n"] = pd.to_numeric(out.get("popularity"), errors="coerce")
    out["win_odds_n"] = pd.to_numeric(out.get("odds"), errors="coerce")
    if "place_odds" in out.columns:
        out["place_low"] = out["place_odds"].map(parse_place_odds_low)
    else:
        out["place_low"] = np.nan
    out["top3_rate"] = [
        top3_rate_for_horse(master, str(row.get("horse_id", "")), before_date)
        for _, row in out.iterrows()
    ]
    return out


def is_247_target_race(
    race_df: pd.DataFrame,
    signals: RaceSignals,
    *,
    exotic_profile: str = "\u5805",
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> bool:
    if cfg.require_upset_profile and exotic_profile != "\u8352":
        return False
    if signals.upset_score < cfg.min_upset_score:
        return False
    if signals.head_count < cfg.min_head_count:
        return False
    if signals.odds_std < cfg.min_odds_std:
        return False
    race_class = str(race_df.get("race_class", pd.Series([""])).iloc[0]).upper()
    distance_m = parse_distance_m(race_df.get("distance", pd.Series([""])).iloc[0])
    class_hit = any(race_class.startswith(c) for c in cfg.upset_classes)
    short_hit = not np.isnan(distance_m) and distance_m > 0 and distance_m <= cfg.short_distance_max_m
    return class_hit or short_hit or signals.head_count >= 12


def _pick_column(
    pool: pd.DataFrame,
    n: int,
    *,
    exclude: set[str],
    sort_cols: Sequence[str],
    ascending: Sequence[bool],
) -> pd.DataFrame:
    cand = pool[~pool["umaban"].astype(str).isin(exclude)].copy()
    if cand.empty:
        return cand.iloc[0:0]
    return cand.sort_values(list(sort_cols), ascending=list(ascending)).head(n)


def select_247_horses(
    race_df: pd.DataFrame,
    master: pd.DataFrame,
    before_date: str,
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> Optional[pd.DataFrame]:
    if len(race_df) < 6:
        return None
    df = _race_df_enriched(race_df, master, before_date)
    n = cfg.horses_per_column
    picked: List[pd.Series] = []
    exclude: set[str] = set()

    col1_pool = df[df["place_low"].notna() & (df["place_low"] <= cfg.place_odds_max)]
    if len(col1_pool) < n:
        col1_pool = df[df["place_low"].notna()].sort_values("place_low")
    if col1_pool.empty:
        col1_pool = df.sort_values("win_odds_n")
    for _, row in _pick_column(
        col1_pool, n, exclude=exclude, sort_cols=["top3_rate", "place_low"], ascending=[False, True]
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    for _, row in _pick_column(
        df[df["pop_n"].between(1, cfg.col2_pop_max)],
        n,
        exclude=exclude,
        sort_cols=["top3_rate", "pop_n"],
        ascending=[False, True],
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    for _, row in _pick_column(
        df[df["pop_n"] >= cfg.col3_pop_min],
        n,
        exclude=exclude,
        sort_cols=["top3_rate", "win_odds_n"],
        ascending=[False, False],
    ).iterrows():
        picked.append(row)
        exclude.add(str(row["umaban"]))

    if len(picked) < 6:
        remain = df[~df["umaban"].astype(str).isin(exclude)].sort_values("top3_rate", ascending=False)
        for _, row in remain.iterrows():
            if len(picked) >= 6:
                break
            picked.append(row)
    if len(picked) < 6:
        return None
    return pd.DataFrame(picked[:6])


def build_sanrenpuku_247_box(
    race_df: pd.DataFrame,
    master: pd.DataFrame,
    before_date: str,
    cfg: Formation247Config = DEFAULT_FORMATION_247,
) -> Optional[SanrenpukuBox]:
    horses = select_247_horses(race_df, master, before_date, cfg)
    if horses is None or len(horses) < 6:
        return None
    umaban = [str(u) for u in horses["umaban"]]
    names = [str(n) for n in horses["horse_name"]]
    return SanrenpukuBox(umaban=umaban, names=names, points=comb(len(umaban), 3))
