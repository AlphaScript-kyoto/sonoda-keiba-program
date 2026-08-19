"""LINE Messaging API でプッシュ通知を送る。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_TEXT_LIMIT = 4800
PAUSED_STATUS_CODE = 0
_LINE_PAUSED_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_line_notify_paused() -> bool:
    """True when LINE_NOTIFY_PAUSED is set (1/on/true/yes). Discord is unaffected."""
    raw = os.getenv("LINE_NOTIFY_PAUSED", "").strip().lower()
    return raw in _LINE_PAUSED_TRUTHY


def line_notify_pause_log_line(channel: str = "all") -> str:
    return f"LINE push {channel} skipped (LINE_NOTIFY_PAUSED=1)"


@dataclass(frozen=True)
class LineSendResult:
    """One LINE push attempt (single chunk to one user)."""

    channel: str
    user_id_suffix: str
    status_code: int
    request_id: str
    chunk: str


def format_line_delivery_log(result: LineSendResult) -> str:
    """Single-line delivery record for automation logs."""
    if result.status_code == PAUSED_STATUS_CODE:
        return line_notify_pause_log_line(result.channel)
    return (
        f"LINE push {result.channel} ...{result.user_id_suffix} "
        f"status={result.status_code} req={result.request_id or '?'} "
        f"chunk={result.chunk}"
    )


def _paused_send_results(channel: str) -> list[LineSendResult]:
    print(line_notify_pause_log_line(channel))
    return [
        LineSendResult(
            channel=channel,
            user_id_suffix="----",
            status_code=PAUSED_STATUS_CODE,
            request_id="paused",
            chunk="skipped",
        )
    ]


def _paused_http_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    return response


def chunk_text_for_line(text: str, max_len: int = LINE_TEXT_LIMIT) -> list[str]:
    """Split text for LINE (prefer line breaks)."""
    body = text.strip()
    if not body:
        return [""]
    if len(body) <= max_len:
        return [body]

    chunks: list[str] = []
    current = ""
    for line in body.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(line) > max_len:
            chunks.append(line[:max_len])
            line = line[max_len:]
        current = line
    if current:
        chunks.append(current)
    return chunks


def _channel_token() -> str:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "LINE_CHANNEL_ACCESS_TOKEN を .env に設定してください。"
            "（.env.example を参照）"
        )
    return token


def _line_credentials() -> tuple[str, str]:
    token = _channel_token()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    if not user_id:
        raise RuntimeError(
            "LINE_USER_ID を .env に設定してください。"
            "（.env.example を参照）"
        )
    return token, user_id


def _user_id_suffix(user_id: str) -> str:
    return user_id[-4:] if len(user_id) >= 4 else user_id


def _line_request_id(response: requests.Response) -> str:
    return str(response.headers.get("x-line-request-id", "")).strip()


def team_user_ids() -> list[str]:
    """Team predict recipients from LINE_TEAM_USER_IDS (comma-separated)."""
    raw = os.getenv("LINE_TEAM_USER_IDS", "").strip()
    if not raw:
        return []
    return [uid.strip() for uid in raw.split(",") if uid.strip()]


def _post_line_push(user_id: str, text: str) -> requests.Response:
    token = _channel_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    response = requests.post(
        LINE_PUSH_URL, headers=headers, json=payload, timeout=30
    )
    print(response.status_code)
    print(response.text)
    return response


def _push_text_to_user(
    user_id: str,
    message: str,
    *,
    channel: str,
) -> list[LineSendResult]:
    parts = chunk_text_for_line(message)
    results: list[LineSendResult] = []
    sent_parts = [part for part in parts if part]
    total = len(sent_parts) if sent_parts else 1

    if not sent_parts:
        response = _post_line_push(user_id, "(empty)")
        results.append(
            LineSendResult(
                channel=channel,
                user_id_suffix=_user_id_suffix(user_id),
                status_code=response.status_code,
                request_id=_line_request_id(response),
                chunk="1/1",
            )
        )
        return results

    for idx, part in enumerate(sent_parts):
        prefix = f"({idx + 1}/{total})\n" if total > 1 else ""
        response = _post_line_push(user_id, prefix + part)
        results.append(
            LineSendResult(
                channel=channel,
                user_id_suffix=_user_id_suffix(user_id),
                status_code=response.status_code,
                request_id=_line_request_id(response),
                chunk=f"{idx + 1}/{total}",
            )
        )
    return results


def _last_response(results: list[LineSendResult]) -> requests.Response:
    """Backward-compatible shim: fabricate a minimal Response-like object."""
    if not results:
        response = requests.Response()
        response.status_code = 500
        return response
    response = requests.Response()
    response.status_code = results[-1].status_code
    return response


def send_line_message(message: str) -> requests.Response:
    """管理者 (LINE_USER_ID) にテキストをプッシュ送信。"""
    return send_line_messages(message)


def send_line_messages(message: str) -> requests.Response:
    """管理者向け push。長文は分割。Returns the last response."""
    if is_line_notify_paused():
        _paused_send_results("admin_push")
        return _paused_http_response()
    _, user_id = _line_credentials()
    results = _push_text_to_user(user_id, message, channel="admin_push")
    return _last_response(results)


def send_line_team_messages(message: str) -> list[LineSendResult]:
    """LINE_TEAM_USER_IDS の各ユーザーへ push（1人ずつ）。"""
    if is_line_notify_paused():
        return _paused_send_results("team_push")
    user_ids = team_user_ids()
    if not user_ids:
        raise RuntimeError(
            "LINE_TEAM_USER_IDS が未設定です。"
            "scripts/line_export_team_ids.py で ID を確認してください。"
        )

    results: list[LineSendResult] = []
    for user_id in user_ids:
        results.extend(
            _push_text_to_user(user_id, message, channel="team_push")
        )
    return results


def send_line_predict_messages(message: str) -> list[LineSendResult]:
    """T-10 predict: team push (per member) + admin push when not in team."""
    if is_line_notify_paused():
        return _paused_send_results("predict")
    admin_id = os.getenv("LINE_USER_ID", "").strip()
    team_ids = team_user_ids()
    results: list[LineSendResult] = []

    if team_ids:
        results.extend(send_line_team_messages(message))
        for rec in results:
            if rec.status_code != 200:
                raise RuntimeError(
                    "team push failed: "
                    f"...{rec.user_id_suffix} "
                    f"status={rec.status_code} req={rec.request_id}"
                )

    if admin_id and admin_id not in team_ids:
        chunk_results = _push_text_to_user(
            admin_id, message, channel="admin_push"
        )
        for rec in chunk_results:
            if rec.status_code != 200:
                raise RuntimeError(
                    "admin push failed: "
                    f"status={rec.status_code} req={rec.request_id}"
                )
        results.extend(chunk_results)
    elif not team_ids:
        if not admin_id:
            raise RuntimeError("LINE_TEAM_USER_IDS と LINE_USER_ID が未設定です。")
        chunk_results = _push_text_to_user(
            admin_id, message, channel="admin_push"
        )
        for rec in chunk_results:
            if rec.status_code != 200:
                raise RuntimeError(
                    "admin push failed: "
                    f"status={rec.status_code} req={rec.request_id}"
                )
        results.extend(chunk_results)

    return results


if __name__ == "__main__":
    send_line_message("test: sonoda-keiba notify bot")
