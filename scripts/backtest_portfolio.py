"""Portfolio backtest: firm win+wide+5pt / upset sanren BOX only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.portfolio_backtest import backtest_portfolio_period
from src.scraper.client import NetkeibaBlockedError


def _print_bet(r) -> None:
    print(
        f"  {r.name}: "
        f"対象{r.races}R / 的中{r.hits} ({r.hit_rate:.1%}) / "
        f"投資{r.investment:,}円 → 払戻{r.return_yen:,}円 / "
        f"回収率 {r.roi:.1%}"
    )
    if r.points > r.races and r.races:
        print(f"    （合計{r.points}点）")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio backtest (firm/upset split)")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    parser.add_argument(
        "--fetch-payback",
        action="store_true",
        help="Fetch missing paybacks from netkeiba",
    )
    args = parser.parse_args()

    print(f"=== Portfolio backtest: {args.from_date} - {args.to_date} ===")
    print("堅: 単勝◎ + ワイド◎-○▲ + 三連複5点 (三連系自信度「高」)")
    print("荒: 三連複BOXのみ (三連系自信度「高」)")
    if args.fetch_payback:
        print("払戻: 未取得分を netkeiba から取得")
    else:
        print("払戻: キャッシュのみ")

    try:
        report = backtest_portfolio_period(
            args.from_date,
            args.to_date,
            fetch_payback=args.fetch_payback,
        )
    except NetkeibaBlockedError as exc:
        print(f"STOP: HTTP 400 — {exc}")
        sys.exit(1)

    print(f"\n対象: {report.race_count}レース")
    print(f"  堅・三連系高: {report.firm_exotic_races}R")
    print(f"  荒・三連系高: {report.upset_exotic_races}R")
    print("\n--- 券種別 ---")
    _print_bet(report.win)
    _print_bet(report.wide)
    _print_bet(report.sanrenpuku_firm)
    _print_bet(report.sanrenpuku_box)
    print("\n--- 合算 ---")
    print(
        f"  投資 {report.total_investment:,}円 → 払戻 {report.total_return:,}円 / "
        f"回収率 {report.total_roi:.1%}"
    )
    print(
        f"  レース的中（いずれか1券種）: "
        f"{report.any_hit_races}/{report.race_count} ({report.total_hit_rate:.1%})"
    )


if __name__ == "__main__":
    main()
