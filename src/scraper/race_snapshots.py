"""Pre-race snapshots: schedule + timed shutuba/odds capture."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from config.settings import DATA_PROCESSED_DIR
from src.predictor.race_schedule import normalize_post_time, race_post_datetime
from src.scraper.client import NetkeibaBlockedError
from src.scraper.odds import fetch_race_odds_snapshot
from src.scraper.race_list import list_race_ids_for_shutuba
from src.scraper.shutuba import fetch_shutuba_html, parse_shutuba

SNAPSHOTS_ROOT = DATA_PROCESSED_DIR / "snapshots"
DEFAULT_CAPTURE_OFFSETS: Tuple[int, ...] = (30, 20, 10)
LABEL_T_MINUS_10 = "t_minus_10"


def label_for_offset(minutes_before: int) -> str:
    return f"t_minus_{minutes_before}"


def parse_capture_offsets(text: str) -> Tuple[int, ...]:
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    if not parts:
        return DEFAULT_CAPTURE_OFFSETS
    offsets = tuple(sorted({int(p) for p in parts}, reverse=True))
    return offsets


def snapshots_dir(date_yyyymmdd: str) -> Path:
    path = SNAPSHOTS_ROOT / date_yyyymmdd
    path.mkdir(parents=True, exist_ok=True)
    return path


def schedule_path(date_yyyymmdd: str) -> Path:
    return snapshots_dir(date_yyyymmdd) / "schedule.json"


def snapshot_path(date_yyyymmdd: str, race_id: str, label: str) -> Path:
    return snapshots_dir(date_yyyymmdd) / f"{race_id}_{label}.json"


def load_schedule(date_yyyymmdd: str) -> Optional[dict]:
    path = schedule_path(date_yyyymmdd)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_schedule(schedule: dict) -> Path:
    date_yyyymmdd = str(schedule["date"])
    path = schedule_path(date_yyyymmdd)
    with path.open("w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return path


def race_meta_from_entries(entries: List[dict]) -> tuple[str, str]:
    if not entries:
        return "", ""
    row = entries[0]
    return (
        normalize_post_time(row.get("post_time", "")),
        str(row.get("race_name", "") or "").strip(),
    )


def update_schedule_race_meta(
    date_yyyymmdd: str,
    race_id: str,
    *,
    post_time: str = "",
    race_name: str = "",
) -> Optional[tuple[str, str]]:
    """schedule.json の発走時刻・レース名を netkeiba 最新に合わせる。

    Returns (old_post_time, new_post_time) when post_time changed, else None.
    """
    schedule = load_schedule(date_yyyymmdd)
    if not schedule:
        return None
    rid = str(race_id)
    post_time = normalize_post_time(post_time)
    race_name = str(race_name or "").strip()
    changed_post: Optional[tuple[str, str]] = None
    meta_changed = False
    for race in schedule.get("races", []):
        if str(race.get("race_id", "")) != rid:
            continue
        old_post = normalize_post_time(race.get("post_time", ""))
        if post_time and old_post != post_time:
            race["post_time"] = post_time
            changed_post = (old_post, post_time)
            meta_changed = True
        if race_name and race.get("race_name") != race_name:
            race["race_name"] = race_name
            meta_changed = True
        break
    if meta_changed:
        schedule["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_schedule(schedule)
    return changed_post


def sync_schedule_from_entries(
    date_yyyymmdd: str,
    race_id: str,
    entries: List[dict],
) -> Optional[tuple[str, str]]:
    post_time, race_name = race_meta_from_entries(entries)
    if not post_time and not race_name:
        return None
    return update_schedule_race_meta(
        date_yyyymmdd,
        race_id,
        post_time=post_time,
        race_name=race_name,
    )


def fetch_and_save_schedule(date_yyyymmdd: str) -> dict:
    race_ids = list_race_ids_for_shutuba(date_yyyymmdd)
    races: List[dict] = []
    for rid in race_ids:
        html = fetch_shutuba_html(rid)
        rows = parse_shutuba(html, rid)
        post_time = ""
        race_name = ""
        if rows:
            post_time = normalize_post_time(rows[0].get("post_time", ""))
            race_name = str(rows[0].get("race_name", "") or "")
        races.append(
            {
                "race_id": rid,
                "race_no": int(rid[-2:]),
                "post_time": post_time,
                "race_name": race_name,
            }
        )

    schedule = {
        "date": date_yyyymmdd,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "capture_offsets": list(DEFAULT_CAPTURE_OFFSETS),
        "races": races,
    }
    save_schedule(schedule)
    return schedule


def is_snapshot_captured(date_yyyymmdd: str, race_id: str, label: str) -> bool:
    return snapshot_path(date_yyyymmdd, race_id, label).exists()


def trigger_datetime(
    date_yyyymmdd: str,
    post_time: str,
    minutes_before: int,
) -> Optional[datetime]:
    post_dt = race_post_datetime(date_yyyymmdd, post_time)
    if post_dt is None:
        return None
    return post_dt - timedelta(minutes=minutes_before)


@dataclass(frozen=True)
class CaptureJob:
    race_id: str
    race_no: int
    post_time: str
    race_name: str
    minutes_before: int
    label: str


def _race_jobs(
    date_yyyymmdd: str,
    schedule: dict,
    offsets: Sequence[int],
) -> Iterable[CaptureJob]:
    for race in schedule.get("races", []):
        rid = str(race.get("race_id", ""))
        post_time = str(race.get("post_time", ""))
        if not rid or not post_time:
            continue
        for minutes in offsets:
            label = label_for_offset(minutes)
            yield CaptureJob(
                race_id=rid,
                race_no=int(race.get("race_no", int(rid[-2:]))),
                post_time=post_time,
                race_name=str(race.get("race_name", "") or ""),
                minutes_before=minutes,
                label=label,
            )


def due_capture_jobs(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    now: Optional[datetime] = None,
) -> List[CaptureJob]:
    current = now or datetime.now()
    due: List[CaptureJob] = []
    for job in _race_jobs(date_yyyymmdd, schedule, offsets):
        if is_snapshot_captured(date_yyyymmdd, job.race_id, job.label):
            continue
        post_dt = race_post_datetime(date_yyyymmdd, job.post_time)
        trigger = trigger_datetime(date_yyyymmdd, job.post_time, job.minutes_before)
        if post_dt is None or trigger is None:
            continue
        if current >= post_dt:
            continue
        if current >= trigger:
            due.append(job)
    return sorted(due, key=lambda j: (j.race_no, -j.minutes_before))


def next_wake_datetime(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    current = now or datetime.now()
    candidates: List[datetime] = []
    for job in _race_jobs(date_yyyymmdd, schedule, offsets):
        if is_snapshot_captured(date_yyyymmdd, job.race_id, job.label):
            continue
        post_dt = race_post_datetime(date_yyyymmdd, job.post_time)
        trigger = trigger_datetime(date_yyyymmdd, job.post_time, job.minutes_before)
        if post_dt is None or trigger is None:
            continue
        if current >= post_dt:
            continue
        if trigger > current:
            candidates.append(trigger)
    return min(candidates) if candidates else None


def all_captures_done(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    now: Optional[datetime] = None,
) -> bool:
    return not due_capture_jobs(date_yyyymmdd, schedule, offsets=offsets, now=now) and (
        next_wake_datetime(date_yyyymmdd, schedule, offsets=offsets, now=now) is None
    )


def capture_race_snapshot(
    date_yyyymmdd: str,
    race_id: str,
    *,
    minutes_before: int,
    include_exotic_odds: bool = False,
) -> dict:
    label = label_for_offset(minutes_before)
    if is_snapshot_captured(date_yyyymmdd, race_id, label):
        path = snapshot_path(date_yyyymmdd, race_id, label)
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        sync_schedule_from_entries(
            date_yyyymmdd, race_id, payload.get("entries", [])
        )
        return payload

    html = fetch_shutuba_html(race_id)
    entries = parse_shutuba(html, race_id)
    sync_schedule_from_entries(date_yyyymmdd, race_id, entries)
    odds_snap = fetch_race_odds_snapshot(race_id, include_exotic=include_exotic_odds)

    payload: Dict[str, Any] = {
        "date": date_yyyymmdd,
        "race_id": race_id,
        "label": label,
        "minutes_before": minutes_before,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "entries": entries,
        "odds": odds_snap.to_dict(),
    }
    if not entries:
        payload["status"] = "no_entries"
    path = snapshot_path(date_yyyymmdd, race_id, label)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def capture_t_minus_10(
    date_yyyymmdd: str,
    race_id: str,
    *,
    include_exotic_odds: bool = False,
) -> dict:
    return capture_race_snapshot(
        date_yyyymmdd,
        race_id,
        minutes_before=10,
        include_exotic_odds=include_exotic_odds,
    )


def capture_due(
    date_yyyymmdd: str,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    include_exotic_odds: bool = False,
    now: Optional[datetime] = None,
) -> List[str]:
    from src.predictor.automation_log import log_watch

    schedule = load_schedule(date_yyyymmdd)
    if schedule is None or not schedule.get("races"):
        schedule = fetch_and_save_schedule(date_yyyymmdd)

    captured: List[str] = []
    for job in due_capture_jobs(
        date_yyyymmdd, schedule, offsets=offsets, now=now
    ):
        try:
            capture_race_snapshot(
                date_yyyymmdd,
                job.race_id,
                minutes_before=job.minutes_before,
                include_exotic_odds=include_exotic_odds,
            )
            schedule = load_schedule(date_yyyymmdd) or schedule
            race_row = next(
                (
                    r
                    for r in schedule.get("races", [])
                    if str(r.get("race_id", "")) == job.race_id
                ),
                None,
            )
            post_time = str(
                (race_row or {}).get("post_time", job.post_time) or job.post_time
            )
            key = f"{job.race_id}:{job.label}"
            captured.append(key)
            print(
                f"  captured T-{job.minutes_before} {job.race_id} "
                f"R{job.race_no} post={post_time}",
                flush=True,
            )
            if race_row and post_time != job.post_time:
                log_watch(
                    date_yyyymmdd,
                    f"schedule post_time R{job.race_no} {job.race_id} "
                    f"{job.post_time} -> {post_time}",
                )
        except NetkeibaBlockedError:
            raise
        except Exception as exc:
            print(
                f"  WARN capture T-{job.minutes_before} {job.race_id}: {exc}",
                flush=True,
            )
    return captured


def watch_scheduled(
    date_yyyymmdd: str,
    *,
    offsets: Sequence[int] = DEFAULT_CAPTURE_OFFSETS,
    include_exotic_odds: bool = False,
) -> None:
    schedule = load_schedule(date_yyyymmdd)
    if schedule is None or not schedule.get("races"):
        schedule = fetch_and_save_schedule(date_yyyymmdd)

    offsets_str = ",".join(str(m) for m in offsets)
    print(f"Scheduled capture offsets: T-{offsets_str.replace(',', ', T-')}", flush=True)

    while True:
        capture_due(
            date_yyyymmdd,
            offsets=offsets,
            include_exotic_odds=include_exotic_odds,
        )
        schedule = load_schedule(date_yyyymmdd) or schedule
        if all_captures_done(date_yyyymmdd, schedule, offsets=offsets):
            print("All scheduled captures done.", flush=True)
            break

        wake_at = next_wake_datetime(date_yyyymmdd, schedule, offsets=offsets)
        if wake_at is None:
            print("No more capture times. Done.", flush=True)
            break

        now = datetime.now()
        sleep_sec = max(0.0, (wake_at - now).total_seconds())
        print(
            f"  next wake {wake_at.strftime('%H:%M:%S')} "
            f"(sleep {sleep_sec:.0f}s)",
            flush=True,
        )
        if sleep_sec > 0:
            time.sleep(sleep_sec)


# --- backward compatibility ---

def should_capture_now(
    date_yyyymmdd: str,
    post_time: str,
    now: Optional[datetime] = None,
    *,
    minutes_before: int = 10,
) -> bool:
    post_dt = race_post_datetime(date_yyyymmdd, post_time)
    if post_dt is None:
        return False
    current = now or datetime.now()
    if current >= post_dt:
        return False
    trigger = post_dt - timedelta(minutes=minutes_before)
    return current >= trigger


def pending_races(
    date_yyyymmdd: str,
    schedule: dict,
    now: Optional[datetime] = None,
    *,
    minutes_before: int = 10,
) -> List[dict]:
    jobs = due_capture_jobs(
        date_yyyymmdd,
        schedule,
        offsets=(minutes_before,),
        now=now,
    )
    return [
        {
            "race_id": j.race_id,
            "race_no": j.race_no,
            "post_time": j.post_time,
            "race_name": j.race_name,
        }
        for j in jobs
    ]


def all_races_done(
    date_yyyymmdd: str,
    schedule: dict,
    now: Optional[datetime] = None,
) -> bool:
    return all_captures_done(
        date_yyyymmdd,
        schedule,
        offsets=(10,),
        now=now,
    )


def watch_once(
    date_yyyymmdd: str,
    *,
    minutes_before: int = 10,
    include_exotic_odds: bool = False,
    now: Optional[datetime] = None,
) -> List[str]:
    return capture_due(
        date_yyyymmdd,
        offsets=(minutes_before,),
        include_exotic_odds=include_exotic_odds,
        now=now,
    )
