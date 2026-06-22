"""Check whether prediction weights likely need retuning after new master data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.score import load_master

DOC_TO = "20260531"
DEFAULT_FROM = "20260101"


def _roi_row(label: str, from_d: str, to_d: str, *, fetch_payback: bool) -> dict:
    report = backtest_period(from_d, to_d, fetch_payback=fetch_payback)
    w, p, sp, wd = report.win_pick, report.place_pick, report.sanrenpuku, report.wide
    return {
        "label": label,
        "from": from_d,
        "to": to_d,
        "races": report.race_count,
        "win_roi": w.roi,
        "place_roi": p.roi,
        "sanren_roi": sp.roi,
        "wide_roi": wd.roi,
    }


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare backtest before/after new data")
    parser.add_argument("--from", dest="from_d", default=DEFAULT_FROM)
    parser.add_argument("--doc-to", default=DOC_TO, help="Last date used when weights were validated")
    parser.add_argument("--fetch-payback", action="store_true")
    args = parser.parse_args()

    master = load_master()
    max_date = str(master["date"].max())
    print(f"master max date: {max_date}")
    if max_date <= args.doc_to:
        print(f"No new races after doc baseline ({args.doc_to}). Retune not required.")
        return

    baseline = _roi_row("baseline (doc)", args.from_d, args.doc_to, fetch_payback=args.fetch_payback)
    extended = _roi_row("extended", args.from_d, max_date, fetch_payback=args.fetch_payback)
    june_from = str(int(args.doc_to[:6]) + 1) + "01"  # 20260601 when doc_to=20260531
    if june_from <= max_date:
        june = _roi_row("added period", june_from, max_date, fetch_payback=args.fetch_payback)
    else:
        june = None

    print()
    for row in [baseline, extended] + ([june] if june else []):
        print(
            f"{row['label']} {row['from']}-{row['to']}  "
            f"R{row['races']}  win={_pct(row['win_roi'])}  place={_pct(row['place_roi'])}  "
            f"sanren={_pct(row['sanren_roi'])}  wide={_pct(row['wide_roi'])}"
        )

    print()
    print("--- recommendation ---")
    sanren_delta = extended["sanren_roi"] - baseline["sanren_roi"]
    wide_delta = extended["wide_roi"] - baseline["wide_roi"]
    win_delta = extended["win_roi"] - baseline["win_roi"]

    urgent = False
    if win_delta < -0.10 or sanren_delta < -0.15:
        urgent = True
        print("Consider tune_weights.py (win/sanren ROI dropped materially).")
    else:
        print("Weight JSON retune: not urgent from aggregate ROI.")

    if wide_delta < -0.10:
        print("Wide ROI weakened in extended period -> run R segment analysis.")
    else:
        print("Wide: no major aggregate warning.")

    print()
    print("R analysis (recommended after new data):")
    print(f"  python scripts/export_backtest_for_r.py --from {args.from_d} --to {max_date}")
    print("  Rscript r_analysis/scripts/run_all.R")
    if not urgent:
        print("Current weights (tuned ~2026-06-07) can stay until R review finishes.")


if __name__ == "__main__":
    main()
