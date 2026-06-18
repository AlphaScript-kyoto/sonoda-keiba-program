"""Send a one-off test message to LINE_TEAM_USER_IDS."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.line_bot import send_line_team_messages, team_user_ids  # noqa: E402


def main() -> None:
    ids = team_user_ids()
    if not ids:
        print("LINE_TEAM_USER_IDS is empty. Set it in .env first.")
        sys.exit(1)

    today = datetime.now().strftime("%Y/%m/%d %H:%M")
    message = (
        "【園田予想bot・テスト配信】\n"
        "\n"
        "チーム向けLINE配信の接続テストです。\n"
        "レース当日は各レースの発走10分前（T-10）頃に\n"
        "予想と買い目の文案をお送りします。\n"
        "\n"
        f"送信時刻: {today}\n"
        "※このメッセージは動作確認用です。"
    )

    print(f"Sending test to {len(ids)} user(s)...")
    resp = send_line_team_messages(message)
    if resp.status_code != 200:
        print("Failed.")
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
