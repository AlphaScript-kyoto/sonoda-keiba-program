"""Grid-search exotic firm/upset confidence thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import ExoticTuneResult, tune_exotic_thresholds
from src.predictor.bets import (
    DEFAULT_EXOTIC_FIRM_THRESHOLDS,
    DEFAULT_EXOTIC_UPSET_THRESHOLDS,
    DEFAULT_STRATEGY,
    ConfidenceThresholds,
)
from src.predictor.score import load_master

CONFIG_PATH = ROOT / "config" / "exotic_thresholds.json"

FIRM_WIN_PROBS = [0.85, 0.88, 0.90]
FIRM_GAPS = [0.70, 0.75, 0.80, 0.85]
UPSET_WIN_PROBS = [0.78, 0.80, 0.82]
UPSET_GAPS = [0.50, 0.55, 0.60]


def _print_results(results: list[ExoticTuneResult], top_n: int = 10) -> None:
    print(f"\n=== top {top_n} (Q1 sanrenpuku ROI) ===")
    print(
        f"{'#':>2}  {'Q1 R':>5}  {'Q1 ROI':>7}  {'Val ROI':>7}  "
        f"firm wp/gap  upset wp/gap"
    )
    for i, r in enumerate(results[:top_n], start=1):
        f, u = r.firm, r.upset
        print(
            f"{i:>2}  {r.q1_sanren_races:>5}  {r.q1_sanren_roi:>6.1%}  "
            f"{r.validate_sanren_roi:>6.1%}  "
            f"{f.win_prob:.2f}/{f.prob_gap:.2f}  {u.win_prob:.2f}/{u.prob_gap:.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune exotic confidence thresholds")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write config/exotic_thresholds.json with recommended thresholds",
    )
    args = parser.parse_args()

    master = load_master()
    baseline_strategy = DEFAULT_STRATEGY
    baseline_only = tune_exotic_thresholds(
        "20260101",
        "20260331",
        "20260401",
        "20260531",
        master=master,
        firm_win_probs=[DEFAULT_EXOTIC_FIRM_THRESHOLDS.win_prob],
        firm_gaps=[DEFAULT_EXOTIC_FIRM_THRESHOLDS.prob_gap],
        upset_win_probs=[DEFAULT_EXOTIC_UPSET_THRESHOLDS.win_prob],
        upset_gaps=[DEFAULT_EXOTIC_UPSET_THRESHOLDS.prob_gap],
        strategy=baseline_strategy,
    )
    if baseline_only:
        b = baseline_only[0]
        print(
            "Baseline (current defaults): "
            f"Q1 sanrenpuku ROI {b.q1_sanren_roi:.1%} ({b.q1_sanren_races}R), "
            f"validate {b.validate_sanren_roi:.1%}"
        )

    results = tune_exotic_thresholds(
        "20260101",
        "20260331",
        "20260401",
        "20260531",
        master=master,
        firm_win_probs=FIRM_WIN_PROBS,
        firm_gaps=FIRM_GAPS,
        upset_win_probs=UPSET_WIN_PROBS,
        upset_gaps=UPSET_GAPS,
        strategy=baseline_strategy,
    )

    _print_results(results)
    if not results:
        print("No grid point passed filters.")
        return

    rec = results[0]
    print(
        "\nRecommended:"
        f" firm win_prob={rec.firm.win_prob} gap={rec.firm.prob_gap};"
        f" upset win_prob={rec.upset.win_prob} gap={rec.upset.prob_gap}"
    )
    print(
        f"  Q1 sanrenpuku ROI {rec.q1_sanren_roi:.1%} ({rec.q1_sanren_races} races),"
        f" validate {rec.validate_sanren_roi:.1%}"
    )
    print(
        "\nUpdate DEFAULT_EXOTIC_FIRM_THRESHOLDS / DEFAULT_EXOTIC_UPSET_THRESHOLDS in bets.py"
        " to match recommended values after review."
    )

    if args.apply:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exotic_firm": asdict(rec.firm),
            "exotic_upset": asdict(rec.upset),
            "q1_sanren_roi": rec.q1_sanren_roi,
            "q1_sanren_races": rec.q1_sanren_races,
            "validate_sanren_roi": rec.validate_sanren_roi,
        }
        CONFIG_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {CONFIG_PATH}")


if __name__ == "__main__":
    main()
