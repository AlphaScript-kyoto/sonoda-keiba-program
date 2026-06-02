"""LINE Messaging API でプッシュ通知を送る。"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


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
    token, user_id = _line_credentials()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}],
    }
    response = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=30)
    print(response.status_code)
    print(response.text)
    return response


if __name__ == "__main__":
    send_line_message("テスト：園田競馬通知ボットです！")
