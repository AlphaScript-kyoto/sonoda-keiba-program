"""Fetch missing race paybacks for a master date range."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.scraper.client import NetkeibaBlockedError
from src.scraper.payback import fetch_paybacks, load_payback_cache


def _race_ids_in_range(master, from_yyyymmdd: str, to_yyyymmdd: str) -> list[str]:
    hist = master[
        (master["date"].astype(str) >= from_yyyymmdd)
        & (master["date"].astype(str) <= to_yyyymmdd)
    ]
    return sorted(hist["race_id"].astype(str).unique().tolist())


def _missing_race_ids(
    race_ids: list[str],
    cache: dict,
    *,
    refresh_if_missing_wide: bool = True,
) -> list[str]:
    missing: list[str] = []
    for rid in race_ids:
        entry = cache.get(rid)
        if entry is None:
            missing.append(rid)
        elif refresh_if_missing_wide and not entry.get("wide"):
            missing.append(rid)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch missing paybacks for Sonoda races in a date range.",
    )
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="List missing race_ids only")
    args = parser.parse_args()

    master = load_master()
    race_ids = _race_ids_in_range(master, args.from_date, args.to_date)
    cache = load_payback_cache()
    missing = _missing_race_ids(race_ids, cache)

    print(
        f"Range {args.from_date}-{args.to_date}: "
        f"{len(race_ids)} races, {len(missing)} missing or incomplete (wide)"
    )
    if not missing:
        print("Nothing to fetch.")
        return

    if args.dry_run:
        for rid in missing:
            print(rid)
        return

    try:
        fetched = fetch_paybacks(
            missing,
            use_cache=True,
            stop_on_block=True,
            refresh_if_missing_wide=True,
        )
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(fetched)} / {len(missing)} requested.")


if __name__ == "__main__":
    main()
