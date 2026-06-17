"""Automation file logging and LINE alerts for race-day watch."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import DATA_PROCESSED_DIR

LOGS_DIR = DATA_PROCESSED_DIR / "logs"
ALERT_STATE_PATH = LOGS_DIR / "alert_state.json"
HEARTBEAT_STALE_MINUTES = 25
HEARTBEAT_GRACE_AFTER_WAKE_MINUTES = 10


def watch_log_path(date_yyyymmdd: str) -> Path:
    return LOGS_DIR / f"watch_{date_yyyymmdd}.log"


def run_today_log_path(date_yyyymmdd: str) -> Path:
    return LOGS_DIR / f"run_today_{date_yyyymmdd}.log"


def heartbeat_path(date_yyyymmdd: str) -> Path:
    return LOGS_DIR / f"watch_heartbeat_{date_yyyymmdd}.json"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(path: Path, msg: str) -> None:
    line = f"[{_timestamp()}] {msg}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_watch(date_yyyymmdd: str, msg: str) -> None:
    append_log(watch_log_path(date_yyyymmdd), msg)


def log_run_today(date_yyyymmdd: str, msg: str) -> None:
    append_log(run_today_log_path(date_yyyymmdd), msg)


def write_heartbeat(
    date_yyyymmdd: str,
    *,
    status: str,
    next_wake_at: Optional[datetime] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    payload: dict[str, Any] = {
        "date": date_yyyymmdd,
        "status": status,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if next_wake_at is not None:
        payload["next_wake_at"] = next_wake_at.isoformat(timespec="seconds")
    if extra:
        payload.update(extra)
    path = heartbeat_path(date_yyyymmdd)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_heartbeat(date_yyyymmdd: str) -> Optional[dict[str, Any]]:
    path = heartbeat_path(date_yyyymmdd)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_alert_state() -> dict[str, Any]:
    if not ALERT_STATE_PATH.exists():
        return {}
    try:
        with ALERT_STATE_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_alert_state(state: dict[str, Any]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with ALERT_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_alert(
    message: str,
    *,
    date_yyyymmdd: Optional[str] = None,
    alert_key: Optional[str] = None,
    cooldown_minutes: int = 30,
    log_channel: str = "watch",
) -> bool:
    """Push alert to LINE. Returns False if skipped by cooldown."""
    key = alert_key or message[:80]
    state = _load_alert_state()
    last_sent = state.get(key)
    if last_sent:
        try:
            last_dt = datetime.fromisoformat(str(last_sent))
            elapsed = (datetime.now() - last_dt).total_seconds() / 60.0
            if elapsed < cooldown_minutes:
                return False
        except ValueError:
            pass

    from tools.line_bot import send_line_message

    text = f"\u3010\u5712\u7530\u30a2\u30e9\u30fc\u30c8\u3011\n{message}"
    send_line_message(text)
    state[key] = datetime.now().isoformat(timespec="seconds")
    _save_alert_state(state)
    if date_yyyymmdd and log_channel == "run_today":
        log_run_today(date_yyyymmdd, f"ALERT sent: {message}")
    elif date_yyyymmdd and log_channel == "watch":
        log_watch(date_yyyymmdd, f"ALERT sent: {message}")
    return True
