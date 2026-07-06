"""Shared payback poll state for race-day LINE notifications."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from src.predictor.race_schedule import normalize_post_time, race_post_datetime
from src.scraper.race_snapshots import snapshots_dir

PAYBACK_START_MINUTES = 5
PAYBACK_POLL_MINUTES = 5
PAYBACK_TIMEOUT_MINUTES = 180


def _path(date_yyyymmdd: str, filename: str) -> Path:
    return snapshots_dir(date_yyyymmdd) / filename


def load_payback_state(date_yyyymmdd: str, filename: str) -> dict:
    path = _path(date_yyyymmdd, filename)
    if not path.exists():
        return {
            "date": date_yyyymmdd,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "races": [],
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_payback_state(date_yyyymmdd: str, filename: str, state: dict) -> None:
    state["date"] = date_yyyymmdd
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with _path(date_yyyymmdd, filename).open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def register_payback_target(
    date_yyyymmdd: str,
    filename: str,
    *,
    race_id: str,
    race_no: int,
    race_name: str,
    post_time: str,
) -> None:
    state = load_payback_state(date_yyyymmdd, filename)
    races = state.get("races", [])
    rid = str(race_id)
    for rec in races:
        if str(rec.get("race_id", "")) == rid:
            rec["race_no"] = int(race_no)
            rec["race_name"] = str(race_name or "")
            rec["post_time"] = str(post_time or "")
            save_payback_state(date_yyyymmdd, filename, state)
            return

    races.append(
        {
            "race_id": rid,
            "race_no": int(race_no),
            "race_name": str(race_name or ""),
            "post_time": str(post_time or ""),
            "status": "pending",
            "notified_at": datetime.now().isoformat(timespec="seconds"),
            "last_checked_at": "",
            "settled_at": "",
        }
    )
    state["races"] = sorted(races, key=lambda x: int(x.get("race_no", 999)))
    save_payback_state(date_yyyymmdd, filename, state)


def sync_payback_post_times(
    date_yyyymmdd: str,
    schedule: dict,
    filename: str,
) -> None:
    post_by_id = {
        str(r.get("race_id", "")): normalize_post_time(r.get("post_time", ""))
        for r in schedule.get("races", [])
        if r.get("race_id")
    }
    state = load_payback_state(date_yyyymmdd, filename)
    changed = False
    for rec in state.get("races", []):
        if str(rec.get("status", "pending")) != "pending":
            continue
        rid = str(rec.get("race_id", ""))
        new_post = post_by_id.get(rid, "")
        if new_post and str(rec.get("post_time", "")) != new_post:
            rec["post_time"] = new_post
            changed = True
    if changed:
        save_payback_state(date_yyyymmdd, filename, state)


def _next_due_poll_time(
    date_yyyymmdd: str,
    post_time: str,
    *,
    now: datetime,
    start_after_minutes: int,
    poll_minutes: int,
) -> Optional[datetime]:
    post_dt = race_post_datetime(date_yyyymmdd, post_time)
    if post_dt is None:
        return None
    first_due = post_dt + timedelta(minutes=int(start_after_minutes))
    if now <= first_due:
        return first_due
    elapsed = now - first_due
    slots = int(elapsed.total_seconds() // (poll_minutes * 60))
    due = first_due + timedelta(minutes=slots * poll_minutes)
    if due < now:
        due += timedelta(minutes=poll_minutes)
    return due


def due_payback_jobs(
    date_yyyymmdd: str,
    filename: str,
    *,
    now: Optional[datetime] = None,
    state: Optional[dict] = None,
    start_after_minutes: int = PAYBACK_START_MINUTES,
    poll_minutes: int = PAYBACK_POLL_MINUTES,
) -> List[dict]:
    current = now or datetime.now()
    state = state if state is not None else load_payback_state(date_yyyymmdd, filename)
    due: List[dict] = []
    for rec in state.get("races", []):
        if rec.get("status") == "done":
            continue
        post_time = str(rec.get("post_time", ""))
        post_dt = race_post_datetime(date_yyyymmdd, post_time)
        if post_dt is None:
            continue
        first_due = post_dt + timedelta(minutes=int(start_after_minutes))
        if current < first_due:
            continue
        last_checked_at = str(rec.get("last_checked_at", "") or "")
        if last_checked_at:
            try:
                last_dt = datetime.fromisoformat(last_checked_at)
                if current < last_dt + timedelta(minutes=int(poll_minutes)):
                    continue
            except ValueError:
                pass
        due.append(rec)
    return sorted(due, key=lambda x: int(x.get("race_no", 999)))


def next_payback_wake(
    date_yyyymmdd: str,
    filename: str,
    *,
    now: Optional[datetime] = None,
    start_after_minutes: int = PAYBACK_START_MINUTES,
    poll_minutes: int = PAYBACK_POLL_MINUTES,
) -> Optional[datetime]:
    current = now or datetime.now()
    state = load_payback_state(date_yyyymmdd, filename)
    candidates: List[datetime] = []
    for rec in state.get("races", []):
        if rec.get("status") == "done":
            continue
        post_time = str(rec.get("post_time", ""))
        next_due = _next_due_poll_time(
            date_yyyymmdd,
            post_time,
            now=current,
            start_after_minutes=start_after_minutes,
            poll_minutes=poll_minutes,
        )
        if next_due is not None:
            candidates.append(next_due)
    return min(candidates) if candidates else None


def has_pending_payback_jobs(date_yyyymmdd: str, filename: str) -> bool:
    state = load_payback_state(date_yyyymmdd, filename)
    return any(
        str(r.get("status", "pending")) not in {"done", "timeout"}
        for r in state.get("races", [])
    )
