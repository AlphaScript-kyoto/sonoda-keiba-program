"""日付単位の予想実行（CLI / UI 共通）。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable, List, Optional, Set

import pandas as pd

from src.predictor.bets import DEFAULT_STRATEGY, RaceBetPlan, build_day_bet_plans
from src.predictor.race_schedule import is_race_started
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
    fetched_race_count: int = 0
    cached_race_count: int = 0


def _skip_race_ids_from_cache(
    date_yyyymmdd: str,
    cache: PredictDayResult,
    now: datetime,
) -> Set[str]:
    skip: Set[str] = set()
    for plan in cache.plans:
        if not plan.post_time:
            continue
        if is_race_started(date_yyyymmdd, plan.post_time, now):
            skip.add(plan.race_id)
    return skip


def fetch_entries_for_date(
    date_yyyymmdd: str,
    *,
    skip_race_ids: Optional[Set[str]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> pd.DataFrame:
    race_ids = list_race_ids_for_shutuba(date_yyyymmdd)
    if not race_ids:
        return pd.DataFrame()
    skip = skip_race_ids or set()
    fetch_ids = [rid for rid in race_ids if rid not in skip]
    total = len(fetch_ids)
    entries: List[dict] = []
    for i, race_id in enumerate(fetch_ids, start=1):
        if on_progress:
            on_progress(i, total, race_id)
        html = fetch_shutuba_html(race_id)
        entries.extend(parse_shutuba(html, race_id))
    return pd.DataFrame(entries) if entries else pd.DataFrame()


def _cached_frames(
    cache: PredictDayResult,
    skip_race_ids: Set[str],
) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    if not skip_race_ids or cache.win_df.empty:
        return pd.DataFrame(), None
    win = cache.win_df[cache.win_df["race_id"].astype(str).isin(skip_race_ids)].copy()
    ex = None
    if cache.exotic_df is not None and not cache.exotic_df.empty:
        ex = cache.exotic_df[
            cache.exotic_df["race_id"].astype(str).isin(skip_race_ids)
        ].copy()
    return win, ex


def _merge_entry_frames(parts: List[pd.DataFrame]) -> pd.DataFrame:
    frames = [p for p in parts if p is not None and not p.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _merge_scored_frames(parts: List[pd.DataFrame]) -> pd.DataFrame:
    return _merge_entry_frames(parts)


def _annotate_started_plans(
    date_yyyymmdd: str,
    plans: List[RaceBetPlan],
    now: datetime,
) -> List[RaceBetPlan]:
    out: List[RaceBetPlan] = []
    for plan in plans:
        started = is_race_started(date_yyyymmdd, plan.post_time, now) if plan.post_time else False
        out.append(replace(plan, is_started=started))
    return out


def _merge_plans(
    race_ids: List[str],
    fresh_plans: List[RaceBetPlan],
    cached_plans: List[RaceBetPlan],
    skip_race_ids: Set[str],
) -> List[RaceBetPlan]:
    fresh_by_id = {p.race_id: p for p in fresh_plans}
    cached_by_id = {p.race_id: p for p in cached_plans if p.race_id in skip_race_ids}
    merged: List[RaceBetPlan] = []
    for rid in race_ids:
        if rid in fresh_by_id:
            merged.append(fresh_by_id[rid])
        elif rid in cached_by_id:
            merged.append(replace(cached_by_id[rid], is_started=True))
    return merged


def run_predict_day(
    date_yyyymmdd: str,
    *,
    offline: bool = False,
    master: Optional[pd.DataFrame] = None,
    on_progress: Optional[ProgressCallback] = None,
    cache: Optional[PredictDayResult] = None,
    now: Optional[datetime] = None,
    force_refresh: bool = False,
) -> PredictDayResult:
    master = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    use_split = DEFAULT_STRATEGY.split_scoring
    current = now or datetime.now()
    skip_race_ids: Set[str] = set()
    cached_win = pd.DataFrame()
    cached_ex: Optional[pd.DataFrame] = None
    cached_plans: List[RaceBetPlan] = []
    race_ids: List[str] = []
    fetched_count = 0
    cached_count = 0
    msg = ""

    if offline:
        entries_df = master[master["date"].astype(str) == date_yyyymmdd].copy()
        if on_progress and not entries_df.empty:
            on_progress(entries_df["race_id"].nunique(), entries_df["race_id"].nunique(), "offline")
        if entries_df.empty:
            return PredictDayResult(
                date=date_yyyymmdd,
                win_df=pd.DataFrame(),
                exotic_df=None,
                plans=[],
                race_count=0,
                message="予想対象がありません（園田開催なし、または出馬表未取得）。",
            )
        win_df = score_entries(entries_df, master, config=win_cfg)
        exotic_df = (
            score_entries(entries_df, master, config=ex_cfg) if use_split else None
        )
        plans = _annotate_started_plans(
            date_yyyymmdd,
            build_day_bet_plans(win_df, exotic_scored=exotic_df, strategy=DEFAULT_STRATEGY),
            current,
        )
        return PredictDayResult(
            date=date_yyyymmdd,
            win_df=win_df,
            exotic_df=exotic_df,
            plans=plans,
            race_count=len(plans),
            message="",
            fetched_race_count=entries_df["race_id"].nunique(),
            cached_race_count=0,
        )

    race_ids = list_race_ids_for_shutuba(date_yyyymmdd)
    if not race_ids:
        return PredictDayResult(
            date=date_yyyymmdd,
            win_df=pd.DataFrame(),
            exotic_df=None,
            plans=[],
            race_count=0,
            message="予想対象がありません（園田開催なし、または出馬表未取得）。",
        )

    if cache and cache.date == date_yyyymmdd and not force_refresh and cache.plans:
        skip_race_ids = _skip_race_ids_from_cache(date_yyyymmdd, cache, current)
        cached_win, cached_ex = _cached_frames(cache, skip_race_ids)
        cached_plans = [p for p in cache.plans if p.race_id in skip_race_ids]
        cached_count = len(skip_race_ids)

    fresh_entries = fetch_entries_for_date(
        date_yyyymmdd,
        skip_race_ids=skip_race_ids,
        on_progress=on_progress,
    )
    fetched_count = len(race_ids) - cached_count

    fresh_win = (
        score_entries(fresh_entries, master, config=win_cfg)
        if not fresh_entries.empty
        else pd.DataFrame()
    )
    win_df = _merge_scored_frames([cached_win, fresh_win])

    exotic_df: Optional[pd.DataFrame] = None
    if use_split:
        fresh_ex = (
            score_entries(fresh_entries, master, config=ex_cfg)
            if not fresh_entries.empty
            else pd.DataFrame()
        )
        exotic_df = _merge_scored_frames(
            [df for df in (cached_ex, fresh_ex) if df is not None]
        )
        if exotic_df.empty:
            exotic_df = None

    if win_df.empty:
        return PredictDayResult(
            date=date_yyyymmdd,
            win_df=pd.DataFrame(),
            exotic_df=None,
            plans=[],
            race_count=0,
            message="予想対象がありません（園田開催なし、または出馬表未取得）。",
        )

    def _exotic_for_build(df_win: pd.DataFrame) -> Optional[pd.DataFrame]:
        if exotic_df is None:
            return None
        ids = set(df_win["race_id"].astype(str).tolist())
        sub = exotic_df[exotic_df["race_id"].astype(str).isin(ids)]
        return sub if not sub.empty else None

    if skip_race_ids and not force_refresh:
        fresh_win_only = win_df[~win_df["race_id"].astype(str).isin(skip_race_ids)]
        fresh_plans = (
            build_day_bet_plans(
                fresh_win_only,
                exotic_scored=_exotic_for_build(fresh_win_only),
                strategy=DEFAULT_STRATEGY,
            )
            if not fresh_win_only.empty
            else []
        )
        plans = _merge_plans(race_ids, fresh_plans, cached_plans, skip_race_ids)
        plans = _annotate_started_plans(date_yyyymmdd, plans, current)
        msg = f"発走済み {cached_count}R は前回データを使用 · 新規取得 {fetched_count}R"
    else:
        plans = _annotate_started_plans(
            date_yyyymmdd,
            build_day_bet_plans(
                win_df, exotic_scored=exotic_df, strategy=DEFAULT_STRATEGY
            ),
            current,
        )

    return PredictDayResult(
        date=date_yyyymmdd,
        win_df=win_df,
        exotic_df=exotic_df,
        plans=plans,
        race_count=len(plans),
        message=msg,
        fetched_race_count=fetched_count,
        cached_race_count=cached_count,
    )


def run_predict_day_safe(
    date_yyyymmdd: str,
    *,
    offline: bool = False,
    master: Optional[pd.DataFrame] = None,
    on_progress: Optional[ProgressCallback] = None,
    cache: Optional[PredictDayResult] = None,
    now: Optional[datetime] = None,
    force_refresh: bool = False,
) -> PredictDayResult:
    try:
        return run_predict_day(
            date_yyyymmdd,
            offline=offline,
            master=master,
            on_progress=on_progress,
            cache=cache,
            now=now,
            force_refresh=force_refresh,
        )
    except NetkeibaBlockedError as exc:
        return PredictDayResult(
            date=date_yyyymmdd,
            win_df=pd.DataFrame(),
            exotic_df=None,
            plans=[],
            race_count=0,
            message=f"通信制限（HTTP 400）。しばらく待って再試行してください。 ({exc})",
        )
