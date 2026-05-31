"""ウォークフォワード: 2025まで学習 -> 2026で検証。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.scoring_config import ScoringConfig
from src.predictor.score import load_master, set_scoring_config
from src.predictor.training_window import describe_training_ranges
from src.predictor.tune_weights import tune_and_refine_for_reference


def _print_report(label: str, rep) -> None:
    print(f"\n--- {label} ---")
    print(f"  単勝: {rep.win_pick.hit_rate:.1%} / 回収 {rep.win_pick.roi:.1%} ({rep.win_pick.races}R)")
    print(f"  三連複: {rep.sanrenpuku.hit_rate:.1%} / 回収 {rep.sanrenpuku.roi:.1%} ({rep.sanrenpuku.races}R)")
    print(f"  三連単: {rep.sanrentan.hit_rate:.1%} / 回収 {rep.sanrentan.roi:.1%} ({rep.sanrentan.races}R)")
    print(f"  ワイド: {rep.wide.hit_rate:.1%} / 回収 {rep.wide.roi:.1%} ({rep.wide.races}R)")


def main() -> None:
    parser = argparse.ArgumentParser(description="2025学習->2026検証")
    parser.add_argument("--reference", default="20260101")
    parser.add_argument("--n-iter", type=int, default=250)
    parser.add_argument("--val-from", default="20260101")
    parser.add_argument("--val-to", default="20260531")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    master = load_master()
    base = ScoringConfig.with_style()

    print("=== ウォークフォワード ===")
    print(f"学習: {describe_training_ranges(args.reference)}")
    print(f"検証: {args.val_from} - {args.val_to}\n")

    old = ScoringConfig.load_tuned()
    _print_report("変更前(検証)", backtest_period(args.val_from, args.val_to, master=master, config=old))

    print(f"\n探索 {args.n_iter}試行...", flush=True)
    refined, _, _ = tune_and_refine_for_reference(
        args.reference, n_iter=args.n_iter, master=master, base_config=base,
    )
    tuned = refined.config
    set_scoring_config(tuned)
    print(f"完了: 1着 {refined.win_hit_rate:.1%} / 3着内 {refined.top3_hit_rate:.1%}")

    if args.save:
        tuned.save()
        print("保存: config/tuned_weights.json")

    _print_report("変更後(検証)", backtest_period(args.val_from, args.val_to, master=master, config=tuned))
    _print_report("2025年", backtest_period("20250101", "20251231", master=master, config=tuned))


if __name__ == "__main__":
    main()
