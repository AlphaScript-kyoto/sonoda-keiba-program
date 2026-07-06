"""Upset-high sanren formation pause gate."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from src.predictor.backtest import BET_UNIT

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = ROOT / "data" / "processed" / "logs" / "upset_high_bet_state.json"

MAX_CONSECUTIVE_MISSES = 4
ROLLING_WINDOW = 10
ROLLING_MIN_ROI_PCT = 70.0
UPSET_HIGH_SETTLE_OFFSET = 20
UPSET = "\u8352"


@dataclass
class UpsetHighBetRecord:
    date: str
    race_no: int
    invest_yen: int
    return_yen: int
    hit: bool


@dataclass
class UpsetHighPendingSignal:
    date: str
    race_no: int
    invest_yen: int
    settled: bool = False


@dataclass
class UpsetHighBetState:
    recent_bets: List[UpsetHighBetRecord] = field(default_factory=list)
    consecutive_misses: int = 0
    paused: bool = False
    pause_reason: str = ""
    pause_triggered_date: str = ""
    resume_on_date: str = ""
    pause_notified_date: str = ""
    pending_signals: List[UpsetHighPendingSignal] = field(default_factory=list)
    updated_at: str = ""

    def to_json(self) -> dict:
        return {
            "recent_bets": [asdict(r) for r in self.recent_bets],
            "consecutive_misses": self.consecutive_misses,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "pause_triggered_date": self.pause_triggered_date,
            "resume_on_date": self.resume_on_date,
            "pause_notified_date": self.pause_notified_date,
            "pending_signals": [asdict(p) for p in self.pending_signals],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json(cls, data: dict) -> UpsetHighBetState:
        return cls(
            recent_bets=[UpsetHighBetRecord(**r) for r in data.get("recent_bets", [])],
            consecutive_misses=int(data.get("consecutive_misses", 0)),
            paused=bool(data.get("paused", False)),
            pause_reason=str(data.get("pause_reason", "")),
            pause_triggered_date=str(data.get("pause_triggered_date", "")),
            resume_on_date=str(data.get("resume_on_date", "")),
            pause_notified_date=str(data.get("pause_notified_date", "")),
            pending_signals=[
                UpsetHighPendingSignal(**p) for p in data.get("pending_signals", [])
            ],
            updated_at=str(data.get("updated_at", "")),
        )


def load_state(path: Path = STATE_PATH) -> UpsetHighBetState:
    if not path.exists():
        return UpsetHighBetState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return UpsetHighBetState.from_json(data)


def save_state(state: UpsetHighBetState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now().isoformat(timespec="seconds")
    path.write_text(
        json.dumps(state.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def next_sonoda_race_date_after(
    from_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    if master is None:
        from src.predictor.score import load_master

        master = load_master()
    dates = sorted(master["date"].astype(str).unique())
    for d in dates:
        if d > from_yyyymmdd:
            return d
    return None


def rolling_roi_pct(
    bets: List[UpsetHighBetRecord],
    window: int = ROLLING_WINDOW,
) -> Optional[float]:
    if len(bets) < window:
        return None
    tail = bets[-window:]
    inv = sum(b.invest_yen for b in tail)
    if inv <= 0:
        return None
    ret = sum(b.return_yen for b in tail)
    return ret / inv * 100.0


def pause_check_reason(state: UpsetHighBetState) -> Optional[str]:
    if state.consecutive_misses >= MAX_CONSECUTIVE_MISSES:
        return f"{MAX_CONSECUTIVE_MISSES}\u9023\u6557"
    roi = rolling_roi_pct(state.recent_bets)
    if roi is not None and roi < ROLLING_MIN_ROI_PCT:
        return (
            f"\u76f4\u8fd1{ROLLING_WINDOW}R ROI {roi:.1f}% "
            f"< {ROLLING_MIN_ROI_PCT:.0f}%"
        )
    return None


def enter_pause(
    state: UpsetHighBetState,
    reason: str,
    today_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
) -> None:
    state.paused = True
    state.pause_reason = reason
    state.pause_triggered_date = today_yyyymmdd
    nxt = next_sonoda_race_date_after(today_yyyymmdd, master)
    state.resume_on_date = nxt or ""


def on_race_day_open(
    date_yyyymmdd: str,
    state: Optional[UpsetHighBetState] = None,
    *,
    master: Optional[pd.DataFrame] = None,
) -> UpsetHighBetState:
    st = state if state is not None else load_state()
    if not st.paused:
        return st
    if st.resume_on_date and date_yyyymmdd >= st.resume_on_date:
        st.paused = False
        st.pause_reason = ""
        st.pause_triggered_date = ""
        st.resume_on_date = ""
        st.pause_notified_date = ""
    return st


def should_send_upset_high_buy(
    state: UpsetHighBetState,
    today_yyyymmdd: str,
    *,
    master: Optional[pd.DataFrame] = None,
    plan=None,
) -> Tuple[bool, str]:
    from src.predictor.upset_p6_rules import (
        P6_DAILY_MAX_RACES,
        is_p6_eligible_plan,
        p6_daily_cap_reason,
    )

    on_race_day_open(today_yyyymmdd, state, master=master)
    if state.paused:
        return False, state.pause_reason or "\u4f11\u6b62\u4e2d"
    reason = pause_check_reason(state)
    if reason:
        enter_pause(state, reason, today_yyyymmdd, master)
        return False, reason
    if plan is not None and not is_p6_eligible_plan(plan):
        return False, "P6\u6761\u4ef6\u5916"
    cap = p6_daily_cap_reason(state, today_yyyymmdd, max_races=P6_DAILY_MAX_RACES)
    if cap:
        return False, cap
    return True, ""


def record_signaled_bet(
    state: UpsetHighBetState,
    date_yyyymmdd: str,
    race_no: int,
    invest_yen: int,
) -> None:
    key = (date_yyyymmdd, int(race_no))
    for p in state.pending_signals:
        if (p.date, p.race_no) == key:
            return
    state.pending_signals.append(
        UpsetHighPendingSignal(
            date=date_yyyymmdd,
            race_no=int(race_no),
            invest_yen=int(invest_yen),
            settled=False,
        )
    )


def _append_settled(state: UpsetHighBetState, rec: UpsetHighBetRecord) -> None:
    state.recent_bets.append(rec)
    if rec.hit:
        state.consecutive_misses = 0
    else:
        state.consecutive_misses += 1
    if len(state.recent_bets) > 200:
        state.recent_bets = state.recent_bets[-200:]


def _race_id_for_no(schedule: dict, race_no: int) -> Optional[str]:
    for race in schedule.get("races", []):
        if int(race.get("race_no", 0)) == int(race_no):
            rid = str(race.get("race_id", "")).strip()
            return rid or None
    return None


def _race_results_ready(master: pd.DataFrame, race_id: str) -> bool:
    sub = master[master["race_id"].astype(str) == str(race_id)]
    if sub.empty:
        return False
    finish = pd.to_numeric(sub["finish"], errors="coerce")
    return int(finish.notna().sum()) >= 3


def _fetch_results_for_race_nos(
    date_yyyymmdd: str,
    race_nos: List[int],
    schedule: dict,
) -> List[str]:
    from src.scraper.fetcher import fetch_races_to_master
    from src.scraper.payback import fetch_paybacks

    race_ids = []
    for rn in race_nos:
        rid = _race_id_for_no(schedule, rn)
        if rid:
            race_ids.append(rid)
    if not race_ids:
        return []
    fetched = fetch_races_to_master(race_ids)
    if fetched:
        fetch_paybacks(fetched, use_cache=True)
    return fetched


def _settle_pending_signals(
    st: UpsetHighBetState,
    pending: List[UpsetHighPendingSignal],
    rec_map: dict,
) -> None:
    from src.predictor.backtest import _exotic_high_for_record
    from src.predictor.bets import DEFAULT_STRATEGY

    for sig in pending:
        rec = rec_map.get((sig.date, int(sig.race_no)))
        if rec is None:
            continue
        eh = _exotic_high_for_record(rec, DEFAULT_STRATEGY)
        if not eh or rec.exotic_profile != UPSET or not rec.sanrenpuku_formation_points:
            sig.settled = True
            continue
        invest = rec.sanrenpuku_formation_points * BET_UNIT
        ret = rec.fuku3_yen if rec.sanrenpuku_formation_hit else 0
        _append_settled(
            st,
            UpsetHighBetRecord(
                date=sig.date,
                race_no=sig.race_no,
                invest_yen=invest,
                return_yen=ret,
                hit=bool(rec.sanrenpuku_formation_hit),
            ),
        )
        sig.settled = True


def _build_rec_map(
    date_yyyymmdd: str,
    master: pd.DataFrame,
    *,
    fetch_payback: bool = False,
) -> dict:
    from src.predictor.backtest import _collect_race_records, _load_paybacks_for_races
    from src.predictor.bets import DEFAULT_STRATEGY
    from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

    hist = master[master["date"].astype(str) == date_yyyymmdd]
    if hist.empty:
        return {}

    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
    recs = _collect_race_records(
        date_yyyymmdd, date_yyyymmdd, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
    )
    return {(r.date, int(r.race_no)): r for r in recs}


def settle_pending_before_race(
    date_yyyymmdd: str,
    before_race_no: int,
    *,
    master: Optional[pd.DataFrame] = None,
    state: Optional[UpsetHighBetState] = None,
    schedule: Optional[dict] = None,
    fetch_if_missing: bool = True,
) -> Tuple[UpsetHighBetState, List[int]]:
    """次レースT-20向け: before_race_no より前の未精算シグナルを結果反映する。"""
    from src.predictor.score import load_master

    st = state if state is not None else load_state()
    pending = [
        p
        for p in st.pending_signals
        if p.date == date_yyyymmdd and not p.settled and int(p.race_no) < int(before_race_no)
    ]
    if not pending:
        return st, []

    if schedule is None:
        from src.scraper.race_snapshots import load_schedule

        schedule = load_schedule(date_yyyymmdd) or {}

    master_df = master if master is not None else load_master()
    race_nos = sorted({int(p.race_no) for p in pending})
    if fetch_if_missing and schedule.get("races"):
        need_fetch = []
        for rn in race_nos:
            rid = _race_id_for_no(schedule, rn)
            if rid and not _race_results_ready(master_df, rid):
                need_fetch.append(rn)
        if need_fetch:
            _fetch_results_for_race_nos(date_yyyymmdd, need_fetch, schedule)
            master_df = load_master()

    rec_map = _build_rec_map(date_yyyymmdd, master_df, fetch_payback=True)
    settled_nos: List[int] = []
    for sig in pending:
        before = sig.settled
        _settle_pending_signals(st, [sig], rec_map)
        if sig.settled and not before:
            settled_nos.append(int(sig.race_no))

    st.pending_signals = [p for p in st.pending_signals if not p.settled]
    return st, settled_nos


def settle_pending_for_date(
    date_yyyymmdd: str,
    *,
    master: Optional[pd.DataFrame] = None,
    state: Optional[UpsetHighBetState] = None,
    fetch_if_missing: bool = True,
) -> UpsetHighBetState:
    from src.predictor.score import load_master
    from src.scraper.race_snapshots import load_schedule

    st = state if state is not None else load_state()
    pending = [p for p in st.pending_signals if p.date == date_yyyymmdd and not p.settled]
    if not pending:
        return st

    schedule = load_schedule(date_yyyymmdd) or {}
    master_df = master if master is not None else load_master()
    race_nos = sorted({int(p.race_no) for p in pending})
    if fetch_if_missing and schedule.get("races"):
        need_fetch = []
        for rn in race_nos:
            rid = _race_id_for_no(schedule, rn)
            if rid and not _race_results_ready(master_df, rid):
                need_fetch.append(rn)
        if need_fetch:
            _fetch_results_for_race_nos(date_yyyymmdd, need_fetch, schedule)
            master_df = load_master()

    rec_map = _build_rec_map(date_yyyymmdd, master_df, fetch_payback=True)
    _settle_pending_signals(st, pending, rec_map)
    st.pending_signals = [p for p in st.pending_signals if not p.settled]
    return st


def build_pause_skip_message(
    date_yyyymmdd: str,
    race_no: int,
    reason: str,
    state: UpsetHighBetState,
) -> str:
    roi = rolling_roi_pct(state.recent_bets)
    roi_s = f"{roi:.1f}%" if roi is not None else "N/A"
    resume = state.resume_on_date or "\u672a\u5b9a"
    return (
        f"{date_yyyymmdd} {race_no}R\n"
        f"\u8352High\u8cb7\u3044\u76ee\u306f\u4f11\u6b62\u4e2d\u3067\u3059\n"
        f"\u7406\u7531: {reason}\n"
        f"\u9023\u6557: {state.consecutive_misses} / "
        f"\u76f4\u8fd1{ROLLING_WINDOW}R ROI: {roi_s}\n"
        f"\u518d\u958b\u4e88\u5b9a: \u7fcc\u958b\u50ac\u65e5 {resume}"
    )


def build_rules_test_message() -> str:
    return (
        "[\u30c6\u30b9\u30c8] \u8352High \u4e09\u9023\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f3 \u4f11\u6b62\u30eb\u30fc\u30eb\n"
        f"\u30fb{MAX_CONSECUTIVE_MISSES}\u9023\u6557\u3067\u4f11\u6b62\n"
        f"\u30fb\u76f4\u8fd1{ROLLING_WINDOW}R ROI < {ROLLING_MIN_ROI_PCT:.0f}% \u3067\u4f11\u6b62\n"
        "\u30fb\u518d\u958b: \u7fcc\u958b\u50ac\u65e5\n"
        "\u901a\u5e38\u4e88\u60f3LINE\u306f\u5f93\u6765\u3069\u304a\u308a\u914d\u4fe1\u3057\u307e\u3059"
    )


def build_settle_timing_test_message() -> str:
    return (
        "[\u30c6\u30b9\u30c8] \u8352High \u7cbe\u7b97\u30bf\u30a4\u30df\u30f3\u30b0\n"
        f"\u30fb\u8cb7\u3044\u76eeLINE\u9001\u4fe1: \u5404\u30ec\u30fc\u30b9 T-10\n"
        f"\u30fb\u7d50\u679c\u53cd\u6620: \u6b21\u30ec\u30fc\u30b9 T-{UPSET_HIGH_SETTLE_OFFSET}\n"
        "  \u2192 \u9023\u6557\u30fb\u76f4\u8fd110R ROI \u3092\u66f4\u65b0\n"
        f"\u30fb\u6b21\u30ec\u30fc\u30b9 T-10 \u3067\u4f11\u6b62\u30b2\u30fc\u30c8\u3092\u5224\u5b9a\n"
        "\u30fb\u6700\u7d42\u30ec\u30fc\u30b9\u5f8c\u306f\u76e3\u8996\u7d42\u4e86\u6642\u306b\u6b8b\u308a\u3092\u7cbe\u7b97"
    )


def build_pause_test_message() -> str:
    sample = build_pause_skip_message(
        "20260618",
        5,
        f"{MAX_CONSECUTIVE_MISSES}\u9023\u6557",
        UpsetHighBetState(
            consecutive_misses=MAX_CONSECUTIVE_MISSES,
            paused=True,
            pause_reason=f"{MAX_CONSECUTIVE_MISSES}\u9023\u6557",
            pause_triggered_date="20260618",
            resume_on_date="20260624",
            recent_bets=[
                UpsetHighBetRecord("20260611", 4, 500, 0, False),
                UpsetHighBetRecord("20260611", 5, 500, 0, False),
                UpsetHighBetRecord("20260611", 6, 500, 0, False),
                UpsetHighBetRecord("20260612", 1, 500, 0, False),
            ],
        ),
    )
    return f"[\u30c6\u30b9\u30c8] \u4f11\u6b62\u901a\u77e5\u306e\u4f8b\n\n{sample}"
