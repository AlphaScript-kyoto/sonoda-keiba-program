"""Race day: predict at T-10 and push copy text to LINE."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import log_watch, send_alert, write_heartbeat
from src.predictor.post_format import copy_channel_label, format_race_copy
from src.predictor.predict_day import PredictDayResult, run_predict_day_safe
from src.predictor.race_schedule import race_post_datetime
from src.scraper.client import NetkeibaBlockedError
from src.scraper.race_snapshots import (
    CaptureJob,
    DEFAULT_CAPTURE_OFFSETS,
    _race_jobs,
    capture_due,
    fetch_and_save_schedule,
    load_schedule,
    next_wake_datetime,
    snapshots_dir,
    trigger_datetime,
)

LINE_NOTIFY_OFFSET = 10


def notified_path(date_yyyymmdd: str) -> Path:
    return snapshots_dir(date_yyyymmdd) / "line_notified.json"


def load_notified_race_ids(date_yyyymmdd: str) -> set[str]:
    path = notified_path(date_yyyymmdd)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {str(x) for x in data.get("race_ids", [])}


def mark_race_notified(date_yyyymmdd: str, race_id: str) -> None:
    path = notified_path(date_yyyymmdd)
    ids = load_notified_race_ids(date_yyyymmdd)
    ids.add(str(race_id))
    payload = {
        "date": date_yyyymmdd,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "race_ids": sorted(ids),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _plan_for_race(result: PredictDayResult, race_no: int):
    for plan in result.plans:
        if int(plan.race_no) == int(race_no):
            return plan
    return None


def build_race_line_message(
    date_yyyymmdd: str,
    race_no: int,
    *,
    result: Optional[PredictDayResult] = None,
) -> str:
    if result is None:
        result = run_predict_day_safe(
            date_yyyymmdd,
            only_race_nos={int(race_no)},
        )
    if result.message and result.win_df.empty:
        return (
            f"[Sonoda {date_yyyymmdd} {race_no}R] predict failed\n"
            f"{result.message}"
        )

    plan = _plan_for_race(result, race_no)
    if plan is None:
        return f"[Sonoda {date_yyyymmdd} {race_no}R] no plan"

    channel = copy_channel_label(plan.expectation_tier)
    post_tag = f" post={plan.post_time}" if plan.post_time else ""
    header = (
        f"[Sonoda {date_yyyymmdd} {race_no}R{post_tag}] "
        f"tier={plan.expectation_tier} ({channel})"
    )
    body = format_race_copy(plan, result.win_df, result.exotic_df)
    return f"{header}\n\n{body}"


def due_line_notify_jobs(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    notify_offset: int = LINE_NOTIFY_OFFSET,
    now: Optional[datetime] = None,
) -> List[CaptureJob]:
    current = now or datetime.now()
    notified = load_notified_race_ids(date_yyyymmdd)
    due: List[CaptureJob] = []
    for job in _race_jobs(date_yyyymmdd, schedule, (notify_offset,)):
        if job.race_id in notified:
            continue
        post_dt = race_post_datetime(date_yyyymmdd, job.post_time)
        trigger = trigger_datetime(date_yyyymmdd, job.post_time, notify_offset)
        if post_dt is None or trigger is None:
            continue
        if current >= post_dt:
            continue
        if current >= trigger:
            due.append(job)
    return sorted(due, key=lambda j: j.race_no)


def send_line_notifications(
    date_yyyymmdd: str,
    jobs: Sequence[CaptureJob],
) -> List[str]:
    from tools.line_bot import send_line_predict_messages, team_user_ids
    import os

    admin_id = os.getenv("LINE_USER_ID", "").strip()
    if not team_user_ids() and not admin_id:
        log_watch(
            date_yyyymmdd,
            "WARN LINE_TEAM_USER_IDS and LINE_USER_ID empty; skip predict push",
        )
        return []

    sent: List[str] = []
    for job in jobs:
        try:
            text = build_race_line_message(date_yyyymmdd, job.race_no)
            send_line_predict_messages(text)
            mark_race_notified(date_yyyymmdd, job.race_id)
            sent.append(job.race_id)
            log_watch(
                date_yyyymmdd,
                f"LINE post sent R{job.race_no} {job.race_id} post={job.post_time}",
            )
        except NetkeibaBlockedError:
            raise
        except Exception as exc:
            msg = f"R{job.race_no} LINE post failed: {exc}"
            log_watch(date_yyyymmdd, f"WARN {msg}")
            send_alert(
                f"R{job.race_no} \u6295\u7a3f\u6587 LINE \u9001\u4fe1\u5931\u6557\n{exc}",
                date_yyyymmdd=date_yyyymmdd,
                alert_key=f"line_post_fail_{date_yyyymmdd}_{job.race_id}",
                cooldown_minutes=15,
            )
    return sent


def process_due_line_notifications(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    notify_offset: int = LINE_NOTIFY_OFFSET,
    now: Optional[datetime] = None,
) -> List[str]:
    jobs = due_line_notify_jobs(
        date_yyyymmdd,
        schedule,
        notify_offset=notify_offset,
        now=now,
    )
    if not jobs:
        return []
    log_watch(
        date_yyyymmdd,
        f"LINE notify: {len(jobs)} race(s) due (T-{notify_offset})",
    )
    return send_line_notifications(date_yyyymmdd, jobs)


def all_captures_done_for_watch(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    offsets: Sequence[int],
    line_notify: bool,
    notify_offset: int,
    now: Optional[datetime] = None,
) -> bool:
    from src.scraper.race_snapshots import all_captures_done

    if not all_captures_done(date_yyyymmdd, schedule, offsets=offsets, now=now):
        return False
    if line_notify and due_line_notify_jobs(
        date_yyyymmdd,
        schedule,
        notify_offset=notify_offset,
        now=now,
    ):
        return False
    return True


def _wake_offsets(
    offsets: Sequence[int],
    line_notify: bool,
    notify_offset: int,
) -> Sequence[int]:
    if not line_notify:
        return offsets
    merged = set(int(m) for m in offsets)
    merged.add(int(notify_offset))
    return tuple(sorted(merged, reverse=True))


def _schedule_summary(schedule: dict) -> str:
    lines = []
    for race in schedule.get("races", []):
        lines.append(
            f"R{race.get('race_no')} {race.get('post_time', '?')}"
        )
    return "\n".join(lines)


def notify_watch_started(date_yyyymmdd: str, schedule: dict, *, line_notify: bool) -> None:
    n = len(schedule.get("races", []))
    log_watch(date_yyyymmdd, f"watch started ({n} races, line={'on' if line_notify else 'off'})")
    write_heartbeat(date_yyyymmdd, status="started", extra={"race_count": n})
    summary = _schedule_summary(schedule)
    send_alert(
        f"\u76e3\u8996\u958b\u59cb {date_yyyymmdd} \u30fb {n}R\n"
        f"LINE\u6295\u7a3f: {'ON' if line_notify else 'OFF'}\n"
        f"{summary}",
        date_yyyymmdd=date_yyyymmdd,
        alert_key=f"watch_start_{date_yyyymmdd}",
        cooldown_minutes=60 * 12,
    )


def notify_watch_finished(date_yyyymmdd: str, schedule: dict, *, line_notify: bool) -> None:
    n = len(schedule.get("races", []))
    notified = len(load_notified_race_ids(date_yyyymmdd))
    log_watch(
        date_yyyymmdd,
        f"watch finished ({notified}/{n} LINE posts)",
    )
    write_heartbeat(date_yyyymmdd, status="done", extra={
        "race_count": n,
        "line_notified": notified,
    })
    if line_notify:
        send_alert(
            f"\u76e3\u8996\u5b8c\u4e86 {date_yyyymmdd}\n"
            f"LINE\u6295\u7a3f: {notified}/{n}R",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"watch_done_{date_yyyymmdd}",
            cooldown_minutes=60 * 12,
        )


def watch_race_day(
    date_yyyymmdd: str,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    include_exotic_odds: bool = False,
    line_notify: bool = True,
    notify_offset: int = LINE_NOTIFY_OFFSET,
) -> None:
    schedule = load_schedule(date_yyyymmdd)
    if schedule is None or not schedule.get("races"):
        schedule = fetch_and_save_schedule(date_yyyymmdd)

    if not schedule.get("races"):
        log_watch(date_yyyymmdd, "no Sonoda races; watch exit")
        write_heartbeat(date_yyyymmdd, status="no_races")
        return

    notify_watch_started(date_yyyymmdd, schedule, line_notify=line_notify)

    offsets_str = ",".join(str(m) for m in offsets)
    log_watch(
        date_yyyymmdd,
        f"offsets T-{offsets_str.replace(',', ', T-')}",
    )

    try:
        while True:
            write_heartbeat(date_yyyymmdd, status="running")
            capture_due(
                date_yyyymmdd,
                offsets=offsets,
                include_exotic_odds=include_exotic_odds,
            )
            schedule = load_schedule(date_yyyymmdd) or schedule
            if line_notify:
                process_due_line_notifications(
                    date_yyyymmdd,
                    schedule,
                    notify_offset=notify_offset,
                )

            if all_captures_done_for_watch(
                date_yyyymmdd,
                schedule,
                offsets=offsets,
                line_notify=line_notify,
                notify_offset=notify_offset,
            ):
                notify_watch_finished(date_yyyymmdd, schedule, line_notify=line_notify)
                break

            wake_at = next_wake_datetime(
                date_yyyymmdd,
                schedule,
                offsets=_wake_offsets(offsets, line_notify, notify_offset),
            )
            if wake_at is None:
                notify_watch_finished(date_yyyymmdd, schedule, line_notify=line_notify)
                break

            write_heartbeat(
                date_yyyymmdd,
                status="sleeping",
                next_wake_at=wake_at,
            )
            now = datetime.now()
            sleep_sec = max(0.0, (wake_at - now).total_seconds())
            log_watch(
                date_yyyymmdd,
                f"next wake {wake_at.strftime('%H:%M:%S')} (sleep {sleep_sec:.0f}s)",
            )
            if sleep_sec > 0:
                time.sleep(sleep_sec)
    except NetkeibaBlockedError as exc:
        log_watch(date_yyyymmdd, f"FATAL netkeiba blocked: {exc}")
        write_heartbeat(date_yyyymmdd, status="error", extra={"error": str(exc)})
        send_alert(
            f"netkeiba \u5236\u9650\u3067\u76e3\u8996\u505c\u6b62 ({date_yyyymmdd})\n{exc}",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"netkeiba_block_{date_yyyymmdd}",
            cooldown_minutes=60,
        )
        raise
    except Exception as exc:
        log_watch(date_yyyymmdd, f"FATAL watch error: {exc}")
        write_heartbeat(date_yyyymmdd, status="error", extra={"error": str(exc)})
        send_alert(
            f"\u76e3\u8996\u7570\u5e38\u7d42\u4e86 ({date_yyyymmdd})\n{exc}",
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"watch_crash_{date_yyyymmdd}",
            cooldown_minutes=30,
        )
        raise


def run_once(
    date_yyyymmdd: str,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    include_exotic_odds: bool = False,
    line_notify: bool = True,
    notify_offset: int = LINE_NOTIFY_OFFSET,
) -> None:
    log_watch(date_yyyymmdd, "run_once started")
    schedule = load_schedule(date_yyyymmdd)
    if schedule is None or not schedule.get("races"):
        schedule = fetch_and_save_schedule(date_yyyymmdd)
    try:
        capture_due(
            date_yyyymmdd,
            offsets=offsets,
            include_exotic_odds=include_exotic_odds,
        )
        if line_notify:
            schedule = load_schedule(date_yyyymmdd) or schedule
            process_due_line_notifications(
                date_yyyymmdd,
                schedule,
                notify_offset=notify_offset,
            )
        log_watch(date_yyyymmdd, "run_once finished")
        write_heartbeat(date_yyyymmdd, status="once_done")
    except NetkeibaBlockedError as exc:
        log_watch(date_yyyymmdd, f"run_once netkeiba blocked: {exc}")
        send_alert(
            f"netkeiba \u5236\u9650 ({date_yyyymmdd})\n{exc}",
            date_yyyymmdd=date_yyyymmdd,
            cooldown_minutes=60,
        )
        raise
