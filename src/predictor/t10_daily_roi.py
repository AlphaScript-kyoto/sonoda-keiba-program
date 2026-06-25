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
    _race_class,
    assign_marks,
    build_race_bet_plan,
    build_sanrenpuku_formation_firm,
    check_sanrenpuku_formation_firm_hit,
    format_sanrenpuku_formation_umaban_line,
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


@dataclass
class T10RaceRoi:
    race_id: str
    race_no: int
    race_name: str
    race_class: str
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
    win_umaban: str = ""
    win_bought: bool = False
    place_umabans: List[str] = field(default_factory=list)
    sanren_display: str = ""

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
        race_class=_race_class(final_race),
        expectation_tier=plan.expectation_tier,
        expectation_score=int(plan.expectation_score or 0),
    )

    investment = 0
    returns = 0

    if pd.notna(axis_odds) and axis_odds >= WIN_MIN_ODDS:
        row.win_points = 1
        row.win_bought = True
        row.win_umaban = axis_u
        investment += BET_UNIT
        if axis_u == finish[0]:
            row.win_hit = True
            returns += _win_payout_yen(axis_u, payback, str(axis.get("odds", "")))
    else:
        row.skipped_win_low_odds = True

    for u in (axis_u, second_u):
        if not u or not _should_buy_place(snap, u):
            continue
        row.place_umabans.append(u)
        row.place_points += 1
        investment += BET_UNIT
        if u in finish[:3]:
            row.place_hits += 1
            returns += _place_payout_yen(u, payback)

    formation = build_sanrenpuku_formation_firm(top5)
    if formation and formation.points > 0:
        row.sanren_points = formation.points
        sanren_line = format_sanrenpuku_formation_umaban_line(formation)
        row.sanren_display = f"{sanren_line}(\u8a08{formation.points}\u70b9)"
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


def _format_t10_race_block(r: T10RaceRoi) -> List[str]:
    cls = f" {r.race_class}" if r.race_class else ""
    name = r.race_name[:16] if r.race_name else ""
    lines = [f"{r.race_no}R {name}{cls} \u671f\u5f85\u5024{r.expectation_tier}"]

    if r.win_bought:
        lines.append(f"\u5358\u52dd\u3000{r.win_umaban}")
    elif r.skipped_win_low_odds:
        lines.append("\u5358\u52dd\u3000\u898b\u9001\u308a")
    else:
        lines.append("\u5358\u52dd\u3000\u2015")

    if r.place_umabans:
        lines.append(f"\u8907\u52dd\u3000{','.join(r.place_umabans)}")
    else:
        lines.append("\u8907\u52dd\u3000\u2015")

    if r.sanren_display:
        lines.append(f"\u4e09\u9023\u8907\u3000{r.sanren_display}")
    else:
        lines.append("\u4e09\u9023\u8907\u3000\u2015")

    lines.append(
        f"\u6295{r.investment}\u5186\u3000\u6255{r.return_yen}\u5186\u3000"
        f"\u56de\u53ce{r.roi_pct:.0f}%"
    )
    return lines


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
        lines.extend(_format_t10_race_block(r))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    total_pts = sum(r.win_points + r.place_points + r.sanren_points for r in report.races)
    lines.append(
        f"合計 {len(report.races)}R {total_pts}点 "
        f"投{report.total_investment} 払{report.total_return} "
        f"回収{report.total_roi_pct:.0f}%"
    )
    return "\n".join(lines)
