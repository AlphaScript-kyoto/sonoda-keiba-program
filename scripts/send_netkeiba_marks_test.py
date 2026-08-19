"""Send T-10 predict with netkeiba marks link to admin only (test)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.race_day_notify import build_race_line_messages
from tools.line_bot import send_line_message


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin-only test: T-10 + netkeiba marks link")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--race", type=int, default=1)
    args = parser.parse_args()

    _plan, text, _buy, _x, _std = build_race_line_messages(
        args.date,
        args.race,
        include_netkeiba_marks_link=True,
    )
    note = (
        "\n\n[test] Tampermonkey \u304c\u6709\u52b9\u306a\u3089\u51fa\u99ac\u8868\u30ea\u30f3\u30af\u3092\u958b\u304f\u3068\u5370\u304c\u81ea\u52d5\u5165\u308a\u307e\u3059\u3002"
        "tools/netkeiba_marks.user.js \u3092\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u6e08\u307f\u3067\u3042\u308b\u3053\u3068\u3002"
    )
    # Test-only note; production T-10 uses format_netkeiba_marks_block without this text.
    message = text + note
    resp = send_line_message(message)
    print(f"status={resp.status_code}")
    if resp.status_code != 200:
        print(resp.text)
        return 1
    print("OK admin test sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
