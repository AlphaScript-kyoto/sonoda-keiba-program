"""Heartbeat health check for race-day watch process."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import (
    HEARTBEAT_GRACE_AFTER_WAKE_MINUTES,
    HEARTBEAT_STALE_MINUTES,
    load_heartbeat,
    log_watch,
    send_alert,
)
from src.predictor.race_schedule import race_post_datetime
from src.scraper.race_snapshots import load_schedule, trigger_datetime

WATCH_LEAD_MINUTES = 35
WATCH_TAIL_MINUTES = 15
HEARTBEAT_CHECK_COOLDOWN_KEY = "heartbeat_stale"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def race_day_window(
    schedule: dict,
    *,
    now: Optional[datetime] = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Active watch window: first T-35 through last post + tail."""
    current = now or datetime.now()
    date_yyyymmdd = str(schedule.get("date", current.strftime("%Y%m%d")))
    races = schedule.get("races") or []
    if not races:
        return None, None

    starts: list[datetime] = []
    ends: list[datetime] = []
    for race in races:
        post_time = str(race.get("post_time", "")).strip()
        if not post_time:
            continue
        post_dt = race_post_datetime(date_yyyymmdd, post_time)
        trigger = trigger_datetime(date_yyyymmdd, post_time, WATCH_LEAD_MINUTES)
        if post_dt is None:
            continue
        if trigger is not None:
            starts.append(trigger)
        ends.append(post_dt + timedelta(minutes=WATCH_TAIL_MINUTES))

    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def is_in_watch_window(
    schedule: dict,
    *,
    now: Optional[datetime] = None,
) -> bool:
    current = now or datetime.now()
    start, end = race_day_window(schedule, now=current)
    if start is None or end is None:
        return False
    return start <= current <= end


def evaluate_heartbeat(
    date_yyyymmdd: str,
    *,
    schedule: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok=True means no alert needed.
    """
    current = now or datetime.now()
    sched = schedule if schedule is not None else load_schedule(date_yyyymmdd)
    if not sched or not sched.get("races"):
        return True, "no_races"

    if not is_in_watch_window(sched, now=current):
        return True, "outside_window"

    hb = load_heartbeat(date_yyyymmdd)
    if hb is None:
        return False, "heartbeat_missing"

    status = str(hb.get("status", ""))
    if status == "done":
        return True, "watch_done"

    updated = _parse_iso(hb.get("updated_at"))
    if updated is None:
        return False, "heartbeat_invalid"

    next_wake = _parse_iso(hb.get("next_wake_at"))
    if next_wake is not None and current < next_wake + timedelta(
        minutes=HEARTBEAT_GRACE_AFTER_WAKE_MINUTES
    ):
        return True, "sleeping_until_wake"

    stale_limit = HEARTBEAT_STALE_MINUTES
    if next_wake is not None and current >= next_wake:
        overdue = (current - next_wake).total_seconds() / 60.0
        stale_limit = max(HEARTBEAT_GRACE_AFTER_WAKE_MINUTES, overdue + 5)

    age_min = (current - updated).total_seconds() / 60.0
    if age_min > stale_limit:
        return False, f"stale_{age_min:.0f}min_status={status}"

    return True, "ok"


def check_and_alert(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Run heartbeat check; send LINE alert if unhealthy. Returns True if alert sent."""
    ok, reason = evaluate_heartbeat(date_yyyymmdd, now=now)
    if ok:
        return False

    message = (
        f"\u76e3\u8996\u30d7\u30ed\u30bb\u30b9\u306e\u5fc3\u81d3\u304c\u6b62\u307e\u3063\u3066\u3044\u308b\u53ef\u80fd\u6027\u304c\u3042\u308a\u307e\u3059\u3002\n"
        f"\u65e5\u4ed8: {date_yyyymmdd}\n"
        f"\u7406\u7531: {reason}\n"
        f"logs/watch_{date_yyyymmdd}.log \u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002"
    )
    sent = send_alert(
        message,
        date_yyyymmdd=date_yyyymmdd,
        alert_key=f"{HEARTBEAT_CHECK_COOLDOWN_KEY}_{date_yyyymmdd}_{reason}",
        cooldown_minutes=20,
    )
    if sent:
        log_watch(date_yyyymmdd, f"heartbeat check FAILED: {reason}")
    return sent
