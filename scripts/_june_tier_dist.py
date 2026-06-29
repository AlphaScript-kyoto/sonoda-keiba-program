"""June expectation tier distribution (master / predict_date)."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.expectation import TIER_ORDER, load_expectation_config
from src.predictor.score import load_master, predict_date
from src.predictor.scoring_config import load_split_scoring_configs


def main() -> None:
    month = sys.argv[1] if len(sys.argv) > 1 else "202606"
    win_cfg, ex_cfg = load_split_scoring_configs()
    cfg = load_expectation_config()
    master = load_master()
    dates = sorted(
        master.loc[master["date"].astype(str).str.startswith(month), "date"]
        .astype(str)
        .unique()
        .tolist()
    )

    total = Counter()
    by_date: dict[str, Counter] = {}
    rows = []

    for date in dates:
        sw = predict_date(date, master=master, fetch_entries=False, config=win_cfg)
        se = predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
        ex_by = {str(r): g for r, g in se.groupby("race_id", sort=False)}
        hist = master[master["date"].astype(str) < date]
        day_cnt = Counter()
        for rid, g in sw.groupby("race_id", sort=False):
            plan = build_race_bet_plan(
                g,
                exotic_race=ex_by.get(str(rid)),
                strategy=DEFAULT_STRATEGY,
                master=hist,
                before_date=date,
            )
            total[plan.expectation_tier] += 1
            day_cnt[plan.expectation_tier] += 1
            rows.append(
                {
                    "date": date,
                    "rno": int(plan.race_no),
                    "tier": plan.expectation_tier,
                    "score": int(plan.expectation_score or 0),
                    "ex_prof": plan.exotic_profile,
                    "ex_conf": plan.exotic_confidence,
                    "fav": plan.fav_odds,
                }
            )
        by_date[date] = day_cnt

    n = sum(total.values())
    y, m = int(month[:4]), int(month[4:6])
    print(f"=== {y}\u5e74{m}\u6708 \u5712\u7530 \u671f\u5f85\u5024\u5206\u5e03 ({n}R) ===")
    mins = cfg.tier_min_scores
    print(
        f"thresholds: SS>={mins['SS']} S>={mins['S']} "
        f"A>={mins['A']} B>={mins['B']}"
    )
    print()
    for t in TIER_ORDER:
        c = total[t]
        bar = "#" * max(1, c // 2) if c else ""
        print(f"  {t}: {c:3d}R ({c/n*100:5.1f}%) {bar}")
    print()
    print("--- \u958b\u50ac\u65e5\u5225 ---")
    for date in dates:
        c = by_date[date]
        parts = " ".join(f"{t}{c[t]}" for t in TIER_ORDER if c[t])
        print(f"  {date[4:6]}/{date[6:8]} ({sum(c.values())}R)  {parts}")

    ss = [r for r in rows if r["tier"] == "SS"]
    s = [r for r in rows if r["tier"] == "S"]
    if ss:
        print()
        print("SS:", [f"{r['date'][6:8]}/{r['rno']}R score={r['score']}" for r in ss])
    if s:
        print()
        print("S:")
        for r in sorted(s, key=lambda x: (x["date"], x["rno"])):
            fav = r["fav"] if r["fav"] == r["fav"] else 0.0
            print(
                f"  {r['date'][6:8]}/{r['rno']:2d}R score={r['score']:3d} "
                f"{r['ex_prof']}/{r['ex_conf'][0]} fav={fav:.1f}"
            )


if __name__ == "__main__":
    main()


def compare_ss_threshold(month: str = "202606", ss_min: int = 95) -> None:
    """Simulate SS threshold change without editing config."""
    from collections import Counter
    from dataclasses import replace

    from src.predictor.expectation import (
        compute_expectation_score,
        is_s_eligible,
        is_ss_eligible,
        tier_from_score,
    )

    win_cfg, ex_cfg = load_split_scoring_configs()
    cfg_base = load_expectation_config()
    cfg_alt = replace(
        cfg_base,
        tier_min_scores={**cfg_base.tier_min_scores, "SS": ss_min},
    )
    master = load_master()
    dates = sorted(
        master.loc[master["date"].astype(str).str.startswith(month), "date"]
        .astype(str)
        .unique()
        .tolist()
    )
    rows = []
    for date in dates:
        sw = predict_date(date, master=master, fetch_entries=False, config=win_cfg)
        se = predict_date(date, master=master, fetch_entries=False, config=ex_cfg)
        ex_by = {str(r): g for r, g in se.groupby("race_id", sort=False)}
        hist = master[master["date"].astype(str) < date]
        for rid, g in sw.groupby("race_id", sort=False):
            p = build_race_bet_plan(
                g,
                exotic_race=ex_by.get(str(rid)),
                strategy=DEFAULT_STRATEGY,
                master=hist,
                before_date=date,
            )
            sc = compute_expectation_score(p)
            t_base = tier_from_score(sc, cfg_base, p)
            t_alt = tier_from_score(sc, cfg_alt, p)
            rows.append((date, int(p.race_no), sc, t_base, t_alt, p.fav_odds))

    n = len(rows)
    c_base = Counter(r[3] for r in rows)
    c_alt = Counter(r[4] for r in rows)
    ss_b, s_b = c_base["SS"], c_base["S"]
    ss_a, s_a = c_alt["SS"], c_alt["S"]
    moved = [r for r in rows if r[3] == "SS" and r[4] != "SS"]

    print(f"=== {month} SS threshold compare ===")
    print(
        f"SS>={cfg_base.tier_min_scores['SS']}: "
        f"SS {ss_b}R ({ss_b/n*100:.1f}%)  S {s_b}R ({s_b/n*100:.1f}%)  "
        f"ratio {ss_b/s_b:.2f}:1" if s_b else "S=0"
    )
    print(
        f"SS>={ss_min}:          "
        f"SS {ss_a}R ({ss_a/n*100:.1f}%)  S {s_a}R ({s_a/n*100:.1f}%)  "
        f"ratio {ss_a/s_a:.2f}:1" if s_a else "S=0"
    )
    print()
    print(f"distribution if SS>={ss_min}:")
    for t in TIER_ORDER:
        print(f"  {t}: {c_alt[t]:3d}R ({c_alt[t]/n*100:5.1f}%)")
    print()
    print(f"downgraded from SS: {len(moved)}R")
    down = Counter(r[4] for r in moved)
    for t in TIER_ORDER:
        if down[t]:
            print(f"  -> {t}: {down[t]}R")
    print()
    print("downgraded races (score fav new_tier):")
    for date, rno, sc, _tb, t_alt, fav in sorted(moved, key=lambda x: (-x[2], x[0], x[1])):
        fav_s = f"{fav:.1f}" if fav == fav else "?"
        print(f"  {date[4:6]}/{date[6:8]} {rno:2d}R score={sc} fav={fav_s} -> {t_alt}")
