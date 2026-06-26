"""Compare old vs new expectation scoring for a date (T-10 snapshots)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.expectation import (
    _head_strength_bonus,
    compute_expectation_score,
    load_expectation_config,
    tier_from_score,
)
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs
from src.predictor.snapshot_compare import list_snapshot_race_ids
from src.scraper.race_snapshots import LABEL_T_MINUS_10, snapshot_path

HIGH = "\u9ad8"
FIRM = "\u5805"


def score_old(plan) -> int:
    if plan.exotic_confidence != HIGH:
        return 0
    s = 25 + (15 if plan.exotic_profile == FIRM else 5)
    wp, gap = plan.win_prob_top, plan.prob_gap
    if wp >= 0.90:
        s += 12
    elif wp >= 0.85:
        s += 8
    elif wp >= 0.82:
        s += 4
    if gap >= 0.75:
        s += 12
    elif gap >= 0.70:
        s += 8
    elif gap >= 0.60:
        s += 4
    if plan.confidence == HIGH:
        s += 8
    if plan.win_profile == FIRM:
        s += 4
    return min(s, 100)


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else "20260625"
    win_cfg, ex_cfg = load_split_scoring_configs()
    cfg = load_expectation_config()
    master = load_master()
    hist = master[master["date"].astype(str) < date]

    rows = []
    for rid in sorted(
        list_snapshot_race_ids(date, label=LABEL_T_MINUS_10),
        key=lambda x: int(x.split("_")[-1]),
    ):
        snap = json.loads(snapshot_path(date, rid, LABEL_T_MINUS_10).read_text(encoding="utf-8"))
        live = pd.DataFrame(snap.get("entries", []))
        if live.empty:
            continue
        sw = score_entries(live, hist, config=win_cfg)
        se = score_entries(live, hist, config=ex_cfg)
        plan = build_race_bet_plan(
            sw, exotic_race=se, strategy=DEFAULT_STRATEGY, master=hist, before_date=date
        )
        s_old = score_old(plan)
        s_new = compute_expectation_score(plan)
        t_old = tier_from_score(s_old, cfg, plan)
        t_new = tier_from_score(s_new, cfg, plan)
        rows.append(
            {
                "rno": plan.race_no,
                "name": str(plan.race_name)[:18],
                "ex": f"{plan.exotic_profile}/{plan.exotic_confidence[0]}",
                "wp": plan.win_prob_top,
                "gap": plan.prob_gap,
                "fav": plan.fav_odds,
                "s_old": s_old,
                "t_old": t_old,
                "s_new": s_new,
                "t_new": t_new,
                "hb": _head_strength_bonus(plan),
            }
        )

    print(f"=== {date} T-10 expectation old vs new ({len(rows)}R) ===")
    print(
        f"Thresholds: SS>={cfg.tier_min_scores['SS']} "
        f"S>={cfg.tier_min_scores['S']} A>={cfg.tier_min_scores['A']}"
    )
    print()
    print("Tier counts  OLD:", dict(Counter(r["t_old"] for r in rows)))
    print("Tier counts  NEW:", dict(Counter(r["t_new"] for r in rows)))
    print()
    print("R  OLD        NEW        head+  fav  wp   gap  ex     race")
    for r in rows:
        mark = " *" if r["t_old"] != r["t_new"] else ""
        print(
            f"{r['rno']:2d}  {r['s_old']:3d} ({r['t_old']:2s})   "
            f"{r['s_new']:3d} ({r['t_new']:2s})   +{r['hb']:2d}  "
            f"{r['fav']:4.1f} {r['wp']:.2f} {r['gap']:.2f}  {r['ex']:5s}  {r['name']}{mark}"
        )

    changed = [r for r in rows if r["t_old"] != r["t_new"]]
    print()
    if changed:
        print("Tier changes:")
        for r in changed:
            print(f"  R{r['rno']}: {r['t_old']} -> {r['t_new']}  ({r['s_old']} -> {r['s_new']} pts)")
    else:
        print("Tier changes: none (score only)")

    print()
    print("--- S+ band score spread ---")
    bins = [(75, 77), (78, 79), (80, 84), (85, 89), (90, 94), (95, 100)]
    for label, tkey, skey in [("OLD", "t_old", "s_old"), ("NEW", "t_new", "s_new")]:
        scores = [r[skey] for r in rows if r[tkey] in ("S", "SS")]
        print(f"{label} S+/SS n={len(scores)} scores={sorted(scores)}")
        for lo, hi in bins:
            n = sum(1 for s in scores if lo <= s <= hi)
            if n:
                print(f"  {lo}-{hi}: {n}")


if __name__ == "__main__":
    main()
