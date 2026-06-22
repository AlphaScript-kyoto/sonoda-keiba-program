"""Compare upset-high 5pt formation ROI: all vs expectation S+."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import (
    BET_UNIT,
    _collect_race_records,
    _exotic_high_for_record,
    _load_paybacks_for_races,
)
from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.expectation import TIER_RANK
from src.predictor.score import load_master, score_entries, set_scoring_config
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

UPSET = "\u8352"
OUT = ROOT / "data" / "processed" / "logs" / "upset_high_tier_analysis.json"
PERIODS = [
    ("2024", "20240101", "20241231"),
    ("2025", "20250101", "20251231"),
    ("2026", "20260101", "20261231"),
]


def is_s_plus(tier: str) -> bool:
    return TIER_RANK.get(tier, 99) <= TIER_RANK["S"]


def roi_stats(rows: list[dict]) -> dict:
    inv = sum(r["inv"] for r in rows)
    ret = sum(r["ret"] for r in rows)
    n = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    return {
        "n_races": n,
        "invest_yen": inv,
        "return_yen": ret,
        "roi_pct": round(ret / inv * 100, 2) if inv else None,
        "hit_rate": round(hits / n, 4) if n else None,
    }


def analyze_period(
    label: str,
    f: str,
    t: str,
    master,
    win_cfg,
    ex_cfg,
    rec_index: dict[tuple[str, int], object],
) -> list[dict]:
    hist = master[
        (master["date"].astype(str) >= f) & (master["date"].astype(str) <= t)
    ]
    rows: list[dict] = []
    for race_id, grp in hist.groupby("race_id", sort=False):
        g = grp.copy()
        date = str(g["date"].iloc[0])
        race_no = int(g["race_no"].iloc[0])
        rec = rec_index.get((date, race_no))
        if rec is None:
            continue
        eh = _exotic_high_for_record(rec, DEFAULT_STRATEGY)
        if rec.exotic_profile != UPSET or not eh or not rec.sanrenpuku_formation_points:
            continue

        before = master[
            (master["date"].astype(str) < date)
            | (
                (master["date"].astype(str) == date)
                & (master["race_no"].astype(int) < race_no)
            )
        ]
        set_scoring_config(win_cfg)
        win_sc = score_entries(g, before)
        set_scoring_config(ex_cfg)
        ex_sc = score_entries(g, before)
        plan = build_race_bet_plan(
            win_sc,
            exotic_race=ex_sc,
            strategy=DEFAULT_STRATEGY,
            master=master,
            before_date=date,
        )
        if plan.exotic_profile != UPSET or plan.exotic_confidence != "\u9ad8":
            continue
        if not plan.sanrenpuku_formation or plan.sanrenpuku_formation.points <= 0:
            continue

        rows.append(
            {
                "year": label,
                "date": date,
                "race_no": race_no,
                "race_name": str(g.get("race_name", "").iloc[0])
                if "race_name" in g.columns
                else "",
                "tier": plan.expectation_tier,
                "score": plan.expectation_score,
                "win_profile": plan.win_profile,
                "exotic_profile": plan.exotic_profile,
                "fav_odds": round(float(plan.fav_odds), 2),
                "win_prob_top": round(float(plan.win_prob_top), 4),
                "prob_gap": round(float(plan.prob_gap), 4),
                "inv": rec.sanrenpuku_formation_points * BET_UNIT,
                "ret": rec.fuku3_yen if rec.sanrenpuku_formation_hit else 0,
                "hit": bool(rec.sanrenpuku_formation_hit),
            }
        )
    return rows


def main() -> None:
    master = load_master()
    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()

    rec_index: dict[tuple[str, int], object] = {}
    for _label, f, t in PERIODS:
        hist = master[
            (master["date"].astype(str) >= f) & (master["date"].astype(str) <= t)
        ]
        race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
        paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
        recs = _collect_race_records(f, t, master, paybacks, win_cfg, ex_cfg, DEFAULT_STRATEGY)
        for rec in recs:
            rec_index[(rec.date, int(rec.race_no))] = rec

    all_rows: list[dict] = []
    by_year: dict[str, list[dict]] = {}
    for label, f, t in PERIODS:
        print(f"analyzing {label}...", flush=True)
        yr = analyze_period(label, f, t, master, win_cfg, ex_cfg, rec_index)
        by_year[label] = yr
        all_rows.extend(yr)
        print(f"  upset_high formation: {len(yr)}", flush=True)

    s_plus_rows = [r for r in all_rows if is_s_plus(r["tier"])]
    below_s = [r for r in all_rows if not is_s_plus(r["tier"])]

    tier_dist = dict(
        sorted(Counter(r["tier"] for r in all_rows).items(), key=lambda x: TIER_RANK.get(x[0], 99))
    )

    report = {
        "segment": "exotic_profile=upset, exotic_high, sanren 5pt formation",
        "tier_s_plus": "SS or S (score>=75)",
        "pooled": {
            "all": roi_stats(all_rows),
            "s_plus": roi_stats(s_plus_rows),
            "below_s": roi_stats(below_s),
            "tier_distribution": tier_dist,
            "s_plus_share_pct": round(len(s_plus_rows) / len(all_rows) * 100, 2)
            if all_rows
            else None,
            "s_plus_win_profile": dict(Counter(r["win_profile"] for r in s_plus_rows)),
            "all_win_profile": dict(Counter(r["win_profile"] for r in all_rows)),
            "s_plus_avg_fav_odds": round(
                sum(r["fav_odds"] for r in s_plus_rows) / len(s_plus_rows), 2
            )
            if s_plus_rows
            else None,
            "all_avg_fav_odds": round(
                sum(r["fav_odds"] for r in all_rows) / len(all_rows), 2
            )
            if all_rows
            else None,
        },
        "by_year": {},
    }

    for label in by_year:
        yr = by_year[label]
        ysp = [r for r in yr if is_s_plus(r["tier"])]
        ybl = [r for r in yr if not is_s_plus(r["tier"])]
        report["by_year"][label] = {
            "all": roi_stats(yr),
            "s_plus": roi_stats(ysp),
            "below_s": roi_stats(ybl),
            "tier_distribution": dict(Counter(r["tier"] for r in yr)),
            "s_plus_count": len(ysp),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
