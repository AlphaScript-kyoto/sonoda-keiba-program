"""学習期間比較: 2024のみ / 全期間 / 全期間+直近重み。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.scoring_config import ScoringConfig
from src.predictor.score import load_master
from src.predictor.training_window import describe_training_ranges
from src.predictor.tune_weights import (
    _prepare_enriched_races,
    build_race_caches,
    evaluate_config_on_caches,
    prepare_enriched_races_for_reference,
    tune_and_refine,
    tune_and_refine_for_reference,
)

TRAIN_FROM = "20150225"
TRAIN_TO = "20260430"
REF_DATE = TRAIN_TO
VAL_FROM = "20260501"
VAL_TO = "20260531"


def _may_backtest(master, config: ScoringConfig) -> dict:
    report = backtest_period(VAL_FROM, VAL_TO, master=master, config=config)
    w = report.win_pick
    return {
        "win_hits": w.hits,
        "win_races": w.races,
        "win_rate": w.hit_rate,
        "win_roi": w.roi,
        "place_roi": report.place_pick.roi,
    }


def _train_eval_unweighted(caches, config: ScoringConfig) -> dict:
    res = evaluate_config_on_caches(caches, config, weighted=False)
    return {
        "win_rate": res.win_hit_rate,
        "top3_rate": res.top3_hit_rate,
        "races": res.races,
    }


def _print_weights(label: str, config: ScoringConfig) -> None:
    active = {k: v for k, v in config.feature_weights.items() if v > 0}
    print(f"  {label}: market={config.market_weight}", end="")
    if active:
        top = sorted(active.items(), key=lambda x: -x[1])[:5]
        print(" / " + ", ".join(f"{k}={v}" for k, v in top))
    else:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="学習期間比較")
    parser.add_argument("--n-iter", type=int, default=250)
    args = parser.parse_args()

    master = load_master()
    min_date = str(master["date"].min())
    train_from = max(TRAIN_FROM, min_date)

    print("=== 学習期間比較 ===")
    print(f"学習: {train_from} 〜 {TRAIN_TO}（2026年5月は検証のみ）")
    print(f"検証: {VAL_FROM} 〜 {VAL_TO}\n")

    baseline = ScoringConfig.load_tuned()

    scenarios = [
        ("ローリング3期間", None, None, False, REF_DATE),
        ("2024年のみ", "20240101", "20241231", False, None),
        ("全期間・均等", train_from, TRAIN_TO, False, None),
        ("全期間・直近重み", train_from, TRAIN_TO, True, REF_DATE),
    ]

    results = []

    for label, fd, td, recency, ref_window in scenarios:
        print(f"--- {label} ---")
        if ref_window:
            print(f"  学習: {describe_training_ranges(ref_window)}")
        elif fd and td:
            print(f"  学習: {fd} 〜 {td}")
        print(f"  重み探索中 ({args.n_iter}試行)...", flush=True)
        if ref_window:
            tuned_res, _, _ = tune_and_refine_for_reference(
                ref_window, n_iter=args.n_iter, master=master
            )
            tuned = tuned_res
            races_train = prepare_enriched_races_for_reference(master, ref_window)
        else:
            tuned = tune_and_refine(
                fd,
                td,
                n_iter=args.n_iter,
                master=master,
                use_recency=recency,
                ref_date=REF_DATE,
                half_life_days=730,
            )
            races_train = _prepare_enriched_races(master, fd, td)
        caches = build_race_caches(
            races_train,
            ref_date=REF_DATE,
            use_recency=recency,
        )
        train_stats = _train_eval_unweighted(caches, tuned.config)
        val_stats = _may_backtest(master, tuned.config)
        results.append((label, tuned, train_stats, val_stats))
        print(
            f"  学習期間(均等評価): 1着 {train_stats['win_rate']:.1%} / "
            f"3着内 {train_stats['top3_rate']:.1%} ({train_stats['races']}R)"
        )
        if recency:
            wtrain = evaluate_config_on_caches(caches, tuned.config, weighted=True)
            print(
                f"  学習期間(重み付き評価): 1着 {wtrain.win_hit_rate:.1%} / "
                f"3着内 {wtrain.top3_hit_rate:.1%}"
            )
        print(
            f"  2026年5月: 単勝 {val_stats['win_hits']}/{val_stats['win_races']} "
            f"({val_stats['win_rate']:.1%}) 回収率 {val_stats['win_roi']:.1%}"
        )
        _print_weights("  重み", tuned.config)
        print()

    print("=== 2026年5月 検証サマリー ===")
    print(f"{'学習期間':<18} {'単勝的中':>10} {'回収率':>8} {'複勝回収':>8}")
    val_base = _may_backtest(master, baseline)
    print(
        f"{'既存(2024 tune)':<18} "
        f"{val_base['win_hits']:>3}/{val_base['win_races']:<3} "
        f"{val_base['win_rate']:>7.1%} {val_base['win_roi']:>7.1%} "
        f"{val_base['place_roi']:>7.1%}"
    )
    best_val = max(results, key=lambda x: x[3]["win_rate"])
    for label, _, _, val in results:
        mark = " *" if label == best_val[0] else ""
        print(
            f"{label:<18} "
            f"{val['win_hits']:>3}/{val['win_races']:<3} "
            f"{val['win_rate']:>7.1%} {val['win_roi']:>7.1%} "
            f"{val['place_roi']:>7.1%}{mark}"
        )


if __name__ == "__main__":
    main()
