"""T-10 snapshot ROI report for expectation tier S+ races (admin nightly)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from src.predictor.backtest import (
    BET_UNIT,
    _finish_order,
    _load_paybacks_for_races,
    _place_payout_yen,
    _win_payout_yen,
)
from src.predictor.bets import (
    DEFAULT_STRATEGY,
    _parse_odds_value,
    assign_marks,
    build_race_bet_plan,
    build_sanrenpuku_formation_firm,
    check_sanrenpuku_formation_firm_hit,
)
from src.predictor.expectation import TIER_RANK
from src.predictor.formation_247 import parse_place_odds_low
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.scraper.payback import RacePayback
from src.scraper.race_snapshots import LABEL_T_MINUS_10, snapshot_path

WIN_MIN_ODDS = 2.0
PLACE_MIN_ODDS = 1.5


def _place_odds_low_from_snap(snap: dict, umaban: str) -> float:
    place_map = (snap.get("odds") or {}).get("place") or {}
    return parse_place_odds_low(str(place_map.get(str(umaban), "")))


def _should_buy_place(snap: dict, umaban: str) -> bool:
    low = _place_odds_low_from_snap(snap, umaban)
    return pd.notna(low) and low >= PLACE_MIN_ODDS


def is_tier_s_plus(tier: str) -> bool:
    return TIER_RANK.get(tier, 99) <= TIER_RANK["S"]
    return TIER_RANK.get(tier, 99) <= TIER_RANK["S"]


@dataclass
class T10RaceRoi:
    race_id: str
    race_no: int
    race_name: str
    expectation_tier: str
    expectation_score: int
    win_points: int = 0
    place_points: int = 0
    sanren_points: int = 0
    investment: int = 0
    return_yen: int = 0
    win_hit: bool = False
    place_hits: int = 0
    sanren_hit: bool = False
    skipped_win_low_odds: bool = False

    @property
    def roi_pct(self) -> float:
        return (self.return_yen / self.investment * 100.0) if self.investment else 0.0


@dataclass
class T10DailyRoiReport:
    date: str
    races: List[T10RaceRoi] = field(default_factory=list)
    skipped_no_result: int = 0
    skipped_not_s_plus: int = 0

    @property
    def total_investment(self) -> int:
        return sum(r.investment for r in self.races)

    @property
    def total_return(self) -> int:
        return sum(r.return_yen for r in self.races)

    @property
    def total_roi_pct(self) -> float:
        inv = self.total_investment
        return (self.total_return / inv * 100.0) if inv else 0.0


def _load_snapshot_entries(date_yyyymmdd: str, race_id: str) -> Optional[dict]:
    path = snapshot_path(date_yyyymmdd, race_id, LABEL_T_MINUS_10)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _score_t10_race(date_yyyymmdd: str, race_id: str, master: pd.DataFrame, *, win_cfg, ex_cfg):
    snap = _load_snapshot_entries(date_yyyymmdd, race_id)
    if snap is None:
        return None

    final_race = master[master["race_id"].astype(str) == race_id].copy()
    if final_race.empty:
        return None

    live_entries = pd.DataFrame(snap.get("entries", []))
    if live_entries.empty:
        return None

    hist_master = master[master["date"].astype(str) < date_yyyymmdd]
    scored_live_win = score_entries(live_entries, hist_master, config=win_cfg)
    scored_live_ex = score_entries(live_entries, hist_master, config=ex_cfg)
    plan = build_race_bet_plan(
        scored_live_win,
        exotic_race=scored_live_ex,
        strategy=DEFAULT_STRATEGY,
        master=hist_master,
        before_date=date_yyyymmdd,
    )
    top5 = assign_marks(scored_live_ex)
    return plan, top5, final_race, snap


def compute_t10_race_roi(
    date_yyyymmdd: str,
    race_id: str,
    master: pd.DataFrame,
    payback: Optional[RacePayback],
    *,
    win_cfg=None,
    ex_cfg=None,
) -> Optional[T10RaceRoi]:
    scored = _score_t10_race(date_yyyymmdd, race_id, master, win_cfg=win_cfg, ex_cfg=ex_cfg)
    if scored is None:
        return None

    plan, top5, final_race, snap = scored
    if not is_tier_s_plus(plan.expectation_tier):
        return None

    finish = _finish_order(final_race)
    if len(finish) < 3 or top5.empty:
        return None

    axis = top5.iloc[0]
    axis_u = str(axis["umaban"])
    axis_odds = _parse_odds_value(axis.get("odds", float("nan")))
    second_u = str(top5.iloc[1]["umaban"]) if len(top5) > 1 else ""

    row = T10RaceRoi(
        race_id=race_id,
        race_no=int(final_race["race_no"].iloc[0]),
        race_name=str(final_race.get("race_name", pd.Series([""])).iloc[0]),
        expectation_tier=plan.expectation_tier,
        expectation_score=int(plan.expectation_score or 0),
    )

    investment = 0
    returns = 0

    if pd.notna(axis_odds) and axis_odds >= WIN_MIN_ODDS:
        row.win_points = 1
        investment += BET_UNIT
        if axis_u == finish[0]:
            row.win_hit = True
            returns += _win_payout_yen(axis_u, payback, str(axis.get("odds", "")))
    else:
        row.skipped_win_low_odds = True

    for u in (axis_u, second_u):
        if not u or not _should_buy_place(snap, u):
            continue
        row.place_points += 1
        investment += BET_UNIT
        if u in finish[:3]:
            row.place_hits += 1
            returns += _place_payout_yen(u, payback)

    formation = build_sanrenpuku_formation_firm(top5)
    if formation and formation.points > 0:
        row.sanren_points = formation.points
        investment += formation.points * BET_UNIT
        if check_sanrenpuku_formation_firm_hit(formation, finish):
            row.sanren_hit = True
            if payback:
                returns += payback.fuku3_yen

    row.investment = investment
    row.return_yen = returns
    return row


def build_t10_daily_roi_report(
    date_yyyymmdd: str,
    master: Optional[pd.DataFrame] = None,
    *,
    fetch_payback: bool = True,
) -> T10DailyRoiReport:
    master_df = master if master is not None else load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    race_ids = list_snapshot_race_ids(date_yyyymmdd, label=LABEL_T_MINUS_10)
    report = T10DailyRoiReport(date=date_yyyymmdd)

    if not race_ids:
        return report

    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)

    for rid in race_ids:
        scored = _score_t10_race(date_yyyymmdd, rid, master_df, win_cfg=win_cfg, ex_cfg=ex_cfg)
        if scored is None:
            continue
        plan, _top5, final_race, _ = scored
        if not is_tier_s_plus(plan.expectation_tier):
            report.skipped_not_s_plus += 1
            continue
        if len(_finish_order(final_race)) < 3:
            report.skipped_no_result += 1
            continue
        row = compute_t10_race_roi(
            date_yyyymmdd,
            rid,
            master_df,
            paybacks.get(rid),
            win_cfg=win_cfg,
            ex_cfg=ex_cfg,
        )
        if row is not None:
            report.races.append(row)

    report.races.sort(key=lambda r: r.race_no)
    return report


def format_t10_daily_roi_message(report: T10DailyRoiReport) -> str:
    lines: List[str] = [
        f"【園田 T-10実績 {report.date}】",
        "期待値S以上のみ",
        "買い: ◎単(2倍以上) + ◎○複勝(1.5倍以上) + 三連複5点",
        "",
    ]

    if not report.races:
        lines.append("対象レースなし")
        if report.skipped_not_s_plus:
            lines.append(f"(S未満 {report.skipped_not_s_plus}R)")
        if report.skipped_no_result:
            lines.append(f"(結果未確定 {report.skipped_no_result}R)")
        return "\n".join(lines)

    for r in report.races:
        win_note = "単勝見送" if r.skipped_win_low_odds and r.win_points == 0 else ""
        hit_bits = []
        if r.win_hit:
            hit_bits.append("単")
        if r.place_hits:
            hit_bits.append(f"複{r.place_hits}")
        if r.sanren_hit:
            hit_bits.append("三連")
        hit_txt = ",".join(hit_bits) if hit_bits else "外れ"
        pts = r.win_points + r.place_points + r.sanren_points
        suffix = f" {win_note}" if win_note else ""
        lines.append(f"R{r.race_no} {r.race_name[:12]} 期待値{r.expectation_tier}")
        lines.append(
            f"  {pts}点 投{r.investment} 払{r.return_yen} "
            f"回収{r.roi_pct:.0f}% {hit_txt}{suffix}"
        )

    lines.append("")
    total_pts = sum(r.win_points + r.place_points + r.sanren_points for r in report.races)
    lines.append(
        f"合計 {len(report.races)}R {total_pts}点 "
        f"投{report.total_investment} 払{report.total_return} "
        f"回収{report.total_roi_pct:.0f}%"
    )
    return "\n".join(lines)
