"""Backfill horse_profile_cache.json from master horse_ids."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.client import NetkeibaBlockedError
from src.scraper.horse_profile import fetch_horse_profiles, load_horse_profile_cache


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch horse career stats into cache")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    master = load_master()
    hist = master[
        (master["date"].astype(str) >= args.from_date)
        & (master["date"].astype(str) <= args.to_date)
    ]
    horse_ids = sorted(hist["horse_id"].astype(str).unique().tolist())
    cache = load_horse_profile_cache()
    missing = [h for h in horse_ids if h and h not in cache]

    print(
        f"Range {args.from_date}-{args.to_date}: "
        f"{len(horse_ids)} horses, {len(missing)} missing profiles"
    )
    if not missing:
        print("Nothing to fetch.")
        return

    if args.dry_run:
        for hid in missing:
            print(hid)
        return

    try:
        fetch_horse_profiles(missing)
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Done. cache size={len(load_horse_profile_cache())}")


if __name__ == "__main__":
    main()
