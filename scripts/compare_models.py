"""現行 / 脚質のみ / 脚質+園田ドメイン の3モデル比較。"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.scoring_config import ScoringConfig
from src.predictor.score import load_master, set_scoring_config
from src.predictor.training_window import describe_training_ranges
from src.predictor.tune_weights import (
    evaluate_config_on_caches,
    feature_names_for,
    prepare_enriched_races_for_reference,
    tune_and_refine_for_reference,
)

VAL_FROM = "20260501"
VAL_TO = "20260531"


def _backtest_summary(master, config: ScoringConfig) -> dict:
    set_scoring_config(config)
    report = backtest_period(VAL_FROM, VAL_TO, master=master, config=config)
    w = report.win_pick
    return {
        "win_rate": w.hit_rate,
        "win_roi": w.roi,
        "place_roi": report.place_pick.roi,
        "sanrenpuku_roi": report.sanrenpuku.roi,
        "sanrentan_roi": report.sanrentan.roi,
        "wide_roi": report.wide.roi,
        "win_hits": f"{w.hits}/{w.races}",
    }


def _train_eval(master, config: ScoringConfig, reference: str, n_iter: int) -> tuple:
    print(f"  重み探索 ({n_iter}試行)...", flush=True)
    tuned, caches, _ = tune_and_refine_for_reference(
        reference, n_iter=n_iter, master=master, base_config=config
    )
    names = feature_names_for(tuned.config)
    train = evaluate_config_on_caches(caches, tuned.config, feature_names=names)
    return tuned.config, train


def main() -> None:
    parser = argparse.ArgumentParser(description="3モデル比較")
    parser.add_argument("--n-iter", type=int, default=200)
    parser.add_argument("--skip-tune", action="store_true", help="現行重みのみ比較")
    parser.add_argument("--reference-date", default="20260430")
    args = parser.parse_args()

    master = load_master()
    reference = args.reference_date or date.today().strftime("%Y%m%d")

    variants = [
        ("現行（脚質・ドメインなし）", ScoringConfig.current_baseline()),
        ("脚質のみ", ScoringConfig.with_style()),
        ("脚質+園田ドメイン", ScoringConfig.with_style_and_domain()),
    ]

    print("=== 3モデル比較 ===")
    print(f"学習: {describe_training_ranges(reference)}")
    print(f"検証: {VAL_FROM}〜{VAL_TO}\n")

    results = []
    saved_paths = {
        "現行（脚質・ドメインなし）": ROOT / "config" / "tuned_weights_baseline.json",
        "脚質のみ": ROOT / "config" / "tuned_weights_style.json",
        "脚質+園田ドメイン": ROOT / "config" / "tuned_weights_domain.json",
    }
    for label, cfg in variants:
        print(f"--- {label} ---")
        if args.skip_tune and label != variants[0][0]:
            tuned_cfg = cfg
            train_stats = None
        elif args.skip_tune:
            tuned_cfg = cfg
            train_stats = None
        else:
            tuned_cfg, train_res = _train_eval(master, cfg, reference, args.n_iter)
            train_stats = train_res
            save_path = saved_paths.get(label)
            if save_path:
                tuned_cfg.save(save_path)

        val = _backtest_summary(master, tuned_cfg)
        results.append((label, tuned_cfg, train_stats, val))

        if train_stats:
            print(
                f"  学習: 1着 {train_stats.win_hit_rate:.1%} / "
                f"3着内 {train_stats.top3_hit_rate:.1%} ({train_stats.races}R)"
            )
        print(
            f"  5月検証: 単勝 {val['win_hits']} ({val['win_rate']:.1%}) "
            f"回収率 {val['win_roi']:.1%}"
        )
        print(
            f"    三連複 {val['sanrenpuku_roi']:.1%} / "
            f"三連単 {val['sanrentan_roi']:.1%} / ワイド {val['wide_roi']:.1%}"
        )
        print()

    best = max(results, key=lambda x: x[3]["win_rate"])
    best_cfg = best[1]
    best_cfg.save(ROOT / "config" / "tuned_weights.json")
    set_scoring_config(best_cfg)
    print("=== サマリー（2026年5月） ===")
    print(f"{'モデル':<22} {'単勝的中':>10} {'回収率':>8} {'三連複':>8} {'三連単':>8} {'ワイド':>8}")
    for label, _, _, val in results:
        mark = " *" if label == best[0] else ""
        print(
            f"{label:<22} {val['win_hits']:>10} {val['win_roi']:>7.1%} "
            f"{val['sanrenpuku_roi']:>7.1%} {val['sanrentan_roi']:>7.1%} "
            f"{val['wide_roi']:>7.1%}{mark}"
        )
    print(f"\n推奨: {best[0]}")


if __name__ == "__main__":
    main()
