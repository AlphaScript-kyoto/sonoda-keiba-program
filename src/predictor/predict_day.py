"""日付単位の予想実行（CLI / UI 共通）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pandas as pd

from src.predictor.bets import DEFAULT_STRATEGY, RaceBetPlan, build_day_bet_plans
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.scraper.client import NetkeibaBlockedError
from src.scraper.race_list import list_race_ids_for_shutuba
from src.scraper.shutuba import fetch_shutuba_html, parse_shutuba

ProgressCallback = Callable[[int, int, str], None]


@dataclass
class PredictDayResult:
    date: str
    win_df: pd.DataFrame
    exotic_df: Optional[pd.DataFrame]
    plans: List[RaceBetPlan] = field(default_factory=list)
    race_count: int = 0
    message: str = ""


def fetch_entries_for_date(date_yyyymmdd: str, *, on_progress: Optional[ProgressCallback] = None) -> pd.DataFrame:
    race_ids = list_race_ids_for_shutuba(date_yyyymmdd)
    if not race_ids:
        return pd.DataFrame()
    total = len(race_ids)
    entries: List[dict] = []
    for i, race_id in enumerate(race_ids, start=1):
        if on_progress:
            on_progress(i, total, race_id)
        html = fetch_shutuba_html(race_id)
        entries.extend(parse_shutuba(html, race_id))
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def run_predict_day(date_yyyymmdd: str, *, offline: bool = False, master: Optional[pd.DataFrame] = None, on_progress: Optional[ProgressCallback] = None) -> PredictDayResult:
    master = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    use_split = DEFAULT_STRATEGY.split_scoring
    if offline:
        entries_df = master[master["date"].astype(str) == date_yyyymmdd].copy()
        if on_progress and not entries_df.empty:
            on_progress(entries_df["race_id"].nunique(), entries_df["race_id"].nunique(), "offline")
    else:
        entries_df = fetch_entries_for_date(date_yyyymmdd, on_progress=on_progress)
    if entries_df.empty:
        return PredictDayResult(date=date_yyyymmdd, win_df=pd.DataFrame(), exotic_df=None, plans=[], race_count=0, message="予想対象がありません（園田開催なし、または出馬表未取得）。")
    win_df = score_entries(entries_df, master, config=win_cfg)
    exotic_df = score_entries(entries_df, master, config=ex_cfg) if use_split else None
    plans = build_day_bet_plans(win_df, exotic_scored=exotic_df, strategy=DEFAULT_STRATEGY)
    return PredictDayResult(date=date_yyyymmdd, win_df=win_df, exotic_df=exotic_df, plans=plans, race_count=len(plans), message="")


def run_predict_day_safe(date_yyyymmdd: str, *, offline: bool = False, master: Optional[pd.DataFrame] = None, on_progress: Optional[ProgressCallback] = None) -> PredictDayResult:
    try:
        return run_predict_day(date_yyyymmdd, offline=offline, master=master, on_progress=on_progress)
    except NetkeibaBlockedError as exc:
        return PredictDayResult(date=date_yyyymmdd, win_df=pd.DataFrame(), exotic_df=None, plans=[], race_count=0, message=f"通信制限（HTTP 400）。しばらく待って再試行してください。 ({exc})")
