"""LINE Messaging API でプッシュ通知を送る。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_TEXT_LIMIT = 4800


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


def _line_credentials() -> tuple[str, str]:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    if not token or not user_id:
        raise RuntimeError(
            "LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を .env に設定してください。"
            "（.env.example を参照）"
        )
    return token, user_id


def send_line_message(message: str) -> requests.Response:
    """指定ユーザーにテキストをプッシュ送信。"""
    return send_line_messages(message)


def send_line_messages(message: str) -> requests.Response:
    """Long text is split into multiple pushes. Returns the last response."""
    parts = chunk_text_for_line(message)
    response: Optional[requests.Response] = None
    for idx, part in enumerate(parts):
        if not part:
            continue
        prefix = f"({idx + 1}/{len(parts)})\n" if len(parts) > 1 else ""
        response = _post_line_text(prefix + part)
    if response is None:
        response = _post_line_text("(empty)")
    return response


def _post_line_text(text: str) -> requests.Response:
    token, user_id = _line_credentials()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    response = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=30)
    print(response.status_code)
    print(response.text)
    return response


if __name__ == "__main__":
    send_line_message("test: sonoda-keiba notify bot")
