"""Export backtest rows for R segment analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, should_skip_win_bet
from src.predictor.score import load_master
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

DEFAULT_OUT = ROOT / "r_analysis" / "input" / "backtest_rows.csv"
FIRM = "\u5805"
UPSET = "\u8352"


def records_to_export_df(records, *, strategy=DEFAULT_STRATEGY) -> pd.DataFrame:
    rows = []
    for rec in records:
        exotic_high = _exotic_high_for_record(rec, strategy)
        skip_win = should_skip_win_bet(rec.win_profile, rec.pred_odds, strategy)
        skip_place = rec.win_profile == UPSET and strategy.skip_place_on_upset

        win_invest = 0 if skip_win else BET_UNIT
        win_return = rec.win_payout if (not skip_win and rec.win_hit) else 0
        place_invest = 0 if skip_place else BET_UNIT
        place_return = rec.place_payout if (not skip_place and rec.place_hit) else 0

        if exotic_high and rec.exotic_profile == FIRM:
            if (
                rec.is_volatile
                and strategy.use_firm_volatile_box
                and rec.sanrenpuku_firm_box_points
            ):
                sp_pts = rec.sanrenpuku_firm_box_points
                sp_hit = rec.sanrenpuku_firm_box_hit
            else:
                sp_pts = rec.sanrenpuku_points
                sp_hit = rec.sanrenpuku_hit
            st_pts = rec.sanrentan_points
            st_hit = rec.sanrentan_hit
            if rec.is_volatile:
                wd_pts = rec.wide_upset_points
                wd_hit = rec.wide_upset_hit
                wd_return = rec.wide_upset_return_yen
            else:
                wd_pts = rec.wide_firm_points
                wd_hit = rec.wide_firm_hit
                wd_return = rec.wide_firm_return_yen
        elif exotic_high and rec.exotic_profile == UPSET:
            sp_pts = rec.sanrenpuku_box_points
            sp_hit = rec.sanrenpuku_box_hit
            st_pts = 0
            st_hit = False
            wd_pts = rec.wide_upset_points
            wd_hit = rec.wide_upset_hit
            wd_return = rec.wide_upset_return_yen
        else:
            sp_pts = st_pts = wd_pts = 0
            sp_hit = st_hit = wd_hit = False
            wd_return = 0

        sp_invest = sp_pts * BET_UNIT if sp_pts else 0
        sp_return = rec.fuku3_yen if (sp_pts and sp_hit) else 0
        st_invest = st_pts * BET_UNIT if st_pts else 0
        st_return = rec.tan3_yen if (st_pts and st_hit) else 0
        wd_invest = wd_pts * BET_UNIT if wd_pts else 0

        rows.append(
            {
                "date": rec.date,
                "race_no": rec.race_no,
                "race_name": rec.race_name,
                "pred_umaban": rec.pred_umaban,
                "pred_horse": rec.pred_horse,
                "pred_odds": rec.pred_odds,
                "actual_1st": rec.actual_1st,
                "win_prob_top": rec.win_prob_top,
                "prob_gap": rec.prob_gap,
                "exotic_prob_top": rec.exotic_prob_top,
                "exotic_prob_gap": rec.exotic_prob_gap,
                "win_profile": rec.win_profile,
                "exotic_profile": rec.exotic_profile,
                "is_volatile": rec.is_volatile,
                "win_high": rec.win_high,
                "exotic_high": exotic_high,
                "win_hit": rec.win_hit,
                "place_hit": rec.place_hit,
                "skip_win": skip_win,
                "skip_place": skip_place,
                "win_invest_yen": win_invest,
                "win_return_yen": win_return,
                "place_invest_yen": place_invest,
                "place_payout_yen": rec.place_payout,
                "hypothetical_place_return_yen": (
                    rec.place_payout if rec.place_hit else 0
                ),
                "place_return_yen": place_return,
                "sanrenpuku_points": sp_pts,
                "sanrenpuku_hit": sp_hit,
                "sanrenpuku_invest_yen": sp_invest,
                "sanrenpuku_return_yen": sp_return,
                "sanrentan_points": st_pts,
                "sanrentan_hit": st_hit,
                "sanrentan_invest_yen": st_invest,
                "sanrentan_return_yen": st_return,
                "wide_points": wd_pts,
                "wide_hit": wd_hit,
                "wide_invest_yen": wd_invest,
                "wide_return_yen": wd_return,
            }
        )
    return pd.DataFrame(rows)


def export_backtest_rows(
    from_yyyymmdd: str,
    to_yyyymmdd: str,
    out_path: Path = DEFAULT_OUT,
    *,
    fetch_payback: bool = False,
) -> Path:
    master = load_master()
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    if hist.empty:
        raise SystemExit(f"No master rows for {from_yyyymmdd}..{to_yyyymmdd}")

    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=fetch_payback)
    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()
    records = _collect_race_records(
        from_yyyymmdd,
        to_yyyymmdd,
        master,
        paybacks,
        win_cfg,
        ex_cfg,
        DEFAULT_STRATEGY,
    )
    df = records_to_export_df(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export backtest rows for R analysis")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output CSV path")
    parser.add_argument("--fetch-payback", action="store_true")
    args = parser.parse_args()
    out = export_backtest_rows(
        args.from_date,
        args.to_date,
        Path(args.out),
        fetch_payback=args.fetch_payback,
    )
    n = len(pd.read_csv(out))
    print(f"Exported {out} ({n} rows)")


if __name__ == "__main__":
    main()
