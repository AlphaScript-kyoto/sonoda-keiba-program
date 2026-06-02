"""Race post time helpers for predict UI partial fetch."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_POST_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def normalize_post_time(text: object) -> str:
    raw = str(text or "").strip()
    m = _POST_TIME_RE.match(raw)
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def race_post_datetime(date_yyyymmdd: str, post_time: str) -> Optional[datetime]:
    t = normalize_post_time(post_time)
    if not t or len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        return None
    try:
        return datetime(
            int(date_yyyymmdd[:4]),
            int(date_yyyymmdd[4:6]),
            int(date_yyyymmdd[6:8]),
            int(t[:2]),
            int(t[3:5]),
        )
    except ValueError:
        return None


def is_race_started(
    date_yyyymmdd: str,
    post_time: str,
    now: Optional[datetime] = None,
) -> bool:
    post_dt = race_post_datetime(date_yyyymmdd, post_time)
    if post_dt is None:
        return False
    current = now if now is not None else datetime.now()
    return current >= post_dt