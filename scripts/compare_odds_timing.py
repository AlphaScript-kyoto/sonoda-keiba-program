"""Compare snapshot(s) vs final master odds for a date."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.score import load_master
from src.predictor.snapshot_compare import (
    compare_day,
    compare_day_all_labels,
    format_compare_report,
)
from src.scraper.race_snapshots import DEFAULT_CAPTURE_OFFSETS, label_for_offset, parse_capture_offsets


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare snapshots vs final odds timing")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument(
        "--label",
        default="",
        help="Snapshot label e.g. t_minus_10 (default: all default offsets)",
    )
    parser.add_argument("--out", default="", help="Optional report path")
    args = parser.parse_args()

    master = load_master()
    if args.label:
        rows = compare_day(args.date, master, label=args.label)
        report = format_compare_report(rows, label=args.label)
    else:
        by_label = compare_day_all_labels(args.date, master)
        parts = []
        for minutes in DEFAULT_CAPTURE_OFFSETS:
            label = label_for_offset(minutes)
            parts.append(format_compare_report(by_label.get(label, []), label=label))
        report = "\n\n".join(parts)

    print(report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
