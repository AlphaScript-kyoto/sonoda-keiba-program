"""Print / optionally LINE-send T-10 ROI report for a date."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.t10_daily_roi import (  # noqa: E402
    build_t10_daily_roi_report,
    format_t10_daily_roi_message,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="T-10 ROI report (expectation S+)")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--line", action="store_true", help="Send to LINE_USER_ID")
    parser.add_argument("--no-fetch-payback", action="store_true")
    args = parser.parse_args()

    report = build_t10_daily_roi_report(
        args.date,
        fetch_payback=not args.no_fetch_payback,
    )
    msg = format_t10_daily_roi_message(report)
    print(msg)

    if args.line:
        from tools.line_bot import send_line_message  # noqa: E402

        send_line_message(msg)


if __name__ == "__main__":
    main()
