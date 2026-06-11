"""Fetch schedule and capture shutuba+odds at scheduled offsets."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scraper.client import NetkeibaBlockedError
from src.scraper.race_snapshots import (
    DEFAULT_CAPTURE_OFFSETS,
    capture_due,
    fetch_and_save_schedule,
    load_schedule,
    parse_capture_offsets,
    schedule_path,
    watch_scheduled,
)


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _print_schedule(date_yyyymmdd: str) -> None:
    sched = load_schedule(date_yyyymmdd)
    if not sched or not sched.get("races"):
        print(f"No schedule for {date_yyyymmdd}")
        return
    print(
        f"Schedule {date_yyyymmdd} ({len(sched['races'])} races) "
        f"-> {schedule_path(date_yyyymmdd)}"
    )
    for r in sched["races"]:
        print(
            f"  R{r.get('race_no'):>2} {r.get('post_time','?'):>5}  "
            f"{r.get('race_id')}  {r.get('race_name','')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch race day and capture snapshots at scheduled offsets"
    )
    parser.add_argument("--date", default=_today_yyyymmdd(), help="YYYYMMDD")
    parser.add_argument(
        "--offsets",
        default=",".join(str(m) for m in DEFAULT_CAPTURE_OFFSETS),
        help="Minutes before post time, comma-separated (default: 30,20,10)",
    )
    parser.add_argument("--schedule-only", action="store_true")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Capture due snapshots once, then exit",
    )
    parser.add_argument("--exotic-odds", action="store_true")
    args = parser.parse_args()
    date_yyyymmdd = args.date
    offsets = parse_capture_offsets(args.offsets)

    print(
        f"[watch] date={date_yyyymmdd} now={datetime.now().strftime('%H:%M:%S')} "
        f"offsets=T-{','.join(str(m) for m in offsets)}",
        flush=True,
    )

    try:
        sched = load_schedule(date_yyyymmdd)
        if sched is None or not sched.get("races"):
            print("Fetching schedule...", flush=True)
            sched = fetch_and_save_schedule(date_yyyymmdd)
        if not sched.get("races"):
            print("No Sonoda races / shutuba not available yet.", flush=True)
            if args.schedule_only or args.once:
                sys.exit(1)
        else:
            _print_schedule(date_yyyymmdd)
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.schedule_only:
        return

    try:
        if args.once:
            capture_due(
                date_yyyymmdd,
                offsets=offsets,
                include_exotic_odds=args.exotic_odds,
            )
        else:
            watch_scheduled(
                date_yyyymmdd,
                offsets=offsets,
                include_exotic_odds=args.exotic_odds,
            )
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
