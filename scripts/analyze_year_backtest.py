"""年間・月別バックテスト集計（問題点の把握用）。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.predictor.backtest import backtest_period
from src.predictor.bets import DEFAULT_THRESHOLDS


def _month_ranges(year: int):
    for m in range(1, 13):
        prefix = f"{year}{m:02d}"
        yield prefix, f"{prefix}01", f"{prefix}31"


def _summarize(report):
    high = [r for r in report.rows if r.confidence == "高"]
    w = report.win_pick
    p = report.place_pick
    sp = report.sanrenpuku
    st = report.sanrentan
    wd = report.wide
    return {
        "races": report.race_count,
        "high": len(high),
        "win_rate": w.hit_rate,
        "win_roi": w.roi,
        "place_roi": p.roi,
        "sp_rate": sp.hit_rate if sp.races else 0.0,
        "sp_roi": sp.roi if sp.races else 0.0,
        "st_rate": st.hit_rate if st.races else 0.0,
        "st_roi": st.roi if st.races else 0.0,
        "wd_rate": wd.hit_rate if wd.races else 0.0,
        "wd_roi": wd.roi if wd.races else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="年間バックテスト月別集計")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--fetch-payback", action="store_true")
    args = parser.parse_args()

    year = args.year
    print(f"=== {year} 年間バックテスト ===")
    print(f"自信度「高」: {DEFAULT_THRESHOLDS.label()}")
    if args.fetch_payback:
        print("払戻: 未取得分を取得")
    else:
        print("払戻: キャッシュのみ（単勝はオッズフォールバック可）")
    print()

    header = (
        f"{'月':>4} {'R':>4} {'高':>4} "
        f"{'単勝%':>6} {'単ROI':>7} "
        f"{'三複%':>6} {'三複ROI':>8} "
        f"{'三単%':>6} {'三単ROI':>8} "
        f"{'W%':>6} {'WROI':>7}"
    )
    print(header)
    print("-" * len(header))

    totals = []
    for label, fd, td in _month_ranges(year):
        report = backtest_period(
            fd, td, fetch_payback=args.fetch_payback, thresholds=DEFAULT_THRESHOLDS
        )
        if report.race_count == 0:
            continue
        s = _summarize(report)
        totals.append(s)
        print(
            f"{label[4:]:>4} {s['races']:>4} {s['high']:>4} "
            f"{s['win_rate']:>5.1%} {s['win_roi']:>6.1%} "
            f"{s['sp_rate']:>5.1%} {s['sp_roi']:>7.1%} "
            f"{s['st_rate']:>5.1%} {s['st_roi']:>7.1%} "
            f"{s['wd_rate']:>5.1%} {s['wd_roi']:>6.1%}"
        )

    if not totals:
        print("対象レースなし")
        return

    n = sum(t["races"] for t in totals)
    h = sum(t["high"] for t in totals)

    def _weighted(key_num, key_den=None):
        if key_den:
            num = sum(t[key_num] * t[key_den] for t in totals)
            den = sum(t[key_den] for t in totals)
            return num / den if den else 0.0
        num = sum(t[key_num] * t["races"] for t in totals)
        return num / n if n else 0.0

    print("-" * len(header))
    print(
        f"{'計':>4} {n:>4} {h:>4} "
        f"{_weighted('win_rate'):>5.1%} "
        f"{sum(t['win_roi']*t['races'] for t in totals)/n:>6.1%} "
        f"{_weighted('sp_rate', 'high'):>5.1%} "
        f"{sum(t['sp_roi']*t['high'] for t in totals)/h if h else 0:>7.1%} "
        f"{_weighted('st_rate', 'high'):>5.1%} "
        f"{sum(t['st_roi']*t['high'] for t in totals)/h if h else 0:>7.1%} "
        f"{_weighted('wd_rate', 'high'):>5.1%} "
        f"{sum(t['wd_roi']*t['high'] for t in totals)/h if h else 0:>6.1%}"
    )


if __name__ == "__main__":
    main()
