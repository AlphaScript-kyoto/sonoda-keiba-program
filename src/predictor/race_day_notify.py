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

from src.predictor.automation_log import log_watch, send_alert, send_team_broadcast, write_heartbeat
from src.predictor.post_format import format_race_copy
from src.predictor.predict_day import PredictDayResult, run_predict_day_safe
from src.predictor.race_schedule import normalize_post_time, race_post_datetime
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
from src.scraper.sonoda_history import find_next_sonoda_race_date_after

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
    _, text = build_race_line_messages(date_yyyymmdd, race_no, result=result)
    return text


def build_upset_high_admin_line_message(
    date_yyyymmdd: str,
    race_no: int,
    plan,
) -> Optional[str]:
    """Admin-only follow-up when exotic upset + high confidence sanren formation."""
    from src.predictor.bets import format_sanrenpuku_formation_umaban_line

    if plan is None:
        return None
    if plan.exotic_profile != "\u8352" or plan.exotic_confidence != "\u9ad8":
        return None
    formation = plan.sanrenpuku_formation
    if formation is None or formation.points <= 0:
        return None

    buy_line = format_sanrenpuku_formation_umaban_line(formation)
    race_name = plan.race_name.strip() if plan.race_name else ""
    header = f"{date_yyyymmdd} {race_no}R"
    if race_name:
        header = f"{header} {race_name}"
    return (
        f"{header}\n"
        f"\u8352High\u30ec\u30fc\u30b9\u3067\u3059\n"
        f"\u8cb7\u3044\u76ee\u306f\n"
        f"\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f3\n"
        f"{buy_line}\n"
        f"\u3067\u3059"
    )


def build_line_predict_header(plan) -> str:
    """T-10 LINE \u5148\u982d\u884c\uff08\u30e1\u30f3\u30d0\u30fc\u5411\u3051\uff09\u3002"""
    rno = int(plan.race_no)
    post = normalize_post_time(plan.post_time) if plan.post_time else ""
    race_name = str(plan.race_name or "").strip()
    if post and race_name:
        return f"{rno}R\u3000{post}\u767a\u8d70\u3000{race_name}"
    if post:
        return f"{rno}R\u3000{post}\u767a\u8d70"
    if race_name:
        return f"{rno}R\u3000{race_name}"
    return f"{rno}R"


def build_race_line_messages(
    date_yyyymmdd: str,
    race_no: int,
    *,
    result: Optional[PredictDayResult] = None,
) -> tuple[Optional[object], str]:
    if result is None:
        result = run_predict_day_safe(
            date_yyyymmdd,
            only_race_nos={int(race_no)},
        )
    if result.message and result.win_df.empty:
        return None, (
            f"{int(race_no)}R\n"
            f"\u4e88\u60f3\u30c7\u30fc\u30bf\u306e\u6e96\u5099\u304c\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
        )

    plan = _plan_for_race(result, race_no)
    if plan is None:
        return None, (
            f"{int(race_no)}R\n"
            f"\u4e88\u60f3\u5bfe\u8c61\u304c\u3042\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
        )

    header = build_line_predict_header(plan)
    body = format_race_copy(plan, result.win_df, result.exotic_df)
    return plan, f"{header}\n\n{body}"


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
    from tools.line_bot import (
        format_line_delivery_log,
        send_line_message,
        send_line_predict_messages,
        team_user_ids,
    )
    import os

    from src.predictor.backtest import BET_UNIT
    from src.predictor.score import load_master
    from src.predictor.upset_high_bet_gate import (
        build_pause_skip_message,
        load_state,
        on_race_day_open,
        record_signaled_bet,
        save_state,
        should_send_upset_high_buy,
    )

    admin_id = os.getenv("LINE_USER_ID", "").strip()
    if not team_user_ids() and not admin_id:
        log_watch(
            date_yyyymmdd,
            "WARN LINE_TEAM_USER_IDS and LINE_USER_ID empty; skip predict push",
        )
        return []

    master = load_master()
    gate_state = on_race_day_open(date_yyyymmdd, load_state(), master=master)

    sent: List[str] = []
    for job in jobs:
        try:
            plan, text = build_race_line_messages(date_yyyymmdd, job.race_no)
            deliveries = send_line_predict_messages(text)
            for rec in deliveries:
                log_watch(date_yyyymmdd, format_line_delivery_log(rec))
            upset_text = build_upset_high_admin_line_message(
                date_yyyymmdd, job.race_no, plan
            )
            if upset_text:
                ok, reason = should_send_upset_high_buy(
                    gate_state, date_yyyymmdd, master=master
                )
                if ok:
                    resp = send_line_message(upset_text)
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"admin upset-high push failed: {resp.status_code} {resp.text}"
                        )
                    invest = 0
                    if plan and plan.sanrenpuku_formation:
                        invest = plan.sanrenpuku_formation.points * BET_UNIT
                    record_signaled_bet(
                        gate_state, date_yyyymmdd, job.race_no, invest
                    )
                    log_watch(
                        date_yyyymmdd,
                        f"LINE upset-high buy sent R{job.race_no} {job.race_id}",
                    )
                else:
                    if gate_state.pause_notified_date != date_yyyymmdd:
                        skip_msg = build_pause_skip_message(
                            date_yyyymmdd, job.race_no, reason, gate_state
                        )
                        resp = send_line_message(skip_msg)
                        if resp.status_code != 200:
                            raise RuntimeError(
                                f"admin upset-high pause failed: "
                                f"{resp.status_code} {resp.text}"
                            )
                        gate_state.pause_notified_date = date_yyyymmdd
                    log_watch(
                        date_yyyymmdd,
                        f"LINE upset-high skipped R{job.race_no} ({reason})",
                    )
            save_state(gate_state)
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


