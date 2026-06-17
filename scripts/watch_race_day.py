"""Fetch schedule and capture shutuba+odds at scheduled offsets."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import log_watch, send_alert
from src.predictor.race_day_notify import run_once, watch_race_day
from src.scraper.client import NetkeibaBlockedError
from src.scraper.race_snapshots import (
    DEFAULT_CAPTURE_OFFSETS,
    fetch_and_save_schedule,
    load_schedule,
    parse_capture_offsets,
    schedule_path,
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
    parser.add_argument(
        "--no-line-notify",
        action="store_true",
        help="Disable T-10 predict + LINE push (snapshots only)",
    )
    args = parser.parse_args()
    date_yyyymmdd = args.date
    offsets = parse_capture_offsets(args.offsets)
    line_notify = not args.no_line_notify

    print(
        f"[watch] date={date_yyyymmdd} now={datetime.now().strftime('%H:%M:%S')} "
        f"offsets=T-{','.join(str(m) for m in offsets)} "
        f"line={'on' if line_notify else 'off'}",
        flush=True,
    )
    log_watch(date_yyyymmdd, "watch_race_day.py started")

    try:
        sched = load_schedule(date_yyyymmdd)
        if sched is None or not sched.get("races"):
            log_watch(date_yyyymmdd, "fetching schedule")
            print("Fetching schedule...", flush=True)
            sched = fetch_and_save_schedule(date_yyyymmdd)
        if not sched.get("races"):
            msg = "No Sonoda races / shutuba not available yet."
            log_watch(date_yyyymmdd, msg)
            print(msg, flush=True)
            if args.schedule_only or args.once:
                sys.exit(1)
        else:
            _print_schedule(date_yyyymmdd)
    except NetkeibaBlockedError as exc:
        log_watch(date_yyyymmdd, f"netkeiba blocked at startup: {exc}")
        send_alert(
            f"netkeiba \u5236\u9650 (\u958b\u59cb\u6642) {date_yyyymmdd}\n{exc}",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"netkeiba_block_startup_{date_yyyymmdd}",
            cooldown_minutes=60,
        )
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.schedule_only:
        return

    try:
        if args.once:
            run_once(
                date_yyyymmdd,
                offsets=offsets,
                include_exotic_odds=args.exotic_odds,
                line_notify=line_notify,
            )
        else:
            watch_race_day(
                date_yyyymmdd,
                offsets=offsets,
                include_exotic_odds=args.exotic_odds,
                line_notify=line_notify,
            )
    except NetkeibaBlockedError as exc:
        print(f"Netkeiba blocked: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        log_watch(date_yyyymmdd, f"unhandled error: {exc}")
        send_alert(
            f"\u76e3\u8996\u30b9\u30af\u30ea\u30d7\u30c8\u7570\u5e38\u7d42\u4e86 ({date_yyyymmdd})\n{exc}",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"watch_script_crash_{date_yyyymmdd}",
            cooldown_minutes=30,
        )
        raise


if __name__ == "__main__":
    main()
