"""◎/○/▲ vs 1番人気・着順分析（exotic split scoring + assign_marks）。"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import MARKS, assign_marks
from src.predictor.score import load_master, score_entries
from src.predictor.scoring_config import load_split_scoring_configs

DATE_FROM = "20230101"
DATE_TO = "20260531"
CACHE_DIR = ROOT / "data" / "processed" / "marks_fav_exotic_by_date"
LEGACY_CACHE_PATH = ROOT / "data" / "processed" / "marks_fav_exotic_cache.pkl"

HONMEI, AI, SAN = MARKS[0], MARKS[1], MARKS[2]


def norm_umaban(u) -> str:
    v = pd.to_numeric(u, errors="coerce")
    if pd.notna(v):
        return str(int(v))
    s = str(u).strip()
    return str(int(s)) if s.isdigit() else s


def pct(n: int, d: int) -> float:
    return (100.0 * n / d) if d else 0.0


def print_mark_stats(label: str, finishes: list[int], *, show_top3: bool) -> None:
    d = len(finishes)
    c1 = sum(1 for f in finishes if f == 1)
    c2 = sum(1 for f in finishes if f == 2)
    c3 = sum(1 for f in finishes if f == 3)
    c4 = sum(1 for f in finishes if f >= 4)
    print(f"  {label} n={d}")
    print(
        f"    1着%={pct(c1, d):.2f}  2着%={pct(c2, d):.2f}  "
        f"3着%={pct(c3, d):.2f}  4着以下%={pct(c4, d):.2f}"
    )
    if show_top3:
        print(f"    3着以内%={pct(c1 + c2 + c3, d):.2f}")


def _date_cache_path(date: str) -> Path:
    return CACHE_DIR / f"{date}.pkl"


def _migrate_legacy_cache() -> None:
    if not LEGACY_CACHE_PATH.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with LEGACY_CACHE_PATH.open("rb") as f:
        legacy = pickle.load(f)
    for date, scored in legacy.items():
        path = _date_cache_path(str(date))
        if not path.exists():
            with path.open("wb") as f:
                pickle.dump(scored, f)
    print(f"  migrated {len(legacy)} dates from legacy cache", flush=True)


def scored_for_date(
    date: str,
    master: pd.DataFrame,
    period: pd.DataFrame,
    ex_cfg,
) -> pd.DataFrame:
    path = _date_cache_path(date)
    if path.exists():
        with path.open("rb") as f:
            return pickle.load(f)
    entries = period[period["date"].astype(str) == date].copy()
    scored = score_entries(entries, master, config=ex_cfg)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(scored, f)
    return scored


def ensure_scored_dates(
    master: pd.DataFrame,
    period: pd.DataFrame,
    ex_cfg,
    dates: list[str],
) -> None:
    _migrate_legacy_cache()
    for i, date in enumerate(dates, 1):
        if _date_cache_path(date).exists():
            continue
        scored_for_date(date, master, period, ex_cfg)
        if i % 10 == 0 or i == len(dates):
            print(f"  scored {i}/{len(dates)} dates", flush=True)


def main() -> None:
    master = load_master()
    _, ex_cfg = load_split_scoring_configs()

    period = master.copy()
    period["date"] = period["date"].astype(str)
    period = period[(period["date"] >= DATE_FROM) & (period["date"] <= DATE_TO)]
    period["finish_n"] = pd.to_numeric(period["finish"], errors="coerce")
    period["pop_n"] = pd.to_numeric(period["popularity"], errors="coerce")
    period["umaban_n"] = period["umaban"].map(norm_umaban)

    dates = sorted(period["date"].astype(str).unique())
    n_races = period["race_id"].astype(str).nunique()
    print(
        f"Scoring exotic config: {n_races} races, "
        f"{len(dates)} dates (cache={CACHE_DIR.name})...",
        flush=True,
    )
    ensure_scored_dates(master, period, ex_cfg, dates)

    records = []
    skipped = {"no_valid_field": 0, "no_scored": 0}

    for date in dates:
        scored = scored_for_date(date, master, period, ex_cfg)
        day = period[period["date"].astype(str) == date]
        for rid, grp in day.groupby("race_id", sort=False):
            rid = str(rid)
            valid = grp.dropna(subset=["finish_n", "pop_n"])
            if len(valid) < 3:
                skipped["no_valid_field"] += 1
                continue

            pred = scored[scored["race_id"].astype(str) == rid]
            if pred.empty:
                skipped["no_scored"] += 1
                continue

            marks = assign_marks(pred)
            marks["umaban_n"] = marks["umaban"].map(norm_umaban)

            finish_map = dict(zip(valid["umaban_n"], valid["finish_n"].astype(int)))
            fav_u = norm_umaban(valid.loc[valid["pop_n"].idxmin(), "umaban"])
            mark_by_u = dict(zip(marks["umaban_n"], marks["mark"]))

            def umaban_for_mark(mk: str) -> str | None:
                hit = marks[marks["mark"] == mk]
                return hit["umaban_n"].iloc[0] if not hit.empty else None

            honmei_u = umaban_for_mark(HONMEI) or marks.sort_values("rank_pred").iloc[0]["umaban_n"]

            rec = {
                "race_id": rid,
                "date": date,
                "year": date[:4],
                "a_match": honmei_u == fav_u,
                "b_match": mark_by_u.get(fav_u) == HONMEI,
            }
            for mk, key in ((HONMEI, "honmei"), (AI, "ai"), (SAN, "san")):
                u = umaban_for_mark(mk)
                rec[f"finish_{key}"] = finish_map.get(u) if u else None
            records.append(rec)

    df = pd.DataFrame(records)
    n = len(df)
    print()
    print("=" * 60)
    print(f"Period: {DATE_FROM}-{DATE_TO}  (exotic/sanrenpuku split scoring + assign_marks)")
    print(f"Races analyzed: {n}")
    print(f"Skipped: {skipped}")
    print("=" * 60)

    print("\n--- Overall ---")
    a_n = int(df["a_match"].sum())
    b_n = int(df["b_match"].sum())
    print(f"A) ◎ umaban == 1番人気 umaban: {a_n}/{n} = {pct(a_n, n):.2f}%")
    print(f"B) 1番人気 got ◎ mark:           {b_n}/{n} = {pct(b_n, n):.2f}%")
    if a_n != b_n:
        print(f"   (A vs B diff: {b_n - a_n} races)")

    print("\nC) ◎ horse finish:")
    print_mark_stats("◎", [int(x) for x in df["finish_honmei"].dropna()], show_top3=False)

    print("\nD) ○ horse finish:")
    print_mark_stats("○", [int(x) for x in df["finish_ai"].dropna()], show_top3=True)

    print("\nE) ▲ horse finish:")
    print_mark_stats("▲", [int(x) for x in df["finish_san"].dropna()], show_top3=True)

    print("\n--- Year breakdown (A: ◎==1番人気) ---")
    print(f"{'year':>6} {'races':>7} {'A_n':>7} {'A%':>8}")
    for year in ["2023", "2024", "2025", "2026"]:
        sub = df[df["year"] == year]
        if sub.empty:
            continue
        an = int(sub["a_match"].sum())
        print(f"{year:>6} {len(sub):>7} {an:>7} {pct(an, len(sub)):>7.2f}%")

    print("\n--- Year breakdown (D/E: 3着以内%) ---")
    print(f"{'year':>6} {'races':>7} {'○ top3%':>10} {'▲ top3%':>10}")
    for year in ["2023", "2024", "2025", "2026"]:
        sub = df[df["year"] == year]
        if sub.empty:
            continue
        ai = [int(x) for x in sub["finish_ai"].dropna()]
        san = [int(x) for x in sub["finish_san"].dropna()]
        ai_top3 = pct(sum(1 for f in ai if f <= 3), len(ai))
        san_top3 = pct(sum(1 for f in san if f <= 3), len(san))
        print(f"{year:>6} {len(sub):>7} {ai_top3:>9.2f}% {san_top3:>9.2f}%")


if __name__ == "__main__":
    main()
