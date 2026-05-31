"""レース予想スクリプト（特徴量スコア方式）。"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.bets import build_day_bet_plans
from src.predictor.score import evaluate_master, load_master, predict_date, set_scoring_config
from src.predictor.tune_weights import tune_and_refine_for_reference
from src.scraper.client import NetkeibaBlockedError


def _print_predictions(df) -> None:
    if df.empty:
        print("予想対象がありません（園田開催なし、または出馬表未取得）。")
        return

    show_cols = [
        "mark",
        "rank_pred",
        "umaban",
        "horse_name",
        "score",
        "win_prob",
        "horse_win_rate",
        "jockey_trainer_win_rate",
        "last3_avg_finish",
        "odds",
        "popularity",
    ]
    plans = {p.race_no: p for p in build_day_bet_plans(df)}

    for race_no, group in df.groupby("race_no", sort=True):
        race_name = group["race_name"].iloc[0] if "race_name" in group.columns else ""
        distance = group["distance"].iloc[0] if "distance" in group.columns else ""
        plan = plans.get(int(race_no))
        print(f"\n--- {int(race_no)}R {race_name} {distance} ---")

        if plan:
            mark_line = "  ".join(
                f"{m}{u} {n}" for m, u, n in plan.marks
            )
            print(f"印: {mark_line}")

        view = group.sort_values("rank_pred").head(5).copy()
        if plan:
            mark_map = {u: m for m, u, _ in plan.marks}
            view["mark"] = view["umaban"].astype(str).map(mark_map).fillna("")
        cols = [c for c in show_cols if c in view.columns]
        print(view[cols].to_string(index=False))

        if plan and (plan.confidence == "高" or "見送り" in plan.confidence or plan.exotic_confidence == "高"):
            print(
                f"【{plan.confidence}】 [単勝:{plan.win_profile} / 三連:{plan.exotic_profile}] "
                f"1番人気{plan.fav_odds:.1f}倍 "
                f"1位勝率 {plan.win_prob_top:.1%} (1-2位差 {plan.prob_gap:.1%})"
            )
            if plan.exotic_confidence == "高":
                if plan.sanrenpuku:
                    print(f"  {plan.sanrenpuku.label}")
                if plan.sanrenpuku_box:
                    print(f"  {plan.sanrenpuku_box.label}")
                if plan.sanrentan:
                    print(f"  {plan.sanrentan.label}")
                if plan.wide:
                    print(f"  {plan.wide.label}")
            else:
                print("  （三連系: 自信度不足のため見送り）")


def main() -> None:
    parser = argparse.ArgumentParser(description="園田競馬のレース予想（特徴量スコア）")
    parser.add_argument("--date", help="予想日 YYYYMMDD（省略時は今日）")
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="マスタ上の過去レースで的中率を表示",
    )
    parser.add_argument(
        "--retune",
        action="store_true",
        help="予想前にローリング学習期間で重みを再探索して保存",
    )
    parser.add_argument("--retune-iter", type=int, default=250, help="--retune 時の探索回数")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="ネット取得せずマスタ上の当該日データで検証",
    )
    args = parser.parse_args()

    target = args.date or date.today().strftime("%Y%m%d")
    master = load_master()

    if args.retune:
        print(f"=== 重み再探索（基準日 {target}） ===")
        refined, _, _ = tune_and_refine_for_reference(
            target, n_iter=args.retune_iter, master=master
        )
        refined.config.save()
        set_scoring_config(refined.config)
        print(
            f"保存完了: 1着 {refined.win_hit_rate:.1%} / "
            f"3着内 {refined.top3_hit_rate:.1%} ({refined.races}R)\n"
        )

    if args.evaluate:
        stats = evaluate_master(master)
        print("=== モデル評価（2024年以降） ===")
        print(f"対象レース: {stats['races']:,}")
        print(f"1着的中率: {stats['win_hit_rate']:.1%}")
        print(f"3着以内に1着: {stats['top3_hit_rate']:.1%}")
        print()

    print(f"=== 予想: {target} 園田 ===")
    try:
        pred = predict_date(
            target,
            master=master,
            fetch_entries=not args.offline,
        )
    except NetkeibaBlockedError as exc:
        print(f"STOP: HTTP 400 — 通信制限の可能性 ({exc})")
        sys.exit(1)

    _print_predictions(pred)


if __name__ == "__main__":
    main()
