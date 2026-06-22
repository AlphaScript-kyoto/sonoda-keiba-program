"""Send upset-high pause gate test messages to admin LINE."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.upset_high_bet_gate import (
    build_pause_test_message,
    build_rules_test_message,
    build_settle_timing_test_message,
)
from tools.line_bot import send_line_message


def main() -> None:
    for msg in (
        build_rules_test_message(),
        build_settle_timing_test_message(),
        build_pause_test_message(),
    ):
        resp = send_line_message(msg)
        if resp.status_code != 200:
            raise SystemExit(f"LINE failed: {resp.status_code} {resp.text}")
        print(resp.status_code)


if __name__ == "__main__":
    main()
