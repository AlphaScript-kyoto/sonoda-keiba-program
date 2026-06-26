"""One-off: T-10 expectation tier S score distribution for a date."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.expectation import TIER_ORDER, load_expectation_config
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.scraper.race_snapshots import LABEL_T_MINUS_10, snapshot_path


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else "20260625"
    win_cfg, ex_cfg = load_split_scoring_configs()
    cfg = load_expectation_config()
    master = load_master()
    hist = master[master["date"].astype(str) < date]

    rows = []
    for rid in list_snapshot_race_ids(date, label=LABEL_T_MINUS_10):
        snap = json.loads(snapshot_path(date, rid, LABEL_T_MINUS_10).read_text(encoding="utf-8"))
        live = pd.DataFrame(snap.get("entries", []))
        if live.empty:
            continue
        sw = score_entries(live, hist, config=win_cfg)
        se = score_entries(live, hist, config=ex_cfg)
        plan = build_race_bet_plan(
            sw, exotic_race=se, strategy=DEFAULT_STRATEGY, master=hist, before_date=date
        )
        rows.append(
            {
                "rno": int(plan.race_no),
                "name": str(plan.race_name)[:20],
                "tier": plan.expectation_tier,
                "score": int(plan.expectation_score or 0),
                "ex_prof": plan.exotic_profile,
                "ex_conf": plan.exotic_confidence,
                "win_p": float(plan.win_prob_top),
                "gap": float(plan.prob_gap),
                "fav": float(plan.fav_odds) if plan.fav_odds == plan.fav_odds else None,
            }
        )
    rows.sort(key=lambda x: x["rno"])

    print(f"=== T-10 expectation distribution {date} ({len(rows)}R) ===")
    print(f"Thresholds: SS>={cfg.tier_min_scores['SS']} S>={cfg.tier_min_scores['S']} "
          f"A>={cfg.tier_min_scores['A']}")
    print("Tier counts:", dict(Counter(r["tier"] for r in rows)))
    print()

    print("R   tier  score  ex/conf   win_p  gap   fav   name")
    for r in rows:
        flag = " <<" if r["tier"] in ("S", "SS") else ""
        fav = r["fav"] if r["fav"] is not None else 0.0
        print(
            f"{r['rno']:2d}  {r['tier']:4s}  {r['score']:3d}   "
            f"{r['ex_prof']}/{r['ex_conf'][0]}  "
            f"{r['win_p']:.2f}  {r['gap']:.2f}  {fav:4.1f}  {r['name']}{flag}"
        )

    s_rows = [r for r in rows if r["tier"] == "S"]
    ss_rows = [r for r in rows if r["tier"] == "SS"]
    print()
    print(f"=== S tier only ({len(s_rows)}R, need >={cfg.tier_min_scores['S']}) ===")
    bins = [(75, 77), (78, 79), (80, 84), (85, 89), (90, 94), (95, 100)]
    for lo, hi in bins:
        n = sum(1 for r in s_rows if lo <= r["score"] <= hi)
        print(f"  {lo:2d}-{hi:2d}: {n:2d} {'#' * n}")
    if ss_rows:
        print(f"  SS: {[(r['rno'], r['score']) for r in ss_rows]}")

    a_rows = [r for r in rows if r["tier"] == "A"]
    print()
    print(f"=== A tier upper ({len(a_rows)}R, threshold {cfg.tier_min_scores['A']}-74) ===")
    for r in sorted(a_rows, key=lambda x: -x["score"]):
        print(f"  R{r['rno']:2d} score={r['score']} (S until +{cfg.tier_min_scores['S'] - r['score'] - 1})")

    border = [r for r in rows if 75 <= r["score"] < 80]
    if border:
        print()
        print("S lower band (75-79, borderline vs A):")
        for r in border:
            print(f"  R{r['rno']} score={r['score']} {r['name']}")


if __name__ == "__main__":
    main()
