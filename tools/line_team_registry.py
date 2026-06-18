"""Register LINE team member user IDs from webhook events or followers API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REGISTRY_PATH = ROOT / "data" / "processed" / "line_team_registry.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"users": []}
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _channel_token() -> str:
    import os

    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set in .env")
    return token


def fetch_display_name(user_id: str) -> Optional[str]:
    token = _channel_token()
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return str(resp.json().get("displayName", "")).strip() or None
    except requests.RequestException:
        return None


def record_user(
    user_id: str,
    *,
    event_type: str,
    text: Optional[str] = None,
    fetch_profile: bool = True,
) -> bool:
    """Append or update user in registry. Returns True if newly added."""
    uid = str(user_id).strip()
    if not uid:
        return False

    data = load_registry()
    users: list[dict[str, Any]] = list(data.get("users") or [])
    by_id = {str(u.get("user_id")): u for u in users}
    now = _now_iso()
    is_new = uid not in by_id

    if is_new:
        entry: dict[str, Any] = {
            "user_id": uid,
            "display_name": None,
            "first_seen": now,
            "last_seen": now,
            "last_event": event_type,
            "message_count": 0,
        }
        users.append(entry)
        by_id[uid] = entry
    else:
        entry = by_id[uid]
        entry["last_seen"] = now
        entry["last_event"] = event_type

    if event_type == "message":
        entry["message_count"] = int(entry.get("message_count") or 0) + 1
        if text:
            entry["last_message"] = text[:200]

    if fetch_profile and not entry.get("display_name"):
        name = fetch_display_name(uid)
        if name:
            entry["display_name"] = name

    data["users"] = sorted(users, key=lambda u: str(u.get("first_seen", "")))
    data["updated_at"] = now
    save_registry(data)
    return is_new


def verify_line_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def process_webhook_events(events: list[dict[str, Any]]) -> list[str]:
    """Extract user IDs from webhook events and update registry."""
    recorded: list[str] = []
    for event in events:
        source = event.get("source") or {}
        if source.get("type") != "user":
            continue
        user_id = source.get("userId")
        if not user_id:
            continue

        event_type = str(event.get("type", "unknown"))
        text = None
        if event_type == "message":
            msg = event.get("message") or {}
            if msg.get("type") == "text":
                text = str(msg.get("text", ""))

        if record_user(str(user_id), event_type=event_type, text=text):
            recorded.append(str(user_id))
        else:
            recorded.append(str(user_id))
    return recorded


def team_user_ids(*, include_unfollowed: bool = False) -> list[str]:
    data = load_registry()
    ids: list[str] = []
    for user in data.get("users") or []:
        if not include_unfollowed and user.get("unfollowed"):
            continue
        uid = str(user.get("user_id", "")).strip()
        if uid:
            ids.append(uid)
    return ids


def export_team_ids_line() -> str:
    ids = team_user_ids()
    return ",".join(ids)


def mark_unfollowed(user_id: str) -> None:
    data = load_registry()
    for user in data.get("users") or []:
        if str(user.get("user_id")) == str(user_id):
            user["unfollowed"] = True
            user["unfollowed_at"] = _now_iso()
    data["updated_at"] = _now_iso()
    save_registry(data)


def process_webhook_payload(payload: dict[str, Any]) -> list[str]:
    events = payload.get("events") or []
    if not isinstance(events, list):
        return []
    out: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type")) == "unfollow":
            source = event.get("source") or {}
            uid = source.get("userId")
            if uid:
                mark_unfollowed(str(uid))
            continue
        out.extend(process_webhook_events([event]))
    return out


def fetch_followers_from_api(*, limit: int = 1000) -> list[str]:
    """Import follower user IDs via LINE Messaging API."""
    token = _channel_token()
    url = "https://api.line.me/v2/bot/followers/ids"
    collected: list[str] = []
    start: Optional[str] = None

    while True:
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if start:
            params["start"] = start
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        for uid in body.get("userIds") or []:
            uid_s = str(uid)
            collected.append(uid_s)
            record_user(uid_s, event_type="followers_api", fetch_profile=True)
        start = body.get("next")
        if not start:
            break
    return collected
