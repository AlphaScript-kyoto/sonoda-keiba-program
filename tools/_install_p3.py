from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent.parent

EXOTIC_APPEND = '''

@dataclass
class ExoticTuneResult:
    firm: ConfidenceThresholds
    upset: ConfidenceThresholds
    q1_sanren_roi: float
    q1_sanren_races: int
    validate_sanren_roi: float


def _sanren_roi_and_races(report: BacktestReport) -> tuple[float, int]:
    return report.sanrenpuku.roi, report.sanrenpuku.races


def _filter_records_by_date(
    records: List[_RaceRecord], from_yyyymmdd: str, to_yyyymmdd: str
) -> List[_RaceRecord]:
    return [r for r in records if from_yyyymmdd <= r.date <= to_yyyymmdd]


def _strategy_with_exotic(
    strategy: BetStrategyConfig,
    firm: ConfidenceThresholds,
    upset: ConfidenceThresholds,
) -> BetStrategyConfig:
    s = copy.copy(strategy)
    s.exotic_firm = firm
    s.exotic_upset = upset
    return s


def tune_exotic_thresholds(
    q1_from: str,
    q1_to: str,
    validate_from: str,
    validate_to: str,
    master: Optional[pd.DataFrame] = None,
    *,
    firm_win_probs: Optional[List[float]] = None,
    firm_gaps: Optional[List[float]] = None,
    upset_win_probs: Optional[List[float]] = None,
    upset_gaps: Optional[List[float]] = None,
    min_q1_sanren_races: int = 25,
    validate_roi_slack: float = 0.03,
    strategy: BetStrategyConfig = DEFAULT_STRATEGY,
) -> List[ExoticTuneResult]:
    """Grid-search exotic_firm / exotic_upset thresholds (split scoring records)."""
    master = master if master is not None else load_master()
    span_from = min(q1_from, validate_from)
    span_to = max(q1_to, validate_to)

    hist = master[
        (master["date"].astype(str) >= span_from)
        & (master["date"].astype(str) <= span_to)
    ]
    race_ids = sorted(hist["race_id"].astype(str).unique().tolist())
    paybacks = _load_paybacks_for_races(race_ids, fetch_missing=False)
    win_cfg, ex_cfg = load_split_scoring_configs()
    all_records = _collect_race_records(
        span_from, span_to, master, paybacks, win_cfg, ex_cfg, strategy
    )
    q1_records = _filter_records_by_date(all_records, q1_from, q1_to)
    val_records = _filter_records_by_date(all_records, validate_from, validate_to)

    baseline_val = _aggregate_records(
        val_records,
        validate_from,
        validate_to,
        DEFAULT_WIN_THRESHOLDS,
        strategy,
    )
    baseline_val_roi, _ = _sanren_roi_and_races(baseline_val)
    min_validate_roi = baseline_val_roi - validate_roi_slack

    fw = firm_win_probs if firm_win_probs is not None else [0.85, 0.88, 0.90]
    fg = firm_gaps if firm_gaps is not None else [0.70, 0.75, 0.80, 0.85]
    uw = upset_win_probs if upset_win_probs is not None else [0.78, 0.80, 0.82]
    ug = upset_gaps if upset_gaps is not None else [0.50, 0.55, 0.60]

    results: List[ExoticTuneResult] = []
    for f_wp in fw:
        for f_gap in fg:
            firm_th = ConfidenceThresholds(
                win_prob=f_wp,
                win_prob_alt=DEFAULT_EXOTIC_FIRM_THRESHOLDS.win_prob_alt,
                prob_gap=f_gap,
                mode=DEFAULT_EXOTIC_FIRM_THRESHOLDS.mode,
            )
            for u_wp in uw:
                for u_gap in ug:
                    upset_th = ConfidenceThresholds(
                        win_prob=u_wp,
                        win_prob_alt=DEFAULT_EXOTIC_UPSET_THRESHOLDS.win_prob_alt,
                        prob_gap=u_gap,
                        mode=DEFAULT_EXOTIC_UPSET_THRESHOLDS.mode,
                    )
                    trial = _strategy_with_exotic(strategy, firm_th, upset_th)
                    q1_report = _aggregate_records(
                        q1_records, q1_from, q1_to, DEFAULT_WIN_THRESHOLDS, trial
                    )
                    q1_roi, q1_races = _sanren_roi_and_races(q1_report)
                    if q1_races < min_q1_sanren_races:
                        continue
                    val_report = _aggregate_records(
                        val_records,
                        validate_from,
                        validate_to,
                        DEFAULT_WIN_THRESHOLDS,
                        trial,
                    )
                    val_roi, _ = _sanren_roi_and_races(val_report)
                    if val_roi < min_validate_roi:
                        continue
                    results.append(
                        ExoticTuneResult(
                            firm=firm_th,
                            upset=upset_th,
                            q1_sanren_roi=q1_roi,
                            q1_sanren_races=q1_races,
                            validate_sanren_roi=val_roi,
                        )
                    )

    results.sort(
        key=lambda r: (r.q1_sanren_roi, r.validate_sanren_roi),
        reverse=True,
    )
    return results
'''

