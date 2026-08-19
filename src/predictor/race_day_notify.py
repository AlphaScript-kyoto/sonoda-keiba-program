"""Race day: predict at T-10 and push copy text to LINE."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.automation_log import log_watch, send_alert, send_team_broadcast, write_heartbeat
from src.predictor.bets import assign_marks
from src.predictor.post_format import format_race_copy
from src.predictor.predict_day import PredictDayResult, run_predict_day_safe
from src.predictor.race_schedule import normalize_post_time, race_post_datetime
from src.scraper.client import NetkeibaBlockedError, is_transient_network_error
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
    update_schedule_race_meta,
)
from src.scraper.sonoda_history import find_next_sonoda_race_date_after

LINE_NOTIFY_OFFSET = 10
# T-10 投稿失敗時: その場で再試行 → それでもダメなら発走前まで短間隔で起こす
LINE_NOTIFY_INLINE_ATTEMPTS = 3
LINE_NOTIFY_INLINE_BACKOFF_SEC = (20.0, 40.0, 60.0)
LINE_NOTIFY_REWAKE_SEC = 60
S_PLUS_PAYBACK_START_MINUTES = 5
S_PLUS_PAYBACK_POLL_MINUTES = 5
S_PLUS_PAYBACK_TIMEOUT_MINUTES = 180
P6_PAYBACK_STATE_FILE = "p6_payback_state.json"


def _send_discord_safe(date_yyyymmdd: str, message: str, *, category: str) -> None:
    from tools.discord_bot import send_discord_message

    if not str(message or "").strip():
        return
    attempts = 3
    for attempt in range(attempts):
        try:
            send_discord_message(message, category=category)
            return
        except Exception as exc:
            if attempt + 1 < attempts and is_transient_network_error(exc):
                time.sleep(5.0 * (attempt + 1))
                continue
            log_watch(
                date_yyyymmdd,
                f"WARN Discord {category} send failed: {exc}",
            )
            return


def next_line_notify_retry_wake(
    date_yyyymmdd: str,
    schedule: dict,
    *,
    notify_offset: int = LINE_NOTIFY_OFFSET,
    now: Optional[datetime] = None,
    rewake_sec: int = LINE_NOTIFY_REWAKE_SEC,
) -> Optional[datetime]:
    """未送信の T-10 があるとき、発走前まで短間隔で起こす時刻。"""
    current = now or datetime.now()
    pending = due_line_notify_jobs(
        date_yyyymmdd,
        schedule,
        notify_offset=notify_offset,
        now=current,
    )
    if not pending:
        return None
    return current + timedelta(seconds=max(1, int(rewake_sec)))


def _copy_t10_x_post_to_clipboard(date_yyyymmdd: str, race_no: int, x_post_text: str) -> None:
    from tools.clipboard_util import copy_to_clipboard, t10_clipboard_enabled

    if not t10_clipboard_enabled():
        return
    if copy_to_clipboard(x_post_text):
        log_watch(
            date_yyyymmdd,
            f"clipboard R{race_no} X post ready ({len(x_post_text)} chars)",
        )
    else:
        log_watch(
            date_yyyymmdd,
            f"WARN clipboard copy failed R{race_no}",
        )


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


def s_plus_payback_state_path(date_yyyymmdd: str) -> Path:
    return snapshots_dir(date_yyyymmdd) / "s_plus_payback_state.json"


def load_s_plus_payback_state(date_yyyymmdd: str) -> dict:
    path = s_plus_payback_state_path(date_yyyymmdd)
    if not path.exists():
        return {
            "date": date_yyyymmdd,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "races": [],
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_s_plus_payback_state(date_yyyymmdd: str, state: dict) -> None:
    state["date"] = date_yyyymmdd
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = s_plus_payback_state_path(date_yyyymmdd)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def register_s_plus_payback_target(
    date_yyyymmdd: str,
    *,
    race_id: str,
    race_no: int,
    race_name: str,
    post_time: str,
) -> None:
    state = load_s_plus_payback_state(date_yyyymmdd)
    races = state.get("races", [])
    rid = str(race_id)
    for rec in races:
        if str(rec.get("race_id", "")) == rid:
            rec["race_no"] = int(race_no)
            rec["race_name"] = str(race_name or "")
            rec["post_time"] = str(post_time or "")
            save_s_plus_payback_state(date_yyyymmdd, state)
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
    state["races"] = sorted(
        races, key=lambda x: int(x.get("race_no", 999))
    )
    save_s_plus_payback_state(date_yyyymmdd, state)


def sync_payback_post_times_from_schedule(
    date_yyyymmdd: str,
    schedule: dict,
) -> None:
    post_by_id = {
        str(r.get("race_id", "")): normalize_post_time(r.get("post_time", ""))
        for r in schedule.get("races", [])
        if r.get("race_id")
    }
    state = load_s_plus_payback_state(date_yyyymmdd)
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
        save_s_plus_payback_state(date_yyyymmdd, state)
    from src.predictor.race_payback_notify import sync_payback_post_times

    sync_payback_post_times(date_yyyymmdd, schedule, P6_PAYBACK_STATE_FILE)


def register_p6_payback_target(
    date_yyyymmdd: str,
    *,
    race_id: str,
    race_no: int,
    race_name: str,
    post_time: str,
) -> None:
    from src.predictor.race_payback_notify import register_payback_target

    register_payback_target(
        date_yyyymmdd,
        P6_PAYBACK_STATE_FILE,
        race_id=race_id,
        race_no=race_no,
        race_name=race_name,
        post_time=post_time,
    )


def due_p6_payback_jobs(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
    state: Optional[dict] = None,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
) -> List[dict]:
    from src.predictor.race_payback_notify import due_payback_jobs, load_payback_state

    # 呼び出し側から state を渡す場合は同一オブジェクトを共有し、
    # status="done" 等の更新が保存対象の state に反映されるようにする。
    state = (
        state
        if state is not None
        else load_payback_state(date_yyyymmdd, P6_PAYBACK_STATE_FILE)
    )
    return due_payback_jobs(
        date_yyyymmdd,
        P6_PAYBACK_STATE_FILE,
        now=now,
        state=state,
        start_after_minutes=start_after_minutes,
        poll_minutes=poll_minutes,
    )


def next_p6_payback_wake(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
) -> Optional[datetime]:
    from src.predictor.race_payback_notify import next_payback_wake

    return next_payback_wake(
        date_yyyymmdd,
        P6_PAYBACK_STATE_FILE,
        now=now,
        start_after_minutes=start_after_minutes,
        poll_minutes=poll_minutes,
    )


def _next_poll_after(
    date_yyyymmdd: str,
    post_time: str,
    *,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
) -> Optional[datetime]:
    post_dt = race_post_datetime(date_yyyymmdd, post_time)
    if post_dt is None:
        return None
    return post_dt + timedelta(minutes=int(start_after_minutes + poll_minutes))


def _next_due_poll_time(
    date_yyyymmdd: str,
    post_time: str,
    *,
    now: datetime,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
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


def due_s_plus_payback_jobs(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
    state: Optional[dict] = None,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
) -> List[dict]:
    current = now or datetime.now()
    state = state if state is not None else load_s_plus_payback_state(date_yyyymmdd)
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


def next_s_plus_payback_wake(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
    start_after_minutes: int = S_PLUS_PAYBACK_START_MINUTES,
    poll_minutes: int = S_PLUS_PAYBACK_POLL_MINUTES,
) -> Optional[datetime]:
    current = now or datetime.now()
    state = load_s_plus_payback_state(date_yyyymmdd)
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


def build_s_plus_payback_message(
    date_yyyymmdd: str,
    *,
    race_no: int,
    race_name: str,
    evaluation,
) -> str:
    race_title = f"{int(race_no)}R"
    if race_name:
        race_title = f"{race_title} {race_name}"
    hit = " 的中" if evaluation.hit else ""
    finish = "-".join(evaluation.finish)
    return "\n".join(
        [
            f"{date_yyyymmdd} {race_title}",
            f"【期待値S+ 三連複結果{hit}】",
            f"結果 {finish}",
            f"買い目 {evaluation.buy_line}",
            f"払戻 {int(evaluation.return_yen):,}円",
        ]
    )


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
    _, text, _, _, _ = build_race_line_messages(date_yyyymmdd, race_no, result=result)
    return text


def _send_member_only_line(message: str) -> List:
    """S+ buy / payback: LINE_TEAM_USER_IDS only (not admin)."""
    from tools.line_bot import send_line_team_messages, team_user_ids

    if not message.strip() or not team_user_ids():
        return []
    return send_line_team_messages(message)


def build_upset_high_admin_line_message(
    date_yyyymmdd: str,
    race_no: int,
    plan,
) -> Optional[str]:
    """Admin-only P6 buy signal (upset x High, volatile, axis odds floor)."""
    from src.predictor.bets import format_sanrenpuku_formation_umaban_line
    from src.predictor.upset_p6_rules import is_p6_eligible_plan

    if plan is None:
        return None
    if not is_p6_eligible_plan(plan):
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
        f"\u3010P6\u3011\u8352\u00d7High\n"
        f"\u8cb7\u3044\u76ee\u306f\n"
        f"\u4e09\u9023\u8907\u30d5\u30a9\u30fc\u30e1\u30fc\u30b7\u30e7\u30f35\u70b9\n"
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


def _exotic_frame_for_race(result: PredictDayResult, race_no: int) -> pd.DataFrame:
    df = result.exotic_df if result.exotic_df is not None else result.win_df
    return df[df["race_no"].astype(int) == int(race_no)].copy()


def netkeiba_marks_link_enabled() -> bool:
    import os

    # Default on for T-10 team LINE. Set NETKEIBA_MARKS_LINK_ENABLED=0 to disable.
    return os.getenv("NETKEIBA_MARKS_LINK_ENABLED", "1").strip() != "0"


def build_race_line_messages(
    date_yyyymmdd: str,
    race_no: int,
    *,
    result: Optional[PredictDayResult] = None,
    include_netkeiba_marks_link: Optional[bool] = None,
) -> tuple[Optional[object], str, Optional[str], str, float]:
    """Return plan, predict text, optional S+ buy text, x_post text, odds_std."""
    from src.predictor.ops_gates import odds_std_from_scored

    if result is None:
        result = run_predict_day_safe(
            date_yyyymmdd,
            only_race_nos={int(race_no)},
        )
    if result.message and result.win_df.empty:
        err = (
            f"{int(race_no)}R\n"
            f"\u4e88\u60f3\u30c7\u30fc\u30bf\u306e\u6e96\u5099\u304c\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
        )
        return None, err, None, err, 0.0

    plan = _plan_for_race(result, race_no)
    if plan is None:
        err = (
            f"{int(race_no)}R\n"
            f"\u4e88\u60f3\u5bfe\u8c61\u304c\u3042\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002"
        )
        return None, err, None, err, 0.0

    header = build_line_predict_header(plan)
    body = format_race_copy(plan, result.win_df, result.exotic_df)
    from src.predictor.t10_daily_roi import format_s_plus_buy_line_message

    exotic_frame = _exotic_frame_for_race(result, race_no)
    top5 = assign_marks(exotic_frame)
    odds_std = odds_std_from_scored(exotic_frame)
    buy_text = format_s_plus_buy_line_message(plan, top5, header_line=header)
    add_marks_link = (
        include_netkeiba_marks_link
        if include_netkeiba_marks_link is not None
        else netkeiba_marks_link_enabled()
    )
    x_post_text = f"{header}\n\n{body}"
    text = x_post_text
    if add_marks_link:
        from src.predictor.netkeiba_marks import format_netkeiba_marks_block

        text += format_netkeiba_marks_block(plan)
    return plan, text, buy_text, x_post_text, odds_std


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
        is_line_notify_paused,
        line_notify_pause_log_line,
        send_line_message,
        send_line_predict_messages,
        team_user_ids,
    )
    import os

    from src.predictor.backtest import BET_UNIT
    from src.predictor.ops_gates import (
        annotate_message_with_notes,
        evaluate_buy_ops_gates,
        load_ops_gate_config,
    )
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
    ops_cfg = load_ops_gate_config()

    sent: List[str] = []
    for job in jobs:
        last_exc: Optional[BaseException] = None
        for attempt in range(LINE_NOTIFY_INLINE_ATTEMPTS):
            try:
                plan, text, buy_text, x_post_text, odds_std = build_race_line_messages(
                    date_yyyymmdd, job.race_no
                )
                post_time = (
                    normalize_post_time(plan.post_time)
                    if plan is not None and plan.post_time
                    else normalize_post_time(job.post_time)
                )
                race_name = (
                    str(plan.race_name or "").strip()
                    if plan is not None
                    else str(job.race_name or "")
                )
                schedule_update = update_schedule_race_meta(
                    date_yyyymmdd,
                    job.race_id,
                    post_time=post_time,
                    race_name=race_name,
                )
                if schedule_update:
                    old_post, new_post = schedule_update
                    log_watch(
                        date_yyyymmdd,
                        f"schedule post_time R{job.race_no} {job.race_id} "
                        f"{old_post} -> {new_post}",
                    )
                deliveries = send_line_predict_messages(text)
                for rec in deliveries:
                    log_watch(date_yyyymmdd, format_line_delivery_log(rec))
                _send_discord_safe(date_yyyymmdd, text, category="t10_predict")
                _copy_t10_x_post_to_clipboard(date_yyyymmdd, job.race_no, x_post_text)
                line_paused = is_line_notify_paused()

                ops_dec = evaluate_buy_ops_gates(
                    date_yyyymmdd,
                    job.race_id,
                    plan,
                    master,
                    odds_std_t10=odds_std,
                    config=ops_cfg,
                )
                for line in ops_dec.log_lines:
                    log_watch(date_yyyymmdd, line)

                if buy_text and not ops_dec.allow_s_plus:
                    log_watch(
                        date_yyyymmdd,
                        f"OPS_GATE S+ buy blocked R{job.race_no} "
                        f"({', '.join(ops_dec.skip_reasons) or 'blocked'})",
                    )
                    buy_text = None
                elif buy_text and ops_dec.observe_notes:
                    buy_text = annotate_message_with_notes(
                        buy_text, ops_dec.observe_notes
                    )

                if buy_text:
                    if line_paused:
                        buy_deliveries: List = []
                    else:
                        buy_deliveries = _send_member_only_line(buy_text)
                    if line_paused:
                        log_watch(
                            date_yyyymmdd,
                            line_notify_pause_log_line("s_plus_buy"),
                        )
                        _send_discord_safe(
                            date_yyyymmdd,
                            buy_text,
                            category="s_plus_buy",
                        )
                        register_s_plus_payback_target(
                            date_yyyymmdd,
                            race_id=job.race_id,
                            race_no=job.race_no,
                            race_name=race_name,
                            post_time=post_time,
                        )
                        log_watch(
                            date_yyyymmdd,
                            f"S+ buy Discord only (LINE paused) R{job.race_no} {job.race_id}",
                        )
                    elif not buy_deliveries:
                        log_watch(
                            date_yyyymmdd,
                            f"WARN S+ buy skipped R{job.race_no} "
                            "(LINE_TEAM_USER_IDS empty)",
                        )
                    else:
                        for rec in buy_deliveries:
                            log_watch(date_yyyymmdd, format_line_delivery_log(rec))
                        _send_discord_safe(
                            date_yyyymmdd,
                            buy_text,
                            category="s_plus_buy",
                        )
                        register_s_plus_payback_target(
                            date_yyyymmdd,
                            race_id=job.race_id,
                            race_no=job.race_no,
                            race_name=race_name,
                            post_time=post_time,
                        )
                        log_watch(
                            date_yyyymmdd,
                            f"LINE S+ buy sent R{job.race_no} {job.race_id}",
                        )
                upset_text = build_upset_high_admin_line_message(
                    date_yyyymmdd, job.race_no, plan
                )
                if upset_text and not ops_dec.allow_p6:
                    log_watch(
                        date_yyyymmdd,
                        f"OPS_GATE P6 buy blocked R{job.race_no} "
                        f"({', '.join(ops_dec.skip_reasons) or 'blocked'})",
                    )
                    upset_text = None
                elif upset_text and ops_dec.observe_notes:
                    upset_text = annotate_message_with_notes(
                        upset_text, ops_dec.observe_notes
                    )
                if upset_text:
                    ok, reason = should_send_upset_high_buy(
                        gate_state, date_yyyymmdd, master=master, plan=plan
                    )
                    if ok:
                        if line_paused:
                            log_watch(
                                date_yyyymmdd,
                                line_notify_pause_log_line("p6_buy"),
                            )
                        else:
                            resp = send_line_message(upset_text)
                            if resp.status_code != 200:
                                raise RuntimeError(
                                    f"admin upset-high push failed: {resp.status_code} {resp.text}"
                                )
                        _send_discord_safe(
                            date_yyyymmdd,
                            upset_text,
                            category="p6_buy",
                        )
                        invest = 0
                        if plan and plan.sanrenpuku_formation:
                            invest = plan.sanrenpuku_formation.points * BET_UNIT
                        record_signaled_bet(
                            gate_state, date_yyyymmdd, job.race_no, invest
                        )
                        register_p6_payback_target(
                            date_yyyymmdd,
                            race_id=job.race_id,
                            race_no=job.race_no,
                            race_name=race_name,
                            post_time=post_time,
                        )
                        log_watch(
                            date_yyyymmdd,
                            f"LINE P6 buy sent R{job.race_no} {job.race_id}",
                        )
                    else:
                        if gate_state.pause_notified_date != date_yyyymmdd:
                            skip_msg = build_pause_skip_message(
                                date_yyyymmdd, job.race_no, reason, gate_state
                            )
                            if line_paused:
                                log_watch(
                                    date_yyyymmdd,
                                    line_notify_pause_log_line("p6_pause"),
                                )
                            else:
                                resp = send_line_message(skip_msg)
                                if resp.status_code != 200:
                                    raise RuntimeError(
                                        f"admin upset-high pause failed: "
                                        f"{resp.status_code} {resp.text}"
                                    )
                            _send_discord_safe(
                                date_yyyymmdd,
                                skip_msg,
                                category="p6_pause",
                            )
                            gate_state.pause_notified_date = date_yyyymmdd
                        log_watch(
                            date_yyyymmdd,
                            f"LINE upset-high skipped R{job.race_no} ({reason})",
                        )
                save_state(gate_state)
                mark_race_notified(date_yyyymmdd, job.race_id)
                sent.append(job.race_id)
                if line_paused:
                    log_watch(
                        date_yyyymmdd,
                        f"notify sent R{job.race_no} {job.race_id} "
                        f"Discord only (LINE paused) post={post_time}",
                    )
                else:
                    log_watch(
                        date_yyyymmdd,
                        f"LINE post sent R{job.race_no} {job.race_id} post={post_time}",
                    )
                last_exc = None
                break
            except NetkeibaBlockedError:
                raise
            except Exception as exc:
                last_exc = exc
                if (
                    is_transient_network_error(exc)
                    and attempt + 1 < LINE_NOTIFY_INLINE_ATTEMPTS
                ):
                    delay = LINE_NOTIFY_INLINE_BACKOFF_SEC[
                        min(attempt, len(LINE_NOTIFY_INLINE_BACKOFF_SEC) - 1)
                    ]
                    log_watch(
                        date_yyyymmdd,
                        f"WARN R{job.race_no} notify retry "
                        f"{attempt + 1}/{LINE_NOTIFY_INLINE_ATTEMPTS} "
                        f"in {delay:.0f}s: {exc}",
                    )
                    time.sleep(delay)
                    continue
                break
        if last_exc is not None:
            msg = f"R{job.race_no} LINE post failed: {last_exc}"
            log_watch(date_yyyymmdd, f"WARN {msg}")
            send_alert(
                f"R{job.race_no} \u6295\u7a3f\u6587 LINE \u9001\u4fe1\u5931\u6557\n{last_exc}",
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


def process_due_s_plus_payback_notifications(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
) -> List[int]:
    from src.predictor.score import load_master
    from src.predictor.t10_daily_roi import evaluate_s_plus_payback_for_race
    from src.scraper.payback import fetch_paybacks
    from tools.line_bot import format_line_delivery_log

    master = load_master()
    state = load_s_plus_payback_state(date_yyyymmdd)
    due = due_s_plus_payback_jobs(date_yyyymmdd, now=now, state=state)
    if not due:
        return []

    current = now or datetime.now()
    settled: List[int] = []
    for rec in due:
        rid = str(rec.get("race_id", ""))
        rno = int(rec.get("race_no", 0))
        race_name = str(rec.get("race_name", "") or "")
        rec["last_checked_at"] = current.isoformat(timespec="seconds")
        try:
            pb_map = fetch_paybacks([rid], use_cache=True, stop_on_block=True)
            pb = pb_map.get(rid)
            if pb is None:
                post_dt = race_post_datetime(date_yyyymmdd, str(rec.get("post_time", "")))
                if (
                    post_dt is not None
                    and current >= post_dt + timedelta(minutes=S_PLUS_PAYBACK_TIMEOUT_MINUTES)
                ):
                    rec["status"] = "timeout"
                    rec["settled_at"] = current.isoformat(timespec="seconds")
                    log_watch(
                        date_yyyymmdd,
                        f"S+ payback timeout R{rno} {rid}",
                    )
                    continue
                log_watch(
                    date_yyyymmdd,
                    f"S+ payback pending R{rno} {rid}",
                )
                continue
            evaluation = evaluate_s_plus_payback_for_race(
                date_yyyymmdd, rid, pb, master=master
            )
            if evaluation is None:
                log_watch(
                    date_yyyymmdd,
                    f"S+ payback pending R{rno} {rid} (result not ready)",
                )
                continue
            msg = build_s_plus_payback_message(
                date_yyyymmdd,
                race_no=rno,
                race_name=race_name,
                evaluation=evaluation,
            )
            from tools.line_bot import is_line_notify_paused, line_notify_pause_log_line

            line_paused = is_line_notify_paused()
            if line_paused:
                log_watch(date_yyyymmdd, line_notify_pause_log_line("s_plus_payback"))
            else:
                deliveries = _send_member_only_line(msg)
                if not deliveries:
                    log_watch(
                        date_yyyymmdd,
                        f"WARN S+ payback skipped R{rno} {rid} "
                        "(LINE_TEAM_USER_IDS empty)",
                    )
                    continue
                for out in deliveries:
                    log_watch(date_yyyymmdd, format_line_delivery_log(out))
            _send_discord_safe(
                date_yyyymmdd,
                msg,
                category="s_plus_payback",
            )
            rec["status"] = "done"
            rec["settled_at"] = current.isoformat(timespec="seconds")
            settled.append(rno)
            log_watch(
                date_yyyymmdd,
                f"S+ payback sent R{rno} {rid} hit={evaluation.hit} "
                f"ret={evaluation.return_yen}",
            )
        except NetkeibaBlockedError:
            raise
        except Exception as exc:
            log_watch(
                date_yyyymmdd,
                f"WARN S+ payback poll failed R{rno} {rid}: {exc}",
            )
            send_alert(
                f"R{rno} 払戻 LINE 送信失敗\n{exc}",
                date_yyyymmdd=date_yyyymmdd,
                alert_key=f"s_plus_payback_fail_{date_yyyymmdd}_{rid}",
                cooldown_minutes=15,
            )
    state["races"] = state.get("races", [])
    save_s_plus_payback_state(date_yyyymmdd, state)
    return settled


def process_due_p6_payback_notifications(
    date_yyyymmdd: str,
    *,
    now: Optional[datetime] = None,
) -> List[int]:
    from src.predictor.p6_payback import build_p6_payback_message, evaluate_p6_payback_for_race
    from src.predictor.race_payback_notify import load_payback_state, save_payback_state
    from src.predictor.score import load_master
    from src.scraper.payback import fetch_paybacks
    from tools.line_bot import send_line_message

    master = load_master()
    state = load_payback_state(date_yyyymmdd, P6_PAYBACK_STATE_FILE)
    due = due_p6_payback_jobs(date_yyyymmdd, now=now, state=state)
    if not due:
        return []

    current = now or datetime.now()
    settled: List[int] = []
    for rec in due:
        rid = str(rec.get("race_id", ""))
        rno = int(rec.get("race_no", 0))
        race_name = str(rec.get("race_name", "") or "")
        rec["last_checked_at"] = current.isoformat(timespec="seconds")
        try:
            pb_map = fetch_paybacks([rid], use_cache=True, stop_on_block=True)
            pb = pb_map.get(rid)
            if pb is None:
                post_dt = race_post_datetime(date_yyyymmdd, str(rec.get("post_time", "")))
                if (
                    post_dt is not None
                    and current >= post_dt + timedelta(minutes=S_PLUS_PAYBACK_TIMEOUT_MINUTES)
                ):
                    rec["status"] = "timeout"
                    rec["settled_at"] = current.isoformat(timespec="seconds")
                    log_watch(
                        date_yyyymmdd,
                        f"P6 payback timeout R{rno} {rid}",
                    )
                    continue
                log_watch(
                    date_yyyymmdd,
                    f"P6 payback pending R{rno} {rid}",
                )
                continue
            evaluation = evaluate_p6_payback_for_race(
                date_yyyymmdd, rid, pb, master=master
            )
            if evaluation is None:
                log_watch(
                    date_yyyymmdd,
                    f"P6 payback pending R{rno} {rid} (result not ready)",
                )
                continue
            msg = build_p6_payback_message(
                race_no=rno,
                race_name=race_name,
                evaluation=evaluation,
            )
            from tools.line_bot import is_line_notify_paused, line_notify_pause_log_line

            if is_line_notify_paused():
                log_watch(date_yyyymmdd, line_notify_pause_log_line("p6_payback"))
            else:
                resp = send_line_message(msg)
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"P6 payback push failed: {resp.status_code} {resp.text}"
                    )
            _send_discord_safe(
                date_yyyymmdd,
                msg,
                category="p6_payback",
            )
            rec["status"] = "done"
            rec["settled_at"] = current.isoformat(timespec="seconds")
            settled.append(rno)
            log_watch(
                date_yyyymmdd,
                f"P6 payback sent R{rno} {rid} hit={evaluation.hit} "
                f"ret={evaluation.return_yen}",
            )
        except NetkeibaBlockedError:
            raise
        except Exception as exc:
            log_watch(
                date_yyyymmdd,
                f"WARN P6 payback poll failed R{rno} {rid}: {exc}",
            )
            send_alert(
                f"R{rno} P6\u6255\u623b LINE\u9001\u4fe1\u5931\u6557\n{exc}",
                date_yyyymmdd=date_yyyymmdd,
                alert_key=f"p6_payback_fail_{date_yyyymmdd}_{rid}",
                cooldown_minutes=15,
            )
    state["races"] = state.get("races", [])
    save_payback_state(date_yyyymmdd, P6_PAYBACK_STATE_FILE, state)
    return settled


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
    if due_s_plus_payback_jobs(date_yyyymmdd, now=now):
        return False
    if due_p6_payback_jobs(date_yyyymmdd, now=now):
        return False
    state = load_s_plus_payback_state(date_yyyymmdd)
    if any(
        str(r.get("status", "pending")) not in {"done", "timeout"}
        for r in state.get("races", [])
    ):
        return False
    from src.predictor.race_payback_notify import has_pending_payback_jobs

    if has_pending_payback_jobs(date_yyyymmdd, P6_PAYBACK_STATE_FILE):
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
        "\u671f\u5f85\u5024S+\u306f\u767a\u8d705\u5206\u5f8c\u304b\u3089\u6255\u623b\u901a\u77e5\u3092\u884c\u3044\u307e\u3059\u3002",
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
    log_watch(date_yyyymmdd, "no Sonoda races; off-day notice check")
    write_heartbeat(date_yyyymmdd, status="no_races")
    if not line_notify:
        return
    next_date = find_next_sonoda_race_date_after(date_yyyymmdd)
    msg = build_no_race_line_message(date_yyyymmdd, next_date)
    from src.predictor.off_day_notify import send_off_day_team_broadcast

    sent = send_off_day_team_broadcast(msg, date_yyyymmdd, next_date)
    if sent and next_date:
        log_watch(date_yyyymmdd, f"off-day broadcast done (next race {next_date})")
    elif sent:
        log_watch(date_yyyymmdd, "off-day broadcast done (next race unknown)")


def notify_watch_started(date_yyyymmdd: str, schedule: dict, *, line_notify: bool) -> None:
    n = len(schedule.get("races", []))
    log_watch(date_yyyymmdd, f"watch started ({n} races, line={'on' if line_notify else 'off'})")
    write_heartbeat(date_yyyymmdd, status="started", extra={"race_count": n})
    if line_notify:
        msg = build_watch_start_line_message(date_yyyymmdd, schedule)
        try:
            sent = send_team_broadcast(
                msg,
                date_yyyymmdd=date_yyyymmdd,
                alert_key=f"watch_start_{date_yyyymmdd}",
                cooldown_minutes=60 * 12,
            )
            if not sent:
                log_watch(date_yyyymmdd, "watch start LINE skipped (cooldown)")
        except Exception as exc:
            log_watch(
                date_yyyymmdd,
                f"WARN watch start broadcast failed (watch continues): {exc}",
            )


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
            sync_payback_post_times_from_schedule(date_yyyymmdd, schedule)
            process_due_upset_high_settlements(date_yyyymmdd, schedule)
            if line_notify:
                process_due_line_notifications(
                    date_yyyymmdd,
                    schedule,
                    notify_offset=notify_offset,
                )
                process_due_s_plus_payback_notifications(date_yyyymmdd)
                process_due_p6_payback_notifications(date_yyyymmdd)

            if all_captures_done_for_watch(
                date_yyyymmdd,
                schedule,
                offsets=offsets,
                line_notify=line_notify,
                notify_offset=notify_offset,
            ):
                notify_watch_finished(date_yyyymmdd, schedule, line_notify=line_notify)
                break

            snap_wake_at = next_wake_datetime(
                date_yyyymmdd,
                schedule,
                offsets=_wake_offsets(offsets, line_notify, notify_offset),
            )
            payback_wake_at = next_s_plus_payback_wake(date_yyyymmdd)
            p6_wake_at = next_p6_payback_wake(date_yyyymmdd)
            retry_wake_at = (
                next_line_notify_retry_wake(
                    date_yyyymmdd,
                    schedule,
                    notify_offset=notify_offset,
                )
                if line_notify
                else None
            )
            wake_candidates = [
                w
                for w in (
                    snap_wake_at,
                    payback_wake_at,
                    p6_wake_at,
                    retry_wake_at,
                )
                if w is not None
            ]
            wake_at = min(wake_candidates) if wake_candidates else None
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
                if retry_wake_at is not None and wake_at == retry_wake_at:
                    log_watch(
                        date_yyyymmdd,
                        f"pending T-10 retry wake in {sleep_sec:.0f}s",
                    )
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
        sync_payback_post_times_from_schedule(date_yyyymmdd, schedule)
        process_due_upset_high_settlements(date_yyyymmdd, schedule)
        if line_notify:
            process_due_line_notifications(
                date_yyyymmdd,
                schedule,
                notify_offset=notify_offset,
            )
            process_due_s_plus_payback_notifications(date_yyyymmdd)
            process_due_p6_payback_notifications(date_yyyymmdd)
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
