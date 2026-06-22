"""Fast upset-high tier ROI using cached backtest rows + tier scoring."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import BET_UNIT
from src.predictor.bets import DEFAULT_STRATEGY, build_race_bet_plan
from src.predictor.expectation import TIER_RANK
from src.predictor.score import load_master, score_entries, set_scoring_config
from src.predictor.scoring_config import ScoringConfig, load_split_scoring_configs

UPSET = "\u8352"
CACHE_DIR = ROOT / "data" / "processed" / "logs" / "upset_high_cache"
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


def main() -> None:
    master = load_master()
    win_cfg = ScoringConfig.load_tuned()
    _, ex_cfg = load_split_scoring_configs()
    all_rows: list[dict] = []
    by_year: dict[str, list[dict]] = {}

    for label, f, t in PERIODS:
        cache = CACHE_DIR / f"records_{f}_{t}.json"
        if not cache.exists():
            raise SystemExit(f"missing cache {cache}; run analyze_upset_high_streaks first")
        raw = json.loads(cache.read_text(encoding="utf-8"))
        hist = master[
            (master["date"].astype(str) >= f) & (master["date"].astype(str) <= t)
        ]
        yr_rows: list[dict] = []
        for rec in raw:
            if rec["exotic_profile"] != UPSET or not rec["exotic_high"]:
                continue
            if not rec["form_pts"]:
                continue
            g = hist[
                (hist["date"].astype(str) == rec["date"])
                & (hist["race_no"].astype(int) == int(rec["race_no"]))
            ]
            if g.empty:
                continue
            date = rec["date"]
            race_no = int(rec["race_no"])
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
            row = {
                "year": label,
                "date": date,
                "race_no": race_no,
                "tier": plan.expectation_tier,
                "score": plan.expectation_score,
                "win_profile": plan.win_profile,
                "fav_odds": round(float(plan.fav_odds), 2),
                "win_prob_top": round(float(plan.win_prob_top), 4),
                "inv": rec["form_pts"] * BET_UNIT,
                "ret": rec["fuku3_yen"] if rec["form_hit"] else 0,
                "hit": rec["form_hit"],
            }
            yr_rows.append(row)
        by_year[label] = yr_rows
        all_rows.extend(yr_rows)
        print(f"{label}: {len(yr_rows)}", flush=True)

    s_plus_rows = [r for r in all_rows if is_s_plus(r["tier"])]
    below_s = [r for r in all_rows if not is_s_plus(r["tier"])]
    tier_dist = dict(
        sorted(
            Counter(r["tier"] for r in all_rows).items(),
            key=lambda x: TIER_RANK.get(x[0], 99),
        )
    )

    report = {
        "segment": "exotic upset + high, 5pt formation",
        "tier_s_plus": "SS or S",
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
            ),
        },
        "by_year": {
            label: {
                "all": roi_stats(rows),
                "s_plus": roi_stats([r for r in rows if is_s_plus(r["tier"])]),
                "below_s": roi_stats([r for r in rows if not is_s_plus(r["tier"])]),
                "tier_distribution": dict(Counter(r["tier"] for r in rows)),
                "s_plus_count": sum(1 for r in rows if is_s_plus(r["tier"])),
            }
            for label, rows in by_year.items()
        },
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
