"""T-10 ROI for all dates with snapshots; optional LINE to admin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import DATA_PROCESSED_DIR
from src.predictor.t10_daily_roi import (  # noqa: E402
    build_t10_daily_roi_report,
    format_t10_daily_roi_message,
)
from src.predictor.score import load_master
from src.scraper.race_snapshots import LABEL_T_MINUS_10


def list_snapshot_dates() -> list[str]:
    root = DATA_PROCESSED_DIR / "snapshots"
    if not root.is_dir():
        return []
    dates: list[str] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        if list(day_dir.glob(f"*_{LABEL_T_MINUS_10}.json")):
            dates.append(day_dir.name)
    return dates


def build_history_message(
    dates: list[str],
    *,
    fetch_payback: bool = False,
) -> str:
    master = load_master()
    parts = [
        "【園田 T-10回収率 過去実績まとめ】",
        "期待値S+ / 単2倍+ / 複1.5倍+ / 三連5点",
        "",
    ]
    grand_inv = grand_ret = grand_pts = grand_races = 0

    for date in dates:
        report = build_t10_daily_roi_report(
            date,
            master=master,
            fetch_payback=fetch_payback,
        )
        parts.append(format_t10_daily_roi_message(report))
        parts.append("")
        grand_inv += report.total_investment
        grand_ret += report.total_return
        grand_pts += sum(
            r.win_points + r.place_points + r.sanren_points for r in report.races
        )
        grand_races += len(report.races)

    roi = (grand_ret / grand_inv * 100.0) if grand_inv else 0.0
    parts.append(f"=== 全期間合計 ({len(dates)}日) ===")
    parts.append(
        f"{grand_races}R {grand_pts}点 投{grand_inv} 払{grand_ret} 回収{roi:.0f}%"
    )
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="T-10 ROI history (all snapshot dates)")
    parser.add_argument(
        "--dates",
        default="",
        help="Comma-separated YYYYMMDD (default: all snapshot dates)",
    )
    parser.add_argument("--line", action="store_true", help="Send to LINE_USER_ID")
    parser.add_argument("--fetch-payback", action="store_true")
    parser.add_argument(
        "--out",
        default=str(DATA_PROCESSED_DIR / "logs" / "t10_roi_history_line.txt"),
    )
    args = parser.parse_args()

    if args.dates.strip():
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        dates = list_snapshot_dates()

    if not dates:
        print("No snapshot dates found.")
        sys.exit(1)

    msg = build_history_message(dates, fetch_payback=args.fetch_payback)
    print(msg)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(msg, encoding="utf-8")
    print(f"\nWrote {out}")

    if args.line:
        from tools.line_bot import send_line_messages  # noqa: E402

        send_line_messages(msg)


if __name__ == "__main__":
    main()
