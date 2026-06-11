"""A/B backtest: model upset BOX vs 2-4-7 formation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, check_sanrenpuku_box_hit
from src.predictor.formation_247 import (
    DEFAULT_FORMATION_247,
    build_sanrenpuku_247_box,
    is_247_target_race,
)
import pandas as pd

from src.predictor.score import load_master
from src.predictor.scoring_config import load_split_scoring_configs


def _roi(hits: int, races: int, invest: int, return_yen: int) -> dict:
    return {
        "races": races,
        "hits": hits,
        "hit_rate": hits / races if races else 0.0,
        "invest": invest,
        "return_yen": return_yen,
        "roi": return_yen / invest if invest else 0.0,
    }


def compare_period(from_d: str, to_d: str) -> None:
    master = load_master()
    hist = master[
        (master["date"].astype(str) >= from_d) & (master["date"].astype(str) <= to_d)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    win_cfg, ex_cfg = load_split_scoring_configs()
    records = _collect_race_records(
        from_d, to_d, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY
    )

    model = {"races": 0, "hits": 0, "invest": 0, "return_yen": 0}
    f247 = {"races": 0, "hits": 0, "invest": 0, "return_yen": 0}
    f247_skip = 0

    ex_by_date_race: dict[tuple[str, int], object] = {}
    for date in sorted(hist["date"].astype(str).unique()):
        day = hist[hist["date"].astype(str) == date]
        for rid, grp in day.groupby("race_id"):
            ex_by_date_race[(date, int(grp["race_no"].iloc[0]))] = grp

    for rec in records:
        if not _exotic_high_for_record(rec, DEFAULT_STRATEGY):
            continue
        if rec.exotic_profile != "\u8352":
            continue

        if rec.sanrenpuku_box_points:
            model["races"] += 1
            model["invest"] += rec.sanrenpuku_box_points * BET_UNIT
            if rec.sanrenpuku_box_hit:
                model["hits"] += 1
                model["return_yen"] += rec.fuku3_yen

        race_df = ex_by_date_race.get((rec.date, rec.race_no))
        if race_df is None:
            f247_skip += 1
            continue
        from src.predictor.bets import collect_race_signals

        sig = collect_race_signals(race_df, rec.exotic_prob_top, rec.exotic_prob_gap)
        if not is_247_target_race(race_df, sig, exotic_profile=rec.exotic_profile):
            f247_skip += 1
            continue
        box = build_sanrenpuku_247_box(race_df, master, rec.date, DEFAULT_FORMATION_247)
        if box is None:
            f247_skip += 1
            continue
        f247["races"] += 1
        f247["invest"] += box.points * BET_UNIT
        finish = (
            race_df.assign(finish_num=pd.to_numeric(race_df["finish"], errors="coerce"))
            .dropna(subset=["finish_num"])
            .sort_values("finish_num")["umaban"]
            .astype(str)
            .tolist()
        )
        if len(finish) >= 3 and check_sanrenpuku_box_hit(box, finish):
            f247["hits"] += 1
            f247["return_yen"] += rec.fuku3_yen

    print(f"=== 2-4-7 A/B {from_d} .. {to_d} ===")
    print(f"records: {len(records)}  247 skipped: {f247_skip}")
    m = _roi(**model)
    f = _roi(**f247)
    print(
        f"Model BOX(荒+高): {m['races']}R hit {m['hits']} ({m['hit_rate']:.1%}) "
        f"ROI {m['roi']:.1%} invest {m['invest']:,} return {m['return_yen']:,}"
    )
    print(
        f"2-4-7 BOX:       {f['races']}R hit {f['hits']} ({f['hit_rate']:.1%}) "
        f"ROI {f['roi']:.1%} invest {f['invest']:,} return {f['return_yen']:,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    args = parser.parse_args()
    compare_period(args.from_date, args.to_date)


if __name__ == "__main__":
    main()
