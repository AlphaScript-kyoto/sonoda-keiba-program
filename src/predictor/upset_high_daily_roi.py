"""Nightly upset x High formation ROI report (admin, T-10 based)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from src.predictor.backtest import BET_UNIT, _finish_order, _load_paybacks_for_races
from src.predictor.bets import (
    DEFAULT_STRATEGY,
    check_sanrenpuku_formation_firm_hit,
)
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.predictor.t10_daily_roi import _score_t10_race
from src.predictor.upset_high_bet_gate import (
    UPSET,
    UpsetHighBetRecord,
    UpsetHighBetState,
    _append_settled,
    _build_rec_map,
    load_state,
    on_race_day_open,
    record_signaled_bet,
    rolling_roi_pct,
    should_send_upset_high_buy,
)
from src.predictor.scoring_config import load_split_scoring_configs
from src.scraper.race_snapshots import LABEL_T_MINUS_10


@dataclass
class UpsetHighDailyBet:
    race_no: int
    race_name: str
    investment: int
    return_yen: int
    hit: bool

    @property
    def roi_pct(self) -> float:
        return (self.return_yen / self.investment * 100.0) if self.investment else 0.0


@dataclass
class UpsetHighDailyRoiReport:
    date: str
    bets: List[UpsetHighDailyBet] = field(default_factory=list)
    continuous_bets: List[UpsetHighDailyBet] = field(default_factory=list)
    qualifying_count: int = 0
    consecutive_misses: int = 0
    rolling_roi_pct: Optional[float] = None
    paused: bool = False

    @property
    def total_investment(self) -> int:
        return sum(b.investment for b in self.bets)

    @property
    def total_return(self) -> int:
        return sum(b.return_yen for b in self.bets)

    @property
    def total_roi_pct(self) -> float:
        inv = self.total_investment
        return (self.total_return / inv * 100.0) if inv else 0.0


def _bet_totals(bets: List[UpsetHighDailyBet]) -> tuple[int, int, float]:
    investment = sum(b.investment for b in bets)
    returns = sum(b.return_yen for b in bets)
    roi = (returns / investment * 100.0) if investment else 0.0
    return investment, returns, roi


def _is_t10_upset_high_plan(plan) -> bool:
    from src.predictor.upset_p6_rules import is_p6_eligible_plan

    return is_p6_eligible_plan(plan)


def _settle_t10_formation_bet(
    plan,
    final_race: pd.DataFrame,
    rec_map: dict,
    date_yyyymmdd: str,
    paybacks: dict,
) -> UpsetHighDailyBet:
    formation = plan.sanrenpuku_formation
    assert formation is not None
    invest = formation.points * BET_UNIT
    rno = int(plan.race_no)
    rec = rec_map.get((date_yyyymmdd, rno))
    if rec is not None:
        hit = bool(rec.sanrenpuku_formation_hit)
        ret = rec.fuku3_yen if hit else 0
    else:
        finish = _finish_order(final_race)
        hit = bool(check_sanrenpuku_formation_firm_hit(formation, finish))
        ret = 0
        if hit:
            pb = paybacks.get(str(plan.race_id))
            if pb:
                ret = pb.fuku3_yen
    name = str(plan.race_name or "")[:12]
    return UpsetHighDailyBet(
        race_no=rno,
        race_name=name,
        investment=invest,
        return_yen=ret,
        hit=hit,
    )


def _qualifying_bets_from_t10_snapshots(
    date_yyyymmdd: str,
    master: pd.DataFrame,
    rec_map: dict,
    paybacks: dict,
) -> List[UpsetHighDailyBet]:
    win_cfg, ex_cfg = load_split_scoring_configs()
    rows: List[UpsetHighDailyBet] = []
    for race_id in list_snapshot_race_ids(date_yyyymmdd, label=LABEL_T_MINUS_10):
        scored = _score_t10_race(date_yyyymmdd, race_id, master, win_cfg=win_cfg, ex_cfg=ex_cfg)
        if scored is None:
            continue
        plan, _top5, final_race, _snap = scored
        if not _is_t10_upset_high_plan(plan):
            continue
        rows.append(_settle_t10_formation_bet(plan, final_race, rec_map, date_yyyymmdd, paybacks))
    rows.sort(key=lambda b: b.race_no)
    return rows


def _bets_from_state_records(
    date_yyyymmdd: str,
    state: UpsetHighBetState,
    rec_map: dict,
) -> List[UpsetHighDailyBet]:
    rows: List[UpsetHighDailyBet] = []
    for bet in sorted(
        (r for r in state.recent_bets if r.date == date_yyyymmdd),
        key=lambda b: b.race_no,
    ):
        rec = rec_map.get((date_yyyymmdd, int(bet.race_no)))
        name = rec.race_name[:12] if rec and rec.race_name else ""
        rows.append(
            UpsetHighDailyBet(
                race_no=int(bet.race_no),
                race_name=name,
                investment=int(bet.invest_yen),
                return_yen=int(bet.return_yen),
                hit=bool(bet.hit),
            )
        )
    return rows


def _replay_actual_bets_with_gate(
    date_yyyymmdd: str,
    t10_bets: List[UpsetHighDailyBet],
    state: UpsetHighBetState,
    master: pd.DataFrame,
) -> List[UpsetHighDailyBet]:
    """Gate replay when state has no settled records for the day."""
    prior = [b for b in state.recent_bets if b.date < date_yyyymmdd]
    misses = 0
    for b in prior:
        if not b.hit:
            misses += 1
        else:
            misses = 0
    replay = UpsetHighBetState(
        recent_bets=list(prior),
        consecutive_misses=misses,
        paused=False,
        pause_reason="",
        pause_triggered_date="",
        resume_on_date="",
        pause_notified_date="",
    )
    on_race_day_open(date_yyyymmdd, replay, master=master)
    actual: List[UpsetHighDailyBet] = []
    for row in t10_bets:
        ok, _reason = should_send_upset_high_buy(replay, date_yyyymmdd, master=master)
        if not ok:
            break
        actual.append(row)
        record_signaled_bet(replay, date_yyyymmdd, row.race_no, row.investment)
        _append_settled(
            replay,
            UpsetHighBetRecord(
                date_yyyymmdd,
                row.race_no,
                row.investment,
                row.return_yen,
                row.hit,
            ),
        )
    return actual


def build_upset_high_daily_roi_report(
    date_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    state: Optional[UpsetHighBetState] = None,
    fetch_payback: bool = True,
) -> UpsetHighDailyRoiReport:
    from src.predictor.score import load_master

    st = state if state is not None else load_state()
    master_df = master if master is not None else load_master()
    race_ids = list_snapshot_race_ids(date_yyyymmdd, label=LABEL_T_MINUS_10)
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
    rec_map = _build_rec_map(date_yyyymmdd, master_df, fetch_payback=fetch_payback)

    continuous_bets = _qualifying_bets_from_t10_snapshots(
        date_yyyymmdd, master_df, rec_map, paybacks
    )
    bets = _bets_from_state_records(date_yyyymmdd, st, rec_map)
    if not bets and continuous_bets:
        bets = _replay_actual_bets_with_gate(date_yyyymmdd, continuous_bets, st, master_df)

    return UpsetHighDailyRoiReport(
        date=date_yyyymmdd,
        bets=bets,
        continuous_bets=continuous_bets,
        qualifying_count=len(continuous_bets),
        consecutive_misses=st.consecutive_misses,
        rolling_roi_pct=rolling_roi_pct(st.recent_bets),
        paused=st.paused,
    )


def _format_bet_lines(bets: List[UpsetHighDailyBet], *, empty_label: str) -> List[str]:
    if not bets:
        return [empty_label]

    lines: List[str] = []
    for b in bets:
        hit_txt = "\u4e2d\u7684" if b.hit else "\u5916\u308c"
        pts = b.investment // BET_UNIT if BET_UNIT else 0
        lines.append(f"R{b.race_no} {b.race_name} {pts}\u70b9")
        lines.append(
            f"  \u6295{b.investment} \u6255{b.return_yen} "
            f"\u56de\u53ce{b.roi_pct:.0f}% {hit_txt}"
        )

    inv, ret, roi = _bet_totals(bets)
    total_pts = inv // BET_UNIT if BET_UNIT else 0
    lines.extend(
        [
            "",
            (
                f"\u5408\u8a08 {len(bets)}R {total_pts}\u70b9 "
                f"\u6295{inv} \u6255{ret} \u56de\u53ce{roi:.0f}%"
            ),
        ]
    )
    return lines


def format_p6_daily_roi_message(report: UpsetHighDailyRoiReport) -> str:
    """Admin nightly summary: actual P6 bets only."""
    lines: List[str] = [
        f"\u3010\u5712\u7530 P6\u5b9f\u7e3e {report.date}\u3011",
        f"\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f35\u70b9\uff08{BET_UNIT}\u5186\u00d75\u70b9\uff09",
        "\u203b\u5b9f\u969b\u306b\u914d\u4fe1\u3057\u305f\u8cb7\u3044\u76ee\uff08\u4f11\u6b62\u30b2\u30fc\u30c8\u53cd\u6620\uff09",
        "",
    ]

    if not report.bets:
        lines.append("\u672c\u65e5\u306e\u8cb7\u3044\u76ee\u306a\u3057")
        if report.qualifying_count > 0 and report.paused:
            lines.append(
                f"\uff08T-10\u8a72\u5f53 {report.qualifying_count}R"
                f"\u30fb\u4f11\u6b62\u4e2d\u306e\u305f\u3081\u898b\u9001\u308a\uff09"
            )
    else:
        lines.extend(
            _format_bet_lines(
                report.bets,
                empty_label="\u672c\u65e5\u306e\u8cb7\u3044\u76ee\u306a\u3057",
            )
        )

    if report.paused:
        lines.append("\u203b\u4f11\u6b62\u4e2d")

    return "\n".join(lines)


def format_upset_high_daily_roi_message(report: UpsetHighDailyRoiReport) -> str:
    """Backward-compatible alias for P6 nightly admin report."""
    return format_p6_daily_roi_message(report)
