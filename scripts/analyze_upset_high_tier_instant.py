"""Instant upset-high tier ROI via backtest CSV + formation cache."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import BET_UNIT
from src.predictor.expectation import TIER_RANK, tier_from_score

UPSET = "\u8352"
FIRM = "\u5805"
CACHE_DIR = ROOT / "data" / "processed" / "logs" / "upset_high_cache"


def expectation_score_row(row: pd.Series) -> int:
    if not row["exotic_high"]:
        return 0
    score = 25
    score += 15 if row["exotic_profile"] == FIRM else 5
    wp = float(row["win_prob_top"])
    gap = float(row["prob_gap"])
    if wp >= 0.90:
        score += 12
    elif wp >= 0.85:
        score += 8
    elif wp >= 0.82:
        score += 4
    if gap >= 0.75:
        score += 12
    elif gap >= 0.70:
        score += 8
    elif gap >= 0.60:
        score += 4
    if row["win_high"]:
        score += 8
    if row["win_profile"] == FIRM:
        score += 4
    return min(score, 100)


def is_s_plus(tier: str) -> bool:
    return TIER_RANK.get(tier, 99) <= TIER_RANK["S"]


def roi(df: pd.DataFrame) -> dict:
    inv = int(df["inv"].sum())
    ret = int(df["ret"].sum())
    n = len(df)
    return {
        "n": n,
        "roi_pct": round(ret / inv * 100, 2) if inv else None,
        "hit_rate": round(df["hit"].mean(), 4) if n else None,
        "invest": inv,
        "return": ret,
    }


def main() -> None:
    periods = [
        ("2024", "20240101", "20241231", ROOT / "r_analysis/input/backtest_rows_2024.csv"),
        ("2025", "20250101", "20251231", ROOT / "r_analysis/input/backtest_rows_2025.csv"),
        ("2026", "20260101", "20261231", ROOT / "r_analysis/input/backtest_rows.csv"),
    ]
    parts = []
    for label, f, t, csv_path in periods:
        cache = CACHE_DIR / f"records_{f}_{t}.json"
        bt = pd.read_csv(csv_path)
        bt["date"] = bt["date"].astype(str)
        form = pd.DataFrame(json.loads(cache.read_text(encoding="utf-8")))
        form = form[
            (form["exotic_profile"] == UPSET)
            & form["exotic_high"]
            & (form["form_pts"] > 0)
        ][["date", "race_no", "form_pts", "form_hit", "fuku3_yen"]]
        form["date"] = form["date"].astype(str)
        m = bt.merge(form, on=["date", "race_no"], how="inner")
        m["year"] = label
        m["inv"] = m["form_pts"] * BET_UNIT
        m["ret"] = m.apply(
            lambda r: r["fuku3_yen"] if r["form_hit"] else 0, axis=1
        )
        m["hit"] = m["form_hit"]
        m["score"] = m.apply(expectation_score_row, axis=1)
        m["tier"] = m["score"].apply(lambda s: tier_from_score(int(s)))
        parts.append(m)

    all_df = pd.concat(parts, ignore_index=True)
    sp = all_df[all_df["tier"].apply(is_s_plus)]
    bl = all_df[~all_df["tier"].apply(is_s_plus)]

    print("=== 荒xHigh 5点フォーメーション (2024-2026) ===")
    print("tier分布:", dict(Counter(all_df["tier"])))
    print("全件:", roi(all_df))
    print("S以上:", roi(sp))
    print("S未満:", roi(bl))
    print(f"S以上 件数: {len(sp)} / {len(all_df)} ({len(sp)/len(all_df)*100:.1f}%)")
    print("全件 win_profile:", dict(Counter(all_df["win_profile"])))
    if len(sp):
        print("S+ win_profile:", dict(Counter(sp["win_profile"])))
        print("S+ avg fav_odds proxy (pred_odds top):", round(sp["pred_odds"].astype(float).mean(), 2))
    print("全件 avg pred_odds:", round(all_df["pred_odds"].astype(float).mean(), 2))
    print()
    for label in ["2024", "2025", "2026"]:
        yr = all_df[all_df["year"] == label]
        ysp = yr[yr["tier"].apply(is_s_plus)]
        print(
            f"{label}: all n={len(yr)} roi={roi(yr)['roi_pct']}% | "
            f"S+ n={len(ysp)} roi={roi(ysp)['roi_pct'] if len(ysp) else 'NA'}%"
        )
    print()
    print("理論上の期待値スコア上限(三連荒): 25+5+12+12+8 = 62 (< S閾値75)")
    print()
    print("=== A/B/C tier ROI (5pt formation) ===")
    for t in ["A", "B", "C"]:
        g = all_df[all_df["tier"] == t]
        r = roi(g)
        print(
            f"{t}: n={r['n']} hit={r['hit_rate']:.1%} "
            f"ROI={r['roi_pct']}% return={r['return']} invest={r['invest']}"
        )
    best = max(
        [("A", roi(all_df[all_df["tier"] == "A"])),
         ("B", roi(all_df[all_df["tier"] == "B"])),
         ("C", roi(all_df[all_df["tier"] == "C"]))],
        key=lambda x: x[1]["roi_pct"] or 0,
    )
    print(f"best_tier: {best[0]} ROI={best[1]['roi_pct']}%")


if __name__ == "__main__":
    main()
