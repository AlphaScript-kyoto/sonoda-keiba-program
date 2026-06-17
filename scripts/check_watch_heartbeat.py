"""Heartbeat check for race-day watch (Task Scheduler every 20 min)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import log_watch
from src.predictor.watch_heartbeat import check_and_alert, evaluate_heartbeat


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check watch process heartbeat and alert via LINE if stale"
    )
    parser.add_argument("--date", default=_today_yyyymmdd(), help="YYYYMMDD")
    args = parser.parse_args()
    date_yyyymmdd = args.date

    ok, reason = evaluate_heartbeat(date_yyyymmdd)
    if ok:
        log_watch(date_yyyymmdd, f"heartbeat check OK ({reason})")
        return

    check_and_alert(date_yyyymmdd)


if __name__ == "__main__":
    main()