def process_due_upset_high_settlements(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    settle_offset: int | None = None,
    now: Optional[datetime] = None,
) -> List[int]:
    """荒×High: 次レースT-20で前レースまでの買い目を精算しゲート状態を更新する。"""
    from src.scraper.race_snapshots import due_capture_jobs
    from src.predictor.upset_high_bet_gate import (
        UPSET_HIGH_SETTLE_OFFSET,
        load_state,
        save_state,
        settle_pending_before_race,
    )

    offset = (
        UPSET_HIGH_SETTLE_OFFSET if settle_offset is None else int(settle_offset)
    )
    current = now or datetime.now()
    due = due_capture_jobs(
        date_yyyymmdd, schedule, offsets=(offset,), now=current
    )
    if not due:
        return []

    state = load_state()
    settled_all: List[int] = []
    seen_race_nos: set[int] = set()
    for job in due:
        if job.race_no in seen_race_nos:
            continue
        seen_race_nos.add(job.race_no)
        state, settled = settle_pending_before_race(
            date_yyyymmdd,
            job.race_no,
            state=state,
            schedule=schedule,
        )
        settled_all.extend(settled)

    if settled_all:
        save_state(state)
        races = ",".join(f"R{n}" for n in settled_all)
        log_watch(
            date_yyyymmdd,
            f"upset-high settled {races} (before T-{offset})",
        )
    return settled_all


def finalize_upset_high_pending(date_yyyymmdd: str) -> None:
    """当日の未精算シグナルを精算（最終レース後・監視終了時）。"""
    from src.predictor.upset_high_bet_gate import (
        load_state,
        save_state,
        settle_pending_for_date,
    )

    state = load_state()
    before = len([p for p in state.pending_signals if not p.settled])
    if before == 0:
        return
    state = settle_pending_for_date(date_yyyymmdd, state=state)
    save_state(state)
    after = len([p for p in state.pending_signals if not p.settled])
    settled = before - after
    if settled:
        log_watch(date_yyyymmdd, f"upset-high finalized {settled} pending signal(s)")


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
    from src.predictor.upset_high_bet_gate import UPSET_HIGH_SETTLE_OFFSET

    merged = set(int(m) for m in offsets)
    merged.add(int(UPSET_HIGH_SETTLE_OFFSET))
    if line_notify:
        merged.add(int(notify_offset))
    return tuple(sorted(merged, reverse=True))