bt_path = ROOT / "src" / "predictor" / "backtest.py"
bt = bt_path.read_text(encoding="utf-8")
if "import copy" not in bt:
    bt = bt.replace(
        "from dataclasses import dataclass, field",
        "import copy\nfrom dataclasses import dataclass, field",
    )
if "DEFAULT_EXOTIC_FIRM_THRESHOLDS" not in bt:
    bt = bt.replace(
        "    DEFAULT_STRATEGY,\n    DEFAULT_WIN_THRESHOLDS,",
        "    DEFAULT_STRATEGY,\n    DEFAULT_EXOTIC_FIRM_THRESHOLDS,\n    DEFAULT_EXOTIC_UPSET_THRESHOLDS,\n    DEFAULT_WIN_THRESHOLDS,",
    )
if "class ExoticTuneResult" not in bt:
    bt = bt.rstrip() + EXOTIC_APPEND + "\n"
    bt_path.write_text(bt, encoding="utf-8")
    ast.parse(bt, filename=str(bt_path))
    print("OK backtest.py patched")
else:
    print("backtest already patched")

tune = '''"""Grid-search exotic firm/upset confidence thresholds."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import ExoticTuneResult, tune_exotic_thresholds
from src.predictor.bets import (
    DEFAULT_EXOTIC_FIRM_THRESHOLDS,
    DEFAULT_EXOTIC_UPSET_THRESHOLDS,
    DEFAULT_STRATEGY,
    BetStrategyConfig,
    ConfidenceThresholds,
)
from src.predictor.score import load_master

CONFIG_PATH = ROOT / "config" / "exotic_thresholds.json"

FIRM_WIN_PROBS = [0.85, 0.88, 0.90]
FIRM_GAPS = [0.70, 0.75, 0.80, 0.85]
UPSET_WIN_PROBS = [0.78, 0.80, 0.82]
UPSET_GAPS = [0.50, 0.55, 0.60]


def _print_results(results: list[ExoticTuneResult], top_n: int = 10) -> None:
    print(f"\\n=== top {top_n} (Q1 sanrenpuku ROI) ===")
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
        "\\nRecommended:"
        f" firm win_prob={rec.firm.win_prob} gap={rec.firm.prob_gap};"
        f" upset win_prob={rec.upset.win_prob} gap={rec.upset.prob_gap}"
    )
    print(
        f"  Q1 sanrenpuku ROI {rec.q1_sanren_roi:.1%} ({rec.q1_sanren_races} races),"
        f" validate {rec.validate_sanren_roi:.1%}"
    )
    print(
        "\\nUpdate DEFAULT_EXOTIC_FIRM_THRESHOLDS / DEFAULT_EXOTIC_UPSET_THRESHOLDS in bets.py"
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
            json.dumps(payload, ensure_ascii=False, indent=2) + "\\n",
            encoding="utf-8",
        )
        print(f"Wrote {CONFIG_PATH}")


if __name__ == "__main__":
    main()
'''

(ROOT / "scripts/tune_exotic_thresholds.py").write_text(tune, encoding="utf-8")
ast.parse(tune, filename=str(ROOT / "scripts/tune_exotic_thresholds.py"))
print("OK scripts/tune_exotic_thresholds.py")
