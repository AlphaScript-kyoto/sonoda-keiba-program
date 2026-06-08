"""Backfill odds_cache.json for races in master."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.client import NetkeibaBlockedError
from src.scraper.odds import fetch_odds_to_cache, load_odds_cache


def _race_ids_in_range(master, from_yyyymmdd: str, to_yyyymmdd: str) -> list[str]:
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    return sorted(hist["race_id"].astype(str).unique().tolist())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch odds into odds_cache.json")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--win-only", action="store_true", help="b1 only (faster)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    master = load_master()
    race_ids = _race_ids_in_range(master, args.from_date, args.to_date)
    cache = load_odds_cache()
    missing = [r for r in race_ids if r not in cache]

    print(
        f"Range {args.from_date}-{args.to_date}: "
        f"{len(race_ids)} races, {len(missing)} missing odds"
    )
    if not missing:
        print("Nothing to fetch.")
        return

    if args.dry_run:
        for rid in missing:
            print(rid)
        return

    try:
        fetch_odds_to_cache(missing, include_exotic=not args.win_only)
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. cache size={len(load_odds_cache())}")


if __name__ == "__main__":
    main()
