"""正規化 + ローリング学習期間の重み探索 + Before/After 比較。"""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.scoring_config import ScoringConfig
from src.predictor.score import load_master, set_scoring_config
from src.predictor.training_window import describe_training_ranges, get_training_ranges
from src.predictor.tune_weights import (
    build_race_caches,
    evaluate_config_on_caches,
    evaluate_config_on_races,
    prepare_enriched_races_for_reference,
    tune_and_refine_for_reference,
)


def _fast_eval_on_caches(caches, config: ScoringConfig) -> dict:
    res = evaluate_config_on_caches(caches, config)
    return {
        "races": res.races,
        "win_hit_rate": res.win_hit_rate,
        "top3_hit_rate": res.top3_hit_rate,
    }


def _fast_eval_on_races(races, config: ScoringConfig) -> dict:
    res = evaluate_config_on_races(races, config)
    return {
        "races": res.races,
        "win_hit_rate": res.win_hit_rate,
        "top3_hit_rate": res.top3_hit_rate,
    }


def _print_eval(label: str, stats: dict) -> None:
    print(
        f"  {label}: 1着 {stats['win_hit_rate']:.1%} / "
        f"3着内 {stats['top3_hit_rate']:.1%} ({stats['races']}R)"
    )


def _print_backtest(label: str, report) -> None:
    w = report.win_pick
    print(
        f"  {label}: 単勝 {w.hits}/{w.races} ({w.hit_rate:.1%}) "
        f"回収率 {w.roi:.1%} / 複勝回収 {report.place_pick.roi:.1%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="重みチューニング & Before/After")
    parser.add_argument("--n-iter", type=int, default=400, help="ランダム探索回数")
    parser.add_argument("--skip-tune", action="store_true", help="探索せず保存済み重みのみ")
    parser.add_argument(
        "--reference-date",
        help="学習ウィンドウの基準日 YYYYMMDD（省略時は今日）",
    )
    parser.add_argument("--may-from", default="20260501")
    parser.add_argument("--may-to", default="20260531")
    parser.add_argument(
        "--objective",
        choices=("win", "top3", "sanrenpuku"),
        default="win",
        help="探索目的（sanrenpuku=3着内率優先+三連複ROI再選定）",
    )
    args = parser.parse_args()

    reference = args.reference_date or date.today().strftime("%Y%m%d")
    master = load_master()
    window_desc = describe_training_ranges(reference)

    print("=== Before / After 比較 ===\n", flush=True)
    print(f"学習ウィンドウ（基準日 {reference}）")
    print(f"  {window_desc}\n")

    legacy = ScoringConfig.legacy()
    raw = ScoringConfig.raw_all_features()

    train_races = prepare_enriched_races_for_reference(master, reference)
    train_caches = build_race_caches(train_races)

    print("[1] 学習期間 評価")
    _print_eval("Legacy 8特徴量・非正規化", _fast_eval_on_races(train_races, legacy))
    _print_eval("全特徴量・非正規化（Phase A+B直後）", _fast_eval_on_races(train_races, raw))

    if args.skip_tune:
        tuned = ScoringConfig.load_tuned()
        print("\n[2] 保存済み tuned_weights.json を使用")
        tuned_caches = train_caches
    else:
        print(f"\n[2] ローリング学習期間 重み探索（正規化 z-score / {args.n_iter}試行 / {args.objective}）...")
        refined, tuned_caches, _ = tune_and_refine_for_reference(
            reference,
            n_iter=args.n_iter,
            master=master,
            objective=args.objective,
            val_from=args.may_from if args.objective == "sanrenpuku" else None,
            val_to=args.may_to if args.objective == "sanrenpuku" else None,
        )
        tuned = refined.config
        save_name = (
            "config/tuned_weights_sanrenpuku.json"
            if args.objective == "sanrenpuku"
            else "config/tuned_weights.json"
        )
        tuned.save(ROOT / save_name)
        print(
            f"  探索後: 1着 {refined.win_hit_rate:.1%} / "
            f"3着内 {refined.top3_hit_rate:.1%} ({refined.races}R)"
        )
        print(f"  保存: {save_name}")

    set_scoring_config(tuned)
    _print_eval("正規化 + チューニング後", _fast_eval_on_caches(tuned_caches, tuned))

    print(f"\n[3] {args.may_from}〜{args.may_to} バックテスト")
    _print_backtest("Legacy", backtest_period(
        args.may_from, args.may_to, master=master, config=legacy
    ))
    _print_backtest("全特徴量・非正規化", backtest_period(
        args.may_from, args.may_to, master=master, config=raw
    ))
    set_scoring_config(tuned)
    _print_backtest("正規化 + チューニング", backtest_period(
        args.may_from, args.may_to, master=master, config=tuned
    ))
    if args.objective == "sanrenpuku":
        set_scoring_config(tuned)
        sp = backtest_period(args.may_from, args.may_to, master=master, config=tuned)
        print(f"  三連複回収率: {sp.sanrenpuku.roi:.1%} ({sp.sanrenpuku.hits}/{sp.sanrenpuku.races})")

    print("\n[4] 採用重み（正規化 + チューニング）")
    print(f"  market_weight: {tuned.market_weight}")
    active = {k: v for k, v in tuned.feature_weights.items() if v > 0}
    for k, v in sorted(active.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
