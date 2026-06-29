"""June segment ROI for expectation S and upset x High."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

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
from src.predictor.formation_247 import parse_place_odds_low
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.predictor.t10_daily_roi import (
    PLACE_MIN_ODDS,
    WIN_MIN_ODDS,
    _load_snapshot_entries,
)
from src.predictor.upset_high_bet_gate import (
    UpsetHighBetRecord,
    UpsetHighBetState,
    _append_settled,
    on_race_day_open,
    record_signaled_bet,
    should_send_upset_high_buy,
)
from src.predictor.upset_high_daily_roi import _is_t10_upset_high_plan
from src.scraper.race_snapshots import LABEL_T_MINUS_10


@dataclass
class SRaceRoi:
    date: str
    race_no: int
    investment: int = 0
    return_yen: int = 0
    hit: bool = False
    win_hit: bool = False
    place_hits: int = 0
    sanren_hit: bool = False


@dataclass
class UHRaceRoi:
    date: str
    race_no: int
    race_name: str
    investment: int
    return_yen: int
    hit: bool
    skipped_gate: bool = False


@dataclass
class SegmentTotals:
    races: int = 0
    investment: int = 0
    return_yen: int = 0
    hits: int = 0
    t10_odds_days: int = 0

    @property
    def roi_pct(self) -> float:
        return (self.return_yen / self.investment * 100.0) if self.investment else 0.0

    @property
    def hit_rate_pct(self) -> float:
        return (self.hits / self.races * 100.0) if self.races else 0.0


def _place_odds_low_from_master(row) -> float:
    if "place_odds" in row.index:
        low = parse_place_odds_low(str(row.get("place_odds", "")))
        if low == low:
            return low
    return float("nan")


def _score_race_fast(
    date_yyyymmdd: str,
    race_id: str,
    master,
    day_win,
    ex_by: dict,
):
    win_g = day_win[day_win["race_id"].astype(str) == race_id]
    if win_g.empty:
        return None

    final_race = master[master["race_id"].astype(str) == race_id].copy()
    if final_race.empty:
        return None

    ex_g = ex_by.get(race_id, win_g)
    hist_master = master[master["date"].astype(str) < date_yyyymmdd]
    plan = build_race_bet_plan(
        win_g,
        exotic_race=ex_g,
        strategy=DEFAULT_STRATEGY,
        master=hist_master,
        before_date=date_yyyymmdd,
    )
    top5 = assign_marks(ex_g)
    snap = _load_snapshot_entries(date_yyyymmdd, race_id)
    return plan, top5, final_race, snap


def compute_s_tier_race_roi(
    date_yyyymmdd: str,
    race_id: str,
    master,
    payback,
    scored,
) -> Optional[SRaceRoi]:
    if scored is None:
        return None
    plan, top5, final_race, snap = scored
    used_t10_odds = snap is not None

    if plan.expectation_tier != "S":
        return None

    finish = _finish_order(final_race)
    if len(finish) < 3 or top5.empty:
        return None

    axis = top5.iloc[0]
    axis_u = str(axis["umaban"])
    second_u = str(top5.iloc[1]["umaban"]) if len(top5) > 1 else ""

    if used_t10_odds:
        axis_odds = _parse_odds_value(axis.get("odds", float("nan")))
    else:
        axis_row = final_race.loc[final_race["umaban"].astype(str) == axis_u]
        axis_odds = _parse_odds_value(
            axis_row["odds"].iloc[0] if not axis_row.empty else float("nan")
        )

    row = SRaceRoi(date=date_yyyymmdd, race_no=int(final_race["race_no"].iloc[0]))
    investment = 0
    returns = 0

    if pd.notna(axis_odds) and axis_odds >= WIN_MIN_ODDS:
        investment += BET_UNIT
        if axis_u == finish[0]:
            row.win_hit = True
            odds_src = str(axis.get("odds", "")) if used_t10_odds else str(axis_odds)
            returns += _win_payout_yen(axis_u, payback, odds_src)

    for u in (axis_u, second_u):
        if not u:
            continue
        low = float("nan")
        if used_t10_odds and snap:
            place_map = (snap.get("odds") or {}).get("place") or {}
            low = parse_place_odds_low(str(place_map.get(str(u), "")))
        else:
            u_row = final_race.loc[final_race["umaban"].astype(str) == u]
            if not u_row.empty:
                low = _place_odds_low_from_master(u_row.iloc[0])
        if pd.isna(low) or low < PLACE_MIN_ODDS:
            continue
        investment += BET_UNIT
        if u in finish[:3]:
            row.place_hits += 1
            returns += _place_payout_yen(u, payback)

    formation = build_sanrenpuku_formation_firm(top5)
    if formation and formation.points > 0:
        investment += formation.points * BET_UNIT
        if check_sanrenpuku_formation_firm_hit(formation, finish):
            row.sanren_hit = True
            if payback:
                returns += payback.fuku3_yen

    row.investment = investment
    row.return_yen = returns
    row.hit = bool(row.win_hit or row.place_hits > 0 or row.sanren_hit)
    return row if investment > 0 else None


def compute_upset_high_race_roi(
    date_yyyymmdd: str,
    race_id: str,
    payback,
    scored,
) -> Optional[UHRaceRoi]:
    if scored is None:
        return None
    plan, _top5, final_race, _snap = scored
    if not _is_t10_upset_high_plan(plan):
        return None

    formation = plan.sanrenpuku_formation
    assert formation is not None
    finish = _finish_order(final_race)
    hit = check_sanrenpuku_formation_firm_hit(formation, finish)
    ret = payback.fuku3_yen if hit and payback else 0
    return UHRaceRoi(
        date=date_yyyymmdd,
        race_no=int(plan.race_no),
        race_name=str(plan.race_name or "")[:12],
        investment=formation.points * BET_UNIT,
        return_yen=ret,
        hit=hit,
    )


def analyze_june(year_month: str = "202606", *, fetch_payback: bool = False):
    master = load_master()
    win_cfg, ex_cfg = load_split_scoring_configs()
    dates = sorted(
        master.loc[master["date"].astype(str).str.startswith(year_month), "date"]
        .astype(str)
        .unique()
        .tolist()
    )
    if not dates:
        raise SystemExit(f"No master races for {year_month}")

    all_rids: List[str] = []
    for d in dates:
        day = master[master["date"].astype(str) == d]
        all_rids.extend(sorted(day["race_id"].astype(str).unique().tolist()))
    paybacks = _load_paybacks_for_races(sorted(set(all_rids)), fetch_missing=fetch_payback)

    s_rows: List[SRaceRoi] = []
    uh_qualifying: List[UHRaceRoi] = []
    t10_days = 0

    for date in dates:
        if list_snapshot_race_ids(date, label=LABEL_T_MINUS_10):
            t10_days += 1
        day_win = predict_date(date, master=master, fetch_entries=False, config=win_cfg)
        day_ex = predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
        ex_by = {str(r): g for r, g in day_ex.groupby("race_id", sort=False)}
        day = master[master["date"].astype(str) == date]
        for rid in sorted(day["race_id"].astype(str).unique().tolist()):
            pb = paybacks.get(rid)
            scored = _score_race_fast(date, rid, master, day_win, ex_by)
            s_row = compute_s_tier_race_roi(date, rid, master, pb, scored)
            if s_row is not None:
                s_rows.append(s_row)
            uh_row = compute_upset_high_race_roi(date, rid, pb, scored)
            if uh_row is not None:
                uh_qualifying.append(uh_row)

    s_tot = SegmentTotals(t10_odds_days=t10_days)
    for r in s_rows:
        s_tot.races += 1
        s_tot.investment += r.investment
        s_tot.return_yen += r.return_yen
        if r.hit:
            s_tot.hits += 1

    gate = UpsetHighBetState()
    uh_actual: List[UHRaceRoi] = []
    for row in sorted(uh_qualifying, key=lambda r: (r.date, r.race_no)):
        on_race_day_open(row.date, gate, master=master)
        ok, _reason = should_send_upset_high_buy(gate, row.date, master=master)
        if not ok:
            uh_actual.append(
                UHRaceRoi(
                    date=row.date,
                    race_no=row.race_no,
                    race_name=row.race_name,
                    investment=row.investment,
                    return_yen=row.return_yen,
                    hit=row.hit,
                    skipped_gate=True,
                )
            )
            continue
        uh_actual.append(row)
        record_signaled_bet(gate, row.date, row.race_no, row.investment)
        _append_settled(
            gate,
            UpsetHighBetRecord(
                row.date,
                row.race_no,
                row.investment,
                row.return_yen,
                row.hit,
            ),
        )

    uh_tot = SegmentTotals()
    for r in uh_actual:
        if r.skipped_gate:
            continue
        uh_tot.races += 1
        uh_tot.investment += r.investment
        uh_tot.return_yen += r.return_yen
        if r.hit:
            uh_tot.hits += 1

    return s_tot, uh_tot, uh_actual


def format_s_message(year_month: str, totals: SegmentTotals) -> str:
    y, m = int(year_month[:4]), int(year_month[4:6])
    profit = totals.return_yen - totals.investment
    sign = "+" if profit > 0 else ""
    yen = "\u5186"
    return "\n".join(
        [
            f"\u3010\u5712\u7530 {y}\u5e74{m}\u6708 \u671f\u5f85\u5024S \u6210\u7e3e\u3011",
            "\u203b\u73fe\u884c\u30ed\u30b8\u30c3\u30af\u30fbT-10\u8cb7\u3044\u76ee"
            "\uff08\u53582\u500d+/\u89075\u500d+/\u4e09\u9023\u89075\u70b9\uff09",
            (
                f"\u5bfe\u8c61 {totals.races}\u30ec\u30fc\u30b9"
                f"\uff08T-10\u30aa\u30c3\u30ba\u3042\u308a {totals.t10_odds_days}"
                f"\u958b\u50ac\u65e5\uff09"
            ),
            f"\u6295\u8cc7 {totals.investment:,}{yen}",
            f"\u6255\u623b {totals.return_yen:,}{yen}",
            f"\u53ce\u652f {sign}{profit:,}{yen}",
            f"\u56de\u53ce\u7387 {totals.roi_pct:.1f}%",
            (
                f"\u4e2d\u7684\u7387 {totals.hit_rate_pct:.1f}%"
                f"\uff08{totals.hits}/{totals.races}\u30ec\u30fc\u30b9\uff09"
            ),
        ]
    )


def format_uh_message(
    year_month: str, totals: SegmentTotals, qualifying: int, skipped: int
) -> str:
    y, m = int(year_month[:4]), int(year_month[4:6])
    profit = totals.return_yen - totals.investment
    sign = "+" if profit > 0 else ""
    yen = "\u5186"
    return "\n".join(
        [
            f"\u3010\u5712\u7530 {y}\u5e74{m}\u6708 \u8352\u00d7High \u6210\u7e3e\u3011",
            "\u203b\u73fe\u884c\u30ed\u30b8\u30c3\u30af\u30fb"
            "\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f35\u70b9"
            "\uff08\u4f11\u6b62\u30b2\u30fc\u30c8\u53cd\u6620\uff09",
            (
                f"\u8cfc\u5165 {totals.races}\u30ec\u30fc\u30b9"
                f"\uff08\u8a72\u5f53 {qualifying}\u30ec\u30fc\u30b9"
                f"\u30fb\u898b\u9001\u308a {skipped}\uff09"
            ),
            f"\u6295\u8cc7 {totals.investment:,}{yen}",
            f"\u6255\u623b {totals.return_yen:,}{yen}",
            f"\u53ce\u652f {sign}{profit:,}{yen}",
            f"\u56de\u53ce\u7387 {totals.roi_pct:.1f}%",
            (
                f"\u4e2d\u7684\u7387 {totals.hit_rate_pct:.1f}%"
                f"\uff08{totals.hits}/{totals.races}\u30ec\u30fc\u30b9\uff09"
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="June ROI for expectation S and upset x High")
    parser.add_argument("--month", default="202606", help="YYYYMM")
    parser.add_argument("--fetch-payback", action="store_true")
    parser.add_argument("--line", action="store_true", help="Send 2 messages to LINE_USER_ID")
    args = parser.parse_args()

    s_tot, uh_tot, uh_rows = analyze_june(args.month, fetch_payback=args.fetch_payback)
    qualifying = len(uh_rows)
    skipped = len([r for r in uh_rows if r.skipped_gate])
    msg_s = format_s_message(args.month, s_tot)
    msg_uh = format_uh_message(args.month, uh_tot, qualifying, skipped)

    print(msg_s)
    print()
    print("---")
    print()
    print(msg_uh)

    if args.line:
        from tools.line_bot import send_line_message

        for msg in (msg_s, msg_uh):
            resp = send_line_message(msg)
            if resp.status_code != 200:
                raise SystemExit(f"LINE failed: {resp.status_code} {resp.text}")
        print("\nLINE: sent 2 messages")


if __name__ == "__main__":
    main()
