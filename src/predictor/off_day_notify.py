"""Throttled off-day LINE notices (Option B: 7d cooldown or next-date change)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

OFF_DAY_STATE_KEY = "off_day_notice"
OFF_DAY_COOLDOWN_DAYS = 7


def should_send_off_day_notice(
    date_yyyymmdd: str,
    next_date_yyyymmdd: Optional[str],
    *,
    now: Optional[datetime] = None,
    state: Optional[dict] = None,
) -> tuple[bool, str]:
    """
    Returns (should_send, reason).
    Send when: first notice, next race date changed, or >=7 days since last send.
    """
    from src.predictor.automation_log import _load_alert_state

    current = now or datetime.now()
    if state is None:
        state = _load_alert_state()
    rec = state.get(OFF_DAY_STATE_KEY) or {}
    next_s = str(next_date_yyyymmdd or "")
    last_at = rec.get("last_sent_at")
    last_next = str(rec.get("last_next_date") or "")

    if not last_at:
        return True, "first"

    if next_s != last_next:
        return True, f"next_date_changed:{last_next}->{next_s}"

    try:
        last_dt = datetime.fromisoformat(str(last_at))
        days = (current.date() - last_dt.date()).days
        if days >= OFF_DAY_COOLDOWN_DAYS:
            return True, f"cooldown_{OFF_DAY_COOLDOWN_DAYS}d"
        return False, f"skip_{days}d_next_unchanged"
    except ValueError:
        return True, "invalid_last_sent"


def record_off_day_notice_sent(
    date_yyyymmdd: str,
    next_date_yyyymmdd: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> None:
    from src.predictor.automation_log import _load_alert_state, _save_alert_state

    current = now or datetime.now()
    state = _load_alert_state()
    state[OFF_DAY_STATE_KEY] = {
        "last_sent_at": current.isoformat(timespec="seconds"),
        "last_off_date": date_yyyymmdd,
        "last_next_date": str(next_date_yyyymmdd or ""),
    }
    _save_alert_state(state)


def send_off_day_team_broadcast(
    message: str,
    date_yyyymmdd: str,
    next_date_yyyymmdd: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Member+admin off-day notice with shared throttle."""
    from src.predictor.automation_log import log_watch
    from tools.line_bot import format_line_delivery_log, send_line_predict_messages

    ok, reason = should_send_off_day_notice(
        date_yyyymmdd, next_date_yyyymmdd, now=now
    )
    if not ok:
        log_watch(date_yyyymmdd, f"off-day LINE skipped ({reason})")
        return False

    deliveries = send_line_predict_messages(message)
    for rec in deliveries:
        log_watch(date_yyyymmdd, format_line_delivery_log(rec))
    record_off_day_notice_sent(date_yyyymmdd, next_date_yyyymmdd, now=now)
    log_watch(date_yyyymmdd, f"off-day LINE sent ({reason})")
    return True


def send_off_day_admin_alert(
    message: str,
    date_yyyymmdd: str,
    next_date_yyyymmdd: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Admin off-day notice (run_today) with same throttle as morning watch."""
    from src.predictor.automation_log import log_run_today, send_alert

    ok, reason = should_send_off_day_notice(
        date_yyyymmdd, next_date_yyyymmdd, now=now
    )
    if not ok:
        log_run_today(date_yyyymmdd, f"off-day LINE skipped ({reason})")
        return False

    sent = send_alert(
        message,
        date_yyyymmdd=date_yyyymmdd,
        alert_key=f"off_day_admin_{date_yyyymmdd}",
        cooldown_minutes=60 * 12,
        log_channel="run_today",
    )
    if not sent:
        log_run_today(date_yyyymmdd, "off-day LINE skipped (alert cooldown)")
        return False

    record_off_day_notice_sent(date_yyyymmdd, next_date_yyyymmdd, now=now)
    log_run_today(date_yyyymmdd, f"off-day LINE sent ({reason})")
    return True
