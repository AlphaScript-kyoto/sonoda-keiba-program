"""馬券戦略のバックテスト（回収率・的中率）。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period, tune_confidence_thresholds
from src.predictor.bets import ConfidenceThresholds, DEFAULT_THRESHOLDS
from src.scraper.client import NetkeibaBlockedError


def _build_thresholds(args) -> ConfidenceThresholds:
    if args.old_thresholds:
        return ConfidenceThresholds(
            win_prob=0.30,
            win_prob_alt=0.22,
            prob_gap=0.12,
            mode="or",
        )
    return ConfidenceThresholds(
        win_prob=args.min_win_prob,
        win_prob_alt=args.min_win_prob_alt,
        prob_gap=args.min_gap,
        mode=args.conf_mode,
    )


def _print_bet_result(r) -> None:
    print(
        f"  {r.name}: "
        f"対象{r.races}R / 的中{r.hits} ({r.hit_rate:.1%}) / "
        f"投資{r.investment:,}円 → 払戻{r.return_yen:,}円 / "
        f"回収率 {r.roi:.1%}"
    )
    if r.points > r.races and r.races:
        print(f"    （合計{r.points}点）")


def _print_detail(rows, limit: int) -> None:
    print("\n=== レース別（自信度「高」のみ） ===")
    shown = 0
    for row in rows:
        if row.confidence != "高":
            continue
        if limit and shown >= limit:
            break
        mark = "◎" if row.win_hit else ("△" if row.place_hit else "×")
        sp = "○" if row.sanrenpuku_hit else "×"
        st = "○" if row.sanrentan_hit else "×"
        wd = "○" if row.wide_hit else "×"
        print(
            f"  {row.date} {row.race_no:>2}R {mark} "
            f"予想{row.pred_umaban}→結果{row.actual_1st} "
            f"({row.pred_horse}) "
            f"[勝率{row.win_prob_top:.0%} 差{row.prob_gap:.0%}] "
            f"三連複{sp} 三連単{st} ワイド{wd}"
        )
        shown += 1


def _print_tune_results(results, top_n: int = 10) -> None:
    print(f"\n=== 閾値探索 上位{top_n}件（三連系合算回収率順） ===")
    print(f"{'#':>2}  {'高':>3}  {'三連複':>7}  {'三連単':>7}  {'合算':>7}  {'単勝(高)':>8}  条件")
    for i, r in enumerate(results[:top_n], start=1):
        th = r.thresholds
        cond = th.label()
        print(
            f"{i:>2}  {r.high_races:>3}R  "
            f"{r.sanrenpuku_roi:>6.1%}  {r.sanrentan_roi:>6.1%}  "
            f"{r.combined_roi:>6.1%}  {r.win_roi_high:>7.1%}  {cond}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="馬券バックテスト（回収率）")
    parser.add_argument("--from", dest="from_date", default="20260501")
    parser.add_argument("--to", dest="to_date", default="20260531")
    parser.add_argument(
        "--fetch-payback",
        action="store_true",
        help="払戻未取得分を結果ページから取得（7〜10秒/件、キャッシュ保存）",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="閾値グリッド探索（三連系回収率が高い組み合わせを表示）",
    )
    parser.add_argument(
        "--min-win-prob",
        type=float,
        default=DEFAULT_THRESHOLDS.win_prob,
        help=f"自信度「高」の勝率閾値（既定 {DEFAULT_THRESHOLDS.win_prob}）",
    )
    parser.add_argument(
        "--min-win-prob-alt",
        type=float,
        default=DEFAULT_THRESHOLDS.win_prob_alt,
        help=f"代替勝率閾値（既定 {DEFAULT_THRESHOLDS.win_prob_alt}）",
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=DEFAULT_THRESHOLDS.prob_gap,
        help=f"1-2位勝率差閾値（既定 {DEFAULT_THRESHOLDS.prob_gap}）",
    )
    parser.add_argument(
        "--conf-mode",
        choices=["or", "and", "strict"],
        default=DEFAULT_THRESHOLDS.mode,
        help="自信度判定モード（or/and/strict）",
    )
    parser.add_argument(
        "--old-thresholds",
        action="store_true",
        help="旧閾値（勝率30%%/差12%%）で比較",
    )
    parser.add_argument(
        "--detail",
        type=int,
        default=20,
        help="自信度「高」レースの詳細表示件数（0で非表示）",
    )
    args = parser.parse_args()
    thresholds = _build_thresholds(args)

    print(f"=== バックテスト: {args.from_date} 〜 {args.to_date} ===")

    if args.tune:
        print("モード: 閾値グリッド探索")
        results = tune_confidence_thresholds(args.from_date, args.to_date)
        _print_tune_results(results)
        if results:
            best = results[0].thresholds
            print(f"\n推奨: --min-win-prob {best.win_prob} --min-win-prob-alt {best.win_prob_alt} "
                  f"--min-gap {best.prob_gap} --conf-mode {best.mode}")
        return

    print(f"自信度「高」: {thresholds.label()}")
    print("予想: マスタの出走データで再現（過去レースは出馬表相当・特徴量リークなし）")
    if args.fetch_payback:
        print("払戻: 未取得分を netkeiba から取得（通信制限に注意）")
    else:
        print("払戻: キャッシュのみ")

    try:
        report = backtest_period(
            args.from_date,
            args.to_date,
            fetch_payback=args.fetch_payback,
            thresholds=thresholds,
        )
    except NetkeibaBlockedError as exc:
        print(f"STOP: HTTP 400 — 通信制限 ({exc})")
        sys.exit(1)

    print(f"\n対象: {report.race_count}レース")
    print("\n--- 回収率（全レース: 単勝・複勝 / 自信度「高」のみ: 三連系） ---")
    _print_bet_result(report.win_pick)
    _print_bet_result(report.place_pick)
    _print_bet_result(report.sanrenpuku)
    _print_bet_result(report.sanrentan)
    _print_bet_result(report.wide)

    high = [r for r in report.rows if r.confidence == "高"]
    win_hits_all = sum(1 for r in report.rows if r.win_hit)
    print(
        f"\n--- サマリー ---\n"
        f"  単勝◎（全{len(report.rows)}R）: {win_hits_all}的中 ({win_hits_all/len(report.rows):.1%})\n"
        f"  自信度「高」: {len(high)}レース"
    )
    if high:
        wh = sum(1 for r in high if r.win_hit)
        sp_h = sum(1 for r in high if r.sanrenpuku_hit)
        st_h = sum(1 for r in high if r.sanrentan_hit)
        wd_h = sum(1 for r in high if r.wide_hit)
        print(f"    単勝的中: {wh}/{len(high)} ({wh/len(high):.1%})")
        print(f"    三連複的中: {sp_h}/{len(high)}")
        print(f"    三連単的中: {st_h}/{len(high)}")
        print(f"    ワイド的中: {wd_h}/{len(high)}")

    if args.detail:
        _print_detail(report.rows, args.detail)


if __name__ == "__main__":
    main()