def build_watch_start_line_message(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    notify_offset: int = LINE_NOTIFY_OFFSET,
) -> str:
    """監視開始時にチームへ送る当日案内文。"""
    month = int(date_yyyymmdd[4:6])
    day = int(date_yyyymmdd[6:8])
    races = sorted(
        schedule.get("races", []),
        key=lambda r: int(r.get("race_no", 0)),
    )
    lines = [
        f"{month}\u6708{day}\u65e5\u3000\u5712\u7530\u7af6\u99ac\u5834",
        f"\u5168{len(races)}R",
        "",
        f"\u5404\u30ec\u30fc\u30b9{notify_offset}\u5206\u524d\u306b\u4e88\u60f3\u5370\u3092\u914d\u4fe1\u3057\u307e\u3059\u3002",
        "\u672c\u65e5\u3082\u5f35\u308a\u5207\u3063\u3066\u3044\u304d\u307e\u3057\u3087\u3046\uff01",
        "",
        "\u3010\u5404\u30ec\u30fc\u30b9\u51fa\u8d70\u6642\u9593\u3011",
    ]
    for race in races:
        rno = int(race.get("race_no", 0))
        post = normalize_post_time(race.get("post_time", "")) or "?"
        lines.append(f"{rno}R\u3000{post}")
    return "\n".join(lines)


def _format_ja_month_day(date_yyyymmdd: str) -> str:
    month = int(date_yyyymmdd[4:6])
    day = int(date_yyyymmdd[6:8])
    return f"{month}\u6708{day}\u65e5"


def build_no_race_line_message(
    date_yyyymmdd: str,
    next_date_yyyymmdd: Optional[str],
) -> str:
    """休場日にチームへ送る案内文。"""
    lines = [
        "\u3010\u4f11\u5834\u306e\u304a\u77e5\u3089\u305b\u3011",
        "\u672c\u65e5\u306f\u4f11\u5834\u306e\u305f\u3081\u3001\u5712\u7530\u7af6\u99ac\u306e\u958b\u50ac\u306f\u3042\u308a\u307e\u305b\u3093\u3002",
    ]
    if next_date_yyyymmdd:
        lines.append(
            f"\u6b21\u56de\u306e\u958b\u50ac\u65e5\u306f"
            f"{_format_ja_month_day(next_date_yyyymmdd)}\u306b\u306a\u308a\u307e\u3059\u3002"
        )
    else:
        lines.append(
            "\u6b21\u56de\u306e\u958b\u50ac\u65e5\u306f\u73fe\u5728\u78ba\u5b9a\u3067\u304d\u3066\u304a\u308a\u307e\u305b\u3093\u3002"
        )
    return "\n".join(lines)


def notify_no_race_day(date_yyyymmdd: str, *, line_notify: bool) -> None:
    log_watch(date_yyyymmdd, "no Sonoda races; sending off-day notice")
    write_heartbeat(date_yyyymmdd, status="no_races")
    if not line_notify:
        return
    next_date = find_next_sonoda_race_date_after(date_yyyymmdd)
    msg = build_no_race_line_message(date_yyyymmdd, next_date)
    sent = send_team_broadcast(
        msg,
        date_yyyymmdd=date_yyyymmdd,
        alert_key=f"no_race_{date_yyyymmdd}",
        cooldown_minutes=60 * 12,
    )
    if not sent:
        log_watch(date_yyyymmdd, "off-day LINE skipped (cooldown)")
    elif next_date:
        log_watch(date_yyyymmdd, f"off-day LINE sent (next race {next_date})")
    else:
        log_watch(date_yyyymmdd, "off-day LINE sent (next race unknown)")


def notify_watch_started(date_yyyymmdd: str, schedule: dict, *, line_notify: bool) -> None:
    n = len(schedule.get("races", []))
    log_watch(date_yyyymmdd, f"watch started ({n} races, line={'on' if line_notify else 'off'})")
    write_heartbeat(date_yyyymmdd, status="started", extra={"race_count": n})
    if line_notify:
        msg = build_watch_start_line_message(date_yyyymmdd, schedule)
        sent = send_team_broadcast(
            msg,
            date_yyyymmdd=date_yyyymmdd,
            alert_key=f"watch_start_{date_yyyymmdd}",
            cooldown_minutes=60 * 12,
        )
        if not sent:
            log_watch(date_yyyymmdd, "watch start LINE skipped (cooldown)")


def notify_watch_finished(date_yyyymmdd: str, schedule: dict, *, line_notify: bool) -> None:
    finalize_upset_high_pending(date_yyyymmdd)
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
        notify_no_race_day(date_yyyymmdd, line_notify=line_notify)
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
            process_due_upset_high_settlements(date_yyyymmdd, schedule)
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
        schedule = load_schedule(date_yyyymmdd) or schedule
        process_due_upset_high_settlements(date_yyyymmdd, schedule)
        if line_notify:
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
